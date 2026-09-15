from datetime import datetime, timedelta, timezone

from src.store import ErrorSignatureStore
from src.notifier.email.reporter import EmailBatchReporter
from src.notifier.email.sender import EmailSender


def run_weekly_report():
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=7)

    store = ErrorSignatureStore()
    reporter = EmailBatchReporter(store)
    sender = EmailSender(
        smtp_host="smtp.example.com",
        sender="ssp@example.com",
    )

    report = reporter.generate_report(
        start_at=start,
        end_at=now,
    )

    body = reporter.render_text(
        report,
        title="[SSP] Weekly Error Report",
    )

    sender.send(
        to=["ops@example.com"],
        subject="[SSP] Weekly Error Report",
        body=body,
    )


if __name__ == "__main__":
    run_weekly_report()

