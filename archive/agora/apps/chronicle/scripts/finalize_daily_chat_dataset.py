#!/usr/bin/env python3
"""Finalize daily chat dataset snapshot.

Reads chat JSONL files and writes per-day snapshots using 00:00~24:00 local day.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Finalize daily chat dataset")
    parser.add_argument(
        "--chat-dir",
        type=Path,
        default=Path(__file__).parent.parent.parent / "data/chronicle/processed",
    )
    parser.add_argument(
        "--daily-dir",
        type=Path,
        default=Path(__file__).parent.parent.parent / "data/chronicle/processed/daily",
    )
    parser.add_argument(
        "--date",
        type=str,
        default="",
        help="Local date in YYYY-MM-DD. Default is today.",
    )
    parser.add_argument(
        "--include-ko",
        action="store_true",
        help="Also finalize Korean review dataset",
    )
    return parser.parse_args()


def parse_iso_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).astimezone().date().isoformat()
    except Exception:
        return None


def read_jsonl(path: Path) -> list[dict[str, Any]]:
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
            except Exception:
                continue
            if isinstance(obj, dict):
                rows.append(obj)
    return rows


def filter_for_day(rows: list[dict[str, Any]], day: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        metadata = row.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}

        ts_day = parse_iso_date(row.get("timestamp"))
        created_day = parse_iso_date(row.get("created_at"))
        meta_ts_day = parse_iso_date(metadata.get("timestamp"))
        meta_created_day = parse_iso_date(metadata.get("created_at"))

        if day in {ts_day, created_day, meta_ts_day, meta_created_day}:
            out.append(row)
    return out


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False))
            f.write("\n")


def main() -> int:
    args = parse_args()
    today = datetime.now().astimezone().date().isoformat()
    day = args.date or today

    ko_in = args.chat_dir / "chat_ko_review.jsonl"
    ko_rows = filter_for_day(read_jsonl(ko_in), day) if args.include_ko else []
    ko_out = args.daily_dir / f"chat_ko_review_{day}.jsonl"
    meta_out = args.daily_dir / f"chat_daily_{day}.json"

    if args.include_ko:
        write_jsonl(ko_out, ko_rows)

    meta = {
        "date": day,
        "generated_at": datetime.now().astimezone().isoformat(),
        "source_chat_dir": str(args.chat_dir),
        "outputs": {},
        "counts": {},
    }
    if args.include_ko:
        meta["outputs"]["ko_review"] = str(ko_out)
        meta["counts"]["ko_review"] = len(ko_rows)
    meta_out.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"date={day}")
    if args.include_ko:
        print(f"ko_rows={len(ko_rows)}")
        print(f"ko_out={ko_out}")
    print(f"meta_out={meta_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
