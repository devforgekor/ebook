import logging
from apps.notifier.providers.base import NotificationProvider
from apps.notifier.core.config import settings
from apps.notifier.notion_client_adapter import NotionAdapter

class NotionProvider(NotificationProvider):
    def __init__(self):
        self.token = settings.NOTION_API_TOKEN
        self.database_id = settings.NOTION_DATABASE_ID
        self.logger = logging.getLogger(__name__)
        self.notion = NotionAdapter(self.token, self.database_id, self.logger)

    async def send(self, text: str) -> bool:
        try:
            # Notion에 간단히 로그 남기기 (title, message)
            self.notion.create_log_entry(
                title="Notifier API",
                severity="info",
                source="notifier",
                message=text,
                user=None,
                slack_ts=None,
                channel=None,
            )
            self.logger.info("Notion log entry created")
            return True
        except Exception as e:
            self.logger.error(f"Notion send failed: {e}")
            return False
