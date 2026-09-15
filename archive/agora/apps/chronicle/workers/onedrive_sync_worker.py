#!/usr/bin/env python3
"""
OneDrive 동기화 워커 (서비스화)
- raw/ 폴더의 파일을 OneDrive로 업로드
- 업로드 확인된 파일만 retention_days(기본 7일) 동안 로컬에 보관
- 환경변수 및 config/onedrive_raw_sync.json로 인증/설정 관리
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import json
import hashlib
from typing import Any

import httpx
import asyncio
from string import Template
from dotenv import load_dotenv
import msal
import requests
def write_heartbeat(status: str, info: str = "", state_dir=Path(__file__).parent.parent / "data/chronicle/state"):
    """상태(heartbeat) 파일을 기록합니다."""
    from datetime import datetime
    state_dir.mkdir(parents=True, exist_ok=True)
    heartbeat = {
        "status": status,
        "info": info,
        "timestamp": datetime.now().isoformat()
    }
    with open(state_dir / "onedrive_sync_heartbeat.json", "w", encoding="utf-8") as f:
        json.dump(heartbeat, f, ensure_ascii=False, indent=2)

async def send_notifier_alert(message, channel="telegram"):
    NOTIFIER_URL = os.getenv("NOTIFIER_URL", "http://localhost:8001")
    NOTIFIER_API_KEY = os.getenv("NOTIFIER_API_KEY", "")
    if not NOTIFIER_API_KEY:
        print("[경고] NOTIFIER_API_KEY 환경변수가 설정되지 않았습니다.")
        return
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{NOTIFIER_URL}/v1/notify",
                json={"text": message, "channel": channel},
                headers={"Authorization": f"Bearer {NOTIFIER_API_KEY}"}
            )
            resp.raise_for_status()
            print(f"[알림] Notifier로 전송 완료: {message[:40]}")
        except Exception as e:
            print(f"[에러] Notifier 알림 실패: {e}")

# 환경변수 로드 (앱 루트 .env)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '../.env'))


# 설정 파일 경로
def get_config_path():
    return Path(os.getenv("ONEDRIVE_SYNC_CONFIG", "config/onedrive_raw_sync.json"))

# 환경변수 템플릿 치환 지원 config 로드
def load_json_with_env(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    try:
        text = path.read_text(encoding="utf-8")
        json_string = Template(text).safe_substitute(os.environ)
        return json.loads(json_string)
    except Exception:
        return default

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

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
    from urllib.parse import quote
    parts = [p for p in remote_path.strip("/").split("/") if p]
    return "/".join(quote(p, safe="") for p in parts)

def create_upload_session(token: str, drive_id: str, remote_path: str) -> str | None:
    GRAPH_BASE = "https://graph.microsoft.com/v1.0"
    encoded = encode_remote_path(remote_path)
    url = f"{GRAPH_BASE}/drives/{drive_id}/root:/{encoded}:/createUploadSession"
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

def upload_file(token: str, drive_id: str, local_path: Path, remote_path: str) -> bool:
    upload_url = create_upload_session(token, drive_id, remote_path)
    if not upload_url:
        return False
    file_size = local_path.stat().st_size
    with local_path.open("rb") as f:
        chunk_size = 5 * 1024 * 1024
        start = 0
        while start < file_size:
            end = min(start + chunk_size, file_size) - 1
            f.seek(start)
            chunk = f.read(end - start + 1)
            headers = {
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Content-Length": str(end - start + 1),
            }
            resp = requests.put(upload_url, headers=headers, data=chunk, timeout=120)
            if resp.status_code not in {200, 201, 202}:
                print(f"chunk upload failed: {resp.status_code} {resp.text}")
                return False
            start = end + 1
    return True

def main():
    try:
        config_path = get_config_path()
        config = load_json_with_env(config_path, {})
        tenant_id = os.getenv("TENANT_ID") or config.get("tenant_id")
        client_id = os.getenv("ONEDRIVE_CLIENT_ID") or config.get("client_id")
        client_secret = os.getenv("ONEDRIVE_SECRET") or config.get("client_secret")
        drive_id = os.getenv("ONEDRIVE_DRIVE_ID") or config.get("drive_id")
        remote_dir = config.get("remote_dir", "chronicle/raw")
        raw_dir = Path(config.get("raw_dir", "../../data/chronicle/raw")).resolve()
        retention_days = int(config.get("retention_days", 7))
        delete_uploaded_only = bool(config.get("delete_uploaded_only", True))

        if not all([tenant_id, client_id, client_secret, drive_id]):
            msg = "OneDrive config incomplete. Check config/onedrive_raw_sync.json"
            print(msg)
            write_heartbeat("error", msg)
            async def alert_error():
                await send_notifier_alert(f"[에러] onedrive_sync_worker 실패: {msg}")
            asyncio.run(alert_error())
            return 1

        token = get_access_token(tenant_id, client_id, client_secret)
        if not token:
            msg = "Token acquisition failed"
            write_heartbeat("error", msg)
            async def alert_error():
                await send_notifier_alert(f"[에러] onedrive_sync_worker 실패: {msg}")
            asyncio.run(alert_error())
            return 1

        uploaded = set()
        for file in sorted(raw_dir.glob("*.json")):
            remote_path = f"{remote_dir}/{file.name}"
            print(f"Uploading {file} → {remote_path}")
            if upload_file(token, drive_id, file, remote_path):
                print(f"Uploaded: {file.name}")
                uploaded.add(file.name)
            else:
                print(f"Failed: {file.name}")

        # 로컬 파일 정리
        now = datetime.now()
        for file in sorted(raw_dir.glob("*.json")):
            mtime = datetime.fromtimestamp(file.stat().st_mtime)
            age = (now - mtime).days
            if age >= retention_days:
                if not delete_uploaded_only or file.name in uploaded:
                    print(f"Deleting local file: {file.name}")
                    file.unlink()

        write_heartbeat("ok", f"uploaded={len(uploaded)}")
        print("OneDrive sync complete.")
        return 0
    except Exception as e:
        err_msg = f"onedrive_sync_worker 에러: {e}"
        print("[에러]", err_msg)
        write_heartbeat("error", err_msg)
        async def alert_error():
            await send_notifier_alert(f"[에러] onedrive_sync_worker 실패: {e}")
        asyncio.run(alert_error())
        return 2

if __name__ == "__main__":
    sys.exit(main())
