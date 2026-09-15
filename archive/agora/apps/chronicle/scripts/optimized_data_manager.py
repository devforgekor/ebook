from pathlib import Path
import os
import json
from datetime import datetime

TITLE_LIST_PATH = Path(__file__).parent.parent / "config/title_list.json"
OPTIMIZED_DIR = Path(__file__).parent.parent / "optimized"
MAX_FILE_SIZE_MB = 10

# 파일명 넘버링: 01, 02 형식
PART_FORMAT = "_{:02d}"

# 객체 구조 예시
# {
#   "year": 2026,
#   "month": 3,
#   "step": 1,
#   "user": "...",
#   "assistant": "...",
#   "reason": "...",
#   "branch": [ {...}, ... ]
# }

def write_heartbeat(status: str, info: str = "", state_dir=Path(__file__).parent.parent / "data/chronicle/state"):
    from datetime import datetime
    state_dir.mkdir(parents=True, exist_ok=True)
    heartbeat = {
        "status": status,
        "info": info,
        "timestamp": datetime.now().isoformat()
    }
    with open(state_dir / "optimizer_heartbeat.json", "w", encoding="utf-8") as f:
        json.dump(heartbeat, f, ensure_ascii=False, indent=2)
def generate_quality_report(title_list, optimized_dir=OPTIMIZED_DIR):
    report = []
    total_count = 0
    total_unknown = 0
    for title in title_list:
        files = sorted((optimized_dir).glob(f"{title}*.jsonl"))
        count = 0
        for file in files:
            with open(file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        obj = json.loads(line)
                        count += 1
                    except Exception:
                        continue
        total_count += count
        if title == "unknown":
            total_unknown = count
        report.append(f"{title}: {count}")
    unknown_ratio = (total_unknown / total_count * 100) if total_count else 0
    report.append(f"총 데이터: {total_count}")
    report.append(f"unknown 비율: {unknown_ratio:.2f}% ({total_unknown}/{total_count})")
    return "\n".join(report)

import asyncio
import httpx

import os
import json
from pathlib import Path
from datetime import datetime

TITLE_LIST_PATH = Path(__file__).parent.parent / "config/title_list.json"
OPTIMIZED_DIR = Path(__file__).parent.parent / "optimized"
MAX_FILE_SIZE_MB = 10

# 파일명 넘버링: 01, 02 형식
PART_FORMAT = "_{:02d}"

# 객체 구조 예시
# {
#   "year": 2026,
#   "month": 3,
#   "step": 1,
#   "user": "...",
#   "assistant": "...",
#   "reason": "...",
#   "branch": [ {...}, ... ]
# }

def load_title_list():
    with open(TITLE_LIST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def get_file_path(title, part=1):
    base = OPTIMIZED_DIR / f"{title}.jsonl"
    if part > 1:
        return OPTIMIZED_DIR / f"{title}{PART_FORMAT.format(part)}.jsonl"
    return base

def save_jsonl(title, data):
    part = 1
    file_path = get_file_path(title, part)
    buffer = []
    size = 0
    for obj in data:
        line = json.dumps(obj, ensure_ascii=False)
        size += len(line.encode("utf-8"))
        buffer.append(line)
        if size >= MAX_FILE_SIZE_MB * 1024 * 1024:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("\n".join(buffer) + "\n")
            part += 1
            file_path = get_file_path(title, part)
            buffer = []
            size = 0
    if buffer:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(buffer) + "\n")

def vacuum(data):
    seen = set()
    result = []
    for obj in data:
        key = json.dumps(obj, sort_keys=True, ensure_ascii=False)
        if key.strip() and key not in seen:
            seen.add(key)
            result.append(obj)
    return result

def retry_unknown(data, title_list):
    unknown_data = [obj for obj in data if obj.get("title") == "unknown"]
    return unknown_data


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


def merge_files(title):
    files = sorted(OPTIMIZED_DIR.glob(f"{title}*.jsonl"))
    merged = []
    for file in files:
        with open(file, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                    merged.append(obj)
                except Exception:
                    continue
    return vacuum(merged)


def main():
    try:
        title_list = load_title_list()
        for title in title_list:
            merged = merge_files(title)
            save_jsonl(title, merged)
        # unknown retry 예시
        unknown_data = retry_unknown(merge_files("unknown"), title_list)
        # unknown 데이터 푸쉬 예시 (최대 5개만)
        async def alert_unknowns():
            for obj in unknown_data[:5]:
                msg = f"[unknown] {obj.get('user', '')}\n{obj.get('assistant', '')}"
                await send_notifier_alert(msg)
        asyncio.run(alert_unknowns())

        # 품질 리포트 생성 및 Notifier로 전송
        quality_report = generate_quality_report(title_list)
        print("[품질 리포트]", quality_report)
        async def alert_report():
            await send_notifier_alert(f"[품질 리포트]\n{quality_report}")
        asyncio.run(alert_report())

        write_heartbeat("ok", "품질 리포트 정상 생성")
    except Exception as e:
        err_msg = f"optimizer_worker 에러: {e}"
        print("[에러]", err_msg)
        write_heartbeat("error", err_msg)
        async def alert_error():
            await send_notifier_alert(f"[에러] optimizer_worker 실패: {e}")
        asyncio.run(alert_error())

if __name__ == "__main__":
    main()
