from datetime import datetime, timezone, timedelta

# -------- Timezones --------

UTC = timezone.utc
KST = timezone(timedelta(hours=9))


# -------- Now helpers --------

def utc_now() -> datetime:
    """
    timezone-aware UTC 현재 시간
    내부 저장/비교/TTL 계산용
    """
    return datetime.now(UTC)


# -------- Conversion helpers --------

def to_kst(dt_utc: datetime) -> datetime:
    """
    UTC datetime -> KST datetime 변환

    - dt_utc는 반드시 timezone-aware UTC여야 함
    """
    if dt_utc.tzinfo is None:
        raise ValueError("dt_utc must be timezone-aware UTC datetime")
    return dt_utc.astimezone(KST)


# -------- Formatting helpers (optional) --------

def format_kst(dt_utc: datetime, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    UTC datetime를 KST 문자열로 변환
    (Slack / 로그 / UI 표시용)
    """
    return to_kst(dt_utc).strftime(fmt)
