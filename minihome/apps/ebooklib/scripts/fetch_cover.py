#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
표지 이미지 수집 로직 — SSOT(소스 사이트) 우선.

소스 사이트가 표지의 SSOT(Single Source of Truth)다.
  1. toki31  : Playwright(유료 프록시)로 /novel/{main_wr_id} 로드
               → .nd-thumb img[alt=제목] 표지 추출
  2. bookto31/ondobook : FlareSolverr로 bbs/board.php 로드
               → imgspeedtoki CDN / og:image / thumb 표지 추출
  3. namu.wiki: SSOT 보조(백업)
  (웹 검색 폴백은 신뢰도가 낮아 사용하지 않는다 — 엉뚱한 이미지 방지)

사용법:
  python3 scripts/fetch_cover.py <novel_id>
  python3 scripts/fetch_cover.py <novel_id> --force
  python3 scripts/fetch_cover.py --all
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "apps" / "backend"
sys.path.insert(0, str(BACKEND))

from lib.paths import LIBRARY_ROOT, find_novel_dir

COVERS_DIR = LIBRARY_ROOT / "covers"

REQ_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}

MAGIC_OK = (b"\xff\xd8\xff", b"\x89PNG", b"RIFF")
MIN_SIZE = 5000


# ---------------------------------------------------------------
# 검증 / 저장
# ---------------------------------------------------------------
def _ext_for(binary: bytes, url: str = "") -> str:
    if binary.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if binary.startswith(b"\x89PNG"):
        return ".png"
    if binary.startswith(b"RIFF") and b"WEBP" in binary[:12]:
        return ".webp"
    low = url.lower().split("?")[0]
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        if low.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    return ".bin"


def _valid_image(binary: Optional[bytes]) -> bool:
    if not binary or len(binary) < MIN_SIZE:
        return False
    return any(binary.startswith(m) for m in MAGIC_OK)


def _download(url: str, timeout: int = 20) -> Optional[bytes]:
    import requests
    try:
        r = requests.get(url, headers=REQ_HEADERS, timeout=timeout, stream=True)
        if r.status_code == 200:
            return r.content
    except Exception:
        pass
    return None


def save_cover(novel_id: str, binary: bytes, url: str = "") -> Optional[Path]:
    if not _valid_image(binary):
        return None
    ext = _ext_for(binary, url)
    if ext == ".bin":
        return None
    for old in COVERS_DIR.glob(f"{novel_id}.*"):
        if old.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
            old.unlink()
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    path = COVERS_DIR / f"{novel_id}{ext}"
    path.write_bytes(binary)
    return path


def has_cover(novel_id: str) -> bool:
    return any(
        (COVERS_DIR / f"{novel_id}{ext}").exists()
        for ext in (".jpg", ".jpeg", ".png", ".webp")
    )


# ---------------------------------------------------------------
# 1. toki31 — Playwright(유료 프록시) + .nd-thumb img[alt]
# ---------------------------------------------------------------
def _toki31_cover(meta: dict) -> Optional[bytes]:
    import asyncio
    main_wr_id = meta.get("main_wr_id")
    title = meta.get("title", "")
    if not main_wr_id:
        return None

    from lib.toki31_playwright import _load_proxy_env, _toki_base

    env = _load_proxy_env()
    proxy_user = env.get("DATAIMPULSE_USER", "") or env.get("MASKPROXY_USER", "")
    proxy_pass = env.get("DATAIMPULSE_PASS", "") or env.get("MASKPROXY_PASS", "")
    proxy_host = env.get("DATAIMPULSE_HOST", "") or env.get("MASKPROXY_HOST", "")
    proxy_port = env.get("DATAIMPULSE_PORT", "") or env.get("MASKPROXY_PORT", "")
    if "dataimpulse" in proxy_host and "__cr." not in proxy_user:
        proxy_user = proxy_user + "__cr.kr"
    if not proxy_user or not proxy_pass:
        return None
    proxy_url = "http://{}:{}".format(proxy_host, proxy_port)
    UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )

    async def _run() -> Optional[bytes]:
        from playwright.async_api import async_playwright
        async with async_playwright() as p:
            b = await p.chromium.launch(
                headless=True,
                proxy={"server": proxy_url, "username": proxy_user, "password": proxy_pass},
            )
            c = await b.new_context(user_agent=UA, locale="ko-KR")
            pg = await c.new_page()
            await pg.goto(
                f"{_toki_base()}/novel/{main_wr_id}",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await pg.wait_for_timeout(2500)
            html = await pg.content()
            await b.close()

            # .nd-thumb img (alt=제목) → 표지 SSOT
            m = re.search(
                r'<div class="nd-thumb">\s*<img[^>]+src="([^"]+)"[^>]+alt="([^"]*)"',
                html,
            )
            if not m:
                m = re.search(r'<img[^>]+src="([^"]+)"[^>]+alt="([^"]*)"[^>]*class="[^"]*nd-thumb[^"]*"', html)
            if m:
                img_url, alt = m.group(1), m.group(2)
                # alt가 제목과 전혀 무관하면 신뢰하지 않음
                if title and alt and title not in alt and alt not in title:
                    return None
                return _download(img_url)
            return None

    try:
        return asyncio.run(_run())
    except Exception:
        return None


# ---------------------------------------------------------------
# 2. bookto31/ondobook — FlareSolverr + CDN/og:image/thumb
# ---------------------------------------------------------------
def _bookto31_cover(meta: dict) -> Optional[bytes]:
    main_wr_id = meta.get("main_wr_id")
    if not main_wr_id:
        return None
    base = {
        "bookto31": "https://23.ondobook.net",
        "newto31": "https://newto31.com",
    }.get(meta.get("source", ""))
    if not base:
        return None
    url = f"{base}/bbs/board.php?bo_table=novel&wr_id={main_wr_id}"
    try:
        from lib.flaresolverr_client import FlareSolverrSession
        fs = FlareSolverrSession(rate_limit=False)
        html = fs.fetch(url, max_attempts=1, timeout_ms=30000)
        if not html:
            return None
        # 1순위: imgspeedtoki CDN cover (GNUBOARD 업로드 썸네일)
        cover_cdn = re.search(
            r"https?://[^\"'\s]*imgspeedtoki[^\"'\s]*/cover/[^\"'\s]+", html
        )
        if cover_cdn:
            img = _download(cover_cdn.group(0))
            if _valid_image(img):
                return img
        # 2순위: og:image
        ogi = re.search(r'<meta[^>]+(?:property|name)="og:image"[^>]+content="([^"]+)"', html)
        if ogi:
            u = ogi.group(1).strip()
            if u.startswith("//"):
                u = "https:" + u
            img = _download(u)
            if _valid_image(img) and "default" not in u.lower():
                return img
        # 3순위: 게시판 본문 첫 이미지 (view-content)
        first_img = re.search(r'<img[^>]+src="(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', html)
        if first_img:
            img = _download(first_img.group(1))
            if _valid_image(img):
                return img
    except Exception:
        pass
    return None


# ---------------------------------------------------------------
# 3. namu.wiki — SSOT 보조
# ---------------------------------------------------------------
def _namu_cover(title: str) -> Optional[bytes]:
    try:
        from services.metadata_namu import search_novel, search_novel_fallback
        meta = search_novel(title) or search_novel_fallback(title)
        if meta and meta.cover_url:
            return _download(meta.cover_url)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------
# 메인
# ---------------------------------------------------------------
def fetch_cover(novel_id: str, meta: Optional[dict] = None, force: bool = False) -> Optional[Path]:
    if not force and has_cover(novel_id):
        print(f"[fetch_cover] {novel_id}: 표지 이미 존재, 스킵 (--force로 재수집)")
        return None

    if meta is None:
        found = find_novel_dir(novel_id)
        meta = json.loads((found / "meta.json").read_text(encoding="utf-8")) if found and (found / "meta.json").exists() else {}

    title = meta.get("title") or novel_id.replace("_", " ")
    source = meta.get("source", "")
    print(f"[fetch_cover] {novel_id} ({title}) [source={source}]")

    if source == "toki31":
        chain = [
            ("toki31 소스", lambda: _toki31_cover(meta)),
            ("namu_wiki", lambda: _namu_cover(title)),
        ]
    else:
        chain = [
            ("bookto31 소스", lambda: _bookto31_cover(meta)),
            ("namu_wiki", lambda: _namu_cover(title)),
        ]

    for name, fn in chain:
        try:
            binary = fn()
        except Exception as e:
            print(f"  - {name}: error {e}")
            binary = None
        if _valid_image(binary):
            path = save_cover(novel_id, binary)
            if path:
                print(f"  ✓ {name} → {path} ({len(binary)} bytes)")
                return path
            print(f"  - {name}: 이미지이나 저장 실패")
        else:
            print(f"  - {name}: 표지 없음")

    print("  ✗ 표지 획득 실패")
    return None


def all_novels() -> list[tuple[str, dict]]:
    results = []
    for root in LIBRARY_ROOT.iterdir():
        if not root.is_dir() or root.name in (
            "covers", "epub", "backups", "ebook_watcher", "webtoon_images", "adult"
        ):
            continue
        for d in root.iterdir():
            if d.is_dir():
                mf = d / "meta.json"
                if mf.exists():
                    meta = json.loads(mf.read_text(encoding="utf-8"))
                    results.append((meta.get("id", d.name), meta))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="소설 표지 이미지 수집 (SSOT 우선)")
    parser.add_argument("novel_id", nargs="?", help="novel_id (미지정 시 --all)")
    parser.add_argument("--all", action="store_true", help="모든 소설 처리")
    parser.add_argument("--force", action="store_true", help="기존 표지 있어도 재수집")
    args = parser.parse_args()

    if args.all:
        novels = all_novels()
        ok = 0
        for nid, meta in novels:
            if fetch_cover(nid, meta, force=args.force):
                ok += 1
        print(f"\n완료: {ok}/{len(novels)}")
        return 0

    if not args.novel_id:
        parser.print_help()
        return 1

    fetch_cover(args.novel_id, force=args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())