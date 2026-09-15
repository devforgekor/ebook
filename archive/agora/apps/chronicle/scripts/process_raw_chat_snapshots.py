#!/usr/bin/env python3
"""Process raw chat snapshots into chat datasets.

Raw files are produced by realtime logger and stored in JSON format.
This worker reads unprocessed raw files, extracts turns, and writes
processed chat JSONL outputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import unicodedata
from pathlib import Path
from apps.chronicle.scripts.token_utils import clean_text, count_tokens
import os
import httpx
import asyncio
def write_heartbeat(status: str, info: str = "", state_dir=Path(__file__).parent.parent / "data/chronicle/state"):
    """상태(heartbeat) 파일을 기록합니다."""
    from datetime import datetime
    state_dir.mkdir(parents=True, exist_ok=True)
    heartbeat = {
        "status": status,
        "info": info,
        "timestamp": datetime.now().isoformat()
    }
    with open(state_dir / "raw_process_heartbeat.json", "w", encoding="utf-8") as f:
        json.dump(heartbeat, f, ensure_ascii=False, indent=2)

async def send_notifier_alert(message, channel="telegram"):
    NOTIFIER_URL = os.getenv("NOTIFIER_URL", "http://localhost:8001")
    NOTIFIER_API_KEY = os.getenv("NOTIFIER_API_KEY", "")
    if not NOTIFIER_API_KEY:
        print("[경고] NOTIFIER_API_KEY 환경변수가 설정되지 않았습니다.")
        return
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{NOTIFIER_URL}/v1/notify",
                json={"text": message, "channel": channel},
                headers={"Authorization": f"Bearer {NOTIFIER_API_KEY}"}
            )
            resp.raise_for_status()
            print(f"[알림] Notifier로 전송 완료: {message[:40]}")
        except Exception as e:
            print(f"[에러] Notifier 알림 실패: {e}")
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Constants
DEFAULT_MAX_GAP_SECONDS = 10
SYSTEM_PROMPT = "You are a helpful and concise assistant. Always follow project instructions and maintain a professional tone."


def load_existing_output_rows(path: Path) -> list[dict[str, Any]]:
    """Legacy: Load existing output rows. Now mostly unused due to append-only mode, 
    but kept for potential migrations or manual merges."""
    if not path.exists():
        return []

    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    rows.append(obj)
            except Exception:
                continue
    return rows


def merge_output_rows(
    existing_rows: list[dict[str, Any]],
    new_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Legacy: Merge existing and new rows with deduplication.
    Used in tests and manual processing scripts."""
    merged: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()

    def extract_dedup_hash(row: dict[str, Any]) -> str | None:
        metadata = row.get("metadata")
        if not isinstance(metadata, dict):
            return None
        dedup_hash = metadata.get("dedup_hash")
        if isinstance(dedup_hash, str) and dedup_hash.strip():
            return dedup_hash.strip()
        return None

    # Process all rows: existing first, then new
    for row in existing_rows + new_rows:
        dedup_hash = extract_dedup_hash(row)
        if dedup_hash:
            if dedup_hash in seen_hashes:
                continue
            seen_hashes.add(dedup_hash)
        merged.append(row)

    return merged


# --- Import from sibling script ---
# Add current directory to path to ensure import works during execution
script_dir = Path(__file__).parent.absolute()
if str(script_dir) not in sys.path:
    sys.path.insert(0, str(script_dir))

from dataclasses import dataclass

@dataclass
class Turn:
    session_id: str
    turn_index: int
    timestamp: str | None
    user_ko: str
    assistant_ko: str
    tool_ids: list[str]
    file_refs: list[str]

def extract_turns_from_rows(rows, fallback_session_id="unknown"):
    turns = []
    for idx, row in enumerate(rows):
        v = row.get("v", {}) if isinstance(row, dict) else {}
        session_id = v.get("sessionId", fallback_session_id)
        requests = v.get("requests", [])
        for req in requests:
            user = req.get("message", [{}])[0].get("text", "")
            assistant = req.get("response", [{}])[0].get("text", "")
            timestamp = str(req.get("timestamp", None))
            turns.append(Turn(
                session_id=session_id,
                turn_index=idx,
                timestamp=timestamp,
                user_ko=user,
                assistant_ko=assistant,
                tool_ids=[],
                file_refs=[]
            ))
    return turns

def extract_reasoning(text):
    import re
    reasoning_match = re.search(r"\[THOUGHT\](.*?)\[/THOUGHT\]", text)
    reasoning = reasoning_match.group(1).strip() if reasoning_match else ""
    answer = re.sub(r"\[THOUGHT\].*?\[/THOUGHT\]", "", text).strip()
    return answer, reasoning

def build_reasoning_en(turn):
    return f"session:{turn.session_id}, tool_ids:{turn.tool_ids}, file_refs:{turn.file_refs}"

def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


# --- Utility Functions ---









def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process raw chat snapshots")
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path(__file__).parent.parent / "data/chronicle/raw",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent.parent / "data/chronicle/processed",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path(__file__).parent.parent / "data/chronicle/state/raw_process_state.json",
    )
    parser.add_argument(
        "--include-ko",
        action="store_true",
        help="Also generate Korean review dataset",
    )
    return parser.parse_args()


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_raw_snapshot(path: Path) -> list[Turn]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

    files = payload.get("files", []) if isinstance(payload, dict) else []
    if not isinstance(files, list):
        return []

    turns: list[Turn] = []
    for item in files:
        if not isinstance(item, dict):
            continue
        rel = str(item.get("relative_path") or "unknown")
        content = item.get("content")
        if not isinstance(content, str):
            continue

        rows: list[Any] = []
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue

        fallback = Path(rel).stem
        turns.extend(extract_turns_from_rows(rows, fallback_session_id=fallback))
    return turns


def pick_sector_timestamp(sector: list[dict[str, Any]]) -> str | None:
    for turn in sector:
        ts = turn.get("timestamp")
        if isinstance(ts, str) and ts.strip():
            return ts.strip()
    return None


def load_existing_seen_hashes(path: Path) -> set[str]:
    """Load seen hashes from a .seen_hashes.jsonl file."""
    hashes = set()
    if not path.exists():
        return hashes
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                h = line.strip()
                if h:
                    hashes.add(h)
    except Exception as e:
        logger.error(f"Failed to load seen hashes from {path}: {e}")
    return hashes


def append_seen_hashes(path: Path, new_hashes: list[str]) -> None:
    """Append new hashes to the .seen_hashes.jsonl file."""
    if not new_hashes:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("a", encoding="utf-8") as f:
            for h in new_hashes:
                f.write(h + "\n")
    except Exception as e:
        logger.error(f"Failed to append seen hashes to {path}: {e}")


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Append rows to a JSONL file."""
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("a", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"Failed to append to {path}: {e}")


def split_by_time_gap(turns_list: list[dict[str, Any]], max_gap: int = DEFAULT_MAX_GAP_SECONDS) -> list[list[dict[str, Any]]]:
    if not turns_list:
        return []
    # Sort by turn_index then timestamp
    turns_list.sort(key=lambda x: (int(x.get("turn_index") or 0), x.get("timestamp") or ""))
    
    sectors = []
    current = [turns_list[0]]
    
    def parse_ts(ts):
        if not ts: return 0
        try:
            # ISO format or float string
            if 'T' in ts:
                return datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp()
            return float(ts)
        except Exception:
            return 0

    for i in range(1, len(turns_list)):
        prev_ts = parse_ts(turns_list[i-1].get("timestamp"))
        curr_ts = parse_ts(turns_list[i].get("timestamp"))
        
        if curr_ts - prev_ts > max_gap and prev_ts > 0 and curr_ts > 0:
            sectors.append(current)
            current = [turns_list[i]]
        else:
            current.append(turns_list[i])
    
    if current:
        sectors.append(current)
    return sectors


def write_processed(turns: list[Turn], output_dir: Path, include_ko: bool = False) -> dict[str, Any]:
    now_iso = datetime.now().astimezone().isoformat()
    
    # 1. Group turns by session
    sessions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for t in turns:
        assistant_raw = getattr(t, "assistant_ko", "")
        assistant_clean, reasoning = extract_reasoning(assistant_raw)
        
        turn_data = {
            "user": clean_text(getattr(t, "user_ko", "")),
            "assistant": clean_text(assistant_clean),
            "reasoning": reasoning,
            "timestamp": t.timestamp,
            "turn_index": t.turn_index,
            "session_id": t.session_id,
        }
        sessions[t.session_id].append(turn_data)

    # 2. Split sessions into sectors (max_gap gap)
    new_output_rows = []
    new_hashes = []
    
    out_path = output_dir / "chat_ko_review.jsonl"
    hash_path = out_path.with_suffix(".seen_hashes.jsonl")
    
    seen_hashes = load_existing_seen_hashes(hash_path)
    total_turns = 0

    for session_id, session_turns in sessions.items():
        sectors = split_by_time_gap(session_turns)
        for sector_idx, sector in enumerate(sectors):
            messages = []
            if SYSTEM_PROMPT:
                messages.append({"role": "system", "content": SYSTEM_PROMPT})
                
            reasoning_blobs = []
            
            for turn in sector:
                if turn["user"]:
                    messages.append({"role": "user", "content": turn["user"]})
                if turn["assistant"]:
                    messages.append({"role": "assistant", "content": turn["assistant"]})
                if turn["reasoning"]:
                    reasoning_blobs.append(turn["reasoning"])
                total_turns += 1

            if not messages:
                continue

            # Deduplication hash for rows produced in this run
            msg_json = json.dumps(messages, sort_keys=True)
            dedup_hash = hashlib.sha256(msg_json.encode()).hexdigest()
            if dedup_hash in seen_hashes:
                continue
            seen_hashes.add(dedup_hash)
            new_hashes.append(dedup_hash)

            token_count = count_tokens(messages)
            sector_timestamp = pick_sector_timestamp(sector)

            output_obj = {
                "messages": messages,
                "timestamp": sector_timestamp,
                "created_at": now_iso,
                "metadata": {
                    "session_id": session_id,
                    "sector_idx": sector_idx,
                    "turn_count": len(sector),
                    "token_count": token_count,
                    "dedup_hash": dedup_hash,
                    "cache_key": hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest(),
                    "timestamp": sector_timestamp,
                    "created_at": now_iso,
                    "reasoning": reasoning_blobs if isinstance(reasoning_blobs, list) and reasoning_blobs else None
                }
            }
            new_output_rows.append(output_obj)

    append_jsonl(out_path, new_output_rows)
    append_seen_hashes(hash_path, new_hashes)

    # 4. Save manifest
    manifest = output_dir / "chat_manifest.json"
    manifest_data = {
        "generated_at": now_iso,
        "source": "raw_snapshots",
        "new_sessions": len(sessions),
        "new_sectors": len(new_output_rows),
        "total_turns": total_turns,
        "output_file": str(out_path),
    }
    save_json(manifest, manifest_data)

    # total_rows_written 추가 반환
    manifest_data["total_rows_written"] = len(new_output_rows)
    return manifest_data


def main() -> int:
    args = parse_args()
    raw_dir = args.raw_dir
    state = load_json(args.state_file, default={"processed": {}})
    processed_map = state.setdefault("processed", {})

    try:
        if not raw_dir.exists():
            logger.error(f"Directory not found: {raw_dir}")
            write_heartbeat("error", f"Directory not found: {raw_dir}")
            async def alert_error():
                await send_notifier_alert(f"[에러] raw_process_worker 실패: Directory not found: {raw_dir}")
            asyncio.run(alert_error())
            return 1

        raw_files = sorted(raw_dir.glob("raw_*.json"))
        raw_paths = {str(p) for p in raw_files}
        
        all_turns: list[Turn] = []
        new_count = 0
        
        for raw_file in raw_files:
            stat = raw_file.stat()
            key = str(raw_file)
            marker = f"{stat.st_mtime}:{stat.st_size}"
            
            if processed_map.get(key, {}).get("marker") == marker:
                continue
                
            turns = parse_raw_snapshot(raw_file)
            if turns:
                all_turns.extend(turns)
                processed_map[key] = {
                    "marker": marker,
                    "processed_at": datetime.now().astimezone().isoformat(),
                }
                new_count += 1

        # Cleanup stale entries in state
        stale_keys = [k for k in processed_map.keys() if k not in raw_paths]
        for k in stale_keys:
            processed_map.pop(k, None)

        if all_turns:
            result = write_processed(all_turns, args.output_dir, include_ko=args.include_ko)
            logger.info(f"raw_files_processed={new_count}")
            logger.info(f"new_turns={result['total_turns']}")
            logger.info(f"new_sectors={result['new_sectors']}")
            logger.info(f"total_rows_written={result['total_rows_written']}")
            logger.info(f"output_file={result['output_file']}")
            write_heartbeat("ok", f"raw_files_processed={new_count}, new_turns={result['total_turns']}")
        else:
            logger.info("raw_files_processed=0")
            logger.info("no_new_turns")
            write_heartbeat("ok", "no_new_turns")

        save_json(args.state_file, state)
        return 0
    except Exception as e:
        err_msg = f"raw_process_worker 에러: {e}"
        logger.error(err_msg)
        write_heartbeat("error", err_msg)
        async def alert_error():
            await send_notifier_alert(f"[에러] raw_process_worker 실패: {e}")
        asyncio.run(alert_error())
        return 2


if __name__ == "__main__":
    import sys
    sys.exit(main())
