from datetime import datetime, timezone
from typing import Optional
from enum import Enum

from src.core_event import CoreEvent
from src.key import build_error_signature_key
from src.state import State, Event, compute_next_state
from src.store import ErrorSignatureStore, ErrorSignatureRecord


class ExecutionResult(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"


class ExecutionContext:
    """
    한 execution 동안 유지되는 컨텍스트
    - 동일 execution에서 이벤트 1회만 보장하기 위함
    """

    def __init__(self):
        self.event_emitted: bool = False


class ErrorSignatureHandler:
    def __init__(self, store: ErrorSignatureStore):
        self.store = store

    def handle_execution_result(
        self,
        ctx: ExecutionContext,
        *,
        plane: str,
        component: str,
        source_or_model: str,
        error_type: str,
        result: ExecutionResult,
    ) -> Optional[CoreEvent]:
        """
        Retry 종료 시점 또는 execution 성공 시점에 호출된다.
        """

        # ---- 동일 execution 이벤트 중복 방지 ----
        if ctx.event_emitted:
            return None
        ctx.event_emitted = True

        # ---- error_signature key 생성 ----
        key = build_error_signature_key(
            plane=plane,
            component=component,
            source_or_model=source_or_model,
            error_type=error_type,
        )

        # ---- 상태 로드 (없으면 NONE) ----
        record: Optional[ErrorSignatureRecord] = self.store.load(key)
        prev_state: Optional[State] = record.status if record else None

        # ---- 이벤트 매핑 ----
        event = (
            Event.FAILURE
            if result == ExecutionResult.FAILURE
            else Event.SUCCESS
        )

        # ---- 상태 전이 계산 (순수 함수) ----
        next_state = compute_next_state(prev_state, event)

        # ---- 상태 저장 ----
        if record is None:
            # NONE → NEW (실패 최초 발생만 가능)
            if next_state == State.NEW:
                record = self.store.create_new(key, next_state)
            else:
                # NONE + SUCCESS 는 상태를 만들지 않음
                return None
        else:
            if event == Event.FAILURE:
                record = self.store.update_on_failure(record, next_state)
            else:
                record = self.store.update_on_success(record, next_state)

        # ---- Slack 알림 훅 (조건부) ----
        
        if self.should_notify(prev_state, next_state):
            return CoreEvent(
                error_signature=key,
                transition=(
                    "NONE→NEW"
                    if prev_state is None
                    else "RESOLVED→NEW"
                ),
                plane=plane,
                component=component,
                source_or_model=source_or_model,
                error_type=error_type,
                occurred_at_utc=datetime.now(timezone.utc),
            )

        return None


    # ---------- 알림 정책 ----------

    @staticmethod
    def should_notify(
        prev_state: Optional[State],
        next_state: State,
    ) -> bool:
        """
        Slack 알림 조건 (Step 0에서 확정된 규칙)
        """
        # NONE → NEW : First Occurrence
        if prev_state is None and next_state == State.NEW:
            return True

        # RESOLVED → NEW : Regression
        if prev_state == State.RESOLVED and next_state == State.NEW:
            return True

        return False

    # ---------- 알림 훅 ----------
    # 실제로는 Notifier 인터페이스에 CoreEvent 전달하는 형태로 구현될 예정
    
    