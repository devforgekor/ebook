#!/usr/bin/env python3
import os
import json

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
RESULTS_DIR = os.path.join(BASE_DIR, "results", "engram")

def list_results():
    return [
        f for f in os.listdir(RESULTS_DIR)
        if f.startswith("RESULT_") and f.endswith(".json")
    ]

def main():
    files = list_results()
    if not files:
        print("No RESULT files found. Exiting.")
        return

    # 의도적으로 하나만 소비
    name = files[0]
    path = os.path.join(RESULTS_DIR, name)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print("=== RESULT SUMMARY ===")
    print(f"file        : {name}")
    print(f"source_ovw  : {data.get('source_ovw')}")
    print(f"generated_at: {data.get('generated_at')}")
    print("summary     :", json.dumps(data.get("summary", {}), ensure_ascii=False))

if __name__ == "__main__":
    main()

