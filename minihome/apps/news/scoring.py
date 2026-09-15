#!/usr/bin/env python3
# Status: production
# Path: collector.py, web api
"""News article scoring — source tier + freshness + keyword matching."""

import sys
from datetime import datetime, timezone
from typing import Dict, List

# Add scripts/ to path for lib imports
_SCRIPTS = "/opt/projects/server/scripts"
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from lib.db import psql_json

# Phase 4: Source tiers — DB-first, fallback to hardcoded
SOURCE_TIERS: Dict[str, int] = {}
_SOURCE_TIERS_LOADED = False


def _load_source_tiers_from_db() -> None:
    """Load source tiers from PostgreSQL. Called once per process."""
    global SOURCE_TIERS, _SOURCE_TIERS_LOADED
    if _SOURCE_TIERS_LOADED:
        return
    _SOURCE_TIERS_LOADED = True

    try:
        rows = psql_json("SELECT source_name, tier FROM news_source_tiers")
        if rows:
            SOURCE_TIERS = {r["source_name"]: r["tier"] for r in rows}
            return
    except Exception:
        pass

    # Fallback to hardcoded
    SOURCE_TIERS = {
        # Korean economy — highest priority for Korean readers
        "매일경제": 1,
        "한국경제": 1,
        "연합뉴스 경제": 1,
        # English AI/Tech
        "TechCrunch AI": 1,
        "The Verge": 1,
        "MIT Technology Review": 1,
        "Ars Technica": 1,
        "Hacker News": 1,
        "OpenAI Blog": 1,
        "Google AI Blog": 1,
        "Hugging Face Blog": 1,
        "GeekNews": 1,
        "Bloomberg Tech": 2,
        "Wired": 2,
        # World economy — useful but not primary
        "Bloomberg Markets": 2,
        "Financial Times": 2,
        "The Economist": 2,
        "WSJ Economy": 2,
        "Reuters Business": 2,
        "CNBC Economy": 2,
        # Tier 3 — niche/aggregator
        "IEEE Spectrum": 2,
        "MarketWatch": 3,
        "Google News Business": 3,
        "Import AI": 2,
        "ITWorld Korea": 3,
        "CNET Korea": 3,
        "ArXiv CS.AI": 3,
        "ArXiv CS.CL": 3,
        "ArXiv CS.LG": 3,
    }


def _ensure_source_tiers() -> None:
    """Ensure source tiers are loaded."""
    if not _SOURCE_TIERS_LOADED:
        _load_source_tiers_from_db()

TOPIC_KEYWORDS = {
    "ai": ["AI", "인공지능", "LLM", "GPT", "Claude", "Gemini", "machine learning", "딥러닝", "Transformer", "AGI"],
    "tech": ["chip", "반도체", "NVIDIA", "AMD", "Intel", "Apple", "삼성", "quantum", "로봇", "autonomous"],
    "economy": ["경제", "투자", "IPO", "M&A", "매출", "수익", "시장", "가격", "주식"],
}


def calc_freshness_score(published_at: str) -> float:
    """신선도 점수 (0-1). 최신일수록 높음."""
    if not published_at:
        return 0.3
    try:
        pub = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        age_hours = max(0, (datetime.now(timezone.utc) - pub).total_seconds() / 3600)
        return max(0.1, 1.0 / (1 + age_hours / 24) ** 1.5)
    except Exception:
        return 0.3


def calc_keyword_score(title: str, summary: str, full_text: str = "") -> float:
    """키워드 매칭 점수 (0-1)."""
    text = f"{title} {summary} {full_text[:500]}".lower()
    matches = 0
    for category_keywords in TOPIC_KEYWORDS.values():
        for kw in category_keywords:
            if kw.lower() in text:
                matches += 1
    return min(1.0, matches / 3)


def calc_source_tier_score(source: str) -> float:
    """소스 등급 점수 (0-1). Tier 1 = 1.0, Tier 3 = 0.3."""
    _ensure_source_tiers()
    tier = SOURCE_TIERS.get(source, 3)
    return {1: 1.0, 2: 0.7, 3: 0.3}.get(tier, 0.3)


def calc_importance_score(article: Dict) -> float:
    """종합 중요도 점수 (0-10)."""
    published_at = article.get("published_at", "")
    if hasattr(published_at, "isoformat"):
        published_at = published_at.isoformat()
    freshness = calc_freshness_score(str(published_at))
    keyword = calc_keyword_score(
        article.get("title", ""),
        article.get("summary_ko", "") or article.get("summary", ""),
        article.get("full_text", ""),
    )
    source = calc_source_tier_score(article.get("source", ""))

    # 가중치: 소스 40%, 신선도 30%, 키워드 30%
    raw = source * 0.4 + freshness * 0.3 + keyword * 0.3

    # Phase 5: Corroboration bonus — multiple sources covering same story
    corroboration = calc_corroboration_score(article)
    raw = raw * (1 + corroboration)

    return round(min(10.0, raw * 10), 1)


def calc_corroboration_score(article: Dict) -> float:
    """Phase 5: Corroboration bonus (0-0.6).

    dedup_group_id 기반 클러스터 크기(k)를 보너스 점수로 반영.
    - k=1 (단일 소스): 0.0
    - k=2: 0.15
    - k=3: 0.30
    - k>=4: 0.45 (max)
    """
    dedup_group_id = article.get("dedup_group_id")
    if not dedup_group_id:
        return 0.0

    try:
        result = psql_json(
            f"SELECT COUNT(*) as cnt FROM news_articles WHERE dedup_group_id = {int(dedup_group_id)}"
        )
        if result and result[0]["cnt"] > 1:
            k = min(result[0]["cnt"], 4)
            return 0.15 * (k - 1)
    except Exception:
        pass

    return 0.0



