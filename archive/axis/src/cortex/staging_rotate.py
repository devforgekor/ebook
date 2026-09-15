#!/usr/bin/env python3
import os
import shutil

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
STAGING_ACTIVE = os.path.join(BASE_DIR, "staging", "active")
STAGING_WARM = os.path.join(BASE_DIR, "staging", "warm")
STAGING_PURGE = os.path.join(BASE_DIR, "staging", "purge-edge")

def ensure_dir(p):
    os.makedirs(p, exist_ok=True)

def move_one(src_dir, dst_dir, prefix=("MET_", "OVW_")):
    for name in os.listdir(src_dir):
        if name.startswith(prefix) and name.endswith(".jsonl"):
            src = os.path.join(src_dir, name)
            dst = os.path.join(dst_dir, name)
            shutil.move(src, dst)
            print(f"[MOVE] {os.path.basename(src_dir)} -> {os.path.basename(dst_dir)} : {name}")
            return True
    return False

def main():
    ensure_dir(STAGING_WARM)
    ensure_dir(STAGING_PURGE)

    # 순서 고정: active -> warm 한 개, 없다면 warm -> purge-edge 한 개
    if move_one(STAGING_ACTIVE, STAGING_WARM):
        return

    move_one(STAGING_WARM, STAGING_PURGE)

if __name__ == "__main__":
    main()

