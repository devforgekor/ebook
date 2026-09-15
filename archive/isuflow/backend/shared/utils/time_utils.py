import os
from datetime import datetime, time
import json
from shared.utils.api_utils import get_env


# ✅ 문자열(HH:MM) → time 객체 변환
def _to_time(val: str) -> time:
    h, m = val.split(":")
    return time(hour=int(h), minute=int(m))


# ✅ OFF_SCHEDULE 로딩 (YYYY-MM-DD 리스트)
def _load_off_schedule():
    raw = get_env("OFF_SCHEDULE_JSON", required=False)
    if not raw:
        return []
    try:
        return json.loads(raw)
    except Exception:
        return []


# ✅ Settings 에서 START_TIME, END_TIME 로딩
def _load_operating_hours():
    start_raw = get_env("START_TIME", required=False) or "08:30"
    end_raw = get_env("END_TIME", required=False) or "17:30"
    return _to_time(start_raw), _to_time(end_raw)


# ✅ 오늘 날짜 OFF_SCHEDULE / 주말 여부 검사
def _is_off_today(off_schedule: list) -> bool:
    today = datetime.now().date()

    # ✅ 주말 OFF
    if today.weekday() >= 5:  # 5=토, 6=일
        return True

    # ✅ OFF_SCHEDULE 포함 여부
    today_str = today.strftime("%Y-%m-%d")
    if today_str in off_schedule:
        return True

    return False


# ✅ 운영시간 체크 (IsuFlow 핵심)
def is_open() -> bool:
    off_schedule = _load_off_schedule()
    start_t, end_t = _load_operating_hours()

    now = datetime.now()
    now_t = now.time()

    # ✅ 날짜 OFF
    if _is_off_today(off_schedule):
        return False

    # ✅ 시간 범위
    if not (start_t <= now_t < end_t):
        return False

    return True


# ✅ START_TIME 기반 warmup 스케줄 계산
def get_start_time_warmup_schedule():
    start_raw = get_env("START_TIME", required=False) or "08:30"
    h, m = start_raw.split(":")
    st = datetime.now().replace(hour=int(h), minute=int(m), second=0, microsecond=0)

    return {
        "http_1": st.replace(minute=st.minute - 5),
        "queue_1": st.replace(minute=st.minute - 3),
        "http_2": st.replace(minute=st.minute + 1),
        "queue_2": st.replace(minute=st.minute + 2),
        "queue_loop": st.replace(minute=st.minute + 8),
        "http_loop": st.replace(minute=st.minute + 15),
    }

