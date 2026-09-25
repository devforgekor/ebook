#!/usr/bin/env python3
# Status: experimental
# Path: ebooklib/apps/backend/services/metadata_official.py
"""공식 플랫폼 메타데이터 — **사용자가 준 URL로만** 조회(문피아/조아라/네이버).

[WHY] 제목·작가·총화수·연재상태 같은 메타데이터는 추측(namu/검색)보다 **정본
플랫폼의 작품 페이지**가 정확하다. 임의 검색은 오매칭 위험이 있으므로, meta에
저장된 사용자 제공 URL(`meta_source_url`)이 있고 그 플랫폼이 지원될 때만 조회한다.

지원:
- 네이버 시리즈: JSON-LD(Book) → name/author/description/image
- 문피아: og 메타 + 본문 라벨(작가/연재/총화)
- 조아라: og 메타 + 본문 라벨(작가/연재/총화)
"""

from __future__ import annotations

import html as _html
import json
import logging
import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

PLATFORM_HOSTS = {
    "naver": ("series.naver.com", "novel.naver.com", "comic.naver.com"),
    "munpia": ("munpia.com",),
    "joara": ("joara.com",),
}


def detect_platform(url: str) -> Optional[str]:
    try:
        host = (urlparse(url or "").hostname or "").lower()
    except Exception:
        return None
    for platform, hosts in PLATFORM_HOSTS.items():
        if any(host == h or host.endswith("." + h) for h in hosts):
            return platform
    return None


def _strip_tags(fragment: str) -> str:
    return _html.unescape(re.sub(r"<[^>]+>", " ", fragment)).strip()


def _og(html_text: str, prop: str) -> str:
    m = re.search(
        rf'<meta[^>]+(?:property|name)=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)',
        html_text,
        re.I,
    )
    if not m:
        m = re.search(
            rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{re.escape(prop)}["\']',
            html_text,
            re.I,
        )
    return _strip_tags(m.group(1)) if m else ""


def _label_value(html_text: str, labels: tuple) -> str:
    """본문에서 '라벨' 뒤 값을 관대하게 추출(사이트별 마크업 차이 흡수).

    [WHY] 마크업이 제각각이라(div/span/th, 콜론 유무) 짧은 텍스트 슬롯을 관대하게
    캡처한다. 과도한 캡처를 막기 위해 값은 태그/줄바꿈을 넘지 않는다.
    """
    for label in labels:
        m = re.search(
            rf"{re.escape(label)}\s*</[^>]*>\s*<\s*(?:div|span|td|p|strong|em|dd)[^>]*>\s*"
            rf"(?:<\s*a[^>]*>)?\s*([^<\n]{{1,120}})",
            html_text,
            re.I,
        )
        if m:
            value = _strip_tags(m.group(1))
            if value and label not in value:
                return value
    return ""


def _total_chapters(html_text: str) -> Optional[int]:
    for pattern in (
        r"총\s*(\d{1,5})\s*화",
        r"(\d{1,5})\s*화\s*완결",
        r"총\s*(\d{1,5})\s*편",
        r"전체\s*(\d{1,5})\s*화",
    ):
        m = re.search(pattern, html_text)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                continue
    return None


def _status(html_text: str) -> str:
    if re.search(r"완결", html_text):
        return "완결"
    if re.search(r"연재\s*중|연재중", html_text):
        return "연재중"
    return "unknown"


def parse_platform(platform: str, html_text: str, url: str = "") -> dict:
    """플랫폼 HTML → 정규화 메타 dict(공통)."""
    out = {
        "title": "",
        "author": "",
        "description": "",
        "cover_url": None,
        "status": "unknown",
        "total_chapters": None,
        "publisher": platform,
        "source_url": url,
        "source": f"official:{platform}",
        "genre": [],
    }
    out["title"] = _og(html_text, "og:title") or _og(html_text, "title")
    out["description"] = _og(html_text, "og:description") or _og(html_text, "description")
    out["cover_url"] = _og(html_text, "og:image") or None

    # 네이버: JSON-LD Book이 가장 정확
    if platform == "naver":
        for m in re.finditer(
            r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
            html_text,
            re.S | re.I,
        ):
            try:
                data = json.loads(m.group(1))
            except (json.JSONDecodeError, TypeError):
                continue
            nodes = data if isinstance(data, list) else [data]
            for node in nodes:
                if not isinstance(node, dict) or node.get("@type") != "Book":
                    continue
                if node.get("name"):
                    out["title"] = str(node["name"]).strip()
                author = node.get("author")
                if isinstance(author, dict):
                    out["author"] = str(author.get("name") or "").strip()
                elif isinstance(author, list) and author:
                    first = author[0]
                    out["author"] = str(
                        first.get("name") if isinstance(first, dict) else first
                    ).strip()
                elif author:
                    out["author"] = str(author).strip()
                if node.get("description"):
                    out["description"] = str(node["description"]).strip()
                if node.get("image"):
                    out["cover_url"] = str(node["image"])
                break
            if out["author"]:
                break

    if not out["author"]:
        out["author"] = _label_value(
            html_text, ("작가", "글쓴이", "저자", "집필", "작품")
        )
    total = _total_chapters(html_text)
    if total:
        out["total_chapters"] = total
    out["status"] = _status(html_text)
    return out


def fetch(url: str, timeout: float = 15.0, fetcher=None) -> Optional[dict]:
    """사용자 제공 URL에서 메타데이터 조회(플랫폼 미지원/실패 시 None)."""
    platform = detect_platform(url)
    if not platform:
        return None
    if fetcher is None:
        try:
            import requests

            resp = requests.get(
                url, timeout=timeout, headers={"User-Agent": _USER_AGENT},
                allow_redirects=True,
            )
            resp.raise_for_status()
            html_text = resp.text
        except Exception as e:  # noqa: BLE001 — 실패는 미보강(추측 금지)
            logger.debug(f"공식 메타 조회 실패({platform}): {e}")
            return None
    else:
        html_text = fetcher(url)
        if not html_text:
            return None
    return parse_platform(platform, html_text, url)


def get_metadata_from_url(url: str) -> Optional[dict]:
    """공개 API — 지원 플랫폼 URL이면 메타 dict, 아니면 None."""
    return fetch(url)


def cover_save_path(novel_id: str) -> Path:
    return Path(f"/opt/ai_data/flaresolverr/covers/{novel_id}.webp")


def download_cover(cover_url: str, save_path: Path, timeout: float = 20.0) -> bool:
    """공식 페이지 표지 이미지를 로컬로 저장(검증 후).

    [WHY] 공식 플랫폼 표지가 가장 정확하므로 로컬 캐시로 내려 안정적으로 서빙한다.
    아이콘/로고 등 비표지 오매칭을 막기 위해 최소 크기/시그니처를 검증한다.
    """
    if not cover_url:
        return False
    try:
        import requests

        resp = requests.get(
            cover_url, timeout=timeout, headers={"User-Agent": _USER_AGENT},
            allow_redirects=True,
        )
        resp.raise_for_status()
        binary = resp.content
    except Exception as e:  # noqa: BLE001
        logger.debug(f"표지 다운로드 실패: {e}")
        return False
    if not binary or len(binary) < 5120:
        return False
    if not (
        binary.startswith(b"\xff\xd8\xff")
        or binary.startswith(b"\x89PNG")
        or (binary.startswith(b"RIFF") and b"WEBP" in binary[:12])
    ):
        return False
    try:
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_bytes(binary)
        return True
    except OSError:
        return False
