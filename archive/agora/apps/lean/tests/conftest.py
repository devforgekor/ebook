import pytest
from pathlib import Path
from apps.lean.config import LeanConfig

class TestLeanConfig(LeanConfig):
    """테스트 전용 설정 (운영/개발과 완전 분리)"""
    LOG_DIR: Path = Path("/tmp/test_logs")
    DATA_DIR: Path = Path("/tmp/test_data")
    TEMP_DIR: Path = Path("/tmp/test_temp")
    LOG_LEVEL: str = "DEBUG"
    LEAN_STREAM: str = "test:lean:stream"
    LEAN_RESULT_STREAM: str = "test:lean:result"
    LEAN_GROUP: str = "test-lean-group"
    LEAN_WORKER_COUNT: int = 1
    LEAN_DLQ: str = "test:lean:deadletter"
    model_config = {
        "env_file": None,
        "env_file_encoding": None,
        "extra": "ignore"
    }

@pytest.fixture(scope="session")
def lean_config():
    return TestLeanConfig()

@pytest.fixture
def temp_dir(lean_config):
    path = lean_config.temp_dir
    path.mkdir(parents=True, exist_ok=True)
    yield path
