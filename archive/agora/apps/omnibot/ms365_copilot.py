#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stdin 기본 동작 + 옵션 모드 지원 대화 로거 (ultra-simple final)
- 파일을 인자 없이 실행하면 자동으로 stdin 실시간 기록 모드로 진입
- 명시적으로 --stdin 플래그 사용도 가능
- --role/--content 로 단건 기록도 가능

규칙(stdin 모드):
  * '너:' 로 시작 → role='assistant'
  * '이유:' 로 시작 → type='reasoning' (직전 메시지 ts를 ref_ts로 참조)
  * 그 외 모든 줄 → role='user'
  * 빈 줄은 content="" 로 명시 저장

공통:
  * 10분 공백 시 새 세션 파일(chat_YYYY-MM-DD_sNN.jsonl) 자동 생성
  * flush + fsync 로 즉시 디스크 반영
"""

import os, json, glob, sys, argparse
from datetime import datetime, timedelta

BASE_DIR_DEFAULT = os.getenv("LOG_DIR", os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../logs/omnibot')))
IDLE_MINUTES_DEFAULT = 10

# --------------------------- 시간/경로 유틸 ---------------------------

def now():
    return datetime.now().astimezone()

def today(dt):
    return dt.strftime("%Y-%m-%d")

def ensure_dir(d):
    os.makedirs(d, exist_ok=True)

def parse_iso(s):
    return datetime.fromisoformat(s)

# --------------------------- 세션/파일 유틸 ---------------------------

def list_sessions(base, date):
    return sorted(glob.glob(os.path.join(base, f"chat_{date}_s*.jsonl")))

def last_record_ts(path):
    """마지막 message/reasoning 레코드의 ts 반환"""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return None
    with open(path, "rb") as f:
        f.seek(0, 2)
        pos = f.tell()
        buf = bytearray()
        while pos > 0:
            pos -= 1
            f.seek(pos)
            b = f.read(1)
            if b == b'\n' and buf:
                line = buf[::-1].decode("utf-8", errors="ignore").strip()
                if line:
                    try:
                        rec = json.loads(line)
                        if rec.get("type") in ("message", "reasoning") and "ts" in rec:
                            return parse_iso(rec["ts"])
                    except:
                        pass
                buf.clear()
            else:
                buf.extend(b)
        if buf:
            line = buf[::-1].decode("utf-8", errors="ignore").strip()
            if line:
                try:
                    rec = json.loads(line)
                    if rec.get("type") in ("message", "reasoning") and "ts" in rec:
                        return parse_iso(rec["ts"])
                except:
                    return None
    return None

def choose_file(dt, base_dir, idle_minutes):
    """현재 시각 기준으로 세션 파일 선택. 10분 이상 공백이면 새 파일."""
    date = today(dt)
    ensure_dir(base_dir)
    existing = list_sessions(base_dir, date)
    if not existing:
        return os.path.join(base_dir, f"chat_{date}_s01.jsonl"), True
    latest = existing[-1]
    ts = last_record_ts(latest)
    if ts is None:
        return latest, False
    if (dt - ts) >= timedelta(minutes=idle_minutes):
        seq = int(os.path.splitext(os.path.basename(latest))[0].split("_s")[-1])
        return os.path.join(base_dir, f"chat_{date}_s{seq+1:02d}.jsonl"), True
    return latest, False

# --------------------------- 쓰기 유틸 ---------------------------

def safe_json_write(path, record):
    """JSON 직렬화 실패 시 repr로 안전하게 대체"""
    try:
        line = json.dumps(record, ensure_ascii=False)
    except Exception as e:
        safe_record = {
            "type": record.get("type", "message"),
            "ts": record.get("ts"),
            "role": record.get("role"),
            "content": repr(record.get("content")),
            "error": f"json encode failed: {e}"
        }
        if "ref_ts" in record:
            safe_record["ref_ts"] = record["ref_ts"]
        line = json.dumps(safe_record, ensure_ascii=False)
    with open(path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())

def write_session_start(path, dt):
    rec = {"type":"session_start","ts":dt.isoformat(),"date":today(dt)}
    safe_json_write(path, rec)

def write_message(path, dt, role, content):
    rec = {"type":"message","ts":dt.isoformat(),"role":role,"content":content}
    safe_json_write(path, rec)
    return rec["ts"]

def write_reasoning(path, dt, ref_ts, content):
    rec = {"type":"reasoning","ts":dt.isoformat(),"ref_ts":ref_ts,"content":content}
    safe_json_write(path, rec)

# --------------------------- 모드 1: stdin 실시간 기록 ---------------------------

def run_stdin(base_dir, idle_minutes):
    print("실시간 기록 모드입니다. 줄마다 입력하세요. (Ctrl+C 로 종료)")
    print("규칙) '너: ...' → assistant,  '이유: ...' → reasoning,  그 외 → user")
    last_message_ts_str = None

    try:
        while True:
            raw = sys.stdin.readline()
            if raw == "":
                # EOF(파이프 종료 등)
                break
            line = raw.rstrip("\n")
            ts_dt = now()

            path, is_new = choose_file(ts_dt, base_dir, idle_minutes)
            if is_new or not os.path.exists(path) or os.path.getsize(path) == 0:
                write_session_start(path, ts_dt)

            stripped = line.strip()

            # 1) 빈 줄 → user, content=""
            if stripped == "":
                last_message_ts_str = write_message(path, ts_dt, "user", "")
                print(f"저장됨 → {path}")
                continue

            # 2) reasoning 레코드
            if stripped.startswith("이유:") or stripped.startswith("이유 :"):
                reason_text = stripped.split(":", 1)[1].strip()
                write_reasoning(path, ts_dt, last_message_ts_str, reason_text)
                print(f"저장됨(이유) → {path}")
                continue

            # 3) assistant 라벨
            if stripped.startswith("너:") or stripped.startswith("너 :"):
                role = "assistant"
                content_value = stripped.split(":", 1)[1].strip()
            else:
                role = "user"
                content_value = stripped

            last_message_ts_str = write_message(path, ts_dt, role, content_value)
            print(f"저장됨 → {path}")

    except KeyboardInterrupt:
        print("\n종료합니다.")

# --------------------------- 모드 2: 옵션 단건 기록 ---------------------------

def run_single(role, content, base_dir, idle_minutes, ts=None, reasoning=None):
    dt = parse_iso(ts) if ts else now()
    path, is_new = choose_file(dt, base_dir, idle_minutes)
    if is_new or not os.path.exists(path) or os.path.getsize(path) == 0:
        write_session_start(path, dt)
    # content가 비면 ""로 기록
    content_value = content if content.strip() else ""
    msg_ts = write_message(path, dt, role, content_value)
    if reasoning:
        write_reasoning(path, dt, msg_ts, reasoning)
    print("저장됨 →", path)

# --------------------------- 진입점 ---------------------------

def main():
    ap = argparse.ArgumentParser(description="M365 대화 JSONL 로거 (stdin 기본)")
    # 모드 전환용
    ap.add_argument("--stdin", action="store_true", help="표준입력 실시간 기록 모드")
    # 단건 기록용 (선택)
    ap.add_argument("--role", choices=["user","assistant"], help="단건 기록 시 화자")
    ap.add_argument("--content", help="단건 기록 시 내용")
    ap.add_argument("--reasoning", default=None, help="단건 기록 시 reasoning(별도 레코드)")
    ap.add_argument("--base-dir", default=BASE_DIR_DEFAULT, help="저장 폴더 (기본 ./logs)")
    ap.add_argument("--idle-minutes", type=int, default=IDLE_MINUTES_DEFAULT, help="세션 분기 임계값(분)")
    ap.add_argument("--ts", default=None, help="ISO8601 시각 강제 지정(테스트용)")
    args = ap.parse_args()

    # 1) 단건 기록 모드가 충분한 인자를 받았으면 그걸 우선 실행
    if args.role and args.content is not None:
        run_single(args.role, args.content, args.base_dir, args.idle_minutes, ts=args.ts, reasoning=args.reasoning)
        return

    # 2) 그 외에는 stdin 모드로 진입 (기본 동작)
    #    (명시적으로 --stdin 을 주든, 아무 인자도 없든 동일하게 stdin 모드)
    run_stdin(args.base_dir, args.idle_minutes)

if __name__ == "__main__":
    main()
    