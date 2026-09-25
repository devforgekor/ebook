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
from typing import Optional, Sequence
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


# 파생작(스핀오프/팬픽/시즌/리메이크 등) 판별 — 플랫폼 태그 또는 부제 토큰.
# [WHY] '화산귀환: 매화당립'(팬픽·패러디)처럼 원작과 다른 작품이 제목 일치로
# 오매칭되는 것을 막는다. 부제 구분자·파생 키워드가 있으면 원작으로 보지 않는다.
_DERIVATIVE_TOKENS = (
    "스핀오프", "외전", "시즌", "리메이크", "리부트", "팬픽", "팬픽션", "패러디",
    "2차창작", "二次", "after", "if", "au", "리턴즈", "returns",
)
_DERIVATIVE_GENRES = ("팬픽", "패러디", "2차창작", "fanfic", "crossover")
_SUBTITLE_SEP = re.compile(r"[:：]|(?:\s[-–—]\s)|[\[(]|\s[|｜]\s")


def is_derivative(title: str, genre: Optional[Sequence[str]] = None, sub_genre: str = "") -> bool:
    """파생작(스핀오프/팬픽/시즌 등) 여부 — 원작 매칭에서 제외하기 위함.

    - 플랫폼 장르/서브장르에 팬픽·패러디 표기가 있으면 True
    - 부제 구분자(:/-/[/()/|) 뒤 토큰에 시즌·외전·팬픽 등이 있으면 True
    """
    genres = " ".join([*(genre or []), sub_genre or ""]).lower()
    if any(g in genres for g in _DERIVATIVE_GENRES):
        return True
    from lib.text_clean import clean_title

    # clean_title이 [독점]·[완결] 등 마케팅 꼬리표를 제거하므로, 그 결과로 판정한다.
    text = clean_title(title or "").lower()
    if any(tok in text for tok in _DERIVATIVE_TOKENS):
        return True
    return bool(_SUBTITLE_SEP.search(text))


def title_matches(query: str, candidate: str) -> bool:
    """검색어와 후보 제목의 일치 판정(오매칭 방지).

    - 정규화 후 완전 일치 → True
    - 후보가 파생작(부제/키워드)이면 → **정확 일치가 아닌 한** False
    - 그 외 부분 포함은 길이 차 ≤ 6일 때만 True
    """
    q, c = _norm(query), _norm(candidate)
    if not q or not c:
        return False
    if q == c:
        return True
    if is_derivative(candidate):
        return False
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
        if is_derivative(it.get("title", ""), [it.get("mainGenre"), it.get("subGenre")]):
            logger.debug(f"파생작 제외(munpia): {it.get('title')} / {it.get('mainGenre')}")
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


KAKAO_SEARCH_API = "https://bff-page.kakao.com/api/gateway/api/v2/search/series"
KAKAO_PRODUCT_API = "https://bff-page.kakao.com/api/gateway/api/v2/content/product/list"

# 카카오 state 코드(일부) → 상태. 미상은 unknown(추측 금지).
_KAKAO_STATE = {"ST61": "연재중", "ST62": "완결", "ST01": "연재중"}


def _kakao_get(url: str, params: dict, timeout: float = 12.0):
    """카카오 BFF API 호출 — Cloudflare/WAF 때문에 일반 requests는 403.

    [WHY] 실측: requests는 403. 브라우저(Playwright) 컨텍스트로만 접근 가능하므로
    필요 시 브라우저로 폴백한다(콜드 1회 부담, 메타 갱신은 드묾).
    """
    try:
        import requests

        r = requests.get(
            url, params=params,
            headers={**_HEADERS, "Accept": "application/json", "Referer": "https://page.kakao.com/"},
            timeout=timeout, verify=False,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:  # noqa: BLE001
        pass
    return _kakao_get_via_browser(url, params, timeout)


def _kakao_get_via_browser(url: str, params: dict, timeout: float = 12.0):
    """Playwright로 API 호출(쿼리 문자열 직접 이동 후 JSON 파싱)."""
    try:
        import asyncio
        from urllib.parse import urlencode

        from playwright.async_api import async_playwright

        full = f"{url}?{urlencode(params)}"
        ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )

        async def _run():
            async with async_playwright() as p:
                b = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
                ctx = await b.new_context(user_agent=ua, locale="ko-KR")
                pg = await ctx.new_page()
                # 카카오 도메인 컨텍스트(쿠키/WAF 통과) 확보 후 API 이동
                await pg.goto("https://page.kakao.com/", wait_until="domcontentloaded", timeout=40000)
                resp = await pg.goto(full, wait_until="domcontentloaded", timeout=40000)
                data = None
                try:
                    data = await resp.json()
                except Exception:
                    body = await pg.inner_text("pre") if await pg.query_selector("pre") else ""
                    import json as _json

                    try:
                        data = _json.loads(body)
                    except Exception:
                        data = None
                await b.close()
                return data

        return asyncio.run(_run())
    except Exception as e:  # noqa: BLE001
        logger.debug(f"카카오 브라우저 API 실패: {e}")
        return None


def search_kakao(title: str, timeout: float = 15.0, want_media: Optional[str] = None) -> Optional[dict]:
    """카카오페이지 검색 → 정규화 메타(작가/총화수/상태/표지)."""
    data = _kakao_get(
        KAKAO_SEARCH_API, {"keyword": title, "category": "all", "sort": "ACCURACY", "page": 0}, timeout
    )
    items = ((data or {}).get("result") or {}).get("list") or []
    matches = [
        it for it in items
        if it.get("type") == "SERIES" and title_matches(title, it.get("title", ""))
    ]
    # [WHY] 같은 제목이 웹툰/웹소설로 공존한다. 미디어 타입 힌트가 'novel'이면
    # 카테고리가 웹소설인 항목을 우선한다(총화수 단위가 달라 오염 방지).
    if want_media == "novel":
        matches.sort(key=lambda it: 0 if (it.get("category") == "웹소설") else 1)
    for it in matches:
        if is_derivative(it.get("title", ""), [it.get("category"), it.get("sub_category")]):
            logger.debug(f"파생작 제외(kakao): {it.get('title')} / {it.get('sub_category')}")
            continue
        sid = it.get("series_id")
        total = None
        prod = _kakao_get(KAKAO_PRODUCT_API, {"series_id": sid, "page": 0, "size": 1}, timeout)
        if prod:
            total = ((prod.get("result") or {}).get("total_count"))
        raw_title = it.get("title", "")
        status = _KAKAO_STATE.get(it.get("state"), "unknown")
        if "완결" in raw_title:
            status = "완결"
        return {
            "title": raw_title,
            "author": (it.get("authors") or "").strip(),
            "description": it.get("description") or "",
            "cover_url": (f"https://dn-img-page.kakao.com/download/resource?kid={it['thumbnail']}"
                          if it.get("thumbnail") else None),
            "status": status,
            "total_chapters": total,
            "publisher": "카카오페이지",
            "source_url": f"https://page.kakao.com/content/{sid}",
            "source": "official:kakao",
            "genre": [g for g in (it.get("category"), it.get("sub_category")) if g],
        }
    return None


def _authors_conflict(a: str, b: str) -> bool:
    """두 작가 표기가 서로 다른 사람인지(정규화 후 완전 불일치) 판정.

    다중 작가(콤마)는 구성원 집합이 겹치면 같은 작품으로 본다.
    """
    from lib.text_clean import clean_author

    def parts(x: str) -> set:
        return {p.strip() for p in re.split(r"[,/·]", clean_author(x or "")) if p.strip()}

    pa, pb = parts(a), parts(b)
    if not pa or not pb:
        return False  # 한쪽이 비면 판단 보류(폐기하지 않음)
    return not (pa & pb)


def find_official(title: str, want_media: Optional[str] = None) -> Optional[dict]:
    """제목으로 공식 메타 검색 — 네이버 → 문피아 → 카카오 (작가 교차검증).

    1차 결과(네이버)의 작가를 기준으로, 하위 소스 결과가 **작가 불일치**면 폐기한다
    (스핀오프/동명이작 오매칭 방지). 상위 결과가 없으면 하위를 그대로 채택한다.
    """
    primary = search_naver(title)
    if primary:
        ref_author = primary.get("author", "")
        for lower in (search_munpia(title), search_kakao(title, want_media=want_media)):
            if lower and _authors_conflict(ref_author, lower.get("author", "")):
                logger.debug(
                    f"작가 불일치로 폐기: {lower.get('source')} "
                    f"({lower.get('author')} != {ref_author})"
                )
        return primary
    # 네이버 실패 → 문피아 → 카카오
    meta = search_munpia(title)
    if meta:
        return meta
    meta = search_kakao(title, want_media=want_media)
    if meta:
        return meta
    for platform in ("ridi", "joara"):
        tmpl, _ = _SEARCH_ENDPOINTS[platform]
        if not _fetch(tmpl.format(q=quote(title))):
            logger.debug(f"{platform} 검색 접근 불가 — 스킵")
            continue
        logger.debug(f"{platform} 검색 응답은 있으나 파서 미구현 — 스킵")
    return None
