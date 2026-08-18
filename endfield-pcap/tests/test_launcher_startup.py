from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

import launcher
from endfield_pcap import runner


@pytest.fixture(autouse=True)
def _mock_npcap_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("endfield_pcap.npcap_setup.prompt_npcap_install_interactive", lambda: True)
    monkeypatch.setattr("launcher.prompt_npcap_install_interactive", lambda: True)


def _game_dir(tmp_path: Path) -> Path:
    game_dir = tmp_path / "Endfield Game"
    game_dir.mkdir()
    (game_dir / "Endfield.exe").write_bytes(b"")
    (game_dir / "GameAssembly.dll").write_bytes(b"")
    return game_dir


def test_default_launch_resolves_game_path_before_entering_cli(monkeypatch, tmp_path: Path) -> None:
    game_dir = _game_dir(tmp_path)
    trace_file = tmp_path / "logs" / "trace.log"
    calls: list[str] = []

    monkeypatch.setattr(launcher.sys, "argv", ["EndfieldLogsClient.exe"])
    monkeypatch.setattr(launcher, "check_and_maybe_start_update", lambda: False)
    monkeypatch.setattr(launcher, "_ensure_desktop_shortcut_once", lambda: None)
    monkeypatch.setattr(
        launcher,
        "ensure_configured_game_dir_interactive",
        lambda: calls.append("game_path") or game_dir,
    )
    monkeypatch.setattr(launcher, "_default_log_dir", lambda: tmp_path / "logs")
    monkeypatch.setattr(launcher, "make_archive_trace_file", lambda _path: trace_file)

    def fake_main() -> int:
        calls.append("main")
        assert launcher.sys.argv[-2:] == ["--dll-dir", str(game_dir.resolve())]
        assert "--trace-file" in launcher.sys.argv
        return 0

    monkeypatch.setattr(launcher, "main", fake_main)

    assert launcher.run() == 0
    assert calls == ["game_path", "main"]


def test_cancelled_game_path_does_not_enter_cli_or_start_any_child(monkeypatch, tmp_path: Path) -> None:
    messages: list[tuple[str, str, bool]] = []
    logs: list[str] = []

    monkeypatch.setattr(launcher.sys, "argv", ["EndfieldLogsClient.exe"])
    monkeypatch.setattr(launcher, "check_and_maybe_start_update", lambda: False)
    monkeypatch.setattr(launcher, "_ensure_desktop_shortcut_once", lambda: None)
    monkeypatch.setattr(launcher, "ensure_configured_game_dir_interactive", lambda: None)
    monkeypatch.setattr(
        launcher,
        "_write_startup_log",
        lambda message: logs.append(message) or (tmp_path / "startup.log"),
    )
    monkeypatch.setattr(
        launcher,
        "_show_startup_message",
        lambda title, message, error=False: messages.append((title, message, error)),
    )
    monkeypatch.setattr(launcher, "main", lambda: pytest.fail("CLI must not run after path cancellation"))

    assert launcher.run() == 1
    assert logs == ["game path setup cancelled; startup aborted before uploader launch"]
    assert len(messages) == 1
    assert "startup aborted" in messages[0][1].lower()


def test_default_launch_surfaces_invisible_startup_failure(monkeypatch, tmp_path: Path) -> None:
    game_dir = _game_dir(tmp_path)
    messages: list[tuple[str, str, bool]] = []
    logs: list[str] = []

    monkeypatch.setattr(launcher.sys, "argv", ["EndfieldLogsClient.exe"])
    monkeypatch.setattr(launcher, "check_and_maybe_start_update", lambda: False)
    monkeypatch.setattr(launcher, "_ensure_desktop_shortcut_once", lambda: None)
    monkeypatch.setattr(launcher, "ensure_configured_game_dir_interactive", lambda: game_dir)
    monkeypatch.setattr(launcher, "_default_log_dir", lambda: tmp_path / "logs")
    monkeypatch.setattr(launcher, "make_archive_trace_file", lambda _path: tmp_path / "trace.log")
    monkeypatch.setattr(launcher, "main", lambda: (_ for _ in ()).throw(RuntimeError("capture failed")))
    monkeypatch.setattr(
        launcher,
        "_write_startup_log",
        lambda message: logs.append(message) or (tmp_path / "startup.log"),
    )
    monkeypatch.setattr(
        launcher,
        "_show_startup_message",
        lambda title, message, error=False: messages.append((title, message, error)),
    )

    assert launcher.run() == 1
    assert "RuntimeError: capture failed" in logs[0]
    assert messages[0][2] is True
    assert "capture failed" in messages[0][1]


def test_runner_launches_uploader_only_after_service_start_and_stops_it(monkeypatch, tmp_path: Path) -> None:
    events: list[str] = []

    class ServiceSpy:
        def __init__(self, config) -> None:
            self.stop_requested = False

        async def run(self) -> None:
            events.append("service_run")
            while not self.stop_requested:
                await asyncio.sleep(0.001)

        def wait_started(self, timeout=None) -> bool:
            events.append("service_started")
            return True

        def request_stop(self) -> None:
            events.append("service_stop")
            self.stop_requested = True

    class ProcessSpy:
        def __init__(self) -> None:
            self.running = True

        def poll(self):
            return None if self.running else 0

        def terminate(self) -> None:
            events.append("uploader_terminate")
            self.running = False

        def wait(self, timeout=None) -> int:
            return 0

        def kill(self) -> None:
            self.running = False

    trace_file = tmp_path / "trace.log"
    config = SimpleNamespace(
        trace_file=trace_file,
        status_file=None,
        log_dir=tmp_path,
        dll_dir=tmp_path / "Endfield Game",
        game_exe="Endfield.exe",
    )
    process = ProcessSpy()

    monkeypatch.setattr(runner, "DamageLogService", ServiceSpy)
    monkeypatch.setattr(runner, "bundle_root", lambda: tmp_path)
    monkeypatch.setattr(
        runner,
        "_launch_managed_uploader",
        lambda _trace, _game: events.append("uploader_launch") or process,
    )
    monkeypatch.setattr(
        runner.runpy,
        "run_path",
        lambda *_args, **_kwargs: events.append("overlay_run"),
    )

    assert runner.run_with_overlay(config) == 0
    assert events.index("service_started") < events.index("uploader_launch")
    assert events.index("uploader_launch") < events.index("overlay_run")
    assert "uploader_terminate" in events
    assert "service_stop" in events


def test_runner_does_not_launch_uploader_when_service_start_fails(monkeypatch, tmp_path: Path) -> None:
    launched: list[bool] = []

    class FailingService:
        def __init__(self, config) -> None:
            pass

        async def run(self) -> None:
            raise RuntimeError("npcap open failed")

        def wait_started(self, timeout=None) -> bool:
            return False

        def request_stop(self) -> None:
            pass

    config = SimpleNamespace(
        trace_file=tmp_path / "trace.log",
        status_file=None,
        log_dir=tmp_path,
        dll_dir=tmp_path / "Endfield Game",
        game_exe="Endfield.exe",
    )
    monkeypatch.setattr(runner, "DamageLogService", FailingService)
    monkeypatch.setattr(runner, "bundle_root", lambda: tmp_path)
    monkeypatch.setattr(
        runner,
        "_launch_managed_uploader",
        lambda *_args: launched.append(True),
    )

    with pytest.raises(RuntimeError, match="npcap open failed"):
        runner.run_with_overlay(config)
    assert launched == []
