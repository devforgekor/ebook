# src/notifier/email/models.py
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ErrorReportItem:
    """
    Email Batch Report용 집계 단위
    (error_signature 기준)
    """
    error_signature: str
    first_seen: datetime
    last_seen: datetime
    occurrences: int
    current_state: str
    
    