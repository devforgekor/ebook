from dataclasses import dataclass
from typing import List, Optional
from .models import ErrorReportItem

@dataclass(frozen=True)
class SummaryStats:
    total: int
    ongoing: int
    resolved: int

def build_summary(report: List[ErrorReportItem]) -> SummaryStats:
    total = len(report)
    ongoing = sum(1 for r in report if r.current_state == "ONGOING")
    resolved = sum(1 for r in report if r.current_state == "RESOLVED")
    return SummaryStats(total=total, ongoing=ongoing, resolved=resolved)

# Slack 1-line monthly summary DTO
@dataclass(frozen=True)
class MonthlySlackSummary:
    year: int
    month: int
    total: int
    ongoing: int
    resolved: int
    new: int
    top_increase_key: Optional[str]
    top_increase_delta: Optional[int]

def build_monthly_slack_summary(
    *,
    year: int,
    month: int,
    curr: List[ErrorReportItem],
    prev: List[ErrorReportItem],
    diff: dict,
) -> MonthlySlackSummary:
    total = len(curr)
    ongoing = sum(1 for r in curr if r.current_state == "ONGOING")
    resolved = sum(1 for r in curr if r.current_state == "RESOLVED")

    prev_keys = {r.error_signature for r in prev}
    new = sum(1 for r in curr if r.error_signature not in prev_keys)

    top_key, top_delta = None, None
    if diff.get("increased"):
        cur, prv = max(
            diff["increased"],
            key=lambda t: (t[0].occurrences - t[1].occurrences),
        )
        top_key = cur.error_signature
        top_delta = cur.occurrences - prv.occurrences

    return MonthlySlackSummary(
        year=year,
        month=month,
        total=total,
        ongoing=ongoing,
        resolved=resolved,
        new=new,
        top_increase_key=top_key,
        top_increase_delta=top_delta,
    )
