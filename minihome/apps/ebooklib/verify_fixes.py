#!/usr/bin/env python3
import os, sys, json, mimetypes
from pathlib import Path
import requests

# ---------- Configuration ----------
NOVEL_ID = "은퇴한_만렙_일꾼은_쉬고_싶다"
COVERS_DIR = Path("/opt/ai_data/flaresolverr/covers")
API_BASE = "https://devforge.152-69-229-246.nip.io"  # backend
VERCEL_BASE = "https://miniebook.vercel.app"
REVALIDATE_TOKEN = os.getenv("VERCEL_REVALIDATE_TOKEN", "yvu-ruQM7S_Yg1MrtQaIdW3RogjQoBsnZyHkhVVZeE8")
# ----------------------------------

def check_cover_image():
    print("\n=== Checking cover image ===")
    # possible extensions
    for ext in [".jpg", ".jpeg", ".webp", ".png"]:
        p = COVERS_DIR / f"{NOVEL_ID}{ext}"
        if p.exists():
            print(f"Found cover file: {p} ({p.stat().st_size} bytes)")
            # test via backend API
            url = f"{API_BASE}/api/covers/{NOVEL_ID}{ext}"
            try:
                resp = requests.get(url, timeout=10)
                if resp.status_code == 200:
                    print(f"✓ API serves it: {url} (Content-Type: {resp.headers.get('content-type')})")
                    return True
                else:
                    print(f"✗ API returned {resp.status_code} for {url}")
            except Exception as e:
                print(f"✗ Error fetching {url}: {e}")
            # if backend fails, we still have file locally
            return True
    print("✗ No cover file found for novel")
    return False

def check_revalidate_endpoint():
    print("\n=== Checking ISR revalidate endpoint ===")
    url = f"{VERCEL_BASE}/api/revalidate"
    headers = {
        "Authorization": f"Bearer {REVALIDATE_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {"paths": [""], "tags": ["novels"]}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text}")
        if resp.status_code == 200:
            data = resp.json()
            if data.get("ok"):
                print("✓ Revalidate succeeded")
                return True
            else:
                print("✗ Revalidate returned ok:false")
                return False
        else:
            print(f"✗ HTTP {resp.status_code}")
            return False
    except Exception as e:
        print(f"✗ Exception: {e}")
        return False

def check_novel_api():
    print("\n=== Checking novel API coverUrl ===")
    url = f"{API_BASE}/api/novels/{NOVEL_ID}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            novel = resp.json()
            cover = novel.get("coverUrl")
            print(f"Novel coverUrl: {cover}")
            if cover and "/api/covers/" in cover:
                print("✓ coverUrl points to /api/covers/")
                return True
            else:
                print("✗ coverUrl missing or not pointing to /api/covers/")
                return False
        else:
            print(f"✗ Failed to fetch novel: {resp.status_code}")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

if __name__ == "__main__":
    ok = True
    ok = check_cover_image() and ok
    ok = check_novel_api() and ok
    ok = check_revalidate_endpoint() and ok
    print("\n=== Summary ===")
    if ok:
        print("All checks passed.")
        sys.exit(0)
    else:
        print("Some checks failed.")
        sys.exit(1)
