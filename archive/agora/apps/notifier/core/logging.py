import logging
from pathlib import Path
from .config import settings

def setup_logging():
    log_dir = Path(settings.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "api.log"

    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=2 * 1024 * 1024,  # 2MB
        backupCount=5
    )
    file_handler.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)

    logging.getLogger('').addHandler(file_handler)
    logging.getLogger('').setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)

    if settings.DEBUG:
        console = logging.StreamHandler()
        console.setLevel(logging.DEBUG)
        console.setFormatter(formatter)
        logging.getLogger('').addHandler(console)
