"""定位并启动终末地游戏本体。

上传器是独立进程，本身不做抓包，也不内置游戏路径检测。这里按可靠性从高到低
依次解析 Endfield.exe：

1. 环境变量 ``ENDFIELD_GAME_EXE`` —— 统一客户端拉起上传器时注入的已解析路径（最可靠）。
2. 统一客户端持久化配置 ``%LOCALAPPDATA%/EndfieldPCAP/settings.json`` 的
   ``service.dll_dir`` + ``service.game_exe``。
3. 上传器自身缓存（用户手动选过一次后记住）。
4. Hypergryph Launcher 默认安装位置（各盘符扫一遍常见路径）。

全部失败时返回 None，由 UI 提示用户手动选择 Endfield.exe（选中后写入上传器缓存）。
仅依赖标准库，可在打包后的冻结环境运行。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

GAME_EXE_NAME = "Endfield.exe"
GAME_DLL_NAME = "GameAssembly.dll"

_ENV_GAME_EXE = "ENDFIELD_GAME_EXE"
_CLIENT_SETTINGS_RELPATH = Path("EndfieldPCAP") / "settings.json"
_UPLOADER_CACHE_RELPATH = Path("EndfieldPCAP") / "uploader_game_path.json"
_LAUNCHER_SUBPATH = Path("Hypergryph Launcher") / "games" / "Endfield Game"


def _is_valid_game_exe(path: Path | None) -> bool:
    if path is None:
        return False
    try:
        return path.is_file() and path.name.lower() == GAME_EXE_NAME.lower() and (path.parent / GAME_DLL_NAME).exists()
    except OSError:
        return False


def _game_exe_from_dir(game_dir: Path | None) -> Path | None:
    if game_dir is None:
        return None
    candidate = game_dir / GAME_EXE_NAME
    return candidate if _is_valid_game_exe(candidate) else None


def _localappdata_root() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")


def _from_env() -> Path | None:
    raw = os.environ.get(_ENV_GAME_EXE)
    if not raw:
        return None
    candidate = Path(raw)
    return candidate if _is_valid_game_exe(candidate) else None


def _from_client_settings() -> Path | None:
    settings_path = _localappdata_root() / _CLIENT_SETTINGS_RELPATH
    if not settings_path.exists():
        return None
    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    service = payload.get("service") if isinstance(payload, dict) else None
    if not isinstance(service, dict):
        return None
    dll_dir = service.get("dll_dir")
    game_exe = service.get("game_exe") or GAME_EXE_NAME
    if not dll_dir:
        return None
    candidate = Path(str(dll_dir)) / str(game_exe)
    return candidate if _is_valid_game_exe(candidate) else None


def _cache_path() -> Path:
    return _localappdata_root() / _UPLOADER_CACHE_RELPATH


def _from_cache() -> Path | None:
    cache_path = _cache_path()
    if not cache_path.exists():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    game_exe = payload.get("game_exe") if isinstance(payload, dict) else None
    if not game_exe:
        return None
    candidate = Path(str(game_exe))
    return candidate if _is_valid_game_exe(candidate) else None


def remember_game_exe(path: Path) -> None:
    cache_path = _cache_path()
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({"game_exe": str(path)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass


def _from_launcher_defaults() -> Path | None:
    for drive_ord in range(ord("C"), ord("Z") + 1):
        root = Path(f"{chr(drive_ord)}:/")
        try:
            if not root.exists():
                continue
        except OSError:
            continue
        for base in (root, root / "Program Files", root / "Program Files (x86)", root / "Games"):
            found = _game_exe_from_dir(base / _LAUNCHER_SUBPATH)
            if found is not None:
                return found
    return None


def resolve_game_exe() -> Path | None:
    for resolver in (_from_env, _from_client_settings, _from_cache, _from_launcher_defaults):
        found = resolver()
        if found is not None:
            return found
    return None


def launch_game(game_exe: Path) -> None:
    """启动游戏本体。失败时抛出 OSError，由调用方提示。"""
    if not _is_valid_game_exe(game_exe):
        raise OSError(f"无效的游戏路径：{game_exe}")
    if sys.platform.startswith("win"):
        os.startfile(str(game_exe))  # type: ignore[attr-defined]  # noqa: S606 - launch user-selected game
        return
    subprocess.Popen([str(game_exe)], cwd=str(game_exe.parent))
