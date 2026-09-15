#!/usr/bin/env python3
# Status: production
# Path: systemd:devforge-news-digest.timer
"""News Digest Builder — DB → LLM 요약 → 텔레그램 발송.

Usage:
  python3 digest.py                # 실행 (기본 24시간 윈도우)
  python3 digest.py --window 48    # 48시간 윈도우
  python3 digest.py --dry-run      # 발송 없이 출력만
  python3 digest.py --limit 5      # 카테고리별 최대 5개
"""

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional

# Add scripts/ to path
_SCRIPTS = "/opt/projects/server/scripts"
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from lib.db import psql_json, esc_sql
from utils import has_chinese

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("news-digest")

# Telegram message size limit (Telegram max is 4096, reserve 100 for margin)
TG_MAX_LEN = 4000

# LLM retry config
LLM_MAX_RETRIES = 3
LLM_RETRY_BASE_DELAY = 2  # seconds

# secrets (loaded once at module level)


def _load_secrets() -> Dict[str, str]:
    secrets = {}
    sf = Path.home() / ".config/devforge/secrets.env"
    if not sf.exists():
        return secrets
    for line in sf.read_text().split("\n"):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            secrets[key.strip()] = val.strip().strip('"').strip("'")
    return secrets


def _fetch_articles(window_hours: int = 24, limit_per_category: int = 10) -> List[Dict]:
    """Fetch recent articles from DB (using esc_sql for safe interpolation)."""
    safe_hours = esc_sql(str(window_hours))
    sql = f"""
        SELECT id, title, source, language, category, summary, highlights,
               published_at, url
        FROM news_articles
        WHERE collected_at >= NOW() - INTERVAL '{safe_hours} hours'
          AND title != 'Test Article'
        ORDER BY category, published_at DESC NULLS LAST
    """
    try:
        rows = psql_json(sql)
    except Exception as e:
        logger.error("DB query failed: %s", e)
        return []

    if not rows:
        return []

    # Group by category, limit each, deduplicate by URL
    by_cat: Dict[str, List[Dict]] = {}
    seen_urls: set = set()
    for r in rows:
        cat = r.get("category", "ai")
        url = r.get("url", "")
        if url in seen_urls:
            continue
        seen_urls.add(url)
        by_cat.setdefault(cat, []).append(r)

    result = []
    for cat, articles in by_cat.items():
        result.extend(articles[:limit_per_category])
    return result


# OpenRouter RR 프록시(openrouter-rr-proxy.service, :8451) — 3개 키 라운드로빈.
# 유료 키이므로 저렴한 유료 모델을 라운드로빈으로 사용해 429/한도 문제를 피한다.
_OR_PROXY_URL = os.environ.get("OPENROUTER_RR_PROXY_URL", "http://127.0.0.1:8451")
_OR_PROXY_MODELS = [
    "openai/gpt-4o-mini",
    "deepseek/deepseek-chat",
    "google/gemini-2.5-flash",
]
_or_model_idx = 0  # 모델 라운드로빈 시작 인덱스


def _call_llm(prompt: str, max_tokens: int = 2000) -> Optional[str]:
    """Call OpenRouter RR proxy (키 라운드로빈) + 유료 모델 라운드로빈."""
    global _or_model_idx

    models = list(_OR_PROXY_MODELS)
    if models:
        # 호출마다 시작 모델을 순환시켜 공평 분배
        models = models[_or_model_idx:] + models[:_or_model_idx]
        _or_model_idx = (_or_model_idx + 1) % len(models)

    system_msg = (
        "You are a news digest writer for a Korean tech audience. "
        "Write concise, informative summaries in Korean. "
        "Each article gets 1-2 sentences. "
        "Group by category (AI, TECH, ECONOMY). "
        "Use bullet points with source attribution. "
        "No fluff, no introductions, no conclusions. "
        "CRITICAL: Use only Korean Hangul and Latin script for proper nouns/numbers. "
        "Never use Chinese characters or Hanja (汉字/中文)."
    )

    for model in models:
        payload = json.dumps({
            "model": model,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.3,
        }).encode()
        req = urllib.request.Request(
            f"{_OR_PROXY_URL}/v1/chat/completions", data=payload,
            headers={"Content-Type": "application/json"},
        )
        for attempt in range(1, LLM_MAX_RETRIES + 1):
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = json.loads(resp.read())
                    content = data["choices"][0]["message"]["content"]
                    if content:
                        return content
                    break  # Empty response, try next model
            except urllib.error.HTTPError as e:
                if e.code in (429, 500, 502, 503) and attempt < LLM_MAX_RETRIES:
                    logger.warning("LLM %s proxy %d — retry %d/%d",
                                   model, e.code, attempt + 1, LLM_MAX_RETRIES)
                    time.sleep(LLM_RETRY_BASE_DELAY * attempt)
                    continue
                logger.error("LLM %s error %d: %s", model, e.code, e.read()[:200])
                break  # Try next model
            except (urllib.error.URLError, ConnectionError, OSError) as e:
                if attempt < LLM_MAX_RETRIES:
                    logger.warning("LLM connection error (attempt %d/%d): %s, retry in %ds",
                                   attempt, LLM_MAX_RETRIES, e, LLM_RETRY_BASE_DELAY * attempt)
                    time.sleep(LLM_RETRY_BASE_DELAY * attempt)
                    continue
                logger.error("LLM connection error: %s", e)
            except (KeyError, IndexError, json.JSONDecodeError) as e:
                logger.error("LLM response parse error: %s", e)
                break  # Try next model

    logger.error("LLM failed after all models")
    return None


def _format_articles_for_llm(articles: List[Dict]) -> str:
    """Format articles into LLM prompt."""
    by_cat: Dict[str, List[Dict]] = {}
    for a in articles:
        cat = a.get("category", "ai")
        by_cat.setdefault(cat, []).append(a)

    lines = []
    for cat, items in by_cat.items():
        lines.append(f"\n## {cat.upper()}")
        for i, a in enumerate(items, 1):
            title = a.get("title", "No title")
            source = a.get("source", "")
            summary = a.get("summary", "")
            url = a.get("url", "")

            line = f"{i}. [{source}] {title}"
            if summary:
                line += f"\n   Summary: {summary[:300]}"
            if url:
                line += f"\n   URL: {url}"
            lines.append(line)

    return "\n".join(lines)


def _build_digest_message(articles: List[Dict], llm_summary: Optional[str]) -> str:
    """Build the final Telegram message with length control."""
    now_kst = datetime.now(timezone(timedelta(hours=9)))
    date_str = now_kst.strftime("%Y년 %m월 %d일")

    by_cat: Dict[str, int] = {}
    for a in articles:
        cat = a.get("category", "ai")
        by_cat[cat] = by_cat.get(cat, 0) + 1

    cat_summary = ", ".join(f"{k}: {v}건" for k, v in by_cat.items())

    header = (
        f"<b>DevForge 뉴스 다이제스트</b>\n"
        f"{date_str}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"  {cat_summary} (총 {len(articles)}건)\n"
    )

    if llm_summary:
        body = f"\n{llm_summary}"
    else:
        body = _manual_format(articles)

    footer = (
        f"\n\n━━━━━━━━━━━━━━━━━━━\n"
        f"  DevForge News Digest"
    )

    message = header + body + footer

    # Enforce Telegram length limit
    if len(message) > TG_MAX_LEN:
        message = message[:TG_MAX_LEN - 20] + "\n\n... (메시지 잘림)"

    return message


def _manual_format(articles: List[Dict]) -> str:
    """Manual formatting fallback when LLM is unavailable."""
    by_cat: Dict[str, List[Dict]] = {}
    for a in articles:
        cat = a.get("category", "ai")
        by_cat.setdefault(cat, []).append(a)

    cat_names = {"ai": "AI", "tech": "기술", "economy": "경제"}
    lines = []

    for cat, items in by_cat.items():
        lines.append(f"\n<b>{cat_names.get(cat, cat)}</b>")
        for a in items[:8]:
            title = a.get("title", "")[:60]
            source = a.get("source", "")
            lines.append(f"  [{source}] {title}")

    return "\n".join(lines)


def _send_telegram(text: str) -> bool:
    """Send via existing telegram_send module with error handling."""
    try:
        sys.path.insert(0, _SCRIPTS)
        from telegram_send import send_text
        ok = send_text(text)
        if ok:
            logger.info("Telegram sent (%d chars)", len(text))
        else:
            logger.error("Telegram send returned False")
        return ok
    except Exception as e:
        logger.error("Telegram send failed: %s", e)
        return False


def run(window_hours: int = 24, limit: int = 10, dry_run: bool = False):
    """Main entry point."""
    logger.info("Starting digest — window=%dh, limit=%d/cat, dry_run=%s",
                window_hours, limit, dry_run)

    articles = _fetch_articles(window_hours, limit)
    if not articles:
        logger.warning("No articles found")
        msg = (
            "<b>DevForge 뉴스 다이제스트</b>\n\n"
            "오늘 수집된 뉴스가 없습니다.\n"
            "collector.py를 실행하여 뉴스를 수집해주세요."
        )
        if not dry_run:
            _send_telegram(msg)
        else:
            print(msg)
        return

    logger.info("%d articles ready", len(articles))

    # Build LLM prompt
    prompt = _format_articles_for_llm(articles)
    llm_summary = _call_llm(prompt)

    if llm_summary and has_chinese(llm_summary):
        logger.warning("LLM digest contained Chinese characters (한문) — regenerating once")
        llm_summary = _call_llm(prompt + "\n\nREMINDER: Do NOT use any Chinese characters or Hanja. Hangul only.")
        if llm_summary and has_chinese(llm_summary):
            logger.warning("LLM digest still contained Chinese characters — dropping summary")
            llm_summary = None

    if llm_summary:
        logger.info("LLM summary generated (%d chars)", len(llm_summary))
    else:
        logger.warning("LLM unavailable, using manual format")

    # Build message
    message = _build_digest_message(articles, llm_summary)

    if dry_run:
        print("\n--- DRY RUN OUTPUT ---")
        print(message)
        print(f"\n--- END ({len(message)} chars) ---")
        return

    _send_telegram(message)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DevForge News Digest")
    parser.add_argument("--window", type=int, default=24, help="Hours to look back")
    parser.add_argument("--limit", type=int, default=10, help="Max articles per category")
    parser.add_argument("--dry-run", action="store_true", help="Print only, don't send")
    args = parser.parse_args()

    run(window_hours=args.window, limit=args.limit, dry_run=args.dry_run)
