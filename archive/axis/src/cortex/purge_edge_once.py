#!/usr/bin/env python3
import os
import argparse

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
PURGE_DIR = os.path.join(BASE_DIR, "staging", "purge-edge")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true", help="Actually delete files")
    args = p.parse_args()

    if not os.path.isdir(PURGE_DIR):
        print("purge-edge directory not found. Exiting.")
        return

    files = [f for f in os.listdir(PURGE_DIR) if f.endswith(".jsonl")]
    if not files:
        print("No files to purge. Exiting.")
        return

    for f in files:
        path = os.path.join(PURGE_DIR, f)
        if args.apply:
            os.remove(path)
            print(f"[DELETE] {f}")
        else:
            print(f"[DRY-RUN] would delete: {f}")

    if not args.apply:
        print("Dry-run only. Re-run with --apply to delete.")

if __name__ == "__main__":
    main()

