import pytest
from pathlib import Path
from apps.telegrambot.config import TelegramBotConfig

class TestTelegramBotConfig(TelegramBotConfig):
    """테스트 전용 설정 (운영/개발과 완전 분리)"""
    LOG_DIR: Path = Path("/tmp/test_logs")
    DATA_DIR: Path = Path("/tmp/test_data")
    TEMP_DIR: Path = Path("/tmp/test_temp")
    TELEGRAM_TOKEN: str = "test-telegram-token"
    GEMINI_KEY: str = "test-gemini-key"
    ADMIN_CHAT_ID: str = "123456789"
    LOG_LEVEL: str = "DEBUG"
    # 필요시 추가 테스트용 설정
    model_config = {
        "env_file": None,
        "env_file_encoding": None,
        "extra": "ignore"
    }

@pytest.fixture(scope="session")
def telegrambot_config():
    return TestTelegramBotConfig()

@pytest.fixture
def temp_dir(telegrambot_config):
    path = telegrambot_config.temp_dir
    path.mkdir(parents=True, exist_ok=True)
    yield path
    # 테스트 후 정리 (필요시)
    # import shutil; shutil.rmtree(path, ignore_errors=True)
