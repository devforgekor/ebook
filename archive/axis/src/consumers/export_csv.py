#!/usr/bin/env python3
import os
import json
import csv

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
RESULTS_DIR = os.path.join(BASE_DIR, "results", "engram")
EXPORT_DIR = os.path.join(BASE_DIR, "exports", "engram")
EXPORT_PATH = os.path.join(EXPORT_DIR, "results.csv")

def ensure_dir(p):
    os.makedirs(p, exist_ok=True)

def list_results():
    return [
        f for f in os.listdir(RESULTS_DIR)
        if f.startswith("RESULT_") and f.endswith(".json")
    ]

def main():
    ensure_dir(EXPORT_DIR)
    files = list_results()
    if not files:
        print("No RESULT files found. Exiting.")
        return

    with open(EXPORT_PATH, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=["result_file", "source_ovw", "generated_at", "summary_json"]
        )
        writer.writeheader()

        for name in files:
            path = os.path.join(RESULTS_DIR, name)
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            writer.writerow({
                "result_file": name,
                "source_ovw": data.get("source_ovw"),
                "generated_at": data.get("generated_at"),
                "summary_json": json.dumps(data.get("summary", {}), ensure_ascii=False),
            })

    print(f"[EXPORT] CSV written: {EXPORT_PATH}")

if __name__ == "__main__":
    main()
    