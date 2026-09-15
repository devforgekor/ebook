import json
from datetime import datetime, timedelta
from azure.data.tables import TableClient, UpdateMode

from shared.utils.api_utils import get_env
from shared.utils.audit_utils import write_audit_log


SETTINGS_TABLE = "Settings"
SETTINGS_ROWKEY = "system"


# ✅ Settings 테이블에서 현재 설정 읽기
def _load_settings():
    conn = get_env("AzureWebJobsStorage")
    table = TableClient.from_connection_string(conn, table_name=SETTINGS_TABLE)

    try:
        row = table.get_entity(partition_key="settings", row_key=SETTINGS_ROWKEY)
        return row
    except Exception:
        return {
            "PartitionKey": "settings",
            "RowKey": SETTINGS_ROWKEY,
            "START_TIME": "08:30",
            "END_TIME": "17:30",
            "OFF_SCHEDULE": "[]",
            "HOLIDAY_RECUR": json.dumps([]),
            "HOLIDAY_CUSTOM": json.dumps([]),
            "HOLIDAY_SEOL": json.dumps({}),
            "HOLIDAY_CHUSEOK": json.dumps({}),
            "BREAK_SUMMER": json.dumps({}),
            "BREAK_WINTER": json.dumps({}),
            "BREAK_SHORT": json.dumps([])
        }


# ✅ Settings 저장
def _save_settings(entity):
    conn = get_env("AzureWebJobsStorage")
    table = TableClient.from_connection_string(conn, table_name=SETTINGS_TABLE)
    table.upsert_entity(entity, mode=UpdateMode.REPLACE)


# ✅ (공통) 날짜 범위 확장 → ["YYYY-MM-DD", ...]
def _expand_range(start: str, end: str, year: int = None):
    """
    start/end 형식:
      - MM.DD
      - YYYY.MM.DD
    year가 지정되면 MM.DD는 해당 year 기준으로 처리
    """
    # YYYY.MM.DD
    if len(start.split(".")) == 3:
        s = datetime.strptime(start, "%Y.%m.%d")
        e = datetime.strptime(end, "%Y.%m.%d")
    else:
        # MM.DD → 지정된 year 사용
        if not year:
            year = datetime.now().year
        s = datetime.strptime(f"{year}.{start}", "%Y.%m.%d")
        e = datetime.strptime(f"{year}.{end}", "%Y.%m.%d")

    days = []
    cur = s
    while cur <= e:
        days.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)
    return days


# ✅ (공통) 단일 MM.DD를 날짜로 변환
def _single_date(md: str, year: int):
    d = datetime.strptime(f"{year}.{md}", "%Y.%m.%d")
    return d.strftime("%Y-%m-%d")

