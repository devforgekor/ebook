"""
send_agg_report.py
- agg/chronicle_YYYY.jsonl에서 최근 1주/1개월 통계 요약
- 텔레그램 Notifier로 자동 전송
- .env에 TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 필요
"""
import json
from pathlib import Path
from datetime import datetime, timedelta
import os
import httpx

DOMAIN = "chronicle"
AGG_DIR = Path(__file__).parent.parent.parent / "data/summary/agg"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_NOTICE_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")

now = datetime.now()

# 연도별 agg 파일 목록
files = sorted(AGG_DIR.glob(f"{DOMAIN}_*.jsonl"))
all_rows = []
for f in files:
    with open(f, encoding="utf-8") as fin:
        for line in fin:
            try:
                row = json.loads(line)
                all_rows.append(row)
            except Exception:
                continue

def agg_stats(rows, start_date, end_date):
    filtered = [r for r in rows if start_date <= r["date"] <= end_date]
    error_sum = sum(r["error_count"] for r in filtered)
    status_sum = sum(r["status_change_count"] for r in filtered)
    return error_sum, status_sum, filtered

# 주간/월간 기간 계산
today = now.date()
week_start = (today - timedelta(days=6)).isoformat()
month_start = (today.replace(day=1)).isoformat()
end_date = today.isoformat()

week_error, week_status, week_rows = agg_stats(all_rows, week_start, end_date)
month_error, month_status, month_rows = agg_stats(all_rows, month_start, end_date)

def send_telegram(msg):
    if not (TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID):
        print("[telegram] 환경변수 미설정, 전송 생략")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}
    try:
        resp = httpx.post(url, json=payload, timeout=10)
        print(f"[telegram] 전송 결과: {resp.status_code}")
    except Exception as e:
        print(f"[telegram] 전송 예외: {e}")

# 메시지 생성
week_msg = f"[AGORA 주간 요약]\n기간: {week_start}~{end_date}\n에러: {week_error}건, 비정상: {week_status}건"
month_msg = f"[AGORA 월간 요약]\n기간: {month_start}~{end_date}\n에러: {month_error}건, 비정상: {month_status}건"

print(week_msg)
print(month_msg)
send_telegram(week_msg)
send_telegram(month_msg)
