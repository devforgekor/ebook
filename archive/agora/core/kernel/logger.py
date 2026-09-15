import json
import logging
import sys
from pathlib import Path
from datetime import datetime
from logging.handlers import RotatingFileHandler

class JSONLFormatter(logging.Formatter):
    def __init__(self, app_name: str):
        super().__init__()
        self.app_name = app_name

    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "app": self.app_name,
            "module": record.module,
            "message": record.getMessage(),
        }
        if hasattr(record, 'extra'):
            log_entry.update(record.extra)
        if record.exc_info:
            log_entry['exc_info'] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)

def setup_logger(name: str, log_dir: Path, level=logging.INFO):
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 이미 핸들러가 설정되어 있으면 중복 추가 방지
    if logger.handlers:
        return logger

    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "service.jsonl"

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(JSONLFormatter(name))
    logger.addHandler(file_handler)

    # 콘솔 핸들러 (개발/디버그용)
    if level == logging.DEBUG:
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
        logger.addHandler(console)

    logger.propagate = False
    return logger
