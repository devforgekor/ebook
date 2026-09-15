# LLM 데이터 파이프라인 구조 및 운영 로직 (2026-03-15)

## 1. 폴더 구조
- `scripts/` : 코드 및 스크립트
- `data/processed/`   : 최종 정제 데이터 (LLM 학습용)
- `data/logs/`       : (선택) 실행/분석 로그
- (data/raw, data/processed, data/refined 등 원본/중간 데이터는 data/ 하위에만 보관)

## 2. 데이터 흐름
- 원본(raw) → 정제 스크립트(scripts/) 실행 → data/processed/에 최종본 생성
- data/processed/ 폴더는 Google Drive와 동기화 (최신본만 업로드)
- Google Drive는 최종본의 중앙 저장소 역할 (여러 환경/서버/협업자와 공유)
- 로컬에서는 scripts/, data/processed/ (필요시 data/logs/)만 관리

## 3. 데이터 읽기/쓰기 정책
- LLM 학습/분석/추론 시에는 반드시 processed/ 폴더(최신본)만 읽음
- Google Drive에서 최신 processed/만 받아 사용 (raw, backup 등은 무시)
- 필요시 날짜/버전별로 processed/ 데이터 관리(롤백/이력 추적)

## 4. state 관리
- 데이터 처리/동기화 진행상황(state)은 별도 `state/` 폴더에 저장 (중복 방지, resume 등)
- state는 최종 데이터와 분리하여 관리 (예: 마지막 처리 파일, 중복 해시, 진행률 등)

## 5. 장점

## 6. 예시
- 정제 스크립트 실행:
-     ```bash
-     python scripts/process_raw_chat_snapshots.py --raw-dir ... --output-dir data/processed/
-     ```
- unknown 토큰 분석:
-     ```bash
-     python scripts/unknown_token_analyzer.py --vocab ... --input data/processed/chat_ko_review.jsonl
-     ```
