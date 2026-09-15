#!/usr/bin/env python3
"""Realtime raw chat logger for VS Code workspaceStorage.

Behavior:
- Watches chatSessions JSONL files continuously.
- Triggers forced save when idle for N seconds after changes.
- Triggers forced save on SIGINT/SIGTERM (best effort).

Saved artifacts are raw snapshot files under the raw directory.
"""

from __future__ import annotations

import argparse
import json
import re
import signal
import time
from datetime import datetime
from pathlib import Path
from typing import Dict

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Realtime chat logger")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path.home() / "Library/Application Support/Code/User/workspaceStorage",
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path(__file__).parent.parent.parent / "data/chronicle/refined/raw",
    )
    parser.add_argument(
        "--state-log",
        type=Path,
        default=Path(__file__).parent.parent.parent / "data/chronicle/refined/realtime/realtime_logger_events.log",
    )
    parser.add_argument(
        "--idle-seconds",
        type=int,
        default=10,
        help="Save if no new chat file changes for this many seconds",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=1.0,
        help="Polling interval in seconds",
    )
    parser.add_argument(
        "--oneshot",
        action="store_true",
        help="Capture one raw snapshot immediately and exit",
    )
    return parser.parse_args()


STOP = False
USER_EVENT_PATTERN = re.compile(r'"k":\["requests",\d+,"message"\]')


def on_signal(signum: int, _frame: object) -> None:
    global STOP
    STOP = True


def log_event(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().astimezone().isoformat()
    with path.open("a", encoding="utf-8") as f:
        f.write(f"[{ts}] {message}\n")


def snapshot_mtimes(source: Path) -> Dict[str, float]:
    data: Dict[str, float] = {}
    for p in source.glob("**/chatSessions/*.jsonl"):
        try:
            data[str(p)] = p.stat().st_mtime
        except FileNotFoundError:
            continue
    return data


def snapshot_sizes(source: Path) -> Dict[str, int]:
    data: Dict[str, int] = {}
    for p in source.glob("**/chatSessions/*.jsonl"):
        try:
            data[str(p)] = p.stat().st_size
        except FileNotFoundError:
            continue
    return data


def build_raw_snapshot(source: Path) -> dict:
    files = []
    for p in sorted(source.glob("**/chatSessions/*.jsonl")):
        try:
            stat = p.stat()
            content = p.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        files.append(
            {
                "path": str(p),
                "relative_path": str(p.relative_to(source)),
                "mtime": stat.st_mtime,
                "size": stat.st_size,
                "content": content,
            }
        )
    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "source": str(source),
        "file_count": len(files),
        "files": files,
    }


def save_raw_snapshot(raw_dir: Path, payload: dict) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%f")
    out = raw_dir / f"raw_{ts}.json"
    if out.exists():
        # Prevent rare same-microsecond filename collisions.
        out = raw_dir / f"raw_{ts}_{int(time.time() * 1000000)}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return out


def snapshot_signature(mtimes: Dict[str, float], sizes: Dict[str, int]) -> str:
    rows: list[str] = []
    for file_path in sorted(mtimes.keys()):
        rows.append(f"{file_path}|{mtimes[file_path]}|{sizes.get(file_path, 0)}")
    return "\n".join(rows)


def detect_user_activity(changed_files: Dict[str, tuple[int, int]]) -> bool:
    for file_path, (old_size, new_size) in changed_files.items():
        if new_size <= old_size:
            continue
        try:
            with open(file_path, "rb") as f:
                f.seek(old_size)
                chunk = f.read(new_size - old_size)
        except Exception:
            continue
        text = chunk.decode("utf-8", errors="replace")
        if USER_EVENT_PATTERN.search(text):
            return True
    return False


def main() -> int:
    args = parse_args()
    source = args.source
    raw_dir = args.raw_dir
    state_log = args.state_log

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    prev = snapshot_mtimes(source)
    prev_sizes = snapshot_sizes(source)
    dirty = False
    last_change_ts = time.time()
    last_user_activity_ts = time.time()
    last_saved_sig = ""

    log_event(state_log, "realtime logger started")

    if args.oneshot:
        snapshot = build_raw_snapshot(source)
        out = save_raw_snapshot(raw_dir, snapshot)
        log_event(state_log, f"oneshot raw save | file_count={snapshot['file_count']} | out={out}")
        log_event(state_log, "realtime logger stopped")
        return 0

    while not STOP:
        cur = snapshot_mtimes(source)
        cur_sizes = snapshot_sizes(source)
        if cur != prev or cur_sizes != prev_sizes:
            changed_files: Dict[str, tuple[int, int]] = {}
            for file_path, new_size in cur_sizes.items():
                old_size = prev_sizes.get(file_path, 0)
                changed_files[file_path] = (old_size, new_size)

            prev = cur
            prev_sizes = cur_sizes
            dirty = True
            last_change_ts = time.time()

            if detect_user_activity(changed_files):
                last_user_activity_ts = time.time()
                log_event(state_log, "user input activity detected")

            log_event(state_log, f"change detected: tracked_files={len(cur)}")

        idle_by_change = (time.time() - last_change_ts) >= args.idle_seconds
        idle_by_user = (time.time() - last_user_activity_ts) >= args.idle_seconds
        if dirty and idle_by_change and idle_by_user:
            sig = snapshot_signature(prev, prev_sizes)
            if sig != last_saved_sig:
                snapshot = build_raw_snapshot(source)
                out = save_raw_snapshot(raw_dir, snapshot)
                log_event(
                    state_log,
                    f"forced raw save after user-idle {args.idle_seconds}s | file_count={snapshot['file_count']} | out={out}",
                )
                last_saved_sig = sig
            else:
                log_event(state_log, "save skipped: snapshot unchanged since last save")
            dirty = False

        time.sleep(args.poll_seconds)

    if dirty:
        sig = snapshot_signature(prev, prev_sizes)
        if sig != last_saved_sig:
            snapshot = build_raw_snapshot(source)
            out = save_raw_snapshot(raw_dir, snapshot)
            log_event(
                state_log,
                f"forced raw save on shutdown signal | file_count={snapshot['file_count']} | out={out}",
            )
        else:
            log_event(state_log, "shutdown save skipped: snapshot unchanged since last save")

    log_event(state_log, "realtime logger stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
