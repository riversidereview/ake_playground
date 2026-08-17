from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon


def asset_path(*parts: str) -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "app" / "assets" / Path(*parts)
    return Path(__file__).resolve().parents[1] / "assets" / Path(*parts)


def app_icon() -> QIcon:
    return QIcon(str(asset_path("logo.ico")))
