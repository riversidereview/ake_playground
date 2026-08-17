from __future__ import annotations

import logging
import os
from pathlib import Path
import sys


def configure_logging(level: str) -> None:
    handlers: list[logging.Handler] = []
    if getattr(sys, "stderr", None) is not None:
        handlers.append(logging.StreamHandler())
    else:
        appdata_root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".endfield-pcap")
        log_path = appdata_root / "EndfieldPCAP" / "logs" / "client.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )

