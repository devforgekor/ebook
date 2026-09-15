from core.kernel.base_config import BaseAppConfig
from pathlib import Path
from pydantic_settings import SettingsConfigDict

class ChronicleConfig(BaseAppConfig):
    """
    Chronicle 앱 설정 (운영/테스트 환경 모두 지원)
    - 운영: .env에서 값 로드
    - 테스트: TestChronicleConfig에서 오버라이드
    """
    # 필수값
    REDIRECT_URI: str
    # 필요시 추가 필드 선언
    BOT_NAME: str = "chronicle"
    LOG_LEVEL: str = "INFO"
    TOTAL_QUOTA: int = 100

    LOG_DIR: Path = Path("./logs")
    DATA_DIR: Path = Path("./data")
    TEMP_DIR: Path = Path("./temp")

    @property
    def log_dir(self) -> Path:
        return self.LOG_DIR / self.BOT_NAME

    @property
    def data_dir(self) -> Path:
        return self.DATA_DIR / self.BOT_NAME

    @property
    def temp_dir(self) -> Path:
        return self.TEMP_DIR / self.BOT_NAME

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

config = ChronicleConfig()
