#!/usr/bin/env python3
import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
WORKING_DIR = os.path.join(BASE_DIR, "working")

RETRY_FLOW = ["_NEW_", "_R1_", "_R2_"]

def next_status_name(filename: str) -> str | None:
    for i, token in enumerate(RETRY_FLOW):
        if token in filename:
            if i + 1 < len(RETRY_FLOW):
                return filename.replace(token, RETRY_FLOW[i + 1], 1)
            else:
                # R2 -> FAIL
                return filename.replace(token, "_FAIL_", 1)
    return None

def main():
    files = [
        f for f in os.listdir(WORKING_DIR)
        if f.startswith("RAW_") and f.endswith(".jsonl")
    ]

    if not files:
        print("No RAW files found. Exiting.")
        return

    # 하나만 처리 (의도적으로)
    fname = files[0]
    next_name = next_status_name(fname)

    if not next_name:
        print(f"No retry state transition for {fname}. Exiting.")
        return

    src = os.path.join(WORKING_DIR, fname)
    dst = os.path.join(WORKING_DIR, next_name)

    os.rename(src, dst)
    print(f"[RETRY] {fname} -> {next_name}")

if __name__ == "__main__":
    main()
    