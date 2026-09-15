from datetime import datetime, timedelta, timezone
from typing import Optional, Dict

from src.state import State


TTL_HOURS = 24


def utc_now() -> datetime:
    """timezone-aware UTC now"""
    return datetime.now(timezone.utc)


class ErrorSignatureRecord:
    def __init__(
        self,
        key: str,
        status: State,
        first_seen_at: datetime,
        last_seen_at: datetime,
        resolved_at: Optional[datetime],
        ttl_expires_at: datetime,
    ):
        self.key = key
        self.status = status
        self.first_seen_at = first_seen_at
        self.last_seen_at = last_seen_at
        self.resolved_at = resolved_at
        self.ttl_expires_at = ttl_expires_at


class ErrorSignatureStore:
    """
    상태 저장소 인터페이스 (현재는 in-memory mock)

    - DB 교체 시 이 클래스 내부만 변경
    - handler/state 로직은 영향 없음
    """

    def __init__(self):
        self._records: Dict[str, ErrorSignatureRecord] = {}

    # ---------- 조회 ----------

    def load(self, key: str) -> Optional[ErrorSignatureRecord]:
        """
        key에 대한 상태 조회

        - 레코드가 없거나
        - TTL이 만료된 경우

        None을 반환한다 (NONE 상태)
        """
        record = self._records.get(key)
        if not record:
            return None

        if record.ttl_expires_at <= utc_now():
            self.delete(key)
            return None

        return record

    # ---------- 저장 ----------

    def create_new(self, key: str, status: State) -> ErrorSignatureRecord:
        """
        NONE → NEW 전이 시 사용
        """
        now = utc_now()

        record = ErrorSignatureRecord(
            key=key,
            status=status,
            first_seen_at=now,
            last_seen_at=now,
            resolved_at=None,
            ttl_expires_at=now + timedelta(hours=TTL_HOURS),
        )

        self._records[key] = record
        return record

    def update_on_failure(
        self,
        record: ErrorSignatureRecord,
        next_status: State,
    ) -> ErrorSignatureRecord:
        """
        FAILURE 이벤트 처리
        """
        record.status = next_status
        record.last_seen_at = utc_now()
        return record

    def update_on_success(
        self,
        record: ErrorSignatureRecord,
        next_status: State,
    ) -> ErrorSignatureRecord:
        """
        SUCCESS 이벤트 처리
        """
        record.status = next_status
        record.resolved_at = utc_now()
        return record

    # ---------- 삭제 ----------

    def delete(self, key: str) -> None:
        self._records.pop(key, None)
