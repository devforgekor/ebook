cat > apps/telegrambot/base_config.py <<'PY'
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class BaseAppConfig(BaseSettings):
    # 공통 설정 (기본값 제공)
    LOG_LEVEL: str = "INFO"
    LOG_DIR: Path = Path("./logs")
    DATA_DIR: Path = Path("./data")
    TEMP_DIR: Path = Path("./temp")

    # Notifier 연동
    NOTIFIER_URL: str = "http://localhost:8001"
    NOTIFIER_API_KEY: str = ""

    # pydantic v2 설정
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
PY