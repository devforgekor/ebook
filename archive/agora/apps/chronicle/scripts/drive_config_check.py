#!/usr/bin/env python3
"""Validate Google Drive sync configuration.

Checks:
- service account key file exists
- folder IDs are configured
- Drive API authentication works
- incoming/processed folders are accessible
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/drive"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check Google Drive sync configuration")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/drive_sync.json"),
        help="Path to drive sync config",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def folder_meta(service, folder_id: str) -> dict[str, Any]:
    return (
        service.files()
        .get(
            fileId=folder_id,
            fields="id, name, mimeType, owners(emailAddress), driveId",
            supportsAllDrives=True,
        )
        .execute()
    )


def main() -> int:
    args = parse_args()
    cfg = load_json(args.config)

    if not cfg:
        print(f"ERROR: config not found or invalid JSON: {args.config}")
        return 1

    service_key = Path(str(cfg.get("service_account_json", ""))).expanduser()
    incoming_id = str(cfg.get("incoming_folder_id", "")).strip()
    processed_id = str(cfg.get("processed_folder_id", "")).strip()

    if not service_key.exists():
        print(f"ERROR: service account key missing: {service_key}")
        return 1

    if not incoming_id:
        print("ERROR: incoming_folder_id is empty")
        return 1

    if not processed_id:
        print("ERROR: processed_folder_id is empty")
        return 1

    key_json = load_json(service_key)
    sa_email = key_json.get("client_email", "(unknown)")
    print(f"service_account_email={sa_email}")

    creds = service_account.Credentials.from_service_account_file(str(service_key), scopes=SCOPES)
    service = build("drive", "v3", credentials=creds, cache_discovery=False)

    try:
        incoming_meta = folder_meta(service, incoming_id)
        print(
            "incoming_ok="
            f"id={incoming_meta.get('id')} name={incoming_meta.get('name')} mimeType={incoming_meta.get('mimeType')}"
        )
    except Exception as exc:
        print(f"ERROR: cannot access incoming folder: {exc}")
        return 1

    try:
        processed_meta = folder_meta(service, processed_id)
        print(
            "processed_ok="
            f"id={processed_meta.get('id')} name={processed_meta.get('name')} mimeType={processed_meta.get('mimeType')}"
        )
    except Exception as exc:
        print(f"ERROR: cannot access processed folder: {exc}")
        return 1

    print("OK: Drive sync configuration is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
