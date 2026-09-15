import json
import tempfile
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    """JSONL 파일 읽기"""
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

def append_jsonl(path: Path, rows: List[Dict[str, Any]]):
    """JSONL 파일에 행 추가"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

def atomic_write_jsonl(path: Path, rows: List[Dict[str, Any]]):
    """원자적 쓰기: 임시 파일에 쓴 후 교체"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', delete=False, dir=path.parent, encoding='utf-8') as tf:
        for row in rows:
            tf.write(json.dumps(row, ensure_ascii=False) + '\n')
        temp_name = tf.name
    os.replace(temp_name, path)  # Unix에서 원자적 교체

def read_json(path: Path, default: Optional[Dict] = None) -> Dict:
    if not path.exists():
        return default or {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default or {}

def write_json(path: Path, data: Dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
