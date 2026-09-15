#!/usr/bin/env python3
# Status: production
# Path: news.collector
"""JSON 상태 파일 → DB 마이그레이션 스크립트.

기존 exa_state.json, tavily_state.json, brave_state.json을
api_key_rotations 테이블로 마이그레이션.
"""

import json
import os
import sys
from pathlib import Path

# Add scripts/ to path for lib imports
_SCRIPTS = "/opt/projects/server/scripts"
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from lib.db import psql_json, psql_ok, esc_sql

STATE_FILES = {
    "exa": "/opt/workspace/minihome/apps/news/exa_state.json",
    "tavily": "/opt/workspace/minihome/apps/news/tavily_state.json",
    "brave": "/opt/workspace/minihome/apps/news/brave_state.json",
}


def migrate_state_file(provider: str, filepath: str) -> bool:
    """단일 상태 파일 마이그레이션"""
    path = Path(filepath)
    if not path.exists():
        print(f"  [migrate] {provider}: 파일 없음 ({filepath}), 스킵")
        return True

    try:
        with open(path) as f:
            state = json.load(f)
    except Exception as e:
        print(f"  [migrate] {provider}: JSON 파싱 실패 - {e}")
        return False

    calls = state.get("_calls", {})
    fails = state.get("_fails", {})
    last_used = state.get("_last_used", {})
    backoff_until = state.get("_backoff_until", {})

    print(f"  [migrate] {provider}: {len(calls)}개 키 마이그레이션 중...")

    for key_str, call_count in calls.items():
        idx = int(key_str)
        fail_count = fails.get(key_str, 0)
        last_used_ts = last_used.get(key_str, 0)
        backoff_ts = backoff_until.get(key_str, 0)

        # timestamp를 ISO 문자열로 변환
        last_used_str = None
        if last_used_ts:
            from datetime import datetime, timezone
            last_used_str = datetime.fromtimestamp(last_used_ts, timezone.utc).isoformat()

        backoff_str = None
        if backoff_ts:
            from datetime import datetime, timezone
            backoff_str = datetime.fromtimestamp(backoff_ts, timezone.utc).isoformat()

        # 키 이름 조회 (기존 상태 파일에 name 정보가 없으므로 인덱스로 추정)
        key_name = f"{provider}-{idx}"

        # DB에 저장 (ON CONFLICT DO UPDATE) - esc_sql로 이스케이프
        sql = f"""
            INSERT INTO api_key_rotations (provider, key_index, key_name, calls, fails, last_used, backoff_until)
            VALUES ('{esc_sql(provider)}', {idx}, '{esc_sql(key_name)}', {call_count}, {fail_count},
                    {f"'{esc_sql(last_used_str)}'" if last_used_str else 'NULL'},
                    {f"'{esc_sql(backoff_str)}'" if backoff_str else 'NULL'})
            ON CONFLICT (provider, key_index) DO UPDATE SET
                calls = EXCLUDED.calls,
                fails = EXCLUDED.fails,
                last_used = EXCLUDED.last_used,
                backoff_until = EXCLUDED.backoff_until,
                updated_at = NOW()
        """
        psql_ok(sql)

    print(f"  [migrate] {provider}: 완료")
    return True


def verify_migration(provider: str) -> bool:
    """마이그레이션 검증"""
    sql = f"""
        SELECT key_index, key_name, calls, fails, last_used, backoff_until
        FROM api_key_rotations
        WHERE provider = '{esc_sql(provider)}'
        ORDER BY key_index
    """
    rows = psql_json(sql)

    if not rows:
        print(f"  [verify] {provider}: 데이터 없음")
        return False

    print(f"  [verify] {provider}: {len(rows)}개 키 확인")
    for r in rows:
        backoff = r.get("backoff_until")
        backoff_str = backoff.isoformat() if backoff else "None"
        print(f"    key_index={r['key_index']}, name={r['key_name']}, calls={r['calls']}, fails={r['fails']}, backoff={backoff_str}")
    return True


def backup_and_remove_json(provider: str, filepath: str):
    """원본 JSON 백업 후 삭제"""
    path = Path(filepath)
    if path.exists():
        backup_path = path.with_suffix(".json.bak")
        path.rename(backup_path)
        print(f"  [cleanup] {provider}: {filepath} → {backup_path} (백업 완료)")


def main():
    print("[migrate] Starting JSON → DB migration...")
    print(f"[migrate] Target files: {list(STATE_FILES.values())}")

    all_ok = True
    for provider, filepath in STATE_FILES.items():
        print(f"\n[migrate] Processing {provider}...")
        if not migrate_state_file(provider, filepath):
            all_ok = False

    if not all_ok:
        print("\n[migrate] 일부 마이그레이션 실패!")
        sys.exit(1)

    print("\n[migrate] Verification...")
    for provider in STATE_FILES.keys():
        verify_migration(provider)

    print("\n[migrate] Backup & cleanup...")
    for provider, filepath in STATE_FILES.items():
        backup_and_remove_json(provider, filepath)

    print("\n[migrate] All done!")


if __name__ == "__main__":
    main()