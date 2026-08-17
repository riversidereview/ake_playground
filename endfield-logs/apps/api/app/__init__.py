import sys
from pathlib import Path

_current_dir = Path(__file__).resolve().parent
for _candidate in [
    _current_dir.parents[1] / "packages" / "parser_core",
    _current_dir.parents[2] / "packages" / "parser_core",
    _current_dir.parents[3] / "packages" / "parser_core",
]:
    if _candidate.exists() and str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))
