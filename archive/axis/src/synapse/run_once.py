#!/usr/bin/env python3
import os
import shutil

# ---- Constants (implementation detail) ----
MAX_WORKING_FILES = 100

# ---- Path Configuration ----
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
WORKING_DIR = os.path.join(BASE_DIR, "working")
STAGING_ACTIVE_DIR = os.path.join(BASE_DIR, "staging", "active")
ARCHIVE_DIR = os.path.join(BASE_DIR, "archive")

# ---- Helpers ----
def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def list_raw_files(limit: int):
    """
    working/에서 RAW 파일을 최대 limit개까지 반환한다.
    - 정렬 없음
    - 우선순위 판단 없음
    """
    files = []
    try:
        for name in os.listdir(WORKING_DIR):
            if name.startswith("RAW_") and name.endswith(".jsonl"):
                files.append(name)
                if len(files) >= limit:
                    break
    except FileNotFoundError:
        pass
    return files

def parse_year_month(filename: str):
    """
    규격: RAW_<STATUS>_<SERVER>_<YYYYMMDD>_<ID>.jsonl
    """
    parts = filename.split("_")
    if len(parts) < 5:
        raise ValueError(f"Invalid filename format: {filename}")
    ymd = parts[3]
    return ymd[:4], ymd[4:6]

# ---- Main Flow ----
def process_one(raw_name: str):
    raw_path = os.path.join(WORKING_DIR, raw_name)

    # --- Step 1: RAW -> MET (staging/active) ---
    # 상태 판단 없음: NEW 그대로 사용
    met_name = raw_name.replace("RAW_", "MET_", 1).replace("_synapse_", "_neuron_", 1)
    met_path = os.path.join(STAGING_ACTIVE_DIR, met_name)
    shutil.copy2(raw_path, met_path)
    print(f"[STAGING] MET created: {met_name}")

    # --- Step 2: RAW -> ARCHIVE (보존) ---
    year, month = parse_year_month(raw_name)
    archive_target_dir = os.path.join(ARCHIVE_DIR, year, month)
    ensure_dir(archive_target_dir)

    archived_raw_name = raw_name.replace("_NEW_", "_DONE_", 1)
    archived_raw_path = os.path.join(archive_target_dir, archived_raw_name)
    shutil.move(raw_path, archived_raw_path)
    print(f"[ARCHIVE] RAW archived: {year}/{month}/{archived_raw_name}")

def main():
    ensure_dir(STAGING_ACTIVE_DIR)
    ensure_dir(ARCHIVE_DIR)

    raws = list_raw_files(MAX_WORKING_FILES)
    if not raws:
        print("No RAW file found in working/. Exiting.")
        return

    for raw_name in raws:
        process_one(raw_name)

    print(f"[DONE] Processed {len(raws)} file(s). One-shot run completed.")

if __name__ == "__main__":
    main()

