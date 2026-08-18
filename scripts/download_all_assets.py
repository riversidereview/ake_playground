import os
import sys
import ssl
import json
import urllib.request
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

BASE_DIR = Path(__file__).resolve().parent.parent / "endfield-logs/apps/web/public/images"
MANIFEST_FILE = Path(__file__).resolve().parent.parent / "endfield-logs/data/required_assets_manifest.json"


def build_opener(proxy: str | None = None):
    handlers = [urllib.request.HTTPSHandler(context=ctx)]
    if proxy:
        handlers.append(urllib.request.ProxyHandler({'http': proxy, 'https': proxy}))
    return urllib.request.build_opener(*handlers)


def download_one(rel_path: str, opener, force: bool = False):
    target_path = BASE_DIR / rel_path
    if not force and target_path.exists() and target_path.stat().st_size > 50:
        return rel_path, True, "cached"

    target_path.parent.mkdir(parents=True, exist_ok=True)
    filename = Path(rel_path).name

    # Ordered candidate sources
    sources = [
        f"https://zmdlogs.com/images/{rel_path}",
        f"https://endfielddex.com/images/{rel_path}",
        f"https://endfielddex.com/images/{filename}",
    ]

    # Special handling for character round/avatar variants
    if "charremoteicon" in rel_path:
        round_name = filename.replace("icon_", "icon_round_")
        sources.insert(0, f"https://zmdlogs.com/images/character/charremoteicon/{round_name}")
        sources.insert(1, f"https://endfielddex.com/images/{round_name}")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    last_err = None
    for url in sources:
        try:
            req = urllib.request.Request(url, headers=headers)
            with opener.open(req, timeout=8) as resp:
                if resp.status == 200:
                    data = resp.read()
                    if len(data) > 30:  # Valid image payload
                        target_path.write_bytes(data)
                        return rel_path, True, f"ok ({len(data)} B)"
        except Exception as e:
            last_err = e
            continue

    return rel_path, False, f"failed: {last_err}"


def main():
    parser = argparse.ArgumentParser(description="Download all required asset images for Endfield Battle Logs.")
    parser.add_argument("--proxy", type=str, default=None, help="HTTP/HTTPS proxy e.g. http://127.0.0.1:11223")
    parser.add_argument("--workers", type=int, default=16, help="Number of concurrent download threads")
    parser.add_argument("--force", action="store_true", help="Force re-download existing files")
    args = parser.parse_args()

    if not MANIFEST_FILE.exists():
        print(f"Error: Manifest file not found at {MANIFEST_FILE}")
        sys.exit(1)

    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        paths = json.load(f)

    opener = build_opener(args.proxy)
    print(f"Starting download of {len(paths)} assets into {BASE_DIR} (workers={args.workers})...")

    success = 0
    failed = 0
    cached = 0
    failed_items = []

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(download_one, p, opener, args.force): p for p in paths}
        for idx, future in enumerate(as_completed(futures), start=1):
            p, ok, msg = future.result()
            if ok:
                if msg == "cached":
                    cached += 1
                else:
                    success += 1
            else:
                failed += 1
                failed_items.append((p, msg))

            if idx % 50 == 0 or idx == len(paths):
                print(f"Progress: [{idx}/{len(paths)}] - {cached} cached, {success} downloaded, {failed} pending", flush=True)

    print("\nDownload Summary:")
    print(f"  - Cached/Existing: {cached}")
    print(f"  - Newly Downloaded: {success}")
    print(f"  - Total Available: {cached + success} / {len(paths)}")
    print(f"  - Failed/Missing: {failed}")

    if failed_items:
        print("\nMissing Assets Sample:")
        for p, err in failed_items[:10]:
            print(f"    {p} -> {err}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
