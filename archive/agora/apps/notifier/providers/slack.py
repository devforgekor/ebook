import logging
from apps.notifier.providers.base import NotificationProvider
from slack_sdk.web.async_client import AsyncWebClient
from apps.notifier.core.config import settings

class SlackProvider(NotificationProvider):
    def __init__(self):
        self.token = settings.SLACK_BOT_TOKEN
        self.channel = settings.SLACK_ALERT_CHANNEL
        self.client = AsyncWebClient(token=self.token)

    async def send(self, text: str) -> bool:
        logger = logging.getLogger(__name__)
        try:
            resp = await self.client.chat_postMessage(channel=self.channel, text=text)
            if resp["ok"]:
                logger.info(f"Slack message sent to {self.channel}")
                return True
            else:
                logger.error(f"Slack send failed: {resp}")
                return False
        except Exception as e:
            logger.error(f"Slack send failed: {e}")
            return False