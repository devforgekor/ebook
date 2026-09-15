"""
공통 로거 설정 – 반드시 앱 진입점에서만 호출할 것!
"""
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from pythonjsonlogger import jsonlogger

def setup_logger(
    name: str,
    log_dir: Path,
    level: str = "INFO",
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
) -> logging.Logger:
    """
    JSONL 포맷의 로거를 설정하고 반환한다.
    - log_dir 하위에 {name}.jsonl 파일로 저장
    - RotatingFileHandler 적용
    - 콘솔에도 같은 포맷으로 출력
    - **경고**: 이 함수는 진입점(main.py, run_bot.py 등)에서 단 한 번만 호출해야 함.
      라이브러리 모듈에서 호출하면 핸들러가 중복되어 로그가 여러 번 출력됨.
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 이미 핸들러가 있으면 추가하지 않음 (중복 방지)
    if logger.handlers:
        return logger

    # 로그 디렉토리 생성
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{name}.jsonl"

    # JSON 포맷터
    formatter = jsonlogger.JsonFormatter(
        fmt='%(asctime)s %(name)s %(levelname)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        json_ensure_ascii=False
    )

    # 파일 핸들러 (Rotating)
    fh = RotatingFileHandler(
        log_file,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding='utf-8'
    )
    fh.setFormatter(formatter)
    logger.addHandler(fh)

    # 콘솔 핸들러
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    # 상위 로거로 전파 방지
    logger.propagate = False

    return logger
