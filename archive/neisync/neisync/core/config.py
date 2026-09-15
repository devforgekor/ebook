
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    NEISync 전역 설정
    - 환경 변수 또는 .env 파일에서 자동 로드
    - 운영/테스트 환경 모두 지원
    """
    # NEIS API
    neis_api_key: str = Field(..., validation_alias='NEIS_API_KEY')
    
    # 경로
    data_root: str = Field('data', validation_alias='DATA_ROOT')
    log_dir: str = Field('data/logs', validation_alias='LOG_DIR')
    
    # HTTP
    http_timeout: float = Field(20.0, validation_alias='HTTP_TIMEOUT')
    http_max_retries: int = Field(3, validation_alias='HTTP_MAX_RETRIES')
    http_rate_per_sec: float = Field(5.0, validation_alias='HTTP_RATE_PER_SEC')
    http_burst: int = Field(5, validation_alias='HTTP_BURST')
    
    # Notifier (Phase 3에서 사용)
    notifier_enabled: bool = Field(False, validation_alias='NOTIFIER_ENABLED')
    notifier_url: str = Field('http://localhost:8001', validation_alias='NOTIFIER_URL')
    notifier_api_key: str = Field('', validation_alias='NOTIFIER_API_KEY')
    
    # 로깅
    log_level: str = Field('INFO', validation_alias='LOG_LEVEL')
    log_format: str = Field('json', validation_alias='LOG_FORMAT')
    
    model_config = SettingsConfigDict(
        env_file='.env',
        env_nested_delimiter='__',   # HTTP__TIMEOUT 형태 지원
        extra='ignore'
    )

settings = Settings()
