"""
Pydantic Settings 기반 lean 앱 설정
환경변수 및 .env 파일 자동 로드
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

class LeanAppSettings(BaseSettings):
    REDIS_URL: str = "redis://localhost:6379"
    LEAN_STREAM: str = "lean:optimize"
    LEAN_RESULT_STREAM: str = "lean:result"
    LEAN_GROUP: str = "lean-workers"
    LEAN_WORKER_COUNT: int = 2
    LEAN_DLQ: str = "lean:deadletter"
    LOG_DIR: str = "logs/lean"
    TEMP_DIR: str = "temp/lean"
    DATA_DIR: str = "data/lean"
    DEBUG: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = LeanAppSettings()
