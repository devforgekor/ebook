# 🛠️ Chronicle 데이터 파이프라인 자동화 & 운영 가이드 (2026-03 최신)

## 전체 구조 요약
- raw → processed → optimized → OneDrive 백업까지 모든 단계 자동화
- 각 단계별 워커/스크립트: process_raw_chat_snapshots.py, optimized_data_manager.py, onedrive_sync_worker.py 등
- 장애/이상 데이터 발생 시 Notifier(HTTP API)로 실시간 알림
- 모든 경로/인증/알림 설정은 .env 및 config 파일로 관리

## 주요 자동화 워커/스크립트

| 역할 | 파일명 | 실행 예시 |
|------|--------|-----------|
| raw → processed 변환 | scripts/process_raw_chat_snapshots.py | python scripts/process_raw_chat_snapshots.py |
| 데이터 품질관리(중복제거/병합/unknown 알림) | scripts/optimized_data_manager.py | python scripts/optimized_data_manager.py |
| OneDrive 업로드/로컬 정리 | workers/onedrive_sync_worker.py | python workers/onedrive_sync_worker.py |
| 임시파일 정리 | scripts/cleanup_temp_files.py | python scripts/cleanup_temp_files.py |
| 일별 스냅샷 | scripts/finalize_daily_chat_dataset.py | python scripts/finalize_daily_chat_dataset.py |

## 스케줄/운영 예시 (cron)
```
0 * * * * .../python scripts/process_raw_chat_snapshots.py
0 3 * * * .../python scripts/cleanup_temp_files.py
0 4 * * * .../python workers/onedrive_sync_worker.py
0 5 * * * .../python scripts/finalize_daily_chat_dataset.py
0 6 * * * .../python scripts/optimized_data_manager.py
```

## Notifier 장애 알림 구조
- optimized_data_manager.py 등에서 unknown/이상 데이터 발생 시 Notifier HTTP API로 실시간 알림
- .env에 NOTIFIER_URL, NOTIFIER_API_KEY, 알림 채널 등 설정
- 장애/품질 이슈 발생 시 관리자에게 즉시 전달

## 환경변수/운영 가이드
- 모든 인증/경로/알림 설정은 .env, config/onedrive_raw_sync.json 등에서 관리
- 예시:
  ```env
  NOTIFIER_URL=http://localhost:8001
  NOTIFIER_API_KEY=your-key
  ONEDRIVE_CLIENT_ID=...
  ONEDRIVE_SECRET=...
  ONEDRIVE_DRIVE_ID=...
  TENANT_ID=...
  ```

## 장애 대응 체크리스트
- 워커/스크립트 실행 실패 시 로그 확인 (logs/, state/ 폴더)
- Notifier 알림 미수신 시 API 키/URL/채널 환경변수 점검
- OneDrive 인증/권한 문제 발생 시 관리자/테넌트 설정 확인
- 데이터 품질 이상(unknown, 중복 등) 발생 시 optimized_data_manager.py 알림 확인

## 신규 멤버/운영자 실전 매뉴얼
1. .env, config 파일에 인증/경로/알림 정보 입력
2. 각 워커/스크립트 수동 실행으로 정상 동작 확인
3. cron/PM2에 등록하여 자동화
4. 장애/알림 발생 시 README 및 로그/알림 참고하여 대응

---
# optimized_data_manager 사용법 및 데이터 구조 예시

## 타이틀 리스트
- config/title_list.json에서 관리

# 🏢 OneDrive 기반 데이터 파이프라인 (2026-03)

## [NEW] OneDrive 연동 및 자동화
- Google Drive 대신 **OneDrive만 공식 지원**합니다.
- 모든 동기화/백업/로컬 정리는 `workers/onedrive_sync_worker.py`로 자동화합니다.
- 설정은 `.env`와 `config/onedrive_raw_sync.json`에서 관리합니다.

### 사용법
1. .env에 ONEDRIVE_CLIENT_ID, ONEDRIVE_SECRET, TENANT_ID 등 입력
2. config/onedrive_raw_sync.json에 drive_id, 경로 등 입력 (환경변수 사용 가능)
3. 워커 실행:
   ```bash
   python workers/onedrive_sync_worker.py
   ```
4. 업로드 성공 파일만 retention_days(기본 7일) 동안 로컬에 보관, 이후 자동 삭제

> Google Drive 관련 동기화는 현재 지원하지 않으며, 필요시 별도 안내 예정

- 예시: dev, news, health, economy, stock, forex, realestate, retire, edu, travel, hobby, world, unknown

## 데이터 구조 예시 (jsonl)
각 줄마다 아래와 같은 객체가 저장됨:


```
{
  "year": 2026,
  "month": 3,
  "step": 1,
  "title": "dev",
  "user": "파이썬에서 리스트를 정렬하는 방법 알려줘.",
  "assistant": "sorted() 함수를 사용하면 리스트를 정렬할 수 있습니다.",
  "reason": "sorted()는 파이썬 내장 함수로 초보자도 쉽게 사용할 수 있기 때문입니다.",
  "branch": [
    {
      "user": "내림차순으로 정렬하려면?",
      "assistant": "sorted(my_list, reverse=True)로 내림차순 정렬이 가능합니다.",
      "reason": "reverse=True 옵션을 사용하면 내림차순이 됩니다."
    }
  ]
}
```

- unknown 타이틀은 "title": "unknown"으로 자동 분류
- optimized 폴더에 타이틀별로 저장, 10MB 넘으면 part 넘버링(01, 02...)
- vacuum(중복/불필요 데이터 제거), retry(unknown 분류), 병합(파일 합치기) 자동화

## 관리 규칙
- 모든 데이터는 UTF-8, LF 줄바꿈, 표준 jsonl 포맷
- vacuum, retry, 병합 등 자동화 스크립트에서 관리
- unknown 데이터는 텔레그램으로 푸쉬, 사용자가 분류하면 규칙에 자동 반영
## 임시파일 관리 및 자동 정리
예시:
```bash
python scripts/cleanup_temp_files.py
```
스케줄러 예시(cron):
```
0 3 * * * /Users/minipark4u/project/agora/apps/chronicle/.venv/bin/python /Users/minipark4u/project/agora/apps/chronicle/scripts/cleanup_temp_files.py
```
# chronicle LLM 데이터 파이프라인 가이드 (2026-03-16)
0 4 * * * /Users/minipark4u/project/agora/apps/chronicle/.venv/bin/python /Users/minipark4u/project/agora/apps/chronicle/workers/onedrive_sync_worker.py

## 폴더 구조 및 데이터 흐름
```
chronicle/
├── scripts/           # 데이터 처리/정제/분석 코드
├── data/
│   ├── raw/           # 원본 데이터 (실시간/Drive 등에서 수집)
│   ├── processed/     # 정제·최종본 (LLM 학습/분석용)
│   ├── refined/       # 추가 가공본 (실험/후처리)
│   ├── logs/          # 실행/분석 로그
│   └── state/         # 처리 이력, resume, 중복 방지
```

1. 원본(raw) → scripts/process_raw_chat_snapshots.py 실행 → processed/에 chat_ko_review.jsonl, chat_manifest.json 등 생성
2. processed/ 폴더는 Google Drive와 동기화 (최신본만 업로드)
3. refined/ 폴더는 추가 실험·후처리 결과 저장
4. state/ 폴더는 처리 이력, 중복 방지, resume 정보 관리
5. logs/ 폴더는 실행/분석 로그 저장

## 데이터 읽기/쓰기 정책
- LLM 학습/분석/추론 시에는 반드시 processed/ 폴더(최신본)만 읽음
- Google Drive에서 최신 processed/만 받아 사용 (raw, backup 등은 무시)
- 필요시 날짜/버전별로 processed/ 데이터 관리(롤백/이력 추적)
- refined/는 실험·후처리 결과만 사용

## state 관리
- 데이터 처리/동기화 진행상황(state)은 별도 state/ 폴더에 저장
- 예시: processed/state/raw_process_state.json (처리 이력, 중복 방지, resume)
- state는 최종 데이터와 분리하여 관리

## 장점
- 데이터 혼선/중복/실수 방지, 협업·자동화·백업 효율적
- 실험/정제/학습 환경 분리로 관리 용이
- 코드(automation)는 git 등으로 버전 관리

## 주요 예시
- 정제 스크립트 실행:
  ```bash
  python scripts/process_raw_chat_snapshots.py --raw-dir data/raw/ --output-dir data/processed/
  ```
- unknown 토큰 분석:
  ```bash
  python scripts/unknown_token_analyzer.py --vocab vocab_test.txt --input data/processed/chat_ko_review.jsonl
  ```
- state 파일 관리:
  - 처리 이력: data/state/raw_process_state.json
  - 중복 방지: .seen_hashes.jsonl
  - resume: state 정보 활용
- processed/ 폴더 주요 파일:
  - chat_ko_review.jsonl: 정제된 대화 데이터
  - chat_manifest.json: 생성 이력/메타
  - chat_en.jsonl: 영문 요약본 (옵션)
  - 날짜별 파일: chat_daily_YYYY-MM-DD.json 등

---

---
이 가이드와 구조를 따르면, chronicle LLM 데이터 파이프라인을 안전하고 효율적으로 운영할 수 있습니다.
