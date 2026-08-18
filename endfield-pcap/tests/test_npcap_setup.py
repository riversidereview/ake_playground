from __future__ import annotations

from pathlib import Path
import pytest

from endfield_pcap.npcap import find_wpcap_dll, has_npcap
from endfield_pcap.npcap_setup import find_bundled_npcap_installer, prompt_npcap_install_interactive


def test_find_bundled_npcap_installer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 1. When no installer is present
    monkeypatch.setattr("endfield_pcap.npcap_setup.app_root", lambda: tmp_path)
    monkeypatch.setattr("endfield_pcap.npcap_setup.bundle_root", lambda: tmp_path)
    assert find_bundled_npcap_installer() is None

    # 2. When npcap-1.88.exe is present in app_root
    installer_file = tmp_path / "npcap-1.88.exe"
    installer_file.write_bytes(b"dummy installer binary")
    found = find_bundled_npcap_installer()
    assert found is not None
    assert found.name == "npcap-1.88.exe"


def test_prompt_npcap_install_interactive_when_already_has_npcap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("endfield_pcap.npcap_setup.has_npcap", lambda: True)
    assert prompt_npcap_install_interactive() is True


def test_find_wpcap_dll_candidates() -> None:
    dll_path = find_wpcap_dll()
    assert dll_path is None or isinstance(dll_path, str)


def test_null_capture_manager_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    from endfield_pcap.npcap import CaptureManager, NullCaptureManager

    monkeypatch.setattr("endfield_pcap.npcap.has_npcap", lambda: False)
    mgr = CaptureManager.create("auto", lambda p: None)
    assert isinstance(mgr, NullCaptureManager)
    mgr.start()
    mgr.restore_default_filters()
    assert mgr.device_snapshot() == []
    assert mgr.stats_snapshot() == {"ps_recv": 0, "ps_drop": 0, "ps_ifdrop": 0}
    mgr.stop()


def test_prompt_npcap_install_user_accepts_returns_false(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    installer = tmp_path / "npcap-1.88.exe"
    installer.write_bytes(b"dummy")
    monkeypatch.setattr("endfield_pcap.npcap_setup.has_npcap", lambda: False)
    monkeypatch.setattr("endfield_pcap.npcap_setup.find_bundled_npcap_installer", lambda: installer)
    monkeypatch.setattr("endfield_pcap.npcap_setup.launch_npcap_installer", lambda path: True)
    monkeypatch.setattr("tkinter.messagebox.askyesno", lambda title, msg, parent=None: True)
    monkeypatch.setattr("tkinter.messagebox.showinfo", lambda title, msg, parent=None: None)

    # When user agrees to install, installer launches and client exits (returns False)
    assert prompt_npcap_install_interactive() is False


def test_prompt_npcap_install_user_declines_returns_true(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    installer = tmp_path / "npcap-1.88.exe"
    installer.write_bytes(b"dummy")
    monkeypatch.setattr("endfield_pcap.npcap_setup.has_npcap", lambda: False)
    monkeypatch.setattr("endfield_pcap.npcap_setup.find_bundled_npcap_installer", lambda: installer)
    monkeypatch.setattr("tkinter.messagebox.askyesno", lambda title, msg, parent=None: False)
    monkeypatch.setattr("tkinter.messagebox.showinfo", lambda title, msg, parent=None: None)

    # When user declines, offline mode is enabled and client proceeds (returns True)
    assert prompt_npcap_install_interactive() is True

