#!/usr/bin/env python3
from __future__ import annotations
import os
import argparse
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

from dotenv import load_dotenv
import msal
import requests

# 환경변수 로드
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../.env'))

"""OneDrive sync for raw chat snapshot files.

Behavior:
- Upload local raw snapshot files to OneDrive.
- Keep local raw files only for retention window (default 7 days).
- Local deletion can be restricted to files confirmed as uploaded.
"""


GRAPH_BASE = "https://graph.microsoft.com/v1.0"
CHUNK_SIZE = 5 * 1024 * 1024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OneDrive raw uploader and local retention manager")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/onedrive_raw_sync.json"),
        help="Path to OneDrive raw sync config JSON",
    )
    parser.add_argument(
        "--mode",
        choices=["upload", "prune", "both"],
        default="both",
    )
    parser.add_argument(
        "--retention-days",
        type=int,
        default=0,
        help="Override retention days (0 means use config value)",
    )
    return parser.parse_args()


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def get_access_token(tenant_id: str, client_id: str, client_secret: str) -> str | None:
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = msal.ConfidentialClientApplication(
        client_id=client_id,
        authority=authority,
        client_credential=client_secret,
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    token = result.get("access_token")
    if not isinstance(token, str) or not token:
        err = result.get("error_description") or result.get("error") or "unknown"
        print(f"skip onedrive sync: token acquisition failed: {err}")
        return None
    return token


def graph_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def encode_remote_path(remote_path: str) -> str:
    parts = [p for p in remote_path.strip("/").split("/") if p]
    return "/".join(quote(p, safe="") for p in parts)


def create_upload_session(token: str, drive_id: str, remote_path: str) -> str | None:
    encoded = encode_remote_path(remote_path)
    url = f"{GRAPH_BASE}/drives/{quote(drive_id, safe='')}/root:/{encoded}:/createUploadSession"
    payload = {"item": {"@microsoft.graph.conflictBehavior": "replace"}}
    resp = requests.post(url, headers=graph_headers(token), json=payload, timeout=60)
    if resp.status_code not in {200, 201}:
        print(f"upload session failed: status={resp.status_code} path={remote_path}")
        return None
    data = resp.json()
    upload_url = data.get("uploadUrl")
    if isinstance(upload_url, str) and upload_url:
        return upload_url
    print(f"upload session failed: missing uploadUrl path={remote_path}")
    return None


def upload_file_chunked(upload_url: str, local_path: Path) -> bool:
    size = local_path.stat().st_size
    offset = 0
    with local_path.open("rb") as f:
        while offset < size:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            start = offset
            end = offset + len(chunk) - 1
            headers = {
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {start}-{end}/{size}",
            }
            resp = requests.put(upload_url, headers=headers, data=chunk, timeout=120)
            if resp.status_code not in {200, 201, 202}:
                print(f"chunk upload failed: status={resp.status_code} file={local_path}")
                return False
            offset += len(chunk)
    return True


def upload_to_onedrive(token: str, drive_id: str, remote_dir: str, local_path: Path) -> bool:
    remote_path = f"{remote_dir.strip('/')}/{local_path.name}" if remote_dir.strip("/") else local_path.name
    upload_url = create_upload_session(token, drive_id, remote_path)
    if not upload_url:
        return False
    return upload_file_chunked(upload_url, local_path)


def collect_raw_targets(raw_dir: Path) -> list[Path]:
    if not raw_dir.exists():
        return []
    # refined 폴더의 모든 .json, .jsonl, .gz, .log 파일 업로드 대상으로 변경
    exts = {".json", ".jsonl", ".gz", ".log"}
    return sorted(p for p in raw_dir.rglob("*") if p.is_file() and p.suffix.lower() in exts)


def run_upload(token: str, cfg: dict[str, Any], state: dict[str, Any]) -> dict[str, int]:
    drive_id = str(cfg.get("drive_id", "")).strip()
    if not drive_id:
        print("skip onedrive upload: missing drive_id")
        return {"scanned": 0, "uploaded": 0}

    remote_dir = str(cfg.get("remote_raw_dir", "chronicle")).strip()
    raw_dir = Path(str(cfg.get("raw_dir", "/Users/minipark4u/app/chronicle/data/raw"))).expanduser()
    uploads_state = state.setdefault("uploads", {})

    targets = collect_raw_targets(raw_dir)
    uploaded = 0
    for p in targets:
        key = str(p)
        size = p.stat().st_size
        digest = sha256_file(p)
        prev = uploads_state.get(key, {})
        if prev.get("size") == size and prev.get("sha256") == digest:
            continue

        ok = upload_to_onedrive(token, drive_id, remote_dir, p)
        if not ok:
            continue

        uploads_state[key] = {
            "size": size,
            "sha256": digest,
            "uploaded_at": now_iso(),
            "remote_dir": remote_dir,
        }
        uploaded += 1

    return {"scanned": len(targets), "uploaded": uploaded}


def can_delete_uploaded_only(path: Path, uploads_state: dict[str, Any]) -> bool:
    key = str(path)
    prev = uploads_state.get(key, {})
    if not isinstance(prev, dict) or not prev:
        return False
    try:
        size = path.stat().st_size
    except Exception:
        return False
    digest = sha256_file(path)
    return prev.get("size") == size and prev.get("sha256") == digest


def run_prune(cfg: dict[str, Any], state: dict[str, Any], retention_days: int) -> dict[str, int]:
    raw_dir = Path(str(cfg.get("raw_dir", "/Users/minipark4u/app/chronicle/data/raw"))).expanduser()
    delete_uploaded_only = bool(cfg.get("delete_uploaded_only", True))
    uploads_state = state.setdefault("uploads", {})

    now = datetime.now().astimezone()
    cutoff = now - timedelta(days=retention_days)

    scanned = 0
    deleted = 0
    skipped_not_uploaded = 0

    for p in collect_raw_targets(raw_dir):
        scanned += 1
        mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=now.tzinfo)
        if mtime >= cutoff:
            continue

        if delete_uploaded_only and not can_delete_uploaded_only(p, uploads_state):
            skipped_not_uploaded += 1
            continue

        try:
            p.unlink()
            uploads_state.pop(str(p), None)
            deleted += 1
        except Exception:
            continue

    existing = {str(p) for p in collect_raw_targets(raw_dir)}
    stale_keys = [k for k in uploads_state.keys() if k not in existing]
    for k in stale_keys:
        uploads_state.pop(k, None)

    return {
        "scanned": scanned,
        "deleted": deleted,
        "skipped_not_uploaded": skipped_not_uploaded,
    }


def main() -> int:
    args = parse_args()
    cfg = load_json(
        args.config,
        default={
            "tenant_id": "",
            "client_id": "",
            "client_secret": "",
            "drive_id": "",
            "remote_raw_dir": "chronicle",
            "raw_dir": "/Users/minipark4u/app/chronicle/data/raw",
            "retention_days": 7,
            "delete_uploaded_only": True,
            "state_file": "/Users/minipark4u/app/chronicle/data/state/onedrive_raw_state.json",
        },
    )

    state_file = Path(str(cfg.get("state_file", "/Users/minipark4u/app/chronicle/data/state/onedrive_raw_state.json"))).expanduser()
    state = load_json(state_file, default={})

    retention_days = args.retention_days or int(cfg.get("retention_days", 7) or 7)
    if retention_days < 1:
        retention_days = 1

    upload_stats = {"scanned": 0, "uploaded": 0}
    prune_stats = {"scanned": 0, "deleted": 0, "skipped_not_uploaded": 0}

    tenant_id = os.getenv("TENANT_ID", str(cfg.get("tenant_id", "")).strip())
    client_id = os.getenv("ONEDRIVE_CLIENT_ID", str(cfg.get("client_id", "")).strip())
    client_secret = os.getenv("ONEDRIVE_SECRET", str(cfg.get("client_secret", "")).strip())

    if args.mode in {"upload", "both"}:
        if not (tenant_id and client_id and client_secret):
            print("skip onedrive upload: missing tenant_id/client_id/client_secret")
        else:
            token = get_access_token(tenant_id, client_id, client_secret)
            if token:
                upload_stats = run_upload(token, cfg, state)

    if args.mode in {"prune", "both"}:
        prune_stats = run_prune(cfg, state, retention_days)

    state["last_run_at"] = now_iso()
    save_json(state_file, state)

    print(f"upload_scanned={upload_stats['scanned']}")
    print(f"upload_uploaded={upload_stats['uploaded']}")
    print(f"prune_scanned={prune_stats['scanned']}")
    print(f"prune_deleted={prune_stats['deleted']}")
    print(f"prune_skipped_not_uploaded={prune_stats['skipped_not_uploaded']}")
    print(f"retention_days={retention_days}")
    print(f"state_file={state_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
