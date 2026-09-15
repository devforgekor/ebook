

import logging
from apps.notifier.providers.base import NotificationProvider
from telegram import Bot
from apps.notifier.core.config import settings

class TelegramProvider(NotificationProvider):
    def __init__(self):
        self.bot = Bot(token=settings.TELEGRAM_NOTICE_TOKEN)
        self.chat_id = settings.TELEGRAM_CHAT_ID

    async def send(self, text: str) -> bool:
        logger = logging.getLogger(__name__)
        try:
            await self.bot.send_message(chat_id=self.chat_id, text=text)
            logger.info(f"Telegram message sent to {self.chat_id}")
            return True
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")
            return False
