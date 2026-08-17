from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import queue
import subprocess
import sys
import threading
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil

from .game_path import is_valid_game_dir
from .npcap import PCAP_IF_LOOPBACK, Wpcap, has_npcap
from .runtime_paths import app_root, bundle_root


DEFAULT_GAME_PORT = 30000
WATCH_SECONDS = 8
PROCESS_NAMES = {
    "endfield.exe",
    "endfieldlogsclient.exe",
    "endfieldpcap.exe",
    "endfieldlogsuploader.exe",
}


@dataclass(slots=True)
class ProcessRow:
    name: str
    pid: int
    path: str
    started: str
    command_line: str


@dataclass(slots=True)
class Snapshot:
    path: Path
    exists: bool
    payload: dict[str, Any] | None
    error: str | None
    size: int
    mtime: datetime | None


@dataclass(slots=True)
class SessionLogSummary:
    path: Path
    size: int
    mtime: datetime
    lines: int
    json_errors: int
    first_ts_ms: int | None
    last_ts_ms: int | None
    type_counts: Counter[str]
    loadout_rows: int
    scene_chars: int


def default_settings_path() -> Path:
    appdata_root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".endfield-pcap")
    return appdata_root / "EndfieldPCAP" / "settings.json"


def default_trace_file() -> Path:
    return Path(os.environ.get("TEMP") or ".") / "dxg_trace.dat"


def default_status_file() -> Path:
    trace_file = default_trace_file()
    return trace_file.with_suffix(trace_file.suffix + ".status.json")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _format_dt(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _format_ts_ms(value: int | None) -> str:
    if value is None:
        return "-"
    try:
        return datetime.fromtimestamp(value / 1000).strftime("%Y-%m-%d %H:%M:%S")
    except (OSError, OverflowError, ValueError):
        return str(value)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_settings() -> dict[str, Any]:
    payload = _read_json(default_settings_path())
    return payload if payload is not None else {}


def _service_settings(settings: dict[str, Any]) -> dict[str, Any]:
    service = settings.get("service")
    return service if isinstance(service, dict) else {}


def _path_from_setting(value: object) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return Path(value).expanduser().resolve()
    except OSError:
        return Path(value)


def _candidate_version_files() -> list[Path]:
    roots = [
        app_root(),
        bundle_root(),
        app_root() / "_internal",
        Path.cwd(),
        Path.cwd() / "_internal",
    ]
    if getattr(sys, "frozen", False):
        roots.append(Path(sys.executable).resolve().parent)
    result: list[Path] = []
    for root in roots:
        candidate = root / "version.json"
        if candidate not in result:
            result.append(candidate)
    return result


def _version_summary() -> str:
    for path in _candidate_version_files():
        payload = _read_json(path)
        if not payload:
            continue
        version = str(payload.get("version") or "-")
        build = str(payload.get("build") or "-")
        channel = str(payload.get("channel") or "-")
        return f"{version} build={build} channel={channel} source={path}"
    return "-"


def _is_admin() -> str:
    if sys.platform != "win32":
        return "unknown"
    try:
        return "yes" if ctypes.windll.shell32.IsUserAnAdmin() else "no"
    except Exception:  # noqa: BLE001 - diagnostics should keep running.
        return "unknown"


def _process_rows() -> list[ProcessRow]:
    rows: list[ProcessRow] = []
    for process in psutil.process_iter(["name", "exe", "create_time", "cmdline"]):
        try:
            name = str(process.info.get("name") or "")
            if name.casefold() not in PROCESS_NAMES:
                continue
            started = "-"
            create_time = process.info.get("create_time")
            if create_time:
                started = datetime.fromtimestamp(float(create_time)).strftime("%Y-%m-%d %H:%M:%S")
            cmdline = process.info.get("cmdline") or []
            rows.append(
                ProcessRow(
                    name=name,
                    pid=int(process.pid),
                    path=str(process.info.get("exe") or "-"),
                    started=started,
                    command_line=" ".join(str(item) for item in cmdline) or "-",
                )
            )
        except (psutil.Error, OSError, ValueError):
            continue
    return sorted(rows, key=lambda row: (row.name.casefold(), row.pid))


def _tcp_rows(game_pids: set[int], port: int) -> list[str]:
    rows: list[str] = []
    try:
        connections = psutil.net_connections(kind="tcp")
    except psutil.Error as exc:
        return [f"net_connections_error={type(exc).__name__}: {exc}"]
    for conn in connections:
        if conn.pid not in game_pids:
            continue
        laddr = conn.laddr
        raddr = conn.raddr
        if not laddr or not raddr:
            continue
        if int(laddr.port) != port and int(raddr.port) != port:
            continue
        rows.append(
            f"pid={conn.pid} state={conn.status} "
            f"{laddr.ip}:{laddr.port} -> {raddr.ip}:{raddr.port}"
        )
    return sorted(rows)


def _list_npcap_devices_with_timeout(timeout_sec: float = 5.0) -> tuple[list[Any] | None, str | None]:
    result_queue: queue.Queue[tuple[list[Any] | None, BaseException | None]] = queue.Queue(maxsize=1)

    def worker() -> None:
        try:
            result_queue.put((Wpcap().list_devices(), None))
        except BaseException as exc:  # noqa: BLE001 - surface driver/enumeration failures in diagnostics.
            result_queue.put((None, exc))

    thread = threading.Thread(target=worker, name="npcap-list-devices", daemon=True)
    thread.start()
    try:
        devices, exc = result_queue.get(timeout=timeout_sec)
    except queue.Empty:
        return None, f"TimeoutError: list_devices exceeded {timeout_sec:.0f}s"
    if exc is not None:
        return None, f"{type(exc).__name__}: {exc}"
    return devices or [], None


def _read_status_snapshot(path: Path) -> Snapshot:
    if not path.exists():
        return Snapshot(path=path, exists=False, payload=None, error=None, size=0, mtime=None)
    try:
        stat = path.stat()
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("status json is not an object")
        return Snapshot(
            path=path,
            exists=True,
            payload=payload,
            error=None,
            size=stat.st_size,
            mtime=datetime.fromtimestamp(stat.st_mtime),
        )
    except Exception as exc:  # noqa: BLE001 - report malformed status.
        try:
            stat = path.stat()
            size = stat.st_size
            mtime = datetime.fromtimestamp(stat.st_mtime)
        except OSError:
            size = 0
            mtime = None
        return Snapshot(path=path, exists=True, payload=None, error=str(exc), size=size, mtime=mtime)


def _intish(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _nested_int(payload: dict[str, Any] | None, *keys: str) -> int:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return 0
        current = current.get(key)
    return _intish(current)


def _status_age_seconds(snapshot: Snapshot) -> int | None:
    payload = snapshot.payload
    if not payload:
        return None
    updated_at = _intish(payload.get("updated_at_ms"))
    if not updated_at:
        return None
    return max(0, int((_now_ms() - updated_at) / 1000))


def _summarize_session_log(path: Path, max_lines: int = 200_000) -> SessionLogSummary:
    type_counts: Counter[str] = Counter()
    first_ts_ms: int | None = None
    last_ts_ms: int | None = None
    loadout_rows = 0
    scene_chars = 0
    lines = 0
    json_errors = 0
    stat = path.stat()
    with path.open("r", encoding="utf-8", errors="ignore") as file:
        for raw_line in file:
            lines += 1
            if lines > max_lines:
                break
            line = raw_line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                json_errors += 1
                continue
            if not isinstance(item, dict):
                continue
            event_type = str(item.get("type") or "-")
            type_counts[event_type] += 1
            ts_ms = _intish(item.get("timestamp_ms"))
            if ts_ms:
                if first_ts_ms is None:
                    first_ts_ms = ts_ms
                last_ts_ms = ts_ms
            if event_type == "LOADOUT" and isinstance(item.get("rows"), list):
                loadout_rows = max(loadout_rows, len(item["rows"]))
            if event_type == "SC_SELF_SCENE_INFO" and isinstance(item.get("char_list"), list):
                scene_chars = max(scene_chars, len(item["char_list"]))
    return SessionLogSummary(
        path=path,
        size=stat.st_size,
        mtime=datetime.fromtimestamp(stat.st_mtime),
        lines=lines,
        json_errors=json_errors,
        first_ts_ms=first_ts_ms,
        last_ts_ms=last_ts_ms,
        type_counts=type_counts,
        loadout_rows=loadout_rows,
        scene_chars=scene_chars,
    )


def _recent_session_logs(log_dir: Path, limit: int = 5) -> list[Path]:
    if not log_dir.exists():
        return []
    try:
        files = sorted(log_dir.rglob("session_*.ndjson"), key=lambda item: item.stat().st_mtime, reverse=True)
    except OSError:
        return []
    return files[:limit]


def _add_status_lines(lines: list[str], label: str, snapshot: Snapshot) -> None:
    lines.append(f"{label}: path={snapshot.path}")
    if not snapshot.exists:
        lines.append(f"{label}: exists=no")
        return
    lines.append(f"{label}: exists=yes size={snapshot.size} mtime={_format_dt(snapshot.mtime)}")
    if snapshot.error:
        lines.append(f"{label}: json_error={snapshot.error}")
        return
    payload = snapshot.payload or {}
    active_flow = payload.get("active_flow") if isinstance(payload.get("active_flow"), dict) else None
    active_flow_text = "-"
    if active_flow:
        active_flow_text = f"{active_flow.get('client') or '-'} -> {active_flow.get('server') or '-'}"
    lines.append(
        f"{label}: state={payload.get('state') or '-'} session_id={payload.get('session_id') or '-'} "
        f"age_seconds={_status_age_seconds(snapshot) if _status_age_seconds(snapshot) is not None else '-'}"
    )
    lines.append(f"{label}: active_flow={active_flow_text}")
    lines.append(
        f"{label}: packets_seen={_nested_int(payload, 'metrics', 'packets_seen')} "
        f"frames_decoded={_nested_int(payload, 'metrics', 'frames_decoded')} "
        f"messages_decoded={_nested_int(payload, 'metrics', 'messages_decoded')} "
        f"events={_nested_int(payload, 'metrics', 'outbound_events_emitted')} "
        f"queue_drop={_nested_int(payload, 'metrics', 'packets_dropped_queue')} "
        f"decompression_errors={_nested_int(payload, 'metrics', 'decompression_errors')} "
        f"protobuf_decode_errors={_nested_int(payload, 'metrics', 'protobuf_decode_errors')}"
    )
    reliability_flags = payload.get("reliability_flags")
    if isinstance(reliability_flags, list) and reliability_flags:
        lines.append(f"{label}: reliability_flags={','.join(str(flag) for flag in reliability_flags)}")
    lines.append(
        f"{label}: pcap_ps_recv={_nested_int(payload, 'pcap_stats', 'ps_recv')} "
        f"pcap_ps_drop={_nested_int(payload, 'pcap_stats', 'ps_drop')} "
        f"pcap_ps_ifdrop={_nested_int(payload, 'pcap_stats', 'ps_ifdrop')}"
    )
    log_info = payload.get("log") if isinstance(payload.get("log"), dict) else {}
    if log_info:
        lines.append(
            f"{label}: log_dir={log_info.get('dir') or '-'} log_path={log_info.get('path') or '-'} "
            f"log_size={log_info.get('size') if log_info.get('size') is not None else '-'} "
            f"write_errors={log_info.get('write_errors') if log_info.get('write_errors') is not None else '-'}"
        )


def _append_delta(lines: list[str], before: Snapshot, after: Snapshot) -> dict[str, int]:
    delta = {
        "packets_seen": _nested_int(after.payload, "metrics", "packets_seen")
        - _nested_int(before.payload, "metrics", "packets_seen"),
        "frames_decoded": _nested_int(after.payload, "metrics", "frames_decoded")
        - _nested_int(before.payload, "metrics", "frames_decoded"),
        "messages_decoded": _nested_int(after.payload, "metrics", "messages_decoded")
        - _nested_int(before.payload, "metrics", "messages_decoded"),
        "events": _nested_int(after.payload, "metrics", "outbound_events_emitted")
        - _nested_int(before.payload, "metrics", "outbound_events_emitted"),
        "decompression_errors": _nested_int(after.payload, "metrics", "decompression_errors")
        - _nested_int(before.payload, "metrics", "decompression_errors"),
        "protobuf_decode_errors": _nested_int(after.payload, "metrics", "protobuf_decode_errors")
        - _nested_int(before.payload, "metrics", "protobuf_decode_errors"),
        "pcap_ps_recv": _nested_int(after.payload, "pcap_stats", "ps_recv")
        - _nested_int(before.payload, "pcap_stats", "ps_recv"),
    }
    lines.append(
        "delta: "
        f"packets_seen={delta['packets_seen']} "
        f"frames_decoded={delta['frames_decoded']} "
        f"messages_decoded={delta['messages_decoded']} "
        f"events={delta['events']} "
        f"decompression_errors={delta['decompression_errors']} "
        f"protobuf_decode_errors={delta['protobuf_decode_errors']} "
        f"pcap_ps_recv={delta['pcap_ps_recv']}"
    )
    return delta


def collect_diagnostic_report(watch_seconds: int = WATCH_SECONDS, game_port: int = DEFAULT_GAME_PORT) -> str:
    lines: list[str] = []
    diagnosis: list[str] = []
    settings = _read_settings()
    service_settings = _service_settings(settings)
    configured_log_dir = _path_from_setting(service_settings.get("log_dir"))
    configured_game_dir = _path_from_setting(service_settings.get("dll_dir"))
    current_app_root = app_root()
    status_path = default_status_file()

    lines.append("Endfield Logs Client diagnostic report")
    lines.append(f"time={datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"version={_version_summary()}")
    lines.append(f"python={platform.python_version()} frozen={getattr(sys, 'frozen', False)}")
    lines.append(f"os={platform.platform()}")
    lines.append(f"app_root={current_app_root}")
    lines.append(f"bundle_root={bundle_root()}")
    lines.append(f"settings={default_settings_path()} exists={'yes' if default_settings_path().exists() else 'no'}")

    lines.append("")
    lines.append("==== 基础检查 ====")
    lines.append(f"is_admin={_is_admin()}")
    lines.append(f"game_dir={configured_game_dir or '-'} valid={'yes' if is_valid_game_dir(configured_game_dir) else 'no'}")
    lines.append(f"configured_log_dir={configured_log_dir or '-'}")
    lines.append(f"default_log_dir={current_app_root / 'logs'}")
    lines.append(f"trace_file={default_trace_file()} exists={'yes' if default_trace_file().exists() else 'no'}")
    lines.append(f"status_file={status_path} exists={'yes' if status_path.exists() else 'no'}")

    if not is_valid_game_dir(configured_game_dir):
        diagnosis.append("游戏目录未配置或无效：在客户端里重新选择 Endfield.exe 或 Endfield Game 目录。")

    lines.append("")
    lines.append("==== 进程 ====")
    processes = _process_rows()
    if not processes:
        lines.append("未发现 Endfield / EndfieldLogs 相关进程。")
    for row in processes:
        lines.append(f"process name={row.name} pid={row.pid} started={row.started}")
        lines.append(f"  path={row.path}")
    game_pids = {row.pid for row in processes if row.name.casefold() == "endfield.exe"}
    client_pids = {
        row.pid
        for row in processes
        if row.name.casefold() in {"endfieldlogsclient.exe", "endfieldpcap.exe"}
    }
    if not game_pids:
        diagnosis.append("当前没有检测到 Endfield.exe：如果要排查没数据，请先启动游戏并进入账号。")
    if not client_pids:
        diagnosis.append("当前没有检测到统一客户端主进程：建议保持客户端运行时再跑诊断器。")
    if len(client_pids) > 1:
        diagnosis.append("检测到多个客户端采集进程：关闭多余客户端，只保留一个。")

    lines.append("")
    lines.append("==== 游戏 TCP 连接 ====")
    tcp_rows = _tcp_rows(game_pids, game_port)
    if not tcp_rows:
        lines.append(f"未发现 Endfield.exe 的 tcp/{game_port} 连接。")
        if game_pids:
            diagnosis.append(f"游戏已运行但没有 tcp/{game_port} 连接：可能还没进游戏服务器，或端口规则需要更新。")
    else:
        lines.extend(tcp_rows)

    lines.append("")
    lines.append("==== Npcap ====")
    npcap_ok = has_npcap()
    lines.append(f"npcap={np_cap_text(npcap_ok)}")
    device_count = 0
    device_error: str | None = None
    if not npcap_ok:
        diagnosis.append("未检测到 Npcap/wpcap.dll：安装 Npcap 后重启客户端。")
    else:
        devices, device_error = _list_npcap_devices_with_timeout()
        if device_error is not None:
            lines.append(f"npcap_error={device_error}")
            diagnosis.append("Npcap 已安装但枚举网卡失败或超时：尝试管理员运行或重新安装 Npcap。")
        else:
            devices = devices or []
            device_count = len(devices)
            lines.append(f"device_count={device_count}")
            for index, device in enumerate(devices, 1):
                loopback = " loopback" if device.flags & PCAP_IF_LOOPBACK else ""
                lines.append(
                    f"device[{index}] desc={device.description or '-'} "
                        f"ipv4={','.join(device.ipv4_addrs) or '-'} name={device.name}{loopback}"
                )
    if npcap_ok and device_count == 0 and device_error is None:
        diagnosis.append("Npcap 没有枚举到网卡：尝试重新安装 Npcap，安装时保留 WinPcap API 兼容。")

    lines.append("")
    lines.append("==== 实时采集状态 ====")
    before = _read_status_snapshot(status_path)
    _add_status_lines(lines, "sample1", before)
    if watch_seconds > 0:
        lines.append(f"等待 {watch_seconds} 秒观察计数变化...")
        time.sleep(watch_seconds)
    after = _read_status_snapshot(status_path)
    _add_status_lines(lines, "sample2", after)
    delta = _append_delta(lines, before, after)

    after_payload = after.payload or {}
    after_age = _status_age_seconds(after)
    if not after.exists:
        diagnosis.append("没有实时状态文件：客户端可能没启动采集服务，或诊断器与客户端不是同一个 Windows 用户。")
    elif after.error:
        diagnosis.append("实时状态文件损坏：重启客户端后再运行诊断器。")
    else:
        state = str(after_payload.get("state") or "")
        if after_age is not None and after_age > 120:
            diagnosis.append("实时状态文件超过 120 秒未更新：客户端采集服务可能已经停止。")
        if state == "waiting_restart":
            diagnosis.append("客户端提示需要重启游戏：保持客户端打开，完全退出游戏后再启动游戏。")
        if _nested_int(after_payload, "log", "write_errors") > 0:
            diagnosis.append("本地日志写入出现错误：检查日志目录权限，或换到普通英文路径。")
        protocol_error_count = (
            _nested_int(after_payload, "metrics", "decompression_errors")
            + _nested_int(after_payload, "metrics", "protobuf_decode_errors")
        )
        if protocol_error_count > 0:
            diagnosis.append(
                "协议解压或 protobuf 解码出现明确失败：保留 debug/issues 目录，优先检查客户端协议表与游戏版本是否一致。"
            )
        if game_pids and npcap_ok and delta["packets_seen"] <= 0 and delta["pcap_ps_recv"] <= 0:
            diagnosis.append("观察期间没有抓到游戏包：检查是否选错网卡、VPN/代理/虚拟网卡影响，或先重新启动游戏。")
        elif game_pids and delta["packets_seen"] > 0 and _nested_int(after_payload, "metrics", "frames_decoded") == 0:
            diagnosis.append("能抓到包但没解出协议帧：通常是启动顺序不对，先开客户端再完整重启游戏。")
        elif (
            game_pids
            and _nested_int(after_payload, "metrics", "frames_decoded") > 0
            and protocol_error_count == 0
        ):
            diagnosis.append("采集和解码看起来是活的；如果悬浮窗没数据，重点看是否进入战斗、日志是否有新事件。")

    lines.append("")
    lines.append("==== 最近本地日志 ====")
    log_dirs = [
        configured_log_dir,
        Path(str((after_payload.get("log") or {}).get("dir"))) if isinstance(after_payload.get("log"), dict) and (after_payload.get("log") or {}).get("dir") else None,
        current_app_root / "logs",
        Path.cwd() / "logs",
    ]
    seen_log_dirs: set[Path] = set()
    latest_summary: SessionLogSummary | None = None
    for raw_dir in log_dirs:
        if raw_dir is None:
            continue
        try:
            log_dir = raw_dir.resolve()
        except OSError:
            log_dir = raw_dir
        if log_dir in seen_log_dirs:
            continue
        seen_log_dirs.add(log_dir)
        lines.append(f"log_root={log_dir} exists={'yes' if log_dir.exists() else 'no'}")
        recent = _recent_session_logs(log_dir)
        if not recent:
            continue
        for path in recent:
            try:
                stat = path.stat()
            except OSError:
                continue
            lines.append(f"  file={path} size={stat.st_size} mtime={_format_dt(datetime.fromtimestamp(stat.st_mtime))}")
        if latest_summary is None:
            try:
                latest_summary = _summarize_session_log(recent[0])
            except OSError as exc:
                lines.append(f"  latest_summary_error={exc}")

    if latest_summary is None:
        diagnosis.append("没有找到 session_*.ndjson：客户端还没有写出任何采集日志。")
    else:
        lines.append("")
        lines.append("latest_log_summary:")
        lines.append(f"  path={latest_summary.path}")
        lines.append(f"  size={latest_summary.size} lines={latest_summary.lines} json_errors={latest_summary.json_errors}")
        lines.append(f"  mtime={_format_dt(latest_summary.mtime)}")
        lines.append(f"  event_time={_format_ts_ms(latest_summary.first_ts_ms)} -> {_format_ts_ms(latest_summary.last_ts_ms)}")
        lines.append(f"  loadout_rows={latest_summary.loadout_rows} scene_chars={latest_summary.scene_chars}")
        top_types = "; ".join(f"{name}={count}" for name, count in latest_summary.type_counts.most_common(12))
        lines.append(f"  top_types={top_types or '-'}")
        if latest_summary.loadout_rows <= 0:
            diagnosis.append("最新日志没有 LOADOUT：队伍信息没读到，通常需要先进入角色/场景后再进战斗。")
        if latest_summary.lines <= 0:
            diagnosis.append("最新日志是空文件：采集服务创建了文件，但还没有收到可解析事件。")
        if (_now_ms() - int(latest_summary.mtime.timestamp() * 1000)) > 10 * 60 * 1000:
            diagnosis.append("最新本地日志超过 10 分钟未更新：当前客户端可能没有持续采集。")

    lines.append("")
    lines.append("==== 快速结论 ====")
    if diagnosis:
        for item in dict.fromkeys(diagnosis):
            lines.append(f"- {item}")
    else:
        lines.append("- 没发现明显阻断项；如果仍然没数据，把这份报告连同出问题时间点发给维护者。")
    lines.append("")
    lines.append("提示：报告包含本机路径、进程和连接信息；发给别人前可以自行遮掉用户名。")
    return "\n".join(lines) + "\n"


def np_cap_text(value: bool) -> str:
    return "yes" if value else "no"


def write_diagnostic_report(out_path: Path | None = None, watch_seconds: int = WATCH_SECONDS) -> Path:
    target = out_path or app_root() / "diagnostics" / f"endfield_logs_diag_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(collect_diagnostic_report(watch_seconds=watch_seconds), encoding="utf-8-sig")
    return target


def _message_box(title: str, text: str) -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x40)
    except Exception:  # noqa: BLE001 - best effort notification.
        return


def run_detector_app(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Endfield Logs Client detector")
    parser.add_argument("--watch-seconds", type=int, default=WATCH_SECONDS)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--no-open", action="store_true")
    parser.add_argument("--no-messagebox", action="store_true")
    parser.add_argument("--print", action="store_true", dest="print_report")
    args = parser.parse_args(argv)

    try:
        report_path = write_diagnostic_report(args.out, max(0, int(args.watch_seconds)))
    except Exception as exc:  # noqa: BLE001 - detector should surface any unexpected failure.
        _message_box("EndfieldLogsDetector", f"诊断失败：{type(exc).__name__}: {exc}")
        raise

    if args.print_report:
        print(report_path.read_text(encoding="utf-8-sig"))
    if not args.no_open and sys.platform == "win32":
        try:
            subprocess.Popen(["notepad.exe", str(report_path)])
        except OSError:
            pass
    if not args.no_messagebox:
        _message_box("EndfieldLogsDetector", f"诊断完成，报告已生成：\n{report_path}")
    return 0
