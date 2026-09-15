# 개발 환경 설정 가이드

## 프로젝트 위치

모든 프로젝트는 `minihome/apps/` 아래에 있습니다.

| 프로젝트 | 위치 |
|----------|------|
| news | minihome/apps/news/ |
| timetable | minihome/apps/timetable/ |
| kuhwa | minihome/apps/kuhwa/ |
| ebooklib | minihome/apps/ebooklib/ |
| cashbook | minihome/apps/cashbook/ |
| minihome | minihome/apps/minihome/ |

workspace/ 루트의 news/, timetable/, kuhwa/, ebooklib/ 은 레거시 빈 디렉토리입니다.

workspace/ 루트의 archive/, azure/ 은 레거시 프로젝트/스크립트입니다.
common-lib/ 은 공유 Python 라이브러리입니다.
minihome/ 은 웹 프로젝트 모노레포입니다.

/opt/projects/
├── server/      ← DevForge 서버 (FastAPI, podman)
├── scripts/     ← 서버 스크립트 (lib, pipelines 등)
└── ...          ← 에이전트 시스템 스크립트

## 아카이브 (workspace/archive/)

완료되거나 사용하지 않는 모든 프로젝트가 보관되어 있습니다.

| 프로젝트 | 위치 |
|----------|------|
| agora | workspace/archive/agora/ |
| isuflow | workspace/archive/isuflow/ |
| neisync | workspace/archive/neisync/ |
| papertrail | workspace/archive/papertrail/ |
| js-utils | workspace/archive/js-utils/ |
| make-vm | workspace/archive/make-vm/ |
| schooldocs | workspace/archive/schooldocs/ |
| axis | workspace/archive/axis/ |
| extentions | workspace/archive/extentions/ |
| schools | workspace/archive/schools/ |

## Python 버전

- **시스템 `python3`**: 3.9.25 유지 (dnf, cloud-init, cockpit 등 시스템 툴용) — 변경 금지
- **개발용 `python3.11`**: 모든 프로젝트 개발 시 명시적 사용

### 사용법

```bash
# venv 생성
python3.11 -m venv .venv

# 활성화 및 실행
source .venv/bin/activate
python main.py

# 직접 실행도 동일
python3.11 main.py
```

### 주의

- `python3` 또는 `python`은 3.9이므로 개발에 사용하지 마세요
- CI/CD 및 Dockerfile은 이미 Python 3.11로 통일됨
