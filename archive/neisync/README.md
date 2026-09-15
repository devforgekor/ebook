# NEISync Rebuild Phase6

**실전 운영/확장/품질/보안/모니터링 통합 가이드**

- 자세한 운영/확장/품질/보안/모니터링 가이드는 [docs/phase6_guide.md](docs/phase6_guide.md) 참고

---

## 구조 및 역할
- `neisync/core/` : 설정, DB, 공통 유틸, 엔진, 로깅, 시간, 필터 등
- `neisync/collectors/` : 급식, 학사일정, 시간표, 학교정보 등 데이터 수집기
- `neisync/constants/` : 코드/경로/에러/스키마 상수
- `neisync/api/` : FastAPI 기반 관리자/운영자용 REST API
- `dashboard/` : Streamlit 대시보드(데이터/통계/현황 시각화)
- `tests/` : 단위/통합/예외/품질 테스트
- `scripts/` : 운영/배포/유틸 스크립트

## 빠른 시작
```bash
# 1. 가상환경 활성화
python -m venv .venv && source .venv/bin/activate
# 2. 의존성 설치
pip install -r requirements.txt
# 3. 환경 변수(.env) 또는 config.yaml 설정
cp .env.example .env
# 4. 급식 데이터 수집 (예시)
python -m neisync.cli meal --db-path data/neisync.db
```

## 주요 기능
- **Streamlit 대시보드**: `streamlit run dashboard/meal_dashboard.py`
- **CLI**: `python -m neisync.cli ...` (급식 수집, 경로 확인 등)
- **API 서버**: `uvicorn neisync.api.admin_api:app --reload`
- **Docker**: `docker build -t neisync . && docker run --env-file .env neisync`

## 테스트/품질 관리
- 전체 테스트: `pytest tests`
- 커버리지: `pytest --cov=neisync tests`
- 린트: `ruff check neisync tests`
- 타입체크: `mypy neisync`
- pre-commit, ruff, mypy, black 등 코드 품질 자동화

## 보안/모니터링/알림
- 환경변수, Secret Manager 등으로 민감정보 안전하게 관리
- 운영 DB/로그 파일 권한 엄격 관리(600/700 등)
- 주요 에러/이상 발생 시 Slack/이메일/SMS 등으로 자동 알림
- Prometheus/Grafana로 실시간 모니터링
- FastAPI `/health` 엔드포인트로 헬스체크 지원

## 기여/확장 가이드
- 새 수집기: `collectors/`에 추가, `core/db_schema.py`에 테이블 정의
- 분석/리포트: `analyzers/`, `exporters/`에 추가
- 대시보드/CLI/API: `dashboard/`, `cli.py`, `api/`에 추가
- 테스트: `tests/`에 시나리오별 케이스 추가, 커버리지 유지
- 문서화: README, developer_guide.md, phase6_guide.md 등 최신화

## 문서/지원
- [phase6 운영 가이드](docs/phase6_guide.md)
- [개발자 가이드](docs/developer_guide.md)
- 문의/이슈: GitHub Issues/Discussions 활용
