"""
agg_summary.py
- 월별 원본 jsonl(chronicle_YY.MM.jsonl 등) → 연도별 요약 jsonl(chronicle_YYYY.jsonl)로 집계
- 일별 에러/비정상 카운트, 주요 이벤트만 저장
- 10MB 넘으면 분할(chronicle_2026_2.jsonl 등)
- 추후 주간/월간 통계 및 텔레그램 전송 연동 가능
"""
import json
from pathlib import Path
from datetime import datetime
import glob

DOMAIN = "chronicle"  # 필요시 sys.argv 등으로 확장 가능
BASE_DIR = Path(__file__).parent.parent.parent.parent
HISTORY_DIR = BASE_DIR / "data/summary/history"
AGG_DIR = BASE_DIR / "data/summary/agg"
AGG_DIR.mkdir(parents=True, exist_ok=True)
MAX_MB = 10

# 월별 원본 파일 목록
files = sorted(HISTORY_DIR.glob(f"{DOMAIN}_*.jsonl"))
all_rows = []
for f in files:
    with open(f, encoding="utf-8") as fin:
        for line in fin:
            try:
                row = json.loads(line)
                all_rows.append(row)
            except Exception:
                continue


# 일별 집계 및 전체 통계용 리스트
from collections import Counter
by_date = {}
all_error_msgs = []
for row in all_rows:
    date = row.get("summary_time", "")[:10]
    if not date:
        continue
    if date not in by_date:
        by_date[date] = {"date": date, "error_count": 0, "status_change_count": 0, "main_errors": [], "main_status": []}
    by_date[date]["error_count"] += len(row.get("error_events", []))
    by_date[date]["status_change_count"] += len(row.get("status_changes", []))
    by_date[date]["main_errors"].extend(row.get("error_events", []))
    by_date[date]["main_status"].extend(row.get("status_changes", []))
    # 에러 메시지 누적
    for e in row.get("error_events", []):
        msg = str(e.get("message") or e)
        all_error_msgs.append(msg)

# Top N 에러 메시지, 최다 에러 발생 일자
N = 5
error_msg_counter = Counter(all_error_msgs)
top_error_msgs = error_msg_counter.most_common(N)
max_error_day = max(by_date.values(), key=lambda x: x["error_count"], default=None)

# 연도별 jsonl로 저장(10MB 분할)
def get_next_agg_path(year):
    base = f"{DOMAIN}_{year}"
    files = sorted(glob.glob(str(AGG_DIR / f"{base}*.jsonl")))
    if not files:
        return AGG_DIR / f"{base}.jsonl"
    last = Path(files[-1])
    if last.stat().st_size < MAX_MB * 1024 * 1024:
        return last
    idx = 2
    while True:
        cand = AGG_DIR / f"{base}_{idx}.jsonl"
        if not cand.exists() or cand.stat().st_size < MAX_MB * 1024 * 1024:
            return cand
        idx += 1

agg_rows = sorted(by_date.values(), key=lambda x: x["date"])
for row in agg_rows:
    # Top N 에러 메시지, 최다 에러 일자 정보도 각 row에 추가(분석 편의)
    row["top_error_msgs"] = top_error_msgs
    if max_error_day:
        row["max_error_day"] = {"date": max_error_day["date"], "error_count": max_error_day["error_count"]}
    year = row["date"][:4]
    out_path = get_next_agg_path(year)
    with open(out_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

print(f"연도별 요약 jsonl 저장 완료: {AGG_DIR}")
