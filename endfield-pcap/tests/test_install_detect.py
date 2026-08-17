from pathlib import Path

from endfield_pcap.game_path import is_valid_game_dir, normalize_game_dir_selection
from endfield_pcap import install_detect


def _touch_game_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "Endfield.exe").write_text("", encoding="utf-8")
    (path / "GameAssembly.dll").write_text("", encoding="utf-8")
    return path


def test_detect_game_dll_dir_finds_custom_nested_location_via_recursive_scan(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path
    game_dir = _touch_game_dir(root / "Apps" / "Whatever" / "Moved Anywhere" / "Endfield Build")

    monkeypatch.setattr(install_detect, "_registry_candidate_game_dirs", lambda: [])
    monkeypatch.setattr(install_detect, "_candidate_game_dirs_from_common_paths", lambda: [])
    monkeypatch.setattr(install_detect, "_iter_drive_roots", lambda: [root])

    assert install_detect.detect_game_dll_dir(refresh=True) == game_dir.resolve()


def test_detect_game_exe_path_prefers_valid_install_over_lonely_exe(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path
    broken_dir = root / "Games" / "Broken Copy"
    broken_dir.mkdir(parents=True, exist_ok=True)
    (broken_dir / "Endfield.exe").write_text("", encoding="utf-8")
    game_dir = _touch_game_dir(root / "Games" / "Playable Copy")

    monkeypatch.setattr(install_detect, "_registry_candidate_game_dirs", lambda: [])
    monkeypatch.setattr(install_detect, "_candidate_game_dirs_from_common_paths", lambda: [])
    monkeypatch.setattr(install_detect, "_iter_drive_roots", lambda: [root])

    assert install_detect.detect_game_exe_path(refresh=True) == (game_dir / "Endfield.exe").resolve()


def test_detect_game_dll_dir_keeps_common_path_fast_path(monkeypatch, tmp_path: Path) -> None:
    game_dir = _touch_game_dir(tmp_path / "Hypergryph Launcher" / "games" / "Endfield Game")

    monkeypatch.setattr(install_detect, "_registry_candidate_game_dirs", lambda: [])
    monkeypatch.setattr(install_detect, "_iter_drive_roots", lambda: [tmp_path])

    assert install_detect.detect_game_dll_dir(refresh=True) == game_dir.resolve()


def test_manual_game_path_validation_accepts_game_dir_or_exe(tmp_path: Path) -> None:
    game_dir = _touch_game_dir(tmp_path / "Endfield Game")

    assert is_valid_game_dir(game_dir)
    assert normalize_game_dir_selection(game_dir / "Endfield.exe") == game_dir.resolve()


def test_manual_game_path_selection_accepts_hypergryph_launcher_dir(tmp_path: Path) -> None:
    launcher_dir = tmp_path / "Hypergryph Launcher"
    game_dir = _touch_game_dir(launcher_dir / "games" / "Endfield Game")

    assert normalize_game_dir_selection(launcher_dir) == game_dir.resolve()
    assert normalize_game_dir_selection(launcher_dir / "games") == game_dir.resolve()
