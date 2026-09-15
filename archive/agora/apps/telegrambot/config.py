# moved from core/config.py

from core.kernel.base_config import BaseAppConfig
from typing import Optional
from pathlib import Path
from pydantic import Field
from pydantic_settings import SettingsConfigDict


class TelegramBotConfig(BaseAppConfig):
    """
    TelegramBot 앱 설정 (운영/테스트 환경 모두 지원)
    - 운영: .env에서 값 로드
    - 테스트: TestTelegramBotConfig에서 오버라이드
    """
    # 필수값 (없으면 실행 안 됨)

    TELEGRAM_TOKEN: str
    GEMINI_KEY: str
    ADMIN_CHAT_ID: str
    AI_MODE: str = Field(default="gemini", description="AI 동작 모드: gemini, rest, notifier")
    GEMINI_REST_URL: str = Field(default="http://localhost:8000", description="Gemini REST API URL (REST 모드에서 사용)")

    # 선택값 (없으면 기본값 사용, 에러 방지)
    TELEGRAM_TEST_TOKEN: str = ""
    BOT_NAME: str = "telegram_bot"
    TOTAL_QUOTA: int = 20
    LOG_LEVEL: str = "INFO"
    
    LOG_DIR: Path = Path("./logs")
    DATA_DIR: Path = Path("./data")
    TEMP_DIR: Path = Path("./temp")

    @property
    def log_dir(self) -> Path:
        """앱별 로그 디렉토리 (운영/테스트 모두 지원)"""
        return self.LOG_DIR / self.BOT_NAME

    @property
    def data_dir(self) -> Path:
        """앱별 데이터 디렉토리"""
        return self.DATA_DIR / self.BOT_NAME

    @property
    def temp_dir(self) -> Path:
        """앱별 임시 디렉토리"""
        return self.TEMP_DIR / self.BOT_NAME

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

config = TelegramBotConfig()