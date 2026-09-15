#!/usr/bin/env python3
from __future__ import annotations
import os
import argparse
import json
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import msal
import requests

# 환경변수 로드
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../.env'))

"""List OneDrive/SharePoint drives accessible with app credentials.

Uses the same credentials from config/onedrive_raw_sync.json to help find drive_id.
"""


GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List accessible drives for OneDrive sync")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/onedrive_raw_sync.json"),
        help="Path to OneDrive raw sync config",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=50,
        help="Maximum number of drives to request",
    )
    return parser.parse_args()


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def get_access_token(tenant_id: str, client_id: str, client_secret: str) -> str | None:
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = msal.ConfidentialClientApplication(
        client_id=client_id,
        authority=authority,
        client_credential=client_secret,
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    token = result.get("access_token")
    if isinstance(token, str) and token:
        return token
    detail = result.get("error_description") or result.get("error") or "unknown"
    print(f"ERR token: {detail}")
    return None


def list_drives(token: str, top: int) -> list[dict[str, Any]]:
    url = f"{GRAPH_BASE}/drives?$top={max(1, top)}"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, timeout=30)
    if resp.status_code != 200:
        print(f"ERR list drives: status={resp.status_code}")
        try:
            print(resp.json())
        except Exception:
            print(resp.text[:500])
        return []
    data = resp.json()
    value = data.get("value", [])
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    return []


def main() -> int:
    args = parse_args()
    cfg = load_json(args.config, default={})

    tenant_id = os.getenv("TENANT_ID", str(cfg.get("tenant_id", "")).strip())
    client_id = os.getenv("ONEDRIVE_CLIENT_ID", str(cfg.get("client_id", "")).strip())
    client_secret = os.getenv("ONEDRIVE_SECRET", str(cfg.get("client_secret", "")).strip())

    missing: list[str] = []
    if not tenant_id:
        missing.append("tenant_id")
    if not client_id:
        missing.append("client_id")
    if not client_secret:
        missing.append("client_secret")

    if missing:
        print(f"ERR missing fields: {', '.join(missing)}")
        return 1

    token = get_access_token(tenant_id, client_id, client_secret)
    if not token:
        return 1

    drives = list_drives(token, args.top)
    if not drives:
        print("No drives returned. Check app permissions and admin consent.")
        return 0

    print(f"drive_count={len(drives)}")
    for d in drives:
        drive_id = d.get("id", "")
        name = d.get("name", "")
        drive_type = d.get("driveType", "")
        web_url = d.get("webUrl", "")
        print(f"id={drive_id}")
        print(f"name={name}")
        print(f"type={drive_type}")
        print(f"url={web_url}")
        print("---")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
