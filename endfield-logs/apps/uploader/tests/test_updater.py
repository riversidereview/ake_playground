from __future__ import annotations

import subprocess
from pathlib import Path

from app import updater_main
from app.services import updater


def test_update_requests_never_advertise_zstd() -> None:
    assert updater.HTTP_HEADERS["Accept-Encoding"] == "gzip, deflate"
    assert "zstd" not in updater.HTTP_HEADERS["Accept-Encoding"]


def test_parse_update_manifest_accepts_newer_relative_package_url() -> None:
    manifest = updater.parse_update_manifest(
        {
            "version": "2026.05.08.3",
            "packageUrl": "/downloads/EndfieldLogsUploader.zip",
            "sha256": "a" * 64,
            "size": "123",
            "required": True,
            "notes": ["补丁更新"],
        },
        base_url="https://zmdlogs.com",
        current_version="2026.05.08.2",
    )

    assert manifest is not None
    assert manifest.version == "2026.05.08.3"
    assert manifest.package_url == "https://zmdlogs.com/downloads/EndfieldLogsUploader.zip"
    assert manifest.sha256 == "a" * 64
    assert manifest.size == 123
    assert manifest.required is True
    assert manifest.notes == ("补丁更新",)


def test_parse_update_manifest_ignores_current_version() -> None:
    manifest = updater.parse_update_manifest(
        {
            "version": "2026.05.08.2",
            "packageUrl": "/downloads/EndfieldLogsUploader.zip",
            "sha256": "b" * 64,
        },
        base_url="https://zmdlogs.com",
        current_version="2026.05.08.2",
    )

    assert manifest is None


def test_should_check_for_updates_skips_unified_client_managed_uploader(monkeypatch) -> None:
    monkeypatch.setattr(updater, "is_packaged_app", lambda: True)
    monkeypatch.setattr(updater, "is_embedded_in_unified_client", lambda: False)

    monkeypatch.setenv("ENDFIELD_LOGS_MANAGED_BY_CLIENT", "1")

    assert updater.should_check_for_updates() is False


def test_should_check_for_updates_skips_uploader_embedded_in_unified_client(monkeypatch) -> None:
    monkeypatch.delenv("ENDFIELD_UPLOADER_SKIP_UPDATE_CHECK", raising=False)
    monkeypatch.delenv("ENDFIELD_LOGS_MANAGED_BY_CLIENT", raising=False)
    monkeypatch.setattr(updater, "is_packaged_app", lambda: True)
    monkeypatch.setattr(updater, "is_embedded_in_unified_client", lambda: True)

    assert updater.should_check_for_updates() is False


def test_launch_updater_copies_runner_and_invokes_temp_executable(monkeypatch, tmp_path) -> None:
    target_dir = tmp_path / "install"
    target_dir.mkdir()
    (target_dir / updater.UPDATER_EXE_NAME).write_text("updater", encoding="utf-8")
    (target_dir / updater.APP_EXE_NAME).write_text("app", encoding="utf-8")
    package_path = tmp_path / "package.zip"
    package_path.write_text("zip", encoding="utf-8")
    updates_dir = tmp_path / "updates"
    calls: list[tuple[list[str], str | None, bool]] = []

    monkeypatch.setattr(updater, "_updates_dir", lambda: updates_dir)
    monkeypatch.setattr(updater.os, "getpid", lambda: 1234)

    def fake_popen(args: list[str], *, cwd: str | None = None, close_fds: bool = False) -> None:
        calls.append((args, cwd, close_fds))

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    updater.launch_updater(package_path, target_dir=target_dir)

    runner_path = updates_dir / "runner" / updater.UPDATER_EXE_NAME
    assert runner_path.read_text(encoding="utf-8") == "updater"
    assert calls
    args, cwd, close_fds = calls[0]
    assert Path(args[0]) == runner_path
    assert "--wait-pid" in args
    assert "1234" in args
    assert "--restart" in args
    assert cwd == str(target_dir.resolve())
    assert close_fds is True


def test_updater_main_replaces_payload_files(tmp_path) -> None:
    payload_root = tmp_path / "payload" / "EndfieldLogsUploader"
    payload_root.mkdir(parents=True)
    (payload_root / updater_main.APP_EXE_NAME).write_text("new app", encoding="utf-8")
    (payload_root / "EndfieldLogsUpdater.exe").write_text("new updater", encoding="utf-8")
    internal_dir = payload_root / "_internal"
    internal_dir.mkdir()
    (internal_dir / "new.txt").write_text("new data", encoding="utf-8")

    target_dir = tmp_path / "target"
    target_dir.mkdir()
    (target_dir / updater_main.APP_EXE_NAME).write_text("old app", encoding="utf-8")
    old_internal_dir = target_dir / "_internal"
    old_internal_dir.mkdir()
    (old_internal_dir / "old.txt").write_text("old data", encoding="utf-8")

    assert updater_main._payload_root(tmp_path / "payload") == payload_root

    updater_main._copy_payload(payload_root, target_dir)

    assert (target_dir / updater_main.APP_EXE_NAME).read_text(encoding="utf-8") == "new app"
    assert (target_dir / "EndfieldLogsUpdater.exe").read_text(encoding="utf-8") == "new updater"
    assert (target_dir / "_internal" / "new.txt").read_text(encoding="utf-8") == "new data"
    assert not (target_dir / "_internal" / "old.txt").exists()
