#!/usr/bin/env python3
# Status: production
# Path: systemd:devforge-news.timer
"""News Collector — RSS + Exa hybrid news system.

Architecture:
  1. RSS (gnews) → headlines
  2. Exa → clean text + highlights + summary
  3. MultilingualProcessor → entities + concepts
  4. scoring → importance_score (source tier + freshness + keywords)
  5. PostgreSQL → news_articles, concepts, term_variants, entity_alias
"""

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

# Add scripts/ to path for lib imports
_SCRIPTS = "/opt/projects/server/scripts"
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from scoring import calc_importance_score
from dedup import cluster_articles_hybrid, select_canonical

from lib.db import psql, psql_json, esc_sql

# Local imports
from exa_extractor import ExaExtractor
from multilingual_processor import MultilingualProcessor
from translator import translate_article

def _is_excluded_title(title: str) -> bool:
    """Check if a title should be excluded before Exa extraction.

    타이틀 키워드 기반 연예/생활 필터는 쓰지 않는다(오탐 유발).
    연예/생활 잡음은 URL 섹션 기반으로 원천 차단(_is_excluded_url).
    여기서는 명백한 광고성 제목만 차단.
    """
    import re
    if not title:
        return True
    promo = r'(promo code|coupon|discount|sponsored|advertisement|광고)'
    if re.search(promo, title, re.IGNORECASE):
        return True
    return False

# Per-source URL path section allowlist — block non-economic sections at source level.
# 매일경제 URL: /news/{section}/... Only allow economic-relevant sections.
_SOURCE_URL_FILTERS = {
    "매일경제": {
        "allowed_sections": {"economy", "stock", "business", "it", "realestate", "world"},
        "blocked_sections": {"society", "politics", "culture"},
    },
}

# 카테고리 자체를 수집하지 않는다: 연예/생활/잡음 섹션은 URL 경로로 원천 차단.
# (타이틀 키워드 필터가 아니라 URL 구조 기반 — 매일경제 /news/{section}/ 패턴 등)
_GLOBAL_BLOCKED_SECTIONS = {
    "society", "politics", "culture", "sports", "entertain",
    "entertainment", "star", "lifeculture", "travel", "weather",
    "economyplus", "realtyplus",
}

# 수집 허용 카테고리 — 이 외의 카테고리는 수집 자체를 하지 않는다.
ALLOWED_CATEGORIES = {"ai", "tech", "kor_economy", "world_economy"}


def _is_excluded_url(source: str, url: str) -> bool:
    """Check if a URL should be excluded before Exa extraction (per-source section filter)."""
    if not url or not source:
        return False
    # URL 경로의 섹션이 전역 차단 목록이면 제외 (연예/생활/사회/스포츠 등)
    if "/news/" in url:
        section = url.split("/news/")[1].split("/")[0]
        if section in _GLOBAL_BLOCKED_SECTIONS:
            return True
    filter_config = _SOURCE_URL_FILTERS.get(source)
    if not filter_config:
        return False
    # Extract section from URL path: /news/{section}/...
    if "/news/" in url:
        section = url.split("/news/")[1].split("/")[0]
        if section in filter_config.get("blocked_sections", set()):
            return True
        if filter_config.get("allowed_sections") and section not in filter_config["allowed_sections"]:
            return True
    return False


def _load_feeds() -> List[Dict[str, Any]]:
    """Load RSS feeds from feeds.yaml."""
    feeds_path = Path(__file__).parent / "feeds.yaml"
    if not feeds_path.exists():
        print(f"[news] feeds.yaml not found at {feeds_path}")
        return []

    with open(feeds_path) as f:
        data = yaml.safe_load(f)

    return [feed for feed in data.get("feeds", []) if feed.get("enabled", True)]


def _fetch_rss(url: str, max_articles: int = 10) -> List[Dict[str, str]]:
    """Fetch RSS feed and extract headlines using feedparser."""
    import feedparser

    try:
        feed = feedparser.parse(url)
        items = []

        for entry in feed.entries[:max_articles]:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            published = entry.get("published", "") or entry.get("updated", "")
            if title and link:
                items.append({
                    "title": title,
                    "url": link,
                    "published_at": published,
                })

        return items

    except Exception as e:
        print(f"[news] RSS fetch error: {url} — {e}")
        return []


def _parse_date(date_str: str) -> Optional[datetime]:
    """Parse various date formats."""
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",  # RFC 2822 (Thu, 04 Dec 2025 05:37:00 +0000)
        "%Y-%m-%dT%H:%M:%S.%fZ",  # ISO 8601 with milliseconds + Z (Exa output)
        "%Y-%m-%dT%H:%M:%S.%f%z",  # ISO 8601 with milliseconds + timezone
        "%Y-%m-%dT%H:%M:%S%z",  # ISO 8601
        "%Y-%m-%dT%H:%M:%SZ",  # ISO 8601 UTC
        "%Y-%m-%d %H:%M:%S",  # Simple
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def _send_alert(subject: str, body: str) -> None:
    """Send alert email for critical failures only."""
    import smtplib
    import ssl
    from email.mime.text import MIMEText
    import traceback
    
    host = os.environ.get("SMTP_HOST")
    try:
        port = int(os.environ.get("SMTP_PORT", "587"))
    except (ValueError, TypeError):
        port = 587
    user = os.environ.get("SMTP_USER")
    pwd = os.environ.get("SMTP_PASSWORD")
    to = os.environ.get("ALERT_EMAIL", user)
    
    if not all([host, port, user, pwd, to]):
        return  # Not configured, skip silently
    
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP(host, port) as s:
            s.starttls(context=ctx)
            s.login(user, pwd)
            s.send_message(msg)
        print(f"[alert] Sent: {subject}")
    except Exception as e:
        print(f"[alert] Failed to send email: {e}")


def _trigger_summary_retry() -> None:
    """Trigger summary_retry service via systemd (non-blocking)."""
    import subprocess
    try:
        result = subprocess.run(
            ["systemctl", "--user", "--no-block", "start", "devforge-summary-retry.service"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            print("[news] Triggered devforge-summary-retry.service")
        else:
            err = result.stderr.strip()[:200]
            print(f"[news] Failed to trigger summary-retry: {err}")
    except Exception as e:
        print(f"[news] Trigger summary-retry error (non-fatal): {e}")
class NewsCollector:
    """News collector — RSS + Exa hybrid."""

    # Category-level article caps (applied after dedup)
    CATEGORY_LIMITS = {
        "ai": 5,
        "tech": 5,
        "kor_economy": 10,
        "world_economy": 10,
    }

    def __init__(self):
        self.feeds = _load_feeds()
        # Sort feeds by priority: high → medium
        priority_order = {"high": 0, "medium": 1}
        self.feeds.sort(key=lambda f: (priority_order.get(f.get("priority", "medium"), 99), f["name"]))
        self.exa = ExaExtractor()
        self.processor = MultilingualProcessor()
        self._stats = {
            "feeds": 0,
            "headlines": 0,
            "extracted": 0,
            "saved": 0,
            "entities": 0,
        }
        # Phase 1: Circuit breaker — per-source failure counter
        self._failure_counts: Dict[str, int] = {}
        self._circuit_breaker_threshold = 2

    def run(self, dry_run: bool = False, limit: int = 20):
        """Run the full collection pipeline.

        Args:
            dry_run: If True, don't save to DB
            limit: Max articles per feed
        """
        import traceback
        
        try:
            print(f"[news] Starting collection — {len(self.feeds)} feeds")
            start_time = time.time()

            # Category-level cap counters
            self._saved_by_category: Dict[str, int] = defaultdict(int)
            self._capped_feeds: List[str] = []

            for i, feed in enumerate(self.feeds):
                cat = feed.get("category", "ai")
                if cat not in ALLOWED_CATEGORIES:
                    print(f"\n[news] Skipping {feed['name']}: category '{cat}' not allowed")
                    continue
                cap = self.CATEGORY_LIMITS.get(cat)
                if cap is not None and self._saved_by_category[cat] >= cap:
                    self._capped_feeds.append(feed["name"])
                    print(f"\n[news] Skipping {feed['name']}: category '{cat}' limit ({cap}) reached")
                    continue
                self._process_feed(feed, dry_run, limit, cap)
                # Rate limiting between feeds (not between articles)
                if i < len(self.feeds) - 1:
                    time.sleep(2)

            if self._capped_feeds:
                print(f"\n[news] Category-capped feeds: {', '.join(self._capped_feeds)}")

            elapsed = time.time() - start_time
            print(f"\n[news] Collection complete in {elapsed:.1f}s")
            print(f"  Feeds: {self._stats['feeds']}")
            print(f"  Headlines: {self._stats['headlines']}")
            print(f"  Extracted: {self._stats['extracted']}")
            print(f"  Saved: {self._stats['saved']}")
            print(f"  Entities: {self._stats['entities']}")

            # ── Post-collection steps ──
            # devforge가 처리·DB의 SSOT. Vercel은 devforge News Read API를
            # fetch해 표시만 하므로 동기화/배포 단계가 없다. 각 단계는 실패해도
            # 전체 run이 죽지 않도록 guard 처리한다.
            if not dry_run:
                try:
                    print("\n[news] Updating dedup groups...")
                    self._update_dedup_groups()
                    print("  Done")
                except Exception as e:
                    print(f"[news] dedup update failed (non-fatal): {e}")

                try:
                    self._check_missing_summaries()
                except Exception as e:
                    print(f"[news] summary check failed (non-fatal): {e}")

                try:
                    self._check_and_alert_critical_failures()
                except Exception as e:
                    print(f"[news] critical-failure check failed (non-fatal): {e}")

                try:
                    _trigger_summary_retry()
                except Exception as e:
                    print(f"[news] summary-retry trigger failed (non-fatal): {e}")

                # Completion heartbeat — watchdog dead-man's switch keyed on
                # "run finished" (not "timer fired"). A timeout-killed run never
                # reaches this point → no heartbeat → watchdog flags it stale.
                try:
                    from lib.watchdog.messenger import heartbeat
                    hb_detail = f"saved={self._stats['saved']}"
                    if heartbeat("news_collector", detail=hb_detail):
                        print(f"[news] Heartbeat recorded (news_collector): {hb_detail}")
                except Exception as e:
                    print(f"[news] heartbeat failed (non-fatal): {e}")

        except Exception as e:
            # Process crash — send alert and re-raise
            _send_alert(
                "🚨 [News] 수집 프로세스 크래시",
                f"예외 발생: {e}\n\n{traceback.format_exc()}"
            )
            raise

    def _process_feed(self, feed: Dict, dry_run: bool, limit: int, category_cap: Optional[int] = None):
        """Process a single RSS feed."""
        name = feed["name"]
        url = feed["url"]
        category = feed.get("category", "ai")
        language = feed.get("language", "ko")

        # Phase 1: Circuit breaker — skip if too many consecutive failures
        if self._failure_counts.get(name, 0) >= self._circuit_breaker_threshold:
            print(f"\n[news] Skipping {name}: {self._circuit_breaker_threshold} consecutive failures (circuit breaker)")
            return

        # Phase 2: Category-level cap — skip if limit already reached
        if category_cap is not None and self._saved_by_category[category] >= category_cap:
            print(f"\n[news] Skipping {name}: category '{category}' limit ({category_cap}) reached")
            return

        print(f"\n[news] Processing: {name} ({language})")

        # Step 1: Fetch RSS
        items = _fetch_rss(url, limit)
        if not items:
            print("  No items found")
            self._failure_counts[name] = self._failure_counts.get(name, 0) + 1
            return

        # Reset failure count on success
        self._failure_counts[name] = 0

        self._stats["feeds"] += 1
        self._stats["headlines"] += len(items)
        print(f"  Found {len(items)} headlines")

        # Step 2: Extract content via Exa
        saved_count = 0
        for item in items:
            # Re-check category cap before each extraction (expensive)
            if category_cap is not None and self._saved_by_category[category] >= category_cap:
                print(f"  [CAP] Category '{category}' limit ({category_cap}) reached — stopping feed")
                break
            article = self._extract_and_process(item, name, category, language)
            if article and not dry_run:
                saved = self._save_article(article)
                if saved:
                    saved_count += 1
                    self._stats["saved"] += 1
                    self._saved_by_category[category] += 1

        # Track failure if no articles saved
        if not dry_run and saved_count == 0 and len(items) > 0:
            self._failure_counts[name] = self._failure_counts.get(name, 0) + 1
        elif not dry_run:
            self._failure_counts[name] = 0

    def _extract_and_process(self, item: Dict, source: str, category: str, language: str) -> Optional[Dict]:
        """Extract content and process entities."""
        url = item["url"]
        title = item["title"]

        # Early title filter — skip celebrity/entertainment/low-quality before expensive Exa call
        if _is_excluded_title(title):
            print(f"  [SKIP] Excluded keyword: {title[:50]}")
            return None

        # Early URL section filter — skip non-economic sections at source level
        if _is_excluded_url(source, url):
            print(f"  [SKIP] Excluded URL section: {title[:50]}")
            return None

        # Step 1: Extract content via Exa
        content = self.exa.extract_content(url)
        if not content:
            content = {
                "url": url,
                "title": title,
                "text": "",
                "highlights": [],
                "summary": "",
                "published_date": item.get("published_at", ""),
            }

        # Skip if no full text extracted
        if not content.get("text"):
            print(f"  [SKIP] No full text: {title[:50]}")
            return None

        # Phase 2: Photo news filter — skip if text too short (photo-only articles)
        text_content = content.get("text", "")
        if len(text_content) < 50:
            print(f"  [SKIP] Text too short ({len(text_content)} chars): {title[:50]}")
            return None

        self._stats["extracted"] += 1

        # Step 2: Extract entities
        text_to_process = f"{title}\n{content.get('summary', '')}\n{content.get('text', '')[:1000]}"
        entities = self.processor.extract_entities(text_to_process, language)
        self._stats["entities"] += len(entities)

        # Step 3: Parse date — fallback to collected_at on failure
        published_at = None
        if content.get("published_date"):
            published_at = _parse_date(content["published_date"])
        if not published_at and item.get("published_at"):
            published_at = _parse_date(item["published_at"])
        # Last resort: use current time (better than NULL for Vercel sort)
        if not published_at:
            published_at = datetime.now(timezone.utc)

        # Step 4: Build article dict
        article = {
            "url": url,
            "title": content.get("title", title),
            "source": source,
            "published_at": published_at,
            "language": language,
            "category": category,
            "full_text": content.get("text", ""),
            "highlights": content.get("highlights", []),
            "summary": content.get("summary", ""),
            "concept_ids": [e["concept_id"] for e in entities],
            "entities": entities,
            "metadata": {
                "exa_highlights_count": len(content.get("highlights", [])),
                "exa_text_length": len(content.get("text", "")),
            },
        }

        # Step 5: Translate to Korean if needed
        article = translate_article(article)

        return article

    def _save_article(self, article: Dict) -> bool:
        """Save article to PostgreSQL using parameterized query via psql_json."""
        # Build JSON fields safely
        concept_ids_json = json.dumps(article.get("concept_ids", []))
        highlights_json = json.dumps(article.get("highlights", []))
        highlights_ko_json = json.dumps(article.get("highlights_ko", []))

        title_ko = article.get("title_ko", "")
        summary_ko = article.get("summary_ko", "")
        # Mark for retry if translation failed (empty title_ko) or no summary
        pipeline_state = "needs_summary" if (not summary_ko or not title_ko) else "raw"

        published_at = article.get("published_at")
        published_at_sql = f"'{esc_sql(published_at.isoformat())}'" if published_at else "NULL"

        # Use CTE with parameterized values to avoid SQL injection in JSON
        sql = f"""
            WITH vals AS (
                SELECT
                    '{esc_sql(article["url"])}'::text AS url,
                    '{esc_sql(article["title"][:500])}'::text AS title,
                    '{esc_sql(article["source"])}'::text AS source,
                    {published_at_sql}::timestamptz AS published_at,
                    '{esc_sql(article["language"])}'::text AS language,
                    '{esc_sql(article["category"])}'::text AS category,
                    '{esc_sql(article.get("full_text", "")[:10000])}'::text AS full_text,
                    '{esc_sql(highlights_json)}'::jsonb AS highlights,
                    '{esc_sql(article.get("summary", "")[:5000])}'::text AS summary,
                    '{esc_sql(concept_ids_json)}'::jsonb AS concept_ids,
                    '{esc_sql(title_ko[:500])}'::text AS title_ko,
                    '{esc_sql(summary_ko[:5000])}'::text AS summary_ko,
                    '{esc_sql(highlights_ko_json)}'::jsonb AS highlights_ko,
                    {calc_importance_score(article)}::real AS relevance_score,
                    '{esc_sql(pipeline_state)}'::text AS pipeline_state
            )
            INSERT INTO news_articles (
                url, title, source, published_at, language, category,
                full_text, highlights, summary, concept_ids,
                title_ko, summary_ko, highlights_ko, relevance_score, pipeline_state
            )
            SELECT url, title, source, published_at, language, category,
                   full_text, highlights, summary, concept_ids,
                   title_ko, summary_ko, highlights_ko, relevance_score, pipeline_state
            FROM vals
            ON CONFLICT (url) DO UPDATE SET
                title = EXCLUDED.title,
                full_text = EXCLUDED.full_text,
                highlights = EXCLUDED.highlights,
                summary = EXCLUDED.summary,
                concept_ids = EXCLUDED.concept_ids,
                title_ko = EXCLUDED.title_ko,
                summary_ko = EXCLUDED.summary_ko,
                highlights_ko = EXCLUDED.highlights_ko,
                relevance_score = EXCLUDED.relevance_score,
                pipeline_state = EXCLUDED.pipeline_state,
                updated_at = NOW()
            RETURNING id
        """

        result = psql(sql)
        if result:
            article_id = int(result)
            self.processor.save_entities(article.get("entities", []), article_id)
            return True

        return False


    def _update_dedup_groups(self):
        """Update dedup_group_id for all articles based on title similarity."""
        articles = psql_json(
            "SELECT id, title, title_ko, source, published_at FROM news_articles"
        )
        if not articles:
            return

        clusters = cluster_articles_hybrid(articles, threshold=0.5, min_size=2)

        # Build single bulk UPDATE using CASE
        for cluster in clusters:
            if len(cluster) <= 1:
                continue

            canonical = select_canonical(cluster)
            canonical_id = canonical["id"]
            other_ids = [a["id"] for a in cluster if a["id"] != canonical_id]

            if other_ids:
                ids_csv = ",".join(str(x) for x in other_ids)
                sql = f"UPDATE news_articles SET dedup_group_id = {canonical_id} WHERE id IN ({ids_csv})"
                psql(sql)

    def _check_missing_summaries(self):
        """Check for articles without summaries/translations and alert if needed."""
        result = psql_json(
            """SELECT COUNT(*) as cnt FROM news_articles
               WHERE title != 'Test Article'
                 AND (summary_ko IS NULL OR summary_ko = '' OR title_ko IS NULL OR title_ko = '')
                 AND pipeline_state != 'needs_summary'"""
        )
        missing = result[0]["cnt"] if result else 0

        if missing > 0:
            print(f"\n  [WARN] {missing} articles missing summary or translation — marking for retry")
            psql(
                """UPDATE news_articles
                   SET pipeline_state = 'needs_summary'
                   WHERE title != 'Test Article'
                     AND (summary_ko IS NULL OR summary_ko = '' OR title_ko IS NULL OR title_ko = '')
                     AND pipeline_state != 'needs_summary'"""
            )

        # Count total needs_summary
        result2 = psql_json(
            """SELECT COUNT(*) as cnt FROM news_articles
               WHERE pipeline_state = 'needs_summary'"""
        )
        needs_retry = result2[0]["cnt"] if result2 else 0
        if needs_retry > 0:
            print(f"  [INFO] {needs_retry} articles need summary retry")

    def _check_and_alert_critical_failures(self) -> None:
        """Check for critical failure conditions and send alerts (called at end of run)."""
        # 1. All feeds circuit breaker open (total collection halt)
        if self._failure_counts and all(
            c >= self._circuit_breaker_threshold for c in self._failure_counts.values()
        ):
            failed_feeds = list(self._failure_counts.keys())
            _send_alert(
                "🚨 [News] 전체 RSS 피드 수집 중단",
                f"모든 피드가 회로차단기에 의해 차단되었습니다.\n차단된 피드: {', '.join(failed_feeds)}"
            )
    
        # 2. API keys exhausted (all keys in backoff)
        try:
            from collector.key_rotator_db import create_db_key_rotator
            from exa_extractor import _load_keys_from_secrets
            
            for provider, secret_key in [
                ("exa", "EXA_API_KEYS"),
                ("tavily", "TRAVILY_API_KEYS"),
                ("brave", "BRAVE_API_KEYS"),
            ]:
                keys = _load_keys_from_secrets(provider, secret_key)
                if not keys:
                    continue
                rotator = create_db_key_rotator(provider, keys)
                stats = rotator.stats()
                if stats["available_keys"] == 0:
                    _send_alert(
                        f"🚨 [News] {provider.upper()} API 키 고갈",
                        f"{provider}의 모든 API 키가 backoff 상태입니다.\n"
                        f"총 키: {stats['total_keys']}, 사용 가능: {stats['available_keys']}"
                    )
        except Exception:
            pass  # Alert check failure shouldn't crash collection


def main():
    """CLI entry point."""

    parser = argparse.ArgumentParser(description="DevForge News Collector")
    parser.add_argument("--dry-run", action="store_true", help="Don't save to DB")
    parser.add_argument("--limit", type=int, default=5, help="Max articles per feed")
    parser.add_argument("--feed", type=str, help="Process specific feed only")
    args = parser.parse_args()

    collector = NewsCollector()

    if args.feed:
        # Filter to specific feed
        collector.feeds = [f for f in collector.feeds if args.feed.lower() in f["name"].lower()]
        if not collector.feeds:
            print(f"No feed matching: {args.feed}")
            sys.exit(1)

    collector.run(dry_run=args.dry_run, limit=args.limit)


if __name__ == "__main__":
    main()
