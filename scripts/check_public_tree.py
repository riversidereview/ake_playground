from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_SUFFIXES = {
    ".7z", ".db", ".key", ".log", ".p12", ".pcap", ".pcapng", ".pem", ".pfx", ".rar", ".sqlite", ".sqlite3", ".zip"
}

FORBIDDEN_PATH_PARTS = {
    ".git", ".local", ".next", ".next-build", ".venv", "venv", "__pycache__", "debug", "dist", "build", "logs", "node_modules", "reports"
}

TEXT_SUFFIXES = {
    ".py", ".ts", ".tsx", ".js", ".mjs", ".cjs", ".json", ".md", ".toml", ".yaml", ".yml", ".html", ".css", ".txt", ".sh", ".bat", ".ps1"
}

CONTENT_RULES = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "private workspace path": re.compile(r"D:\\newproject|C:\\Users\\tangg", re.IGNORECASE),
    "production server path": re.compile(r"/srv/endfield", re.IGNORECASE),
    "legacy production IP": re.compile(r"(?<!\d)1\.14\.96\.10(?!\d)"),
    "tracked embedded key module": re.compile(r"\bembedded_keys\b"),
}

EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

ALLOWED_RESOURCE_FILES = {
    Path("endfield-logs/data/README.md"),
    Path("endfield-pcap/data/README.md"),
    Path("endfield-pcap/jsondata/README.md"),
    Path("endfield-pcap/proto/README.md"),
    Path("endfield-pcap/secrets/README.md"),
    Path("endfield-logs/apps/web/public/images/README.md"),
    Path("endfield-logs/apps/web/public/endaxis/README.md"),
}

RESOURCE_ROOTS = tuple(path.parent for path in ALLOWED_RESOURCE_FILES)

def main() -> int:
    t0 = time.time()
    issues: list[str] = []
    checked_count = 0

    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in FORBIDDEN_PATH_PARTS and not d.startswith('.')]
        current_dir = Path(dirpath)
        for filename in filenames:
            p = current_dir / filename
            relative = p.relative_to(ROOT)
            if any(part in FORBIDDEN_PATH_PARTS for part in relative.parts):
                continue

            checked_count += 1
            lower_name = filename.lower()
            lower_suffix = p.suffix.lower()

            if lower_suffix in FORBIDDEN_SUFFIXES:
                issues.append(f"forbidden file type: {relative}")
            if lower_name == ".env" or (lower_name.startswith(".env.") and lower_name != ".env.example"):
                issues.append(f"forbidden environment file: {relative}")
            for resource_root in RESOURCE_ROOTS:
                if relative.parent == resource_root and relative not in ALLOWED_RESOURCE_FILES:
                    issues.append(f"unexpected runtime resource: {relative}")

            if lower_suffix not in TEXT_SUFFIXES and lower_name not in {".env.example", ".gitignore", "dockerfile"}:
                continue
            if relative == Path("scripts/check_public_tree.py"):
                continue

            try:
                # Skip large files (> 200KB)
                if p.stat().st_size > 200_000:
                    continue
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            for label, pattern in CONTENT_RULES.items():
                if pattern.search(text):
                    issues.append(f"{label}: {relative}")

            for email in EMAIL_PATTERN.findall(text):
                if not email.lower().endswith("@example.com"):
                    issues.append(f"non-example email: {relative}")
                    break

    print(f"Scanned {checked_count} files in {time.time()-t0:.2f}s.")
    if issues:
        print("Public-tree audit failed:")
        for issue in sorted(set(issues)):
            print(f"- {issue}")
        return 1
    print("Public-tree audit passed.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
