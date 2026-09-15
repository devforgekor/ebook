#!/usr/bin/env python3
import os
import json

# ---- Path Configuration ----
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
STAGING_ACTIVE_DIR = os.path.join(BASE_DIR, "staging", "active")

# ---- Helpers ----
def list_met_files():
    return [
        f for f in os.listdir(STAGING_ACTIVE_DIR)
        if f.startswith("MET_") and f.endswith(".jsonl")
    ]

def read_jsonl(path: str):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows

def write_jsonl(path: str, records):
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

# ---- Main Flow ----
def main():
    met_files = list_met_files()
    if not met_files:
        print("No MET files found in staging/active. Exiting.")
        return

    # 의도적으로 하나만 처리
    met_name = met_files[0]
    met_path = os.path.join(STAGING_ACTIVE_DIR, met_name)

    # MET 읽기
    records = read_jsonl(met_path)

    # --- OVW 생성 (아주 단순한 요약) ---
    ovw_payload = {
        "source_met": met_name,
        "record_count": len(records)
    }

    ovw_name = met_name.replace("MET_", "OVW_", 1)
    ovw_path = os.path.join(STAGING_ACTIVE_DIR, ovw_name)

    write_jsonl(ovw_path, [ovw_payload])

    print(f"[CORTEX] OVW created: {ovw_name}")

if __name__ == "__main__":
    main()
    