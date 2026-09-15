def run_weekly_email_report() -> None:
    now_kst = datetime.now(KST)
    now_utc = now_kst.astimezone(timezone.utc)
    start_utc = now_utc - timedelta(days=7)

    store = ErrorSignatureStore()
    reporter = EmailBatchReporter(store)
    sender = EmailSender(
        smtp_host="smtp.example.com",
        sender="ssp@example.com",
    )

    report = reporter.generate_report(
        start_at=start_utc,
        end_at=now_utc,
    )

    body = reporter.render_weekly_report(
        report,
        start_at=start_utc,
        end_at=now_utc,
    )

    sender.send(
        to=["ops@example.com"],
        subject="[SSP] Weekly Error Report",
        body=body,
    )
