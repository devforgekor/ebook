import json
from datetime import datetime
from azure.data.tables import TableClient, UpdateMode
from shared.utils.api_utils import get_env


SETTINGS_TABLE = "Settings"
SETTINGS_PK = "settings"
SETTINGS_RK = "system"


class SettingsModel:
    """
    시스템 전체 Settings를 관리하는 모델 클래스.

    Settings 테이블 구조:
    PartitionKey = "settings"
    RowKey       = "system"

    저장 필드 예:
      START_TIME          → "08:30"
      END_TIME            → "17:30"
      OFF_SCHEDULE        → JSON string ["2026-02-08", ...]
      HOLIDAY_RECUR       → JSON string ["01-01","03-01"]
      HOLIDAY_CUSTOM      → JSON string ["06-10"]
      HOLIDAY_SEOL        → JSON string {"start": "02.08", "days": 3}
      HOLIDAY_CHUSEOK     → JSON string {...}
      BREAK_SUMMER        → JSON string {"start": "...", "end": "..."}
      BREAK_WINTER        → JSON string {"start": "YYYY.MM.DD", "end": "YYYY.MM.DD"}
      BREAK_SHORT         → JSON string [{"start":"MM.DD","end":"MM.DD"}, ...]
    """

    def __init__(self):
        self.conn = get_env("AzureWebJobsStorage")
        self.table = TableClient.from_connection_string(
            self.conn, table_name=SETTINGS_TABLE
        )
        self.entity = self._load()

    # ---------------------------------------------------------------------
    # ✅ Private: Settings 로드
    # ---------------------------------------------------------------------
    def _load(self):
        try:
            entity = self.table.get_entity(
                partition_key=SETTINGS_PK,
                row_key=SETTINGS_RK
            )
            return entity
        except Exception:
            # 최초 실행 시 기본값 생성
            default = {
                "PartitionKey": SETTINGS_PK,
                "RowKey": SETTINGS_RK,
                "START_TIME": "08:30",
                "END_TIME": "17:30",
                "OFF_SCHEDULE": "[]",
                "HOLIDAY_RECUR": "[]",
                "HOLIDAY_CUSTOM": "[]",
                "HOLIDAY_SEOL": "{}",
                "HOLIDAY_CHUSEOK": "{}",
                "BREAK_SUMMER": "{}",
                "BREAK_WINTER": "{}",
                "BREAK_SHORT": "[]",
                "last_updated": datetime.utcnow().isoformat()
            }
            self.table.upsert_entity(default, mode=UpdateMode.REPLACE)
            return default

    # ---------------------------------------------------------------------
    # ✅ Getter Methods
    # ---------------------------------------------------------------------
    def start_time(self) -> str:
        return self.entity.get("START_TIME", "08:30")

    def end_time(self) -> str:
        return self.entity.get("END_TIME", "17:30")

    def off_schedule(self) -> list:
        try:
            return json.loads(self.entity.get("OFF_SCHEDULE", "[]"))
        except Exception:
            return []

    def holiday_recur(self) -> list:
        return json.loads(self.entity.get("HOLIDAY_RECUR", "[]"))

    def holiday_custom(self) -> list:
        return json.loads(self.entity.get("HOLIDAY_CUSTOM", "[]"))

    def holiday_seol(self) -> dict:
        return json.loads(self.entity.get("HOLIDAY_SEOL", "{}"))

    def holiday_chuseok(self) -> dict:
        return json.loads(self.entity.get("HOLIDAY_CHUSEOK", "{}"))

    def break_summer(self) -> dict:
        return json.loads(self.entity.get("BREAK_SUMMER", "{}"))

    def break_winter(self) -> dict:
        return json.loads(self.entity.get("BREAK_WINTER", "{}"))

    def break_short(self) -> list:
        return json.loads(self.entity.get("BREAK_SHORT", "[]"))

    # ---------------------------------------------------------------------
    # ✅ Setter Methods
    # ---------------------------------------------------------------------
    def set_off_schedule(self, off_list: list):
        self.entity["OFF_SCHEDULE"] = json.dumps(off_list, ensure_ascii=False)

    def set_start_end(self, start: str, end: str):
        self.entity["START_TIME"] = start
        self.entity["END_TIME"] = end

    def set_holidays(self, body: dict):
        """updateSchedule 에서 사용"""
        for key, value in body.items():
            if isinstance(value, (dict, list)):
                self.entity[key] = json.dumps(value, ensure_ascii=False)
            else:
                self.entity[key] = value

    # ---------------------------------------------------------------------
    # ✅ Save Method
    # ---------------------------------------------------------------------
    def save(self):
        self.entity["last_updated"] = datetime.utcnow().isoformat()
        self.table.upsert_entity(self.entity, mode=UpdateMode.REPLACE)
        return True
    