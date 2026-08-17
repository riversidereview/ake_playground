from __future__ import annotations

import sys
from pathlib import Path


def _bootstrap_paths() -> None:
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    candidates = [
        base_dir / "src",
        base_dir.parent / "_internal" / "src",
        Path(__file__).resolve().parent / "_internal" / "src",
    ]
    for candidate in candidates:
        candidate_str = str(candidate)
        if candidate.exists() and candidate_str not in sys.path:
            sys.path.insert(0, candidate_str)


_bootstrap_paths()

from endfield_pcap.diagnostic import run_detector_app


if __name__ == "__main__":
    raise SystemExit(run_detector_app())
