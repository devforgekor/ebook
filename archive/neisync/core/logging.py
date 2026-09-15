import json
import logging
import re
import time
import gzip
import hashlib
import os
import socket
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from logging import LogRecord, LoggerAdapter
from neisync.core.config import settings

# 민감정보 마스킹 패턴
SENSITIVE_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'Bearer\s+[A-Za-z0-9\-\._]+'), 'Bearer <REDACTED>'),
    (re.compile(r'(NEIS_API_KEY\s*[:=]\s*)\S+', re.IGNORECASE), r'\1<REDACTED>'),
    (re.compile(r'\b(sk|rk)_[A-Za-z0-9]{18,}\b'), '<REDACTED_TOKEN>'),
    (re.compile(r'[0-9a-fA-F]{32,}'), '<REDACTED_HEX>'),
]

def redact(text: str) -> str:
    for pattern, replacement in SENSITIVE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text

class JsonFormatter(logging.Formatter):
    def format(self, record: LogRecord) -> str:
        log_obj = {
            'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(record.created)),
            'lvl': record.levelname,
            'name': record.name,
            'msg': redact(record.getMessage()),
        }
        if record.exc_info:
            log_obj['exc'] = self.formatException(record.exc_info)
        if hasattr(record, 'extra'):
            log_obj.update(record.extra)
        return json.dumps(log_obj, ensure_ascii=False)

class JsonlRotator:
    """JSONL 파일 로테이터 (크기, 시간, 행 수 기준)"""
    def __init__(self, base_dir: Path, name: str,
                 max_bytes: int = 10 * 1024 * 1024,
                 max_duration: int = 3600,
                 max_rows: int = 100000):
        self.base_dir = Path(base_dir)
        self.name = name
        self.max_bytes = max_bytes
        self.max_duration = max_duration
        self.max_rows = max_rows
        self.open_path: Optional[Path] = None
        self.final_path: Optional[Path] = None
        self.file_handle = None
        self.start_time = 0.0
        self.rows = 0
        self.size = 0
        self._new_file()
    
    def _new_file(self):
        if self.file_handle:
            self._finalize_file()
        timestamp = time.strftime('%Y%m%dT%H%M%S', time.gmtime())
        self.open_path = self.base_dir / f"{self.name}-{timestamp}-{os.getpid():05d}.open.jsonl"
        self.open_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_handle = open(self.open_path, 'a', encoding='utf-8')
        self.start_time = time.monotonic()
        self.rows = 0
        self.size = 0
    
    def write(self, record: Dict[str, Any]):
        if self._should_roll():
            self._new_file()
        line = json.dumps(record, ensure_ascii=False) + '\n'
        self.file_handle.write(line)
        self.file_handle.flush()
        os.fsync(self.file_handle.fileno())
        self.rows += 1
        self.size += len(line.encode('utf-8'))
    
    def _should_roll(self) -> bool:
        return (self.size >= self.max_bytes or
                self.rows >= self.max_rows or
                (time.monotonic() - self.start_time) >= self.max_duration)
    
    def _finalize_file(self):
        if not self.file_handle:
            return
        self.file_handle.close()
        self.file_handle = None
        final_name = self.open_path.name.replace('.open.jsonl', '.jsonl.gz')
        self.final_path = self.open_path.parent / final_name
        with open(self.open_path, 'rb') as src, gzip.open(self.final_path, 'wb') as dst:
            dst.writelines(src)
        sha256 = hashlib.sha256()
        with gzip.open(self.final_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        meta = {
            'file': final_name,
            'sha256': sha256.hexdigest(),
            'rows': self.rows,
            'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'host': socket.gethostname(),
            'codec': 'gzip'
        }
        meta_path = self.final_path.with_suffix(self.final_path.suffix + '.meta.json')
        with open(meta_path, 'w', encoding='utf-8') as f:
            json.dump(meta, f, ensure_ascii=False)
        self.open_path.unlink()
        self.open_path = None
    
    def close(self):
        self._finalize_file()

_rotators: Dict[str, JsonlRotator] = {}

def get_logger(name: str, **context) -> LoggerAdapter:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return LoggerAdapter(logger, context)

def get_file_logger(name: str) -> JsonlRotator:
    if name not in _rotators:
        log_dir = Path(settings.log_dir)
        _rotators[name] = JsonlRotator(log_dir, name)
    return _rotators[name]

def cleanup_orphan_logs():
    log_dir = Path(settings.log_dir)
    for open_file in log_dir.glob('*.open.jsonl'):
        try:
            gz_path = open_file.with_suffix('.jsonl.gz')
            with open(open_file, 'rb') as src, gzip.open(gz_path, 'wb') as dst:
                dst.writelines(src)
            meta_path = gz_path.with_suffix(gz_path.suffix + '.meta.json')
            with open(meta_path, 'w') as f:
                json.dump({'recovered': True, 'original': open_file.name}, f)
            open_file.unlink()
            print(f"[복구] {open_file} → {gz_path}")
        except Exception as e:
            print(f"[오류] {open_file} 복구 실패: {e}")
