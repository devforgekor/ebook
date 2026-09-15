
import logging
from apps.notifier.providers.base import NotificationProvider
import aiosmtplib
from email.message import EmailMessage
from apps.notifier.core.config import settings

logger = logging.getLogger(__name__)

class EmailProvider(NotificationProvider):
    async def send(self, text: str) -> bool:
        if not all([
            settings.SMTP_HOST, settings.SMTP_USER, settings.SMTP_PASSWORD,
            settings.EMAIL_FROM, settings.EMAIL_TO
        ]):
            logger.error("Email credentials not fully configured")
            return False
        msg = EmailMessage()
        msg["From"] = settings.EMAIL_FROM
        msg["To"] = settings.EMAIL_TO
        msg["Subject"] = "알림"
        msg.set_content(text)
        try:
            send_kwargs = dict(
                msg=msg,
                hostname=settings.SMTP_HOST,
                port=settings.SMTP_PORT,
                username=settings.SMTP_USER,
                password=settings.SMTP_PASSWORD,
            )
            # 포트에 따라 TLS/STARTTLS 분기
            if settings.SMTP_PORT == 465:
                send_kwargs["use_tls"] = True
            else:
                send_kwargs["start_tls"] = True
            await aiosmtplib.send(**send_kwargs)
            logger.info(f"Email sent to {settings.EMAIL_TO}")
            return True
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return False
