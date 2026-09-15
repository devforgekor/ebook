# 🏃‍♂️ Lean 앱 (토큰 최적화) 리빌딩 가이드

## 주요 구조 및 실행법

- **토큰 최적화 워커**: Redis Streams 기반, 메시지 유실 방지, graceful shutdown, 데드레터 지원
	- 실행: `python workers/redis_worker.py`
- **API 서버**: FastAPI 기반, run_in_threadpool로 CPU 연산 처리, 전략 프리셋/세부 규칙 모두 지원
	- 실행: `uvicorn api.main:app --reload --port 8002`
- **토크나이저/최적화**: core/ai/token_utils.py의 Tokenizer/TokenOptimizer 구조 사용
- **통계 기록**: core/stats.py에서 JSONL로 토큰 절감량 기록
- **테스트**: pytest 기반 단위/통합 테스트 제공

## 환경변수 예시
```
REDIS_URL=redis://localhost:6379
LEAN_STREAM=lean:optimize
LEAN_RESULT_STREAM=lean:result
LEAN_GROUP=lean-workers
LEAN_WORKER_COUNT=2
LEAN_DLQ=lean:deadletter
LEAN_STATS_DIR=data/lean/stats
```

## PM2 예시
- workers/redis_worker.py: 워커 진입점
- api/main.py, api/routes.py: API 서버
## Lean 서비스 운영/개발 가이드 (systemd 기준)

### 1. .env 파일 준비
- 프로젝트 루트 또는 앱 디렉토리에 .env 파일을 생성하고 환경변수 입력

### 2. systemd 서비스 등록 및 실행
1. 서비스 유닛 파일(예: lean.service)에서 [Service] 섹션에 EnvironmentFile=/path/to/.env 지정
2. 아래 명령어로 서비스 등록 및 실행
	```bash
	sudo cp lean.service /etc/systemd/system/
	sudo systemctl daemon-reload
	sudo systemctl enable lean
	sudo systemctl start lean
	sudo systemctl status lean
	sudo journalctl -u lean -f
	```

### 3. 로컬 개발
- .env 파일만 있으면 python-dotenv로 자동 로드됨 (코드에 load_dotenv 추가)
- systemd 없이 직접 python main.py 실행 가능

---
자세한 리빌딩 원칙/배경은 rebuild.md 참고.


# ⚠️ [중요] legacy(main.py, token_utils.py, blpop/rpush 등)는 더 이상 사용하지 않습니다.

이 앱은 반드시 아래 구조로 운영/개발/테스트해야 합니다.

- 토큰 최적화/전처리: core/ai/token_utils.py (Tokenizer/TokenOptimizer)
- Redis Streams 워커: workers/redis_worker.py
- FastAPI API 서버: api/
- 통계 기록: core/stats.py
- 테스트: tests/ (pytest)

자세한 예시, 함수 설명, 정책은 README 상단, rebuild.md, core/ai/token_utils.py, workers/redis_worker.py 참고.
