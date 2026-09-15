from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Literal

@dataclass(frozen=True)
class CoreEvent:
    """
    Core가 외부로 방출하는 '운영 사건'
    Notifier, Bot, Batch Report의 유일한 입력 단위
    """
    error_signature: str
    transition: Literal["NONE→NEW", "RESOLVED→NEW"]
    plane: str
    component: str
    source_or_model: str
    error_type: str
    occurred_at_utc: datetime = datetime.now()
    