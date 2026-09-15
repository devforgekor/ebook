#!/usr/bin/env python3
# Status: production
# Path: systemd:devforge-summary-retry.timer, collector.py
"""Retry summary generation for articles with pipeline_state='needs_summary'."""

import json
import sys
import time
from typing import List

_SCRIPTS = "/opt/projects/server/scripts"
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from lib.db import psql, psql_json

# Add news scripts to path
_NEWS = "/opt/workspace/minihome/apps/news"
if _NEWS not in sys.path:
    sys.path.insert(0, _NEWS)

from translator import translate_to_korean

BATCH_SIZE = 10
RATE_LIMIT_SEC = 3.0  # Gemini 폴백 기준 여유 간격


def get_needs_summary(limit: int = BATCH_SIZE) -> List[dict]:
    """Get articles needing summary retry."""
    return psql_json(
        f"""SELECT id, title, title_ko, full_text, source, language
            FROM news_articles
            WHERE pipeline_state = 'needs_summary'
              AND full_text IS NOT NULL AND LENGTH(full_text) > 100
            ORDER BY collected_at DESC
            LIMIT {limit}"""
    )


def update_summary(article_id: int, title_ko: str, summary_ko: str, highlights_ko: list):
    """Update article with generated summary and title."""
    from lib.db import esc_sql
    highlights_json = esc_sql(json.dumps(highlights_ko, ensure_ascii=False))
    sql = f"""UPDATE news_articles
              SET title_ko = '{esc_sql(title_ko)}',
                  summary_ko = '{esc_sql(summary_ko)}',
                  highlights_ko = '{highlights_json}'::jsonb,
                  pipeline_state = 'raw',
                  updated_at = NOW()
              WHERE id = {article_id}
              RETURNING id"""
    result = psql(sql)
    if not result:
        print(f"  [WARN] ID {article_id}: UPDATE returned no rows (may have failed silently)")


def retry_batch(dry_run: bool = False) -> dict:
    """Process one batch of articles needing summary."""
    stats = {"processed": 0, "success": 0, "failed": 0}

    articles = get_needs_summary()
    if not articles:
        print("[summary-retry] No articles needing summary")
        return stats

    print(f"[summary-retry] Processing {len(articles)} articles...")

    for i, a in enumerate(articles):
        aid = a["id"]
        title = a["title_ko"] or a["title"]
        full_text = a["full_text"][:3000]

        try:
            result = translate_to_korean(title, "", [], full_text)
            title_ko = result.get("title_ko", "")
            summary = result.get("summary_ko", "")
            highlights = result.get("highlights_ko", [])

            if summary and len(summary) > 20 and not result.get("_summary_fallback"):
                if not dry_run:
                    update_summary(aid, title_ko, summary, highlights)
                stats["success"] += 1
                print(f"  [{i+1}] ID {aid}: OK ({len(summary)} chars)")
            else:
                # 번역 실패(일시적 한도/오류) — 영구 실패로 태우지 않고
                # needs_summary 유지 → 다음 주기에 재시도 (Gemini 폴백 포함).
                stats["failed"] += 1
                print(f"  [{i+1}] ID {aid}: DEFERRED (translation failed, keep needs_summary)")
        except Exception as e:
            stats["failed"] += 1
            print(f"  [{i+1}] ID {aid}: ERROR - {e}")

        stats["processed"] += 1
        time.sleep(RATE_LIMIT_SEC)

    # Neon 동기화 없음 — 로컬 DB가 SSOT이고 Vercel은 devforge News Read API를
    # 직접 조회하므로 여기서는 로컬 업데이트만 수행한다.
    return stats


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Retry summary generation")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--loops", type=int, default=1, help="Number of batches to process")
    args = parser.parse_args()

    total = {"processed": 0, "success": 0, "failed": 0}

    for loop in range(args.loops):
        if args.loops > 1:
            print(f"\n=== Batch {loop+1}/{args.loops} ===")
        stats = retry_batch(dry_run=args.dry_run)
        for k in total:
            total[k] += stats[k]

        # Check if more remain
        remaining = psql_json(
            "SELECT COUNT(*) as cnt FROM news_articles WHERE pipeline_state = 'needs_summary'"
        )
        count = remaining[0]["cnt"] if remaining else 0
        if count == 0:
            print("\n[summary-retry] All articles have summaries!")
            break

        if loop < args.loops - 1:
            print(f"  {count} articles remaining, waiting before next batch...")
            time.sleep(10)

    print(f"\n[summary-retry] Total: {total['processed']} processed, {total['success']} success, {total['failed']} failed")


if __name__ == "__main__":
    main()
