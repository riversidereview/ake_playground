from __future__ import annotations

import argparse
import ctypes
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path


APP_EXE_NAME = "EndfieldLogsUploader.exe"
LOG_FILE_NAME = "updater.log"


def _log_path() -> Path:
    appdata_root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".endfield-pcap")
    log_dir = appdata_root / "EndfieldPCAP" / "updates"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / LOG_FILE_NAME


def _log(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    try:
        with _log_path().open("a", encoding="utf-8") as file:
            file.write(f"[{timestamp}] {message}\n")
    except OSError:
        pass


def _message_box(title: str, message: str) -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)
    except Exception:
        pass


def _wait_for_pid(pid: int, timeout_seconds: int = 45) -> None:
    if pid <= 0:
        return
    deadline = time.monotonic() + timeout_seconds
    if os.name == "nt":
        synchronize = 0x00100000
        wait_timeout = 0x00000102
        handle = ctypes.windll.kernel32.OpenProcess(synchronize, False, pid)
        if not handle:
            return
        try:
            while time.monotonic() < deadline:
                result = ctypes.windll.kernel32.WaitForSingleObject(handle, 250)
                if result != wait_timeout:
                    return
            raise RuntimeError("等待主程序退出超时")
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except OSError:
            return
        time.sleep(0.25)
    raise RuntimeError("等待主程序退出超时")


def _payload_root(staging_dir: Path) -> Path:
    direct = staging_dir / APP_EXE_NAME
    if direct.exists():
        return staging_dir
    for child in staging_dir.iterdir():
        if child.is_dir() and (child / APP_EXE_NAME).exists():
            return child
    matches = list(staging_dir.rglob(APP_EXE_NAME))
    if matches:
        return matches[0].parent
    raise RuntimeError("更新包中没有找到 EndfieldLogsUploader.exe")


def _copy_payload(payload_root: Path, target_dir: Path) -> None:
    if not (payload_root / APP_EXE_NAME).exists():
        raise RuntimeError("更新包结构不正确")
    target_dir.mkdir(parents=True, exist_ok=True)
    for source in payload_root.iterdir():
        target = target_dir / source.name
        if target.exists():
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            shutil.copy2(source, target)


def _extract_package(package_path: Path) -> Path:
    staging_dir = Path(tempfile.mkdtemp(prefix="endfield-uploader-update-"))
    with zipfile.ZipFile(package_path) as archive:
        staging_root = staging_dir.resolve()
        for item in archive.infolist():
            target = (staging_dir / item.filename).resolve()
            if not target.is_relative_to(staging_root):
                raise RuntimeError("更新包包含不安全路径")
        archive.extractall(staging_dir)
    return staging_dir


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="EndfieldLogsUpdater", add_help=True)
    parser.add_argument("--package", required=True, help="已下载的上传器 zip 更新包。")
    parser.add_argument("--target-dir", required=True, help="要替换的上传器安装目录。")
    parser.add_argument("--app-exe", required=True, help="更新完成后要启动的主程序路径。")
    parser.add_argument("--wait-pid", type=int, default=0, help="等待该进程退出后再替换文件。")
    parser.add_argument("--restart", action="store_true", help="更新完成后重启主程序。")
    parser.add_argument("--cleanup-package", action="store_true", help="更新完成后删除 zip 包。")
    return parser


def main() -> int:
    args = _build_arg_parser().parse_args(sys.argv[1:])
    package_path = Path(args.package).resolve()
    target_dir = Path(args.target_dir).resolve()
    app_exe = Path(args.app_exe).resolve()
    staging_dir: Path | None = None

    try:
        _log(f"update start package={package_path} target={target_dir}")
        if not package_path.exists():
            raise RuntimeError(f"更新包不存在：{package_path}")
        _wait_for_pid(args.wait_pid)
        staging_dir = _extract_package(package_path)
        payload_root = _payload_root(staging_dir)
        _copy_payload(payload_root, target_dir)
        if args.cleanup_package:
            package_path.unlink(missing_ok=True)
        if args.restart:
            subprocess.Popen([str(app_exe)], cwd=str(target_dir), close_fds=True)
        _log("update complete")
        return 0
    except Exception as exc:  # noqa: BLE001
        _log(f"update failed: {exc}")
        _message_box("Endfield Logs 更新失败", f"上传器更新失败：{exc}\n\n请重新下载最新版上传器。")
        return 1
    finally:
        if staging_dir is not None:
            shutil.rmtree(staging_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
