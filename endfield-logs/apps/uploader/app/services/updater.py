from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin

import httpx

from app.services.api_client import SAFE_ACCEPT_ENCODING, UPLOADER_CLIENT_VERSION


MANIFEST_PATH = "/downloads/uploader-version.json"
UPDATER_EXE_NAME = "EndfieldLogsUpdater.exe"
APP_EXE_NAME = "EndfieldLogsUploader.exe"
UPDATE_CHECK_TIMEOUT_SECONDS = 5.0
HTTP_HEADERS = {
    "Accept-Encoding": SAFE_ACCEPT_ENCODING,
    "User-Agent": "EndfieldLogsUploader-Updater/1",
}


class UpdateError(RuntimeError):
    pass


@dataclass(frozen=True)
class UpdateManifest:
    version: str
    package_url: str
    sha256: str
    size: int | None = None
    required: bool = False
    notes: tuple[str, ...] = ()


def is_packaged_app() -> bool:
    return bool(getattr(sys, "frozen", False))


def is_embedded_in_unified_client() -> bool:
    if not is_packaged_app():
        return False
    parts = {part.lower() for part in Path(sys.executable).resolve().parts}
    return {"endfieldlogsclient", "_internal", "uploader"}.issubset(parts)


def should_check_for_updates() -> bool:
    if os.environ.get("ENDFIELD_UPLOADER_SKIP_UPDATE_CHECK"):
        return False
    if os.environ.get("ENDFIELD_LOGS_MANAGED_BY_CLIENT"):
        return False
    if is_embedded_in_unified_client():
        return False
    return is_packaged_app()


def version_tuple(value: str) -> tuple[int, ...]:
    parts = [int(part) for part in re.findall(r"\d+", value)]
    if len(parts) < 3:
        raise ValueError("version must include year, month, and day")
    return tuple(parts)


def is_newer_version(candidate: str, current: str = UPLOADER_CLIENT_VERSION) -> bool:
    return version_tuple(candidate) > version_tuple(current)


def manifest_url(base_url: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", MANIFEST_PATH.lstrip("/"))


def parse_update_manifest(payload: dict, *, base_url: str, current_version: str = UPLOADER_CLIENT_VERSION) -> UpdateManifest | None:
    version = str(payload.get("version") or "").strip()
    package_url = str(payload.get("packageUrl") or payload.get("package_url") or "").strip()
    sha256 = str(payload.get("sha256") or "").strip().lower()
    if not version or not package_url or not sha256:
        return None
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        return None
    if not is_newer_version(version, current_version):
        return None

    notes_payload = payload.get("notes")
    if isinstance(notes_payload, list):
        notes = tuple(str(item) for item in notes_payload if str(item).strip())
    elif isinstance(notes_payload, str) and notes_payload.strip():
        notes = (notes_payload.strip(),)
    else:
        notes = ()

    size_payload = payload.get("size")
    try:
        size = int(size_payload) if size_payload is not None else None
    except (TypeError, ValueError):
        size = None

    return UpdateManifest(
        version=version,
        package_url=urljoin(base_url.rstrip("/") + "/", package_url),
        sha256=sha256,
        size=size,
        required=bool(payload.get("required")),
        notes=notes,
    )


def fetch_update_manifest(base_url: str, *, current_version: str = UPLOADER_CLIENT_VERSION) -> UpdateManifest | None:
    try:
        response = httpx.get(
            manifest_url(base_url),
            timeout=UPDATE_CHECK_TIMEOUT_SECONDS,
            headers=HTTP_HEADERS,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, json.JSONDecodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    try:
        return parse_update_manifest(payload, base_url=base_url, current_version=current_version)
    except ValueError:
        return None


def _updates_dir() -> Path:
    appdata_root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".endfield-pcap")
    return appdata_root / "EndfieldPCAP" / "updates"


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def download_update_package(
    manifest: UpdateManifest,
    *,
    progress: Callable[[int, int | None], None] | None = None,
) -> Path:
    updates_dir = _updates_dir()
    updates_dir.mkdir(parents=True, exist_ok=True)
    package_path = updates_dir / f"EndfieldLogsUploader-{manifest.version}.zip"
    if package_path.exists() and _sha256_file(package_path) == manifest.sha256:
        return package_path

    fd, tmp_name = tempfile.mkstemp(prefix=package_path.name, suffix=".tmp", dir=updates_dir)
    os.close(fd)
    tmp_path = Path(tmp_name)
    downloaded = 0
    try:
        with httpx.stream(
            "GET",
            manifest.package_url,
            timeout=httpx.Timeout(10.0, read=120.0),
            headers=HTTP_HEADERS,
        ) as response:
            response.raise_for_status()
            total = int(response.headers.get("Content-Length") or manifest.size or 0) or manifest.size
            with tmp_path.open("wb") as file:
                for chunk in response.iter_bytes(1024 * 512):
                    if not chunk:
                        continue
                    file.write(chunk)
                    downloaded += len(chunk)
                    if progress is not None:
                        progress(downloaded, total)
        digest = _sha256_file(tmp_path)
        if digest != manifest.sha256:
            raise UpdateError(f"下载包校验失败：期望 {manifest.sha256}，实际 {digest}")
        tmp_path.replace(package_path)
        return package_path
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def install_dir() -> Path:
    if is_packaged_app():
        return Path(sys.executable).resolve().parent
    return Path.cwd().resolve()


def launch_updater(package_path: Path, *, target_dir: Path | None = None, restart: bool = True) -> None:
    target = (target_dir or install_dir()).resolve()
    updater_path = target / UPDATER_EXE_NAME
    app_path = target / APP_EXE_NAME
    if not updater_path.exists():
        raise UpdateError(f"找不到更新器：{updater_path}")
    if not app_path.exists():
        raise UpdateError(f"找不到主程序：{app_path}")

    runner_dir = _updates_dir() / "runner"
    runner_dir.mkdir(parents=True, exist_ok=True)
    runner_path = runner_dir / UPDATER_EXE_NAME
    shutil.copy2(updater_path, runner_path)

    args = [
        str(runner_path),
        "--package",
        str(package_path.resolve()),
        "--target-dir",
        str(target),
        "--app-exe",
        str(app_path),
        "--wait-pid",
        str(os.getpid()),
        "--cleanup-package",
    ]
    if restart:
        args.append("--restart")
    subprocess.Popen(args, cwd=str(target), close_fds=True)
