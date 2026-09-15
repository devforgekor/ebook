#!/usr/bin/env python3
# core/kst_time.py
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

def now_kst() -> datetime:
    """
    현재 KST(한국 표준시) datetime 반환
    """
    return datetime.now(KST)

def now_utc() -> datetime:
    return datetime.now(UTC)

def kst_to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = KST.localize(dt)
    return dt.astimezone(UTC)

def utc_to_kst(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = UTC.localize(dt)
    return dt.astimezone(KST)

def get_kst_time() -> str:
    return now_kst().strftime("%Y-%m-%d %H:%M:%S KST")

def get_utc_time() -> str:
    return now_utc().strftime("%Y-%m-%d %H:%M:%S UTC")