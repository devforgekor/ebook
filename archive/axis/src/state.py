from enum import Enum
from typing import Optional


class State(str, Enum):
    NEW = "NEW"
    ONGOING = "ONGOING"
    RESOLVED = "RESOLVED"


class Event(str, Enum):
    FAILURE = "FAILURE"
    SUCCESS = "SUCCESS"


def compute_next_state(
    prev_state: Optional[State],
    event: Event,
) -> State:
    """
    prev_state:
      - None: 상태 레코드가 없음 (= NONE)
      - State.NEW | State.ONGOING | State.RESOLVED

    event:
      - Event.FAILURE
      - Event.SUCCESS
    """

    # NONE 상태 (레코드 없음)
    if prev_state is None:
        if event == Event.FAILURE:
            return State.NEW
        else:
            # NONE + SUCCESS는 의미 없음 → 상태 생성 안 함
            return State.RESOLVED  # 실제로는 store 단계에서 무시해도 됨

    # 기존 상태가 있을 때
    if prev_state == State.NEW:
        if event == Event.FAILURE:
            return State.ONGOING
        else:  # SUCCESS
            return State.RESOLVED

    if prev_state == State.ONGOING:
        if event == Event.FAILURE:
            return State.ONGOING
        else:  # SUCCESS
            return State.RESOLVED

    if prev_state == State.RESOLVED:
        if event == Event.FAILURE:
            return State.NEW  # Regression
        else:  # SUCCESS
            return State.RESOLVED

    # 안전 장치 (여기까지 올 일 없음)
    raise ValueError(f"Unhandled transition: {prev_state}, {event}")
