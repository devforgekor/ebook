from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    NOTIFIER_API_KEY: str
    NOTIFIER_HOST: str = "127.0.0.1"
    NOTIFIER_PORT: int = 8001
    TELEGRAM_NOTICE_TOKEN: str
    TELEGRAM_CHAT_ID: str
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 465
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    EMAIL_FROM: str | None = None
    EMAIL_TO: str | None = None
    # Slack 관련 환경변수
    SLACK_BOT_TOKEN: str | None = None
    SLACK_APP_TOKEN: str | None = None  # Socket Mode용, 필요시
    SLACK_ALERT_CHANNEL: str = "#general"
    DEBUG: bool = False
    LOG_DIR: str = "logs"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8"
    }

settings = Settings()
