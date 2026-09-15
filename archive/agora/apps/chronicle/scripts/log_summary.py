"""
여러 도메인(chronicle, lean, telegrambot 등) 로그/상태 파일 집계 및 요약 스크립트
- 각 도메인별 data/<도메인>/state/ 내 상태 파일 및 주요 로그 파일 자동 분석
- 최근 24시간 내 에러/경고/상태 변화, 주요 이벤트 카운트 요약
- 에러/비정상 상태 발견 시 Notifier로 실시간 알림 전송
- 결과는 data/chronicle/reports/log_summary.txt 에 저장(추후 도메인별 리포트 확장 가능)
"""

import os
import json
from datetime import datetime, timedelta
from pathlib import Path
import re

import httpx
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr


# 설정
BASE_DIR = Path(__file__).parent.parent.parent.parent  # agora 루트
DOMAINS = [d.name for d in (BASE_DIR / "data").iterdir() if d.is_dir()]
REPORT_DIR = BASE_DIR / "data/chronicle/reports"
REPORT_FILE = REPORT_DIR / "log_summary.txt"
# summary 폴더 및 히스토리 폴더
SUMMARY_DIR = BASE_DIR / "data/summary"
SUMMARY_HISTORY_DIR = SUMMARY_DIR / "history"
MAX_HISTORY_MB = 10
HISTORY_KEEP_DAYS = 40
# Notifier 설정 (환경변수 또는 .env에서)
NOTIFIER_URL = os.environ.get("NOTIFIER_URL")
NOTIFIER_API_KEY = os.environ.get("NOTIFIER_API_KEY")
# 이메일 알림 설정
SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASS = os.environ.get("SMTP_PASS")
MAIL_FROM = os.environ.get("MAIL_FROM", SMTP_USER)
MAIL_TO = os.environ.get("MAIL_TO")  # 콤마로 여러명 가능

# 집계 기간: 최근 24시간
now = datetime.now()
cutoff = now - timedelta(days=1)


def parse_state_files(domain):
    results = []
    state_dir = BASE_DIR / f"data/{domain}/state"
    if not state_dir.exists():
        return results
    for f in state_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            ts = data.get("timestamp")
            if ts:
                dt = datetime.fromtimestamp(ts)
                if dt >= cutoff:
                    results.append({"file": f.name, "status": data.get("status"), "info": data.get("info"), "timestamp": dt, "domain": domain})
        except Exception as e:
            results.append({"file": f.name, "error": str(e), "domain": domain})
    return results

def parse_log_files(domain):
    events = []
    # 주요 로그 파일 후보: refined/realtime/*.log, logs/*.log 등
    log_dirs = [BASE_DIR / f"data/{domain}/refined/realtime", BASE_DIR / f"data/{domain}/logs"]
    pat = re.compile(r"\[(.*?)\] (.*)")
    for log_dir in log_dirs:
        if not log_dir.exists():
            continue
        for log_file in log_dir.glob("*.log"):
            for line in log_file.read_text(encoding="utf-8", errors="replace").splitlines():
                m = pat.match(line)
                if m:
                    try:
                        dt = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                        if dt >= cutoff:
                            events.append({"timestamp": dt, "message": m.group(2), "file": log_file.name, "domain": domain})
                    except Exception:
                        continue
    return events


def summarize():
    all_state = []
    all_logs = []
    domain_summaries = {}
    for domain in DOMAINS:
        state = parse_state_files(domain)
        logs = parse_log_files(domain)
        error_events = [e for e in logs if "error" in e["message"].lower() or "fail" in e["message"].lower()]
        status_changes = [s for s in state if s.get("status") and s.get("status") != "ok"]
        # 도메인별 json 요약 저장용
        domain_summaries[domain] = {
            "summary_time": now.isoformat(),
            "state": state,
            "logs": logs,
            "error_events": error_events,
            "status_changes": status_changes,
        }
        all_state.extend(state)
        all_logs.extend(logs)
    # 텍스트 요약(전체)
    error_events = [e for e in all_logs if "error" in e["message"].lower() or "fail" in e["message"].lower()]
    status_changes = [s for s in all_state if s.get("status") and s.get("status") != "ok"]
    lines = []
    lines.append(f"로그/상태 요약 (최근 24시간, 기준: {now:%Y-%m-%d %H:%M:%S})\n")
    lines.append(f"- 상태 파일 변화: {len(all_state)}건 (에러/비정상: {len(status_changes)}건)")
    for s in status_changes:
        lines.append(f"  * [{s['domain']}] {s['file']} | status={s.get('status')} | info={s.get('info')} | ts={s.get('timestamp')}")
    lines.append(f"\n- 로그 이벤트: {len(all_logs)}건 (에러/실패: {len(error_events)}건)")
    for e in error_events:
        lines.append(f"  * [{e['domain']}] [{e['timestamp']}] {e['message']} | file={e['file']}")
    return "\n".join(lines), status_changes, error_events, domain_summaries


def send_notifier_alert(msg: str):
    if NOTIFIER_URL and NOTIFIER_API_KEY:
        try:
            resp = httpx.post(NOTIFIER_URL, json={"message": msg}, headers={"Authorization": f"Bearer {NOTIFIER_API_KEY}"}, timeout=10)
            if resp.status_code == 200:
                print("[notifier] 알림 전송 성공")
            else:
                print(f"[notifier] 알림 실패: {resp.status_code} {resp.text}")
        except Exception as e:
            print(f"[notifier] 알림 예외: {e}")
    else:
        print("[notifier] NOTIFIER_URL/NOTIFIER_API_KEY 미설정, 알림 생략")

def send_email_alert(subject: str, body: str):
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS and MAIL_TO):
        print("[email] SMTP 환경변수 미설정, 이메일 알림 생략")
        return
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = formataddr(("AGORA 모니터링", MAIL_FROM))
        msg["To"] = MAIL_TO
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(MAIL_FROM, MAIL_TO.split(","), msg.as_string())
        print("[email] 이메일 알림 전송 성공")
    except Exception as e:
        print(f"[email] 이메일 알림 예외: {e}")

import glob
def get_next_history_path(domain, ym):
    """10MB 넘으면 _2, _3 등으로 분할"""
    base = f"{domain}_{ym}"
    files = sorted(glob.glob(str(SUMMARY_HISTORY_DIR / f"{base}*.jsonl")))
    if not files:
        return SUMMARY_HISTORY_DIR / f"{base}.jsonl"
    last = Path(files[-1])
    if last.stat().st_size < MAX_HISTORY_MB * 1024 * 1024:
        return last
    # 분할
    idx = 2
    while True:
        cand = SUMMARY_HISTORY_DIR / f"{base}_{idx}.jsonl"
        if not cand.exists() or cand.stat().st_size < MAX_HISTORY_MB * 1024 * 1024:
            return cand
        idx += 1

def cleanup_old_history():
    cutoff = now - timedelta(days=HISTORY_KEEP_DAYS)
    for f in SUMMARY_HISTORY_DIR.glob("*.jsonl"):
        mtime = datetime.fromtimestamp(f.stat().st_mtime)
        if mtime < cutoff:
            try:
                f.unlink()
                print(f"[history] 오래된 파일 삭제: {f}")
            except Exception as e:
                print(f"[history] 삭제 실패: {f} {e}")

def main():
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    summary, status_changes, error_events, domain_summaries = summarize()
    REPORT_FILE.write_text(summary, encoding="utf-8")
    print(f"요약 리포트가 저장되었습니다: {REPORT_FILE}")
    # 도메인별 json 요약 저장(최신)
    for domain, data in domain_summaries.items():
        out_path = SUMMARY_DIR / f"{domain}.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        # 월별 jsonl 파일에 append, 10MB 넘으면 분할
        ym = now.strftime("%y.%m")
        hist_path = get_next_history_path(domain, ym)
        with open(hist_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False, default=str) + "\n")
    cleanup_old_history()
    print(f"도메인별 요약 json이 저장되었습니다: {SUMMARY_DIR}, 히스토리: {SUMMARY_HISTORY_DIR}")
    # 에러/비정상 상태 발견 시 알림
    if status_changes or error_events:
        alert_msg = f"[log_summary] 에러/비정상 상태 감지!\n상태:{len(status_changes)}건, 로그:{len(error_events)}건\n자세한 내용은 리포트 및 summary 폴더 참조."
        send_notifier_alert(alert_msg)
        # 이메일 알림도 병행
        subject = "[AGORA] 에러/비정상 상태 감지 알림"
        body = f"에러/비정상 상태가 감지되었습니다.\n상태:{len(status_changes)}건, 로그:{len(error_events)}건\n\n자세한 내용은 서버의 data/summary/ 및 리포트 파일을 참조하세요.\n\n요약:\n" + summary[:1000]
        send_email_alert(subject, body)

if __name__ == "__main__":
    main()
