#!/usr/bin/env python3
from __future__ import annotations
import os
import argparse
import hashlib
import io
import json
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

# 환경변수 로드
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../.env'))

"""Google Drive sync for chat datasets.

This script supports:
- Upload local artifacts to Drive incoming folder.
- Download processed artifacts from Drive processed folder.

Authentication: service account JSON key.
"""


SCOPES = ["https://www.googleapis.com/auth/drive"]
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = SCRIPT_DIR.parent / "config" / "drive_sync.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Google Drive uploader/downloader")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to drive sync config JSON",
    )
    parser.add_argument(
        "--mode",
        choices=["upload", "download", "both"],
        default="both",
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


def build_drive(service_account_file: Path):
    creds = service_account.Credentials.from_service_account_file(
        str(service_account_file), scopes=SCOPES
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def list_drive_files(service, folder_id: str) -> list[dict[str, Any]]:
    q = f"'{folder_id}' in parents and trashed=false"
    files: list[dict[str, Any]] = []
    page_token = None
    while True:
        resp = (
            service.files()
            .list(
                q=q,
                fields="nextPageToken, files(id, name, mimeType, modifiedTime, size)",
                pageToken=page_token,
                pageSize=1000,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
        )
        files.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return files


def find_by_name(service, folder_id: str, name: str) -> str | None:
    safe_name = name.replace("'", "\\'")
    q = f"name='{safe_name}' and '{folder_id}' in parents and trashed=false"
    resp = (
        service.files()
        .list(
            q=q,
            fields="files(id, name)",
            pageSize=1,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )
    files = resp.get("files", [])
    if not files:
        return None
    return files[0].get("id")


def upload_file(service, folder_id: str, local_path: Path, remote_name: str, existing_id: str | None) -> str:
    mime, _ = mimetypes.guess_type(str(local_path))
    media = MediaFileUpload(str(local_path), mimetype=mime or "application/octet-stream", resumable=True)

    if existing_id:
        updated = (
            service.files()
            .update(
                fileId=existing_id,
                media_body=media,
                supportsAllDrives=True,
                fields="id",
            )
            .execute()
        )
        return str(updated["id"])

    created = (
        service.files()
        .create(
            body={"name": remote_name, "parents": [folder_id]},
            media_body=media,
            supportsAllDrives=True,
            fields="id",
        )
        .execute()
    )
    return str(created["id"])


def download_file(service, file_id: str, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    fh = io.FileIO(str(out_path), "wb")
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.close()


def collect_upload_targets(roots: list[Path]) -> list[Path]:
    out: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            # temp 폴더 하위 파일은 제외
            if any("/temp/" in str(p.parent) or str(p).startswith(str(root / "temp")) for _ in [0]):
                continue
            if p.is_file() and p.suffix.lower() in {".json", ".jsonl", ".gz", ".log"}:
                out.append(p)
    return sorted(out)


def run_upload(service, cfg: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    incoming_id = str(cfg.get("incoming_folder_id", "")).strip()
    if not incoming_id:
        print("skip upload: missing incoming_folder_id")
        return {"uploaded": 0, "scanned": 0}

    roots = [Path(p).expanduser() for p in cfg.get("upload_roots", [])]
    targets = collect_upload_targets(roots)
    uploads_state = state.setdefault("uploads", {})

    uploaded = 0
    for p in targets:
        key = str(p)
        digest = sha256_file(p)
        size = p.stat().st_size
        prev = uploads_state.get(key, {})
        if prev.get("sha256") == digest and prev.get("size") == size:
            continue

        existing_id = prev.get("drive_file_id")
        if not existing_id:
            existing_id = find_by_name(service, incoming_id, p.name)

        file_id = upload_file(service, incoming_id, p, p.name, existing_id)
        uploads_state[key] = {
            "sha256": digest,
            "size": size,
            "drive_file_id": file_id,
            "uploaded_at": datetime.now().astimezone().isoformat(),
        }
        uploaded += 1

    return {"uploaded": uploaded, "scanned": len(targets)}


def run_download(service, cfg: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    processed_id = str(cfg.get("processed_folder_id", "")).strip()
    if not processed_id:
        print("skip download: missing processed_folder_id")
        return {"downloaded": 0, "available": 0}

        download_dir = Path(str(cfg.get("download_dir", "/Users/minipark4u/app/chronicle/data/processed_from_drive"))).expanduser()
    files = list_drive_files(service, processed_id)
    downloads_state = state.setdefault("downloads", {})

    downloaded = 0
    for item in files:
        file_id = str(item["id"])
        modified = str(item.get("modifiedTime", ""))
        name = str(item.get("name", file_id))

        prev = downloads_state.get(file_id, {})
        if prev.get("modifiedTime") == modified:
            continue

        out_path = download_dir / name
        download_file(service, file_id, out_path)
        downloads_state[file_id] = {
            "name": name,
            "modifiedTime": modified,
            "downloaded_at": datetime.now().astimezone().isoformat(),
        }
        downloaded += 1

    return {"downloaded": downloaded, "available": len(files)}


def main() -> int:
    args = parse_args()
    cfg = load_json(
        args.config,
        default={
            "service_account_json": "",
            "incoming_folder_id": "",
            "processed_folder_id": "",
            "upload_roots": [
                "/Users/minipark4u/app/chronicle/data/daily",
            ],
            "download_dir": "/Users/minipark4u/app/chronicle/data/processed_from_drive",
            "state_file": "/Users/minipark4u/app/chronicle/data/state/drive_sync_state.json",
        },
    )

    # 환경변수 우선 적용
    service_account_json = os.getenv("GGDRIVE_SERVICE_ACCOUNT_JSON", str(cfg.get("service_account_json", "")))
    service_key = Path(service_account_json).expanduser()
    if not service_key.exists():
        print(f"skip sync: service_account_json not found: {service_key}")
        return 0

    state_file = Path(
        str(cfg.get("state_file", "/Users/minipark4u/app/chronicle/data/state/drive_sync_state.json"))
    ).expanduser()
    state = load_json(state_file, default={})

    service = build_drive(service_key)

    upload_stats = {"uploaded": 0, "scanned": 0}
    download_stats = {"downloaded": 0, "available": 0}

    if args.mode in {"upload", "both"}:
        upload_stats = run_upload(service, cfg, state)
    if args.mode in {"download", "both"}:
        download_stats = run_download(service, cfg, state)

    state["last_sync_at"] = datetime.now().astimezone().isoformat()
    save_json(state_file, state)

    print(f"upload_scanned={upload_stats['scanned']}")
    print(f"upload_uploaded={upload_stats['uploaded']}")
    print(f"download_available={download_stats['available']}")
    print(f"download_downloaded={download_stats['downloaded']}")
    print(f"state_file={state_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
