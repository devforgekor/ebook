from pydantic_settings import BaseSettings
from pathlib import Path
import os

class BaseAppConfig(BaseSettings):
    # 공통 설정
    LOG_LEVEL: str = "INFO"
    LOG_DIR: Path = Path("./logs")      # 프로젝트 루트 기준
    DATA_DIR: Path = Path("./data")
    TEMP_DIR: Path = Path("./temp")

    # Notifier 연동
    NOTIFIER_URL: str = "http://localhost:8001"
    NOTIFIER_API_KEY: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"
