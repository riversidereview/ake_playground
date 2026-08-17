import os
import ssl
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

# Setup proxy & SSL
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

proxy_handler = urllib.request.ProxyHandler({'http': 'http://127.0.0.1:11223', 'https': 'http://127.0.0.1:11223'})
opener = urllib.request.build_opener(proxy_handler, urllib.request.HTTPSHandler(context=ctx))

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../endfield-logs/apps/web/public/images"))
MANIFEST_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "../endfield-logs/data/required_assets_manifest.json"))

def download_one(rel_path):
    target_path = os.path.join(BASE_DIR, rel_path)
    if os.path.exists(target_path) and os.path.getsize(target_path) > 0:
        return rel_path, True, "already exists"
    
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    
    # Candidate URL sources
    filename = os.path.basename(rel_path)
    sources = [
        f"https://endfielddex.com/images/{filename}",
        f"https://endfielddex.com/images/{rel_path}",
    ]
    
    # Specific mappings for character round icons
    if "charremoteicon" in rel_path:
        round_name = filename.replace("icon_", "icon_round_")
        sources.insert(0, f"https://endfielddex.com/images/{round_name}")
        sources.insert(1, f"https://endfielddex.com/images/{filename}")

    for url in sources:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            with opener.open(req, timeout=8) as resp:
                if resp.status == 200:
                    data = resp.read()
                    if len(data) > 100:
                        with open(target_path, "wb") as out_f:
                            out_f.write(data)
                        return rel_path, True, f"ok ({len(data)} bytes)"
        except Exception:
            continue
            
    return rel_path, False, "not found on mirrors"

def main():
    if not os.path.exists(MANIFEST_FILE):
        print(f"Manifest file not found: {MANIFEST_FILE}")
        return
        
    with open(MANIFEST_FILE, "r", encoding="utf-8") as f:
        paths = json.load(f)
        
    print(f"Starting download for {len(paths)} assets into {BASE_DIR}...")
    success = 0
    failed = 0
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(download_one, p): p for p in paths}
        for future in as_completed(futures):
            p, ok, msg = future.result()
            if ok:
                success += 1
            else:
                failed += 1
            if (success + failed) % 50 == 0 or (success + failed) == len(paths):
                print(f"Progress: {success + failed}/{len(paths)} ({success} downloaded/cached, {failed} pending)")

    print(f"\nDownload completed: {success} successful, {failed} pending.")

if __name__ == "__main__":
    main()
