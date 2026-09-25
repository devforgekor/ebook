#!/usr/bin/env python3
# Status: experimental
# Path: called by — scripts/pipeline.py (official feed refresh); tests via lib
"""공식 주소/점검 피드(t.me/toki1234) 파싱 — 도메인 후보 등록 + 점검 감지.

[WHY] 도메인이 자주 바뀌고 점검 공지가 텔레그램으로만 오므로, 공식 채널을 읽어
후보 도메인을 sources.json에 등록하고 점검 중에는 수집을 건너뛰어 유료 트래픽·실패를
아낀다. 피드 장애 시에는 아무것도 차단하지 않는다(fail-open).
"""

from __future__ import annotations

import html as _html
import logging
import re
from collections.abc import Sequence

logger = logging.getLogger(__name__)

FEED_URL = "https://t.me/s/toki1234"
FEED_TTL_SEC = 3600
DOMAIN_HINTS = ("toki", "newto", "sbxh")
_MAINTENANCE_TOKENS = ("점검", "중단", "제한", "정상화")
_EXCLUDE_HINTS = ("t.me", "telegram.org", "telegra.ph", "telesco.pe")

_HOST_RE = re.compile(r"https?://([a-z0-9][a-z0-9.-]*\.[a-z]{2,})", re.IGNORECASE)
_MSG_RE = re.compile(
    r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', re.DOTALL
)
_TAG_RE = re.compile(r"<[^>]+>")


def _message_text(fragment: str) -> str:
    return _html.unescape(_TAG_RE.sub(" ", fragment)).strip()


def parse_feed(html_text: str) -> dict:
    """공식 채널 HTML → {domains, maintenance, last_message, n_messages}.

    - domains: 최근 메시지들에 등장한 도메인(패밀리 힌트 필터, 등장 순서, 중복 제거)
    - maintenance: **마지막 메시지**에 점검/중단/제한/정상화 토큰 포함 여부(보수적)
    """
    messages = [_message_text(m) for m in _MSG_RE.findall(html_text)]
    last = messages[-1] if messages else ""
    domains: list[str] = []
    for match in _HOST_RE.finditer(html_text):
        host = match.group(1).lower()
        if any(x in host for x in _EXCLUDE_HINTS):
            continue
        if not any(k in host for k in DOMAIN_HINTS):
            continue
        if host not in domains:
            domains.append(host)
    maintenance = any(token in last for token in _MAINTENANCE_TOKENS)
    return {
        "domains": domains,
        "maintenance": maintenance,
        "last_message": last[:400],
        "n_messages": len(messages),
    }


def fetch_feed(url: str = FEED_URL, timeout: float = 10.0) -> dict | None:
    """공식 채널 미리보기 조회 → parse_feed. 실패 시 None(fail-open)."""
    try:
        import requests

        resp = requests.get(
            url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"}
        )
        resp.raise_for_status()
    except Exception as e:  # noqa: BLE001 — 피드 장애는 차단하지 않는다
        logger.debug(f"공식 피드 조회 실패(무시): {e}")
        return None
    return parse_feed(resp.text)


def merge_candidates(domains: Sequence[str], source: str = "toki31") -> int:
    """피드 도메인을 sources.json 후보로 등록(베이스 변경 없음). 추가 수 반환.

    [WHY] 자동 전환은 헬스체크/리다이렉트가 결정해야 하므로 set_base=False로
    후보만 늘린다(공식 공지 순서만으로 현재 도메인을 단정하지 않음).
    """
    added = 0
    try:
        from lib.sources import add_source_domain, get_domains

        existing = set(get_domains(source) or [])
    except Exception as e:  # noqa: BLE001
        logger.debug(f"도메인 등록 불가(무시): {e}")
        return 0
    for host in domains:
        host = (host or "").strip().lower().rstrip("/")
        if not host or host in existing:
            continue
        if not any(k in host for k in DOMAIN_HINTS):
            continue
        try:
            if add_source_domain(source, host, set_base=False):
                existing.add(host)
                added += 1
        except Exception as e:  # noqa: BLE001
            logger.debug(f"도메인 등록 실패({host}): {e}")
    return added
