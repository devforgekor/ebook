#!/usr/bin/env python3
from __future__ import annotations
import os
import argparse
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from dotenv import load_dotenv
import msal
import requests

# 환경변수 로드
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../.env'))

"""Check OneDrive raw sync configuration health.

Checks:
- Required config keys are present.
- AAD token can be acquired.
- drive_id is reachable.
- remote_raw_dir path exists (or can be created by uploader).
"""


GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check OneDrive raw sync config")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/onedrive_raw_sync.json"),
        help="Path to OneDrive raw sync config",
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


def encode_remote_path(remote_path: str) -> str:
    parts = [p for p in remote_path.strip("/").split("/") if p]
    return "/".join(quote(p, safe="") for p in parts)


def check_drive(token: str, drive_id: str) -> bool:
    url = f"{GRAPH_BASE}/drives/{quote(drive_id, safe='')}"
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if resp.status_code != 200:
        print(f"ERR drive_id: status={resp.status_code}")
        return False
    data = resp.json()
    print(f"OK drive_id: name={data.get('name', '')} id={data.get('id', '')}")
    return True


def check_remote_path(token: str, drive_id: str, remote_raw_dir: str) -> None:
    encoded = encode_remote_path(remote_raw_dir)
    url = f"{GRAPH_BASE}/drives/{quote(drive_id, safe='')}/root:/{encoded}"
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    if resp.status_code == 200:
        print(f"OK remote_raw_dir exists: {remote_raw_dir}")
        return
    if resp.status_code == 404:
        print(f"WARN remote_raw_dir missing: {remote_raw_dir} (uploader will create on first upload)")
        return
    print(f"WARN remote_raw_dir check failed: status={resp.status_code} path={remote_raw_dir}")


def main() -> int:
    args = parse_args()
    cfg = load_json(args.config, default={})

    tenant_id = os.getenv("TENANT_ID", str(cfg.get("tenant_id", "")).strip())
    client_id = os.getenv("ONEDRIVE_CLIENT_ID", str(cfg.get("client_id", "")).strip())
    client_secret = os.getenv("ONEDRIVE_SECRET", str(cfg.get("client_secret", "")).strip())
    drive_id = str(cfg.get("drive_id", "")).strip()
    remote_raw_dir = str(cfg.get("remote_raw_dir", "chronicle")).strip()

    missing: list[str] = []
    if not tenant_id:
        missing.append("tenant_id")
    if not client_id:
        missing.append("client_id")
    if not client_secret:
        missing.append("client_secret")
    if not drive_id:
        missing.append("drive_id")

    if missing:
        print(f"ERR missing fields: {', '.join(missing)}")
        return 1

    token = get_access_token(tenant_id, client_id, client_secret)
    if not token:
        return 1
    print("OK token")

    if not check_drive(token, drive_id):
        return 1

    check_remote_path(token, drive_id, remote_raw_dir)
    print("OK: OneDrive raw sync configuration is valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
