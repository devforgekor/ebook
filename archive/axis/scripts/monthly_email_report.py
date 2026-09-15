from datetime import datetime, timedelta, timezone

from src.store import ErrorSignatureStore
from src.notifier.email.reporter import EmailBatchReporter
from src.notifier.email.sender import EmailSender
from src.notifier.email.summary import build_monthly_slack_summary
from src.notifier.slack_webhook import SlackWebhookNotifier

KST = timezone(timedelta(hours=9))
SLACK_WEBHOOK_URL = "https://hooks.slack.com/services/XXX/YYY/ZZZ"

def get_month_range(year: int, month: int):
    start_kst = datetime(year, month, 1, tzinfo=KST)
    end_kst = (datetime(year + (month==12), (month%12)+1, 1, tzinfo=KST) - timedelta(seconds=1))
    return start_kst.astimezone(timezone.utc), end_kst.astimezone(timezone.utc)

def run_monthly_email_report():
    now = datetime.now(KST)
    year, month = (now.year, now.month-1 if now.month>1 else 12)
    py, pm = (year, month-1 if month>1 else 12)

    c_s, c_e = get_month_range(year, month)
    p_s, p_e = get_month_range(py, pm)

    store = ErrorSignatureStore()
    reporter = EmailBatchReporter(store)
    sender = EmailSender("smtp.example.com", "ssp@example.com")
    slack = SlackWebhookNotifier(SLACK_WEBHOOK_URL)

    curr = reporter.generate_report(start_at=c_s, end_at=c_e)
    prev = reporter.generate_report(start_at=p_s, end_at=p_e)

    body = reporter.render_monthly_report(report=curr, year=year, month=month, prev_report=prev)
    sender.send(["ops@example.com"], f"[SSP] Monthly Error Report – {year}-{month:02d}", body)

    diff = reporter.compute_monthly_diff(prev, curr)
    slack_summary = build_monthly_slack_summary(
        year=year, month=month, curr=curr, prev=prev, diff=diff
    )
    slack.send_monthly_summary(slack_summary)
    