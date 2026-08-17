# Endfield Logs unified client

This directory contains the packet capture service, protocol parser, trace
bridge, overlay, updater, and the parser core used by the Windows client.

## Requirements

- Windows and Python 3.13 or newer.
- Npcap with WinPcap-compatible mode enabled.
- A PEM key supplied by the user through `ENDFIELD_RSA_KEY_FILE` or
  `--rsa-key-txt`.
- Optional generated parser metadata through `ENDFIELD_LOGS_DATA_ROOT`.

Private keys, extracted game tables, raw protocol sources, packet captures, and
release artifacts are not included in this repository.

## Run from source

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
$env:ENDFIELD_RSA_KEY_FILE = "C:\path\to\your\authorized-key.pem"
.\.venv\Scripts\python.exe -m endfield_pcap serve
```

Useful options:

```text
--npcap-device auto
--dll-dir C:\path\to\Endfield\Game
--no-overlay
--debug
```

The open-source build never imports an embedded key. Missing optional mapping
resources may reduce display names or disable data-driven rDPS rules, but should
remain visible through diagnostics rather than being silently trusted.

Client-side integrity fields are corruption checks, not proof of authenticity.
Production ranking services must enforce their trust boundary on the server.

