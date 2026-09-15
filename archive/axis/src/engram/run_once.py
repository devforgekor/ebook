#!/usr/bin/env python3
import os
import json
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
STAGING_ACTIVE = os.path.join(BASE_DIR, "staging", "active")
RESULTS_DIR = os.path.join(BASE_DIR, "results", "engram")

def ensure_dir(p):
    os.makedirs(p, exist_ok=True)

def list_ovw_files():
    return [
        f for f in os.listdir(STAGING_ACTIVE)
        if f.startswith("OVW_") and f.endswith(".jsonl")
    ]

def read_jsonl(path: str):
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows

def main():
    ensure_dir(RESULTS_DIR)

    ovw_files = list_ovw_files()
    if not ovw_files:
        print("No OVW files found. Exiting.")
        return

    # 의도적으로 하나만 집계
    ovw_name = ovw_files[0]
    ovw_path = os.path.join(STAGING_ACTIVE, ovw_name)

    ovw_records = read_jsonl(ovw_path)
    if not ovw_records:
        print(f"OVW empty: {ovw_name}. Exiting.")
        return

    # ---- 결과 생성 (아주 단순한 집계) ----
    result = {
        "source_ovw": ovw_name,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "summary": ovw_records[0],  # 최소: OVW의 첫 레코드만 반영
    }

    out_name = ovw_name.replace("OVW_", "RESULT_", 1).replace(".jsonl", ".json")
    out_path = os.path.join(RESULTS_DIR, out_name)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[ENGRAM] Result written: results/engram/{out_name}")

if __name__ == "__main__":
    main()
    