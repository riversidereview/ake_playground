param(
    [int]$WatchSeconds = 15,
    [string]$PcapPort = "30000"
)

$ErrorActionPreference = "Continue"

function Add-ReportLine {
    param([string]$Text = "")
    $script:ReportLines += $Text
    Write-Host $Text
}

function Add-Section {
    param([string]$Title)
    Add-ReportLine ""
    Add-ReportLine "==== $Title ===="
}

function Format-Value {
    param($Value)
    if ($null -eq $Value) {
        return "-"
    }
    return [string]$Value
}

function Get-ProcessRows {
    $rows = @()
    try {
        $processes = Get-CimInstance Win32_Process |
            Where-Object { $_.Name -match '^(Endfield|EndfieldPCAP)\.exe$' }
        foreach ($process in $processes) {
            $started = "-"
            try {
                if ($process.CreationDate) {
                    $started = [Management.ManagementDateTimeConverter]::ToDateTime($process.CreationDate).ToString("yyyy-MM-dd HH:mm:ss")
                }
            } catch {
                $started = "-"
            }
            $rows += [pscustomobject]@{
                Name        = $process.Name
                Pid         = $process.ProcessId
                Started     = $started
                Path        = $process.ExecutablePath
                CommandLine = $process.CommandLine
            }
        }
    } catch {
        $rows += Get-Process |
            Where-Object { $_.ProcessName -like '*Endfield*' } |
            ForEach-Object {
                [pscustomobject]@{
                    Name        = "$($_.ProcessName).exe"
                    Pid         = $_.Id
                    Started     = if ($_.StartTime) { $_.StartTime.ToString("yyyy-MM-dd HH:mm:ss") } else { "-" }
                    Path        = $_.Path
                    CommandLine = "-"
                }
            }
    }
    return @($rows | Sort-Object Name, Pid)
}

function Get-StatusSnapshot {
    param([string]$StatusPath)
    if (-not (Test-Path -LiteralPath $StatusPath)) {
        return [pscustomobject]@{
            Exists      = $false
            Path        = $StatusPath
            Raw         = $null
            Json        = $null
            Error       = $null
            Length      = 0
            LastWrite   = $null
        }
    }

    $item = Get-Item -LiteralPath $StatusPath
    try {
        $raw = Get-Content -LiteralPath $StatusPath -Raw -Encoding UTF8
        $json = $raw | ConvertFrom-Json
        return [pscustomobject]@{
            Exists      = $true
            Path        = $StatusPath
            Raw         = $raw
            Json        = $json
            Error       = $null
            Length      = $item.Length
            LastWrite   = $item.LastWriteTime
        }
    } catch {
        return [pscustomobject]@{
            Exists      = $true
            Path        = $StatusPath
            Raw         = $null
            Json        = $null
            Error       = $_.Exception.Message
            Length      = $item.Length
            LastWrite   = $item.LastWriteTime
        }
    }
}

function Add-StatusSummary {
    param(
        [string]$Label,
        $Snapshot
    )

    Add-ReportLine "$Label status_path=$($Snapshot.Path)"
    if (-not $Snapshot.Exists) {
        Add-ReportLine "$Label exists=False"
        return
    }
    Add-ReportLine "$Label exists=True size=$($Snapshot.Length) last_write=$($Snapshot.LastWrite)"
    if ($Snapshot.Error) {
        Add-ReportLine "$Label json_error=$($Snapshot.Error)"
        return
    }
    $json = $Snapshot.Json
    if ($null -eq $json) {
        Add-ReportLine "$Label json=-"
        return
    }

    Add-ReportLine "$Label state=$(Format-Value $json.state) session_id=$(Format-Value $json.session_id)"
    if ($json.active_flow) {
        Add-ReportLine "$Label active_flow client=$(Format-Value $json.active_flow.client) server=$(Format-Value $json.active_flow.server)"
    } else {
        Add-ReportLine "$Label active_flow=None"
    }

    if ($json.metrics) {
        Add-ReportLine "$Label metrics packets_seen=$(Format-Value $json.metrics.packets_seen) frames_decoded=$(Format-Value $json.metrics.frames_decoded) messages_decoded=$(Format-Value $json.metrics.messages_decoded) events=$(Format-Value $json.metrics.outbound_events_emitted) queue_drop=$(Format-Value $json.metrics.packets_dropped_queue)"
    }
    if ($json.pcap_stats) {
        Add-ReportLine "$Label pcap ps_recv=$(Format-Value $json.pcap_stats.ps_recv) ps_drop=$(Format-Value $json.pcap_stats.ps_drop) ps_ifdrop=$(Format-Value $json.pcap_stats.ps_ifdrop)"
    }
    if ($json.session) {
        Add-ReportLine "$Label session login_client=$(Format-Value $json.session.client_login_done) login_server=$(Format-Value $json.session.server_login_done) cipher_client=$(Format-Value $json.session.client_cipher_ready) cipher_server=$(Format-Value $json.session.server_cipher_ready)"
        Add-ReportLine "$Label session reliability=$(Format-Value ($json.session.reliability_flags -join ',')) startup_tcp_gap_count=$(Format-Value $json.session.startup_tcp_gap_count)"
        if ($json.session.decoded_class_counts) {
            $classes = $json.session.decoded_class_counts.PSObject.Properties |
                Sort-Object { [int]$_.Value } -Descending |
                Select-Object -First 8 |
                ForEach-Object { "$($_.Name)=$($_.Value)" }
            Add-ReportLine "$Label decoded_top=$($classes -join '; ')"
        }
    }
    if ($json.capture_devices) {
        $index = 0
        foreach ($device in @($json.capture_devices)) {
            $index += 1
            Add-ReportLine "$Label capture_device[$index] desc=$(Format-Value $device.description) ipv4=$((@($device.ipv4_addrs) -join ',')) name=$(Format-Value $device.name)"
        }
    }
}

function Get-NumberOrZero {
    param($Value)
    if ($null -eq $Value) {
        return 0
    }
    try {
        return [int64]$Value
    } catch {
        return 0
    }
}

function Get-DiagCommand {
    $localExeCandidates = @(
        (Join-Path $PSScriptRoot "EndfieldPCAP.exe"),
        (Join-Path (Get-Location) "EndfieldPCAP.exe")
    )
    foreach ($candidate in $localExeCandidates) {
        if (Test-Path -LiteralPath $candidate) {
            $resolved = (Resolve-Path -LiteralPath $candidate).Path
            return [pscustomobject]@{
                Display = "$resolved diag"
                File    = $resolved
                Args    = @("diag")
            }
        }
    }

    $venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    $srcModule = Join-Path $PSScriptRoot "src\endfield_pcap"
    if ((Test-Path -LiteralPath $venvPython) -and (Test-Path -LiteralPath $srcModule)) {
        $resolved = (Resolve-Path -LiteralPath $venvPython).Path
        return [pscustomobject]@{
            Display = "$resolved -m endfield_pcap diag"
            File    = $resolved
            Args    = @("-m", "endfield_pcap", "diag")
        }
    }

    $distExeCandidates = @(
        (Join-Path $PSScriptRoot "dist_officialtimer\EndfieldPCAP\EndfieldPCAP.exe"),
        (Join-Path $PSScriptRoot "dist\EndfieldPCAP\EndfieldPCAP.exe")
    )
    foreach ($candidate in $distExeCandidates) {
        if (-not (Test-Path -LiteralPath $candidate)) {
            continue
        }
        $resolved = (Resolve-Path -LiteralPath $candidate).Path
        $internalDir = Join-Path (Split-Path -Parent $resolved) "_internal"
        $tclDir = Join-Path $internalDir "_tcl_data"
        if ((Test-Path -LiteralPath $internalDir) -and (-not (Test-Path -LiteralPath $tclDir))) {
            continue
        }
        return [pscustomobject]@{
            Display = "$resolved diag"
            File    = $resolved
            Args    = @("diag")
        }
    }
    return $null
}

function Get-ExecutableCandidate {
    $candidates = @(
        (Join-Path $PSScriptRoot "EndfieldPCAP.exe"),
        (Join-Path (Get-Location) "EndfieldPCAP.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    return $null
}

$script:ReportLines = @()
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$reportPath = Join-Path (Get-Location) "endfield_pcap_diag_$timestamp.txt"
$statusPath = Join-Path $env:TEMP "dxg_trace.dat.status.json"
$tracePath = Join-Path $env:TEMP "dxg_trace.dat"

Add-ReportLine "EndfieldPCAP one-click diagnostic"
Add-ReportLine "time=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') user=$env:USERNAME computer=$env:COMPUTERNAME"
Add-ReportLine "cwd=$(Get-Location)"
Add-ReportLine "temp=$env:TEMP"

Add-Section "Admin"
try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    $isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    Add-ReportLine "is_admin=$isAdmin"
} catch {
    Add-ReportLine "is_admin=unknown error=$($_.Exception.Message)"
}

Add-Section "Processes"
$processRows = Get-ProcessRows
if (-not $processRows) {
    Add-ReportLine "No Endfield/EndfieldPCAP processes found."
} else {
    foreach ($row in $processRows) {
        Add-ReportLine "process name=$($row.Name) pid=$($row.Pid) started=$($row.Started)"
        Add-ReportLine "  path=$(Format-Value $row.Path)"
        Add-ReportLine "  cmd=$(Format-Value $row.CommandLine)"
    }
    $pcapCount = @($processRows | Where-Object { $_.Name -ieq "EndfieldPCAP.exe" }).Count
    if ($pcapCount -gt 1) {
        Add-ReportLine "WARN multiple EndfieldPCAP.exe instances detected: $pcapCount"
    }
}

Add-Section "TCP Connections"
$gamePids = @($processRows | Where-Object { $_.Name -ieq "Endfield.exe" } | ForEach-Object { [int]$_.Pid })
try {
    $connections = @(Get-NetTCPConnection -ErrorAction Stop |
        Where-Object {
            ($gamePids -contains [int]$_.OwningProcess) -or
            ([string]$_.RemotePort -eq $PcapPort) -or
            ([string]$_.LocalPort -eq $PcapPort)
        } |
        Sort-Object OwningProcess, RemotePort, LocalPort)
    if (-not $connections) {
        Add-ReportLine "No matching TCP connections found."
    } else {
        foreach ($conn in $connections) {
            Add-ReportLine "tcp pid=$($conn.OwningProcess) state=$($conn.State) $($conn.LocalAddress):$($conn.LocalPort) -> $($conn.RemoteAddress):$($conn.RemotePort)"
        }
    }
} catch {
    Add-ReportLine "Get-NetTCPConnection failed: $($_.Exception.Message)"
    Add-ReportLine "netstat fallback:"
    try {
        $netstat = netstat -ano | Select-String -Pattern "(:$PcapPort\s)"
        foreach ($line in @($netstat | Select-Object -First 40)) {
            Add-ReportLine "  $($line.Line.Trim())"
        }
    } catch {
        Add-ReportLine "netstat failed: $($_.Exception.Message)"
    }
}

Add-Section "Trace And Status"
if (Test-Path -LiteralPath $tracePath) {
    $traceItem = Get-Item -LiteralPath $tracePath
    Add-ReportLine "trace exists=True path=$tracePath size=$($traceItem.Length) last_write=$($traceItem.LastWriteTime)"
    try {
        $tail = Get-Content -LiteralPath $tracePath -Tail 5 -Encoding UTF8
        Add-ReportLine "trace_tail_count=$(@($tail).Count)"
        foreach ($line in @($tail)) {
            Add-ReportLine "  $line"
        }
    } catch {
        Add-ReportLine "trace_tail_error=$($_.Exception.Message)"
    }
} else {
    Add-ReportLine "trace exists=False path=$tracePath"
}

$snapshot1 = Get-StatusSnapshot -StatusPath $statusPath
Add-StatusSummary -Label "sample1" -Snapshot $snapshot1

if ($WatchSeconds -gt 0) {
    Add-ReportLine ""
    Add-ReportLine "Waiting $WatchSeconds seconds for counter delta..."
    Start-Sleep -Seconds $WatchSeconds
}

$snapshot2 = Get-StatusSnapshot -StatusPath $statusPath
Add-StatusSummary -Label "sample2" -Snapshot $snapshot2

Add-Section "Delta"
if ($snapshot1.Json -and $snapshot2.Json) {
    $p1 = Get-NumberOrZero $snapshot1.Json.metrics.packets_seen
    $p2 = Get-NumberOrZero $snapshot2.Json.metrics.packets_seen
    $f1 = Get-NumberOrZero $snapshot1.Json.metrics.frames_decoded
    $f2 = Get-NumberOrZero $snapshot2.Json.metrics.frames_decoded
    $m1 = Get-NumberOrZero $snapshot1.Json.metrics.messages_decoded
    $m2 = Get-NumberOrZero $snapshot2.Json.metrics.messages_decoded
    $r1 = Get-NumberOrZero $snapshot1.Json.pcap_stats.ps_recv
    $r2 = Get-NumberOrZero $snapshot2.Json.pcap_stats.ps_recv
    Add-ReportLine "delta packets_seen=$($p2 - $p1) frames_decoded=$($f2 - $f1) messages_decoded=$($m2 - $m1) ps_recv=$($r2 - $r1)"
} else {
    Add-ReportLine "delta unavailable because status JSON is missing or invalid."
}

Add-Section "EndfieldPCAP Diag"
$diagCommand = Get-DiagCommand
if ($diagCommand) {
    Add-ReportLine "diag_command=$($diagCommand.Display)"
    try {
        $diagOutput = & $diagCommand.File @($diagCommand.Args) 2>&1 | Select-Object -First 120
        foreach ($line in @($diagOutput)) {
            Add-ReportLine "$line"
        }
    } catch {
        Add-ReportLine "diag_failed=$($_.Exception.Message)"
    }
} else {
    Add-ReportLine "EndfieldPCAP.exe not found near script/current directory."
}

Add-Section "Recent Logs"
$logRoots = @()
if ($snapshot2.Json -and $snapshot2.Json.log -and $snapshot2.Json.log.dir) {
    $logRoots += [string]$snapshot2.Json.log.dir
}
$logRoots += (Join-Path (Get-Location) "logs")
$logRoots += (Join-Path $PSScriptRoot "logs")
$logRoots = @($logRoots | Where-Object { $_ } | Select-Object -Unique)
foreach ($root in $logRoots) {
    if (-not (Test-Path -LiteralPath $root)) {
        Add-ReportLine "log_root missing $root"
        continue
    }
    Add-ReportLine "log_root $root"
    try {
        $files = Get-ChildItem -LiteralPath $root -Recurse -File -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 10
        foreach ($file in @($files)) {
            Add-ReportLine "  file=$($file.FullName) size=$($file.Length) last_write=$($file.LastWriteTime)"
        }
    } catch {
        Add-ReportLine "  log_list_error=$($_.Exception.Message)"
    }
}

Add-Section "Quick Diagnosis"
$diagnosis = @()
$pcapInstances = @($processRows | Where-Object { $_.Name -ieq "EndfieldPCAP.exe" }).Count
$gameInstances = @($processRows | Where-Object { $_.Name -ieq "Endfield.exe" }).Count
if ($pcapInstances -gt 1) {
    $diagnosis += "Multiple EndfieldPCAP instances are running. Close all and run only one."
}
if ($gameInstances -eq 0) {
    $diagnosis += "Endfield.exe is not running."
}
if (-not $snapshot2.Exists) {
    $diagnosis += "Status file is missing. The service may not be the instance writing to this user TEMP."
} elseif ($snapshot2.Json) {
    $state = [string]$snapshot2.Json.state
    $activeFlow = $snapshot2.Json.active_flow
    $packetsSeen = Get-NumberOrZero $snapshot2.Json.metrics.packets_seen
    $framesDecoded = Get-NumberOrZero $snapshot2.Json.metrics.frames_decoded
    $psRecv = Get-NumberOrZero $snapshot2.Json.pcap_stats.ps_recv
    if ($state -eq "waiting_restart") {
        $diagnosis += "Service thinks the game was already running. Close game, keep one service running, then start game again."
    }
    if ($psRecv -eq 0 -and $packetsSeen -eq 0) {
        $diagnosis += "Npcap opened but no tcp/$PcapPort packets are reaching the selected device."
    } elseif (-not $activeFlow) {
        $diagnosis += "Packets are captured, but no Endfield active_flow is locked. Check game tcp/$PcapPort connection owner and possible duplicate process/tunnel."
    } elseif ($framesDecoded -eq 0) {
        $diagnosis += "active_flow exists but no frames decoded. This usually means handshake was missed or capture is one-sided."
    } else {
        $diagnosis += "Capture and decoding appear alive. If overlay is empty, inspect battle events/log output next."
    }
}
foreach ($item in $diagnosis) {
    Add-ReportLine "- $item"
}

Set-Content -LiteralPath $reportPath -Value $script:ReportLines -Encoding UTF8
Add-ReportLine ""
Add-ReportLine "Report saved: $reportPath"
