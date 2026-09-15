# src/notifier/slack_webhook.py
import requests
from datetime import timedelta, timezone

from src.core_event import CoreEvent
from src.notifier.base import Notifier
from src.notifier.email.summary import MonthlySlackSummary


KST = timezone(timedelta(hours=9))


class SlackWebhookNotifier(Notifier):
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def notify(self, event: CoreEvent) -> None:
        payload = self._build_payload(event)
        self._send(payload)

    # ---------- 내부 구현 ----------

    def _send(self, payload: dict) -> None:
        response = requests.post(
            self.webhook_url,
            json=payload,
            timeout=3,
        )
        response.raise_for_status()
    
    def send_monthly_summary(self, summary: MonthlySlackSummary) -> None:
        msg = (
            f"📊 [SSP Monthly Summary {summary.year}-{summary.month:02d}] "
            f"Total: {summary.total} | Ongoing: {summary.ongoing} | "
            f"Resolved: {summary.resolved} | New: {summary.new}"
        )
        if summary.top_increase_key:
            msg += f" | ↑ Top: {summary.top_increase_key} (+{summary.top_increase_delta})"
        self._send({"text": msg})

    def _build_payload(self, event: CoreEvent) -> dict:
        header_text = (
            "🚨 SSP Error Detected"
            if event.transition == "NONE→NEW"
            else "♻️ SSP Error Regression"
        )

        occurred_kst = event.occurred_at_utc.astimezone(KST)
        occurred_str = occurred_kst.strftime("%Y-%m-%d %H:%M:%S KST")

        return {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": header_text,
                    },
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Signal*\n`{event.error_signature}`",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Type*\n{event.transition}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Plane*\n{event.plane.upper()}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Component*\n{event.component}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Model / Source*\n{event.source_or_model}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Error Type*\n{event.error_type}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Occurred At*\n{occurred_str}",
                        },
                    ],
                },
            ]
        }
    