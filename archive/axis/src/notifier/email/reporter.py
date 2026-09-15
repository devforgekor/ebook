from datetime import datetime
from typing import List, Optional

from src.store import ErrorSignatureStore
from .models import ErrorReportItem
from .summary import build_summary


class EmailBatchReporter:
    def __init__(self, store: ErrorSignatureStore):
        self.store = store

    # -------- Aggregation --------
    def generate_report(self, *, start_at: datetime, end_at: datetime) -> List[ErrorReportItem]:
        records = self.store.list_between(start_at, end_at)
        return [
            ErrorReportItem(
                error_signature=r.key,
                first_seen=r.first_seen,
                last_seen=r.last_seen,
                occurrences=r.count,
                current_state=r.status.value,
            )
            for r in records
        ]

    # -------- Weekly --------
    def render_weekly_report(
        self,
        report: List[ErrorReportItem],
        *,
        start_at: datetime,
        end_at: datetime,
    ) -> str:
        title = f"[SSP] Weekly Error Report – {start_at.date()} ~ {end_at.date()}"
        lines = [title, "=" * len(title), ""]

        s = build_summary(report)
        lines += [
            "1. Executive Summary",
            "-" * 22,
            f"• Total unique error_signatures : {s.total}",
            f"• Still ongoing                 : {s.ongoing}",
            f"• Resolved during this week     : {s.resolved}",
            "",
            "2. Ongoing Issues",
            "-" * 16,
        ]

        on = [r for r in report if r.current_state == "ONGOING"]
        if not on:
            lines.append("• (none)")
        else:
            for r in on:
                lines += [
                    f"• {r.error_signature}",
                    f"  First Seen   : {r.first_seen}",
                    f"  Last Seen    : {r.last_seen}",
                    f"  Occurrences  : {r.occurrences}",
                    "",
                ]

        lines += ["3. Resolved This Week", "-" * 19]
        rs = [r for r in report if r.current_state == "RESOLVED"]
        if not rs:
            lines.append("• (none)")
        else:
            for r in rs:
                lines += [
                    f"• {r.error_signature}",
                    f"  Period      : {r.first_seen} ~ {r.last_seen}",
                    f"  Occurrences : {r.occurrences}",
                    "",
                ]

        return "\n".join(lines)

    # -------- Monthly diff helpers --------
    def compute_monthly_diff(self, prev: List[ErrorReportItem], curr: List[ErrorReportItem]) -> dict:
        pm = {r.error_signature: r for r in prev}
        cm = {r.error_signature: r for r in curr}
        inc, dec, st, new, gone = [], [], [], [], []

        for k, c in cm.items():
            if k not in pm:
                new.append(c); continue
            p = pm[k]
            d = c.occurrences - p.occurrences
            if d > 0: inc.append((c, p))
            elif d < 0: dec.append((c, p))
            if c.current_state != p.current_state: st.append((c, p))

        for k, p in pm.items():
            if k not in cm: gone.append(p)

        return {"increased": inc, "decreased": dec, "state_changed": st, "new": new, "gone": gone}

    def render_monthly_diff_section(self, diff: dict) -> List[str]:
        lines = ["2. Month-over-Month Changes", "-" * 27, ""]
        if diff["increased"]:
            lines.append("↑ Increased Occurrences")
            for c, p in diff["increased"]:
                d = c.occurrences - p.occurrences
                lines += [f"• {c.error_signature}", f"  Occurrences : {p.occurrences} → {c.occurrences} (+{d})", ""]
        if diff["decreased"]:
            lines.append("↓ Decreased Occurrences")
            for c, p in diff["decreased"]:
                d = c.occurrences - p.occurrences
                lines += [f"• {c.error_signature}", f"  Occurrences : {p.occurrences} → {c.occurrences} ({d})", ""]
        if diff["state_changed"]:
            lines.append("State Changes")
            for c, p in diff["state_changed"]:
                lines += [f"• {c.error_signature}", f"  State : {p.current_state} → {c.current_state}", ""]
        if diff["new"]:
            lines.append("New This Month")
            for c in diff["new"]: lines.append(f"• {c.error_signature}")
            lines.append("")
        if diff["gone"]:
            lines.append("Gone Since Last Month")
            for p in diff["gone"]: lines.append(f"• {p.error_signature}")
            lines.append("")
        return lines

    # -------- Monthly (FINAL) --------
    def render_monthly_report(
        self,
        report: List[ErrorReportItem],
        *,
        year: int,
        month: int,
        prev_report: Optional[List[ErrorReportItem]] = None,
    ) -> str:
        title = f"[SSP] Monthly Error Report – {year}-{month:02d}"
        lines = [title, "=" * len(title), ""]

        s = build_summary(report)
        lines += [
            "1. Executive Summary",
            "-" * 22,
            f"• Total unique error_signatures : {s.total}",
            f"• Still ongoing                : {s.ongoing}",
            f"• Resolved during this month   : {s.resolved}",
            "",
        ]

        if prev_report is not None:
            diff = self.compute_monthly_diff(prev_report, report)
            lines += self.render_monthly_diff_section(diff)
            lines.append("")

        lines += ["3. Persistent Issues (Still ONGOING)", "-" * 38]
        on = [r for r in report if r.current_state == "ONGOING"]
        if not on:
            lines.append("• (none)")
        else:
            for r in on:
                lines += [
                    f"• {r.error_signature}",
                    f"  First Seen  : {r.first_seen}",
                    f"  Last Seen   : {r.last_seen}",
                    f"  Occurrences : {r.occurrences}",
                    "",
                ]
        return "\n".join(lines)
    