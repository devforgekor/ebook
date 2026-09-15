def record_token_savings(path: Path, user: str, saved: int):
    entry = {
        "user": user,
        "saved": saved,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
"""
Lean 토큰 최적화 통계 기록 모듈 (JSONL)
- 절감 토큰 수, 요청/응답 로그 등 기록
"""
import json
from pathlib import Path
from datetime import datetime
import os

STATS_DIR = Path(os.getenv("LEAN_STATS_DIR", "data/lean/stats"))
STATS_DIR.mkdir(parents=True, exist_ok=True)
STATS_FILE = STATS_DIR / "token_stats.jsonl"


def log_token_stats(request_id: str, original_tokens: int, new_tokens: int, strategy: str = None):
    entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "request_id": request_id,
        "original_tokens": original_tokens,
        "new_tokens": new_tokens,
        "token_saved": original_tokens - new_tokens,
        "strategy": strategy,
    }
    with open(STATS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
