from __future__ import annotations

import asyncio
import os
import runpy
import subprocess
import threading
import time
from pathlib import Path

from .runtime_paths import bundle_root
from .service import DamageLogService, ServiceConfig
from .trace_bridge import make_archive_trace_file


def _launch_managed_uploader(trace_file: Path, game_exe: Path) -> subprocess.Popen | None:
    if os.environ.get("ENDFIELD_LOGS_DISABLE_UPLOADER") == "1":
        return None
    root = bundle_root()
    candidates = [
        root / "uploader" / "EndfieldLogsUploader" / "EndfieldLogsUploader.exe",
        root.parent / "uploader" / "EndfieldLogsUploader" / "EndfieldLogsUploader.exe",
    ]
    for candidate in candidates:
        if not candidate.exists():
            continue
        env = os.environ.copy()
        env["ENDFIELD_UPLOADER_SKIP_UPDATE_CHECK"] = "1"
        env["ENDFIELD_LOGS_MANAGED_BY_CLIENT"] = "1"
        env["ENDFIELD_GAME_EXE"] = str(game_exe)
        try:
            return subprocess.Popen(
                [str(candidate), "--watch-log", str(trace_file)],
                cwd=str(candidate.parent),
                env=env,
            )
        except OSError:
            return None
    return None


def _stop_managed_uploader(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.kill()
        except OSError:
            return


def _wait_for_service_start(
    service: DamageLogService,
    thread: threading.Thread,
    errors: list[BaseException],
    *,
    timeout: float = 8.0,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if service.wait_started(0.05):
            return
        if errors:
            raise errors[0]
        if not thread.is_alive():
            # The worker may have crossed its final instruction just before
            # publishing the captured exception. Join briefly, then prefer
            # the real startup cause over the generic lifecycle message.
            thread.join(timeout=0.05)
            if errors:
                raise errors[0]
            raise RuntimeError("采集服务在启动完成前意外退出。")
    raise TimeoutError("采集服务启动超时，上传器未启动。")


def run_with_overlay(config: ServiceConfig) -> int:
    root = bundle_root()
    trace_file = config.trace_file or make_archive_trace_file(config.log_dir)
    config.trace_file = trace_file
    status_file = config.status_file or trace_file.with_suffix(trace_file.suffix + ".status.json")
    config.status_file = status_file
    os.environ["ENDFIELD_PCAP_TRACE_FILE"] = str(trace_file)
    os.environ["ENDFIELD_PCAP_STATUS_FILE"] = str(status_file)
    os.environ.setdefault("ENDFIELD_LOGS_DATA_ROOT", str(root))
    os.environ.setdefault("ENDFIELD_LOGS_PARSER_CORE", str(root / "packages" / "parser_core"))

    service = DamageLogService(config)
    error: list[BaseException] = []

    def service_main() -> None:
        try:
            asyncio.run(service.run())
        except BaseException as exc:  # noqa: BLE001 - surface in caller.
            error.append(exc)

    thread = threading.Thread(target=service_main, name="endfield-pcap-service", daemon=True)
    thread.start()
    uploader_process: subprocess.Popen | None = None
    try:
        _wait_for_service_start(service, thread, error)
        game_exe = (Path(config.dll_dir) / config.game_exe).resolve()
        uploader_process = _launch_managed_uploader(trace_file, game_exe)
        runpy.run_path(str(Path(root) / "overlay.py"), run_name="__main__")
    finally:
        _stop_managed_uploader(uploader_process)
        service.request_stop()
        thread.join(timeout=5)
    if error:
        raise error[0]
    return 0
