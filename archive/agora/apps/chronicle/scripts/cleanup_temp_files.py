#!/usr/bin/env python3
"""
임시파일 정리 스크립트: data/temp 폴더에서 생성 후 10일이 지난 파일 자동 삭제
"""
import os
import time
from pathlib import Path

TEMP_DIR = Path(__file__).parent.parent.parent / "data/chronicle/temp"
DAYS = 10
SECONDS = DAYS * 24 * 60 * 60

now = time.time()

for file in TEMP_DIR.glob("*"):
    if file.is_file():
        mtime = file.stat().st_mtime
        if now - mtime > SECONDS:
            try:
                file.unlink()
                print(f"Deleted: {file}")
            except Exception as e:
                print(f"Failed to delete {file}: {e}")
