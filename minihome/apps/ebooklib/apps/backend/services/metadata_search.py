#!/usr/bin/env python3
# Status: experimental
# Path: ebooklib/apps/backend/services/metadata_search.py
"""제목으로 공식 플랫폼 작품 URL/메타 검색.

[WHY] 사용자가 URL을 주지 않아도 정본에 가깝게 채우기 위해 제목으로 검색한다.
다만 **오매칭 금지**가 최우선: 정규화 제목이 실제로 일치(또는 강하게 포함)할 때만 채택한다.
플랫폼별 접근성 차이는 실측 결과를 반영한다:
- 네이버 시리즈: 검색/상세 모두 HTTP 접근 가능(1차 소스)
- 카카오페이지/리디북스/문피아/조아라: 비로그인·클라이언트 렌더링/차단이 잦아
  **접근 가능할 때만** 시도하고, 실패하면 조용히 스킵(추측으로 채우지 않음)
"""

from __future__ import annotations

import logging
import re
from typing import Optional
from urllib.parse import quote

logger = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
_HEADERS = {"User-Agent": _UA, "Accept-Language": "ko-KR,ko;q=0.9"}

NAVER_SEARCH = "https://series.naver.com/search/search.series?t=novel&q={q}"
NAVER_DETAIL = "https://series.naver.com/novel/detail.series?productNo={pid}"

# 플랫폼 키 → (검색 URL 템플릿, 작품 링크 정규식)
_SEARCH_ENDPOINTS = {
    "naver": (NAVER_SEARCH, r'href="(/novel/detail\.series\?productNo=\d+)"'),
    "kakao": ("https://page.kakao.com/search/result?keyword={q}", r'/content/(\d{5,})'),
    "ridi": ("https://ridibooks.com/search?q={q}", r'href="(/books/\d+[^"]*)"'),
    "munpia": ("https://novel.munpia.com/search/list?searchKeyword={q}", r'href="(/[0-9]{4,})"'),
    "joara": ("https://www.joara.com/search/search_list.html?search_text={q}", r'href="(https?://www\.joara\.com/book/\d+[^"]*)"'),
}

# 플랫폼별 제목 신뢰도(실측 접근성 기준). 앞일수록 우선.
PLATFORM_PRIORITY = ("naver", "kakao", "ridi", "munpia", "joara")


def _norm(s: str) -> str:
    from lib.text_clean import clean_title

    return re.sub(r"[\s\-_·:：|]", "", clean_title(s or "")).lower()


def title_matches(query: str, candidate: str) -> bool:
    """검색어와 후보 제목의 일치 판정(오매칭 방지).

    - 정규화 후 완전 일치, 또는 후보가 검색어를 포함(길이 차 ≤ 6)할 때만 True.
    """
    q, c = _norm(query), _norm(candidate)
    if not q or not c:
        return False
    if q == c:
        return True
    return (q in c or c in q) and abs(len(q) - len(c)) <= 6


def _fetch(url: str, timeout: float = 12.0) -> Optional[str]:
    try:
        import requests

        r = requests.get(url, headers=_HEADERS, timeout=timeout, verify=False)
        if r.status_code != 200:
            return None
        return r.text
    except Exception as e:  # noqa: BLE001
        logger.debug(f"검색 fetch 실패({url[:50]}): {e}")
        return None


def search_naver(title: str, timeout: float = 12.0) -> Optional[dict]:
    """네이버 시리즈 검색 → 상세 메타(작가·총화수·상태·표지)."""
    html = _fetch(NAVER_SEARCH.format(q=quote(title)), timeout)
    if not html:
        return None
    links = re.findall(r'href="(/novel/detail\.series\?productNo=\d+)"', html)
    if not links:
        return None
    # 검색 결과 제목 후보(있으면) — 오매칭 방지
    og_titles = re.findall(r'<img[^>]+alt="([^"]{1,60})"', html)
    picked = links[0]
    for link, alt in zip(links, og_titles + [""] * len(links)):
        if not alt or title_matches(title, alt):
            picked = link
            break
    detail = _fetch("https://series.naver.com" + picked, timeout)
    if not detail:
        return None
    from services.metadata_official import parse_platform

    meta = parse_platform("naver", detail, "https://series.naver.com" + picked)
    if not meta.get("title") or not title_matches(title, meta["title"]):
        return None
    return meta


MUNPIA_API = "https://www.munpia.com/api/v1/main/search"


def search_munpia(title: str, timeout: float = 12.0) -> Optional[dict]:
    """문피아 검색 API(비로그인, JSON) → 정규화 메타.

    [WHY] 문피아는 SPA지만 검색 API가 열려 있어 JSON으로 작가/총화수(entryCount)/
    완결여부/표지/줄거리를 안정적으로 얻는다. 제목 일치 검증으로 오매칭을 막는다.
    """
    try:
        import requests

        r = requests.get(
            MUNPIA_API,
            params={
                "query": title, "tab": "NOVEL", "sort": "SIMILARITY",
                "novelType": "ALL", "finishedOnly": "false", "adultMode": "false",
                "page": 0, "size": 10,
            },
            headers={**_HEADERS, "Accept": "application/json", "Referer": "https://www.munpia.com/"},
            timeout=timeout, verify=False,
        )
        if r.status_code != 200:
            return None
        items = (r.json().get("result") or {}).get("searchNovelTabDtos") or []
    except Exception as e:  # noqa: BLE001
        logger.debug(f"문피아 검색 실패: {e}")
        return None
    for it in items:
        if not title_matches(title, it.get("title", "")):
            continue
        novel_id = it.get("novelId")
        return {
            "title": it.get("title", ""),
            "author": it.get("author", ""),
            "description": (it.get("story") or "")[:500],
            "cover_url": it.get("coverUrl"),
            "status": "완결" if it.get("finished") else "연재중",
            "total_chapters": it.get("entryCount"),
            "publisher": "문피아",
            "source_url": f"https://www.munpia.com/novel/detail/{novel_id}",
            "source": "official:munpia",
            "genre": [g for g in (it.get("mainGenre"), it.get("subGenre")) if g],
        }
    return None


def find_official(title: str) -> Optional[dict]:
    """제목으로 공식 메타 검색 — 네이버 시리즈 → 문피아 → (접근 가능 시) 기타.

    Returns: metadata_official.parse_platform 형태의 dict 또는 None.
    """
    # 1차: 네이버 시리즈(HTTP 접근 가능, 파싱 검증됨)
    meta = search_naver(title)
    if meta:
        return meta
    # 2차: 문피아(검색 API JSON — 작가·총화수·완결 정확)
    meta = search_munpia(title)
    if meta:
        return meta
    # 3차: 나머지는 클라이언트 렌더링/차단이 잦아 시도만 하고 스킵
    for platform in ("kakao", "ridi", "joara"):
        tmpl, _ = _SEARCH_ENDPOINTS[platform]
        if not _fetch(tmpl.format(q=quote(title))):
            logger.debug(f"{platform} 검색 접근 불가 — 스킵")
            continue
        logger.debug(f"{platform} 검색 응답은 있으나 파서 미구현 — 스킵")
    return None
