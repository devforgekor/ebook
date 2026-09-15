import pytest
from pathlib import Path
from apps.omnibot.config import OmnibotConfig

class TestOmnibotConfig(OmnibotConfig):
    """테스트 전용 설정 (운영/개발과 완전 분리)"""
    LOG_DIR: Path = Path("/tmp/test_logs")
    DATA_DIR: Path = Path("/tmp/test_data")
    TEMP_DIR: Path = Path("/tmp/test_temp")
    LOG_LEVEL: str = "DEBUG"
    OMNIBOT_TOKEN: str = "test-omnibot-token"
    model_config = {
        "env_file": None,
        "env_file_encoding": None,
        "extra": "ignore"
    }

@pytest.fixture(scope="session")
def omnibot_config():
    return TestOmnibotConfig()

@pytest.fixture
def temp_dir(omnibot_config):
    path = omnibot_config.temp_dir
    path.mkdir(parents=True, exist_ok=True)
    yield path
