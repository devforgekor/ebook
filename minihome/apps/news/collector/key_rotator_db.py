#!/usr/bin/env python3
# Status: production
# Path: news.collector
"""DB-backed Key Rotator — KeyRotator와 동일한 인터페이스, JSON 대신 PostgreSQL 사용."""

import time
import random
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Tuple
from lib.db import psql, psql_json, psql_ok, esc_sql

# 기존 KeyRotator와 동일한 상수
DAILY_QUOTA_THRESHOLD = 300  # seconds — >= 5min = daily quota exhaustion
ACCOUNT_RPM_INTERVAL = 3.0   # seconds between uses of keys from the same account
STALE_FAIL_SECONDS = 300     # clear fail counts older than 5 min

KST = timezone(timedelta(hours=9))


def extract_account_from_key_name(name: str) -> str:
    """Extract account prefix from key name. 기존 KeyRotator와 동일."""
    idx = name.rfind("_gemini_")
    if idx != -1:
        return name[:idx]
    if ":" in name:
        return name.split(":", 1)[0]
    return name


class DBKeyRotator:
    """
    KeyRotator와 동일한 공개 인터페이스:
    - pick() -> Optional[tuple[int, str, str]]  # (index, name, key)
    - success(idx: int)
    - rate_limited(idx: int, retry_seconds: int)
    - stats() -> dict
    """

    def __init__(self, provider: str, keys: List[Tuple[str, str]]):
        """
        Args:
            provider: 'exa', 'tavily', 'brave' 등 프로바이더 이름
            keys: [(display_name, api_key), ...] 리스트
        """
        self.provider = provider
        # Load all existing keys from DB first, then merge with provided keys
        self.keys = self._load_keys_from_db(keys)
        self.n = len(self.keys)
        self._sync_keys_to_db()

    def _load_keys_from_db(self, provided_keys: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        """DB에서 기존 키 로드하고 제공된 키와 병합"""
        sql = f"""
            SELECT key_index, key_name FROM api_key_rotations
            WHERE provider = '{esc_sql(self.provider)}'
            ORDER BY key_index
        """
        db_rows = psql_json(sql)
        
        # Build map of existing keys
        existing = {row["key_index"]: (row["key_name"], None) for row in db_rows}
        
        # Merge with provided keys
        merged = {}
        for idx, (name, key) in enumerate(provided_keys):
            if idx in existing:
                merged[idx] = (existing[idx][0], key)  # Use DB name, provided key
            else:
                merged[idx] = (name, key)
        
        # Add any extra DB keys not in provided list
        for idx, (name, _) in existing.items():
            if idx not in merged:
                merged[idx] = (name, None)  # Key from DB but no provided key
        
        # Convert to list sorted by index
        return [merged[i] for i in sorted(merged.keys())]

    def _sync_keys_to_db(self):
        """키 메타데이터 DB 동기화 (최초 1회, 키 변경 시 재실행)"""
        for idx, (name, _) in enumerate(self.keys):
            sql = f"""
                INSERT INTO api_key_rotations (provider, key_index, key_name, calls, fails)
                VALUES ('{esc_sql(self.provider)}', {idx}, '{esc_sql(name)}', 0, 0)
                ON CONFLICT (provider, key_index) DO NOTHING
            """
            psql_ok(sql)

    def _load_state_from_db(self) -> List[dict]:
        """DB에서 전체 상태 로드"""
        sql = f"""
            SELECT key_index, key_name, calls, fails, last_used, backoff_until
            FROM api_key_rotations
            WHERE provider = '{esc_sql(self.provider)}'
            ORDER BY key_index
        """
        rows = psql_json(sql)
        # timestamp 문자열을 파싱 가능한 형태로 정규화
        for row in rows:
            for field in ['last_used', 'backoff_until']:
                val = row.get(field)
                if isinstance(val, str):
                    # 이미 ISO 문자열인 경우 그대로 둠 (parse_ts가 처리)
                    pass
        return rows

    def _clear_stale_fails(self, rows: List[dict]) -> List[dict]:
        """STALE_FAIL_SECONDS 이상 사용되지 않은 키의 fail 카운트 초기화"""
        now = time.time()

        def parse_ts(val):
            if val is None:
                return 0
            if isinstance(val, (int, float)):
                return val
            if isinstance(val, str):
                try:
                    from datetime import datetime
                    return datetime.fromisoformat(val.replace('Z', '+00:00')).timestamp()
                except:
                    return 0
            if hasattr(val, 'timestamp'):
                return val.timestamp()
            return 0

        for row in rows:
            last_ts = parse_ts(row.get("last_used"))
            if last_ts and row["fails"] > 0:
                if (now - last_ts) > STALE_FAIL_SECONDS:
                    # DB 업데이트
                    sql = f"""
                        UPDATE api_key_rotations
                        SET fails = 0
                        WHERE provider = '{esc_sql(self.provider)}' AND key_index = {row["key_index"]}
                    """
                    psql_ok(sql)
                    row["fails"] = 0
        return rows

    def pick(self) -> Optional[Tuple[int, str, str]]:
        """
        다음 사용 가능한 키 반환.
        Returns: (index, name, key) 또는 None (모든 키 backoff 중)
        """
        now = time.time()
        rows = self._load_state_from_db()
        rows = self._clear_stale_fails(rows)

        def parse_ts(val):
            if val is None:
                return 0
            if isinstance(val, (int, float)):
                return val
            if isinstance(val, str):
                try:
                    from datetime import datetime
                    return datetime.fromisoformat(val.replace('Z', '+00:00')).timestamp()
                except:
                    return 0
            if hasattr(val, 'timestamp'):
                return val.timestamp()
            return 0

        # 계정별 마지막 사용 시간 계산
        account_last_used = {}
        for row in rows:
            acct = extract_account_from_key_name(row["key_name"])
            last_ts = parse_ts(row.get("last_used"))
            account_last_used[acct] = max(account_last_used.get(acct, 0), last_ts)

        # 정렬 키 구성
        def _sort_key(row: dict, acct: str) -> tuple:
            return (
                row["fails"],
                row["calls"],
                account_last_used.get(acct, 0),
                parse_ts(row.get("last_used")),
            )

        # backoff 중이 아닌 키 분리
        outside = []
        inside = []
        for row in rows:
            backoff_ts = parse_ts(row.get("backoff_until"))
            if backoff_ts > now:
                continue

            acct = extract_account_from_key_name(row["key_name"])
            acct_last = account_last_used.get(acct, 0)
            if acct_last == 0:
                in_window = False
            else:
                in_window = (now - acct_last) < ACCOUNT_RPM_INTERVAL

            sk = _sort_key(row, acct)
            if in_window:
                inside.append((sk, row))
            else:
                outside.append((sk, row))

        # Outside-window 우선, 없으면 inside-window에서 대기 후 선택
        if outside:
            pool = outside
        elif inside:
            oldest_acct_last = min(account_last_used.get(extract_account_from_key_name(r["key_name"]), 0)
                                   for _, r in inside)
            wait = ACCOUNT_RPM_INTERVAL - (now - oldest_acct_last)
            if wait > 0:
                time.sleep(wait)
            pool = inside
        else:
            return None  # 모든 키 backoff 중

        # pool의 첫 번째 요소만 정렬 (튜플의 첫 번째 요소가 정렬 키)
        pool.sort(key=lambda x: x[0])
        chosen = pool[0][1]
        idx = chosen["key_index"]

        # 키 인덱스 검증
        if idx >= len(self.keys):
            # DB에 있는 키가 더 많음 - 제공된 키 리스트와 동기화 필요
            return None

        # last_used 업데이트
        sql = f"""
            UPDATE api_key_rotations
            SET last_used = NOW()
            WHERE provider = '{esc_sql(self.provider)}' AND key_index = {idx}
        """
        psql_ok(sql)

        return idx, chosen["key_name"], self.keys[idx][1]

    def success(self, idx: int):
        """성공 호출 기록"""
        sql = f"""
            UPDATE api_key_rotations
            SET calls = calls + 1, last_used = NOW(), backoff_until = NULL
            WHERE provider = '{esc_sql(self.provider)}' AND key_index = {idx}
        """
        psql_ok(sql)

    def rate_limited(self, idx: int, retry_seconds: int):
        """429 에러 기록 및 backoff 설정"""
        sql = f"""
            UPDATE api_key_rotations
            SET fails = fails + 1
            WHERE provider = '{esc_sql(self.provider)}' AND key_index = {idx}
        """
        psql_ok(sql)

        if retry_seconds >= DAILY_QUOTA_THRESHOLD:
            # 일일 할당량 소진 — 내일 17:00 KST까지 backoff
            now_kst = datetime.now(KST)
            today_5pm = now_kst.replace(hour=17, minute=0, second=0, microsecond=0)
            if now_kst >= today_5pm:
                today_5pm += timedelta(days=1)
            backoff_until = today_5pm
        else:
            # 일시적 rate limit — 지터 적용 backoff
            jitter = retry_seconds * random.uniform(-0.2, 0.2)
            delay = max(1, retry_seconds + jitter)
            backoff_until = datetime.fromtimestamp(time.time() + delay, timezone.utc)

        backoff_str = backoff_until.isoformat()
        sql = f"""
            UPDATE api_key_rotations
            SET backoff_until = '{esc_sql(backoff_str)}'
            WHERE provider = '{esc_sql(self.provider)}' AND key_index = {idx}
        """
        psql_ok(sql)

    def stats(self) -> dict:
        """현재 회전 상태 반환 (모니터링용)"""
        now = time.time()
        rows = self._load_state_from_db()

        def parse_ts(val):
            if val is None:
                return 0
            if isinstance(val, (int, float)):
                return val
            if isinstance(val, str):
                try:
                    from datetime import datetime
                    return datetime.fromisoformat(val.replace('Z', '+00:00')).timestamp()
                except:
                    return 0
            if hasattr(val, 'timestamp'):
                return val.timestamp()
            return 0

        key_stats = []
        for row in rows:
            backoff_ts = parse_ts(row.get("backoff_until"))
            backoff_remaining = max(0.0, backoff_ts - now)
            last_used_ts = parse_ts(row.get("last_used"))

            key_stats.append({
                "index": row["key_index"],
                "name": row["key_name"],
                "calls": row["calls"],
                "fails": row["fails"],
                "last_used": last_used_ts,
                "in_backoff": backoff_remaining > 0,
                "backoff_remaining": round(backoff_remaining, 1),
            })

        total_calls = sum(ks["calls"] for ks in key_stats)
        avg_calls = total_calls / max(self.n, 1)
        active = [ks for ks in key_stats if not ks["in_backoff"]]

        return {
            "total_keys": self.n,
            "available_keys": len(active),
            "total_calls": total_calls,
            "avg_calls_per_key": round(avg_calls, 1),
            "keys": key_stats,
        }


# 하위 호환성을 위한 팩토리 함수
def create_db_key_rotator(provider: str, keys: List[Tuple[str, str]]) -> DBKeyRotator:
    """DBKeyRotator 인스턴스 생성"""
    return DBKeyRotator(provider, keys)