# 코드 정리 계획서

## 목적
- common-lib 내 코드 혼재 정리
- 코드 삭제 없이 조직화
- 에이전트 코드 생성 위치 표준화

## 원칙
1. **코드 삭제 금지** — 사용하지 않아도 보존
2. **삽입 정렬** — 새 코드 규칙 준수, 기존은 그대로
3. **단계적 정리** — 한 번에 다 안 함

---

## 현재 상태 (서버 로직 분석 결과)

| 위치 | 파일 수 | 설명 |
|------|---------|------|
| `src/common_lib/` | 44 | 진짜 공통 (import 사용 가능) |
| `workspace/archive/` | 268 | 9개 완료 프로젝트 (보존용) |
| `minihome/apps/` | 64 | 6개 독립 웹 앱 (공유 로직 없음) |
| **합계** | **504** | |

### 발견된 중복 패턴 (4단계)

#### L1 — 완전 중복 (동일 파일)
| 쌍 | 동일 파일 | 차이 |
|-----|-----------|------|
| `news/` ↔ `minihome/apps/news/` | 9/12 동일 | 2개 경로 상수, 1개 멀티모달 |
| `timetable/calendar_sync/` ↔ `minihome/apps/timetable/calendar_sync/` | 8/8 동일 | 없음 |
| `timetable/lib/db.py` ↔ `minihome/apps/timetable/lib/db.py` | 동일 | 없음 |
| `timetable/main.py` ↔ `minihome/apps/timetable/main.py` | ~90% 동일 | 경로 주석, import 2개 |

#### L2 — 구조적 중복 (2중 디렉토리)
위치: `workspace/archive/neisync/` 내부

| 위치 A | 위치 B | 상태 |
|--------|--------|------|
| `neisync/core/http.py` (98 line) | `neisync/neisync/core/http.py` (4 line) | A=실체, B=스텁 |
| `neisync/core/collector.py` (65 line) | `neisync/neisync/core/collector.py` (4 line) | A=실체, B=스텁 |

#### L3 — 목적 중복 (같은 기능, 다른 구현)

> archive/ 내 코드는 보존용. 현재 통합 대상 아님.

| 기능 | 파일 수 | 위치 예시 | 공통 가능성 |
|------|---------|-----------|-------------|
| config.py | 10 | agora(6, archive/), neisync(1, archive/), common_lib(3) | common_lib/core/config.py 활용 검토 |
| db/database.py | 6 | news(2, archive/), timetable(2), ebooklib(1), neisync(1, archive/) | timetable + ebooklib 추후 검토 |
| logger | 4 | agora(2, archive/), common_lib/core, neisync(1, archive/), agora/notifier | common_lib/core/logger.py 활용 검토 |
| http client | 4 | agora(1, archive/), common_lib/core, neisync(2, archive/), agora/utils | common_lib/core/http.py 활용 검토 |
| main.py | 9 | 각 프로젝트 | 공통 없음 (각 프로젝트 독립) |

#### L4 — 기능 유사 (Deploy 등)
| 기능 | 파일 수 | 위치 |
|------|---------|------|
| deploy | 10 | papertrail(4), schooldocs(3), make-vm(1), azure(2), domain(1) |

## Phase 1: 규칙 수립 (1일)

### 1.1 CLAUDE.yaml에 위치 규칙 추가
```yaml
location_rules:
  - "새 코드: 항상 프로젝트 루트에서 생성"
  - "2번 이상 반복 사용 → src/common_lib/ 로 harvest"
  - "harvest/ 내 코드: 사용자 검토 대상 (아직 미사용)"
  - "에이전트 코드 생성 전 반드시 CLAUDE.yaml 리드"
```

### 1.2 AGENTS.yaml에 추가
```yaml
before_coding:
  - "어디에 만들지 CLAUDE.yaml 확인"
  - "프로젝트 내지 common-lib/src 직생성 금지"
```

## Phase 2: harvest/ 재분류 (2일)

### 2.1 workspace/archive/ 내부 구조 태그
각 프로젝트에 STATUS 파일 생성:

```
workspace/archive/
├── agora/STATUS          → "active" (사용 중) | "dormant" (보존용)
├── isuflow/STATUS
├── js-utils/STATUS
├── make-vm/STATUS
├── neisync/STATUS
├── papertrail/STATUS
├── schooldocs/STATUS
├── axis/STATUS
├── extentions/STATUS
└── schools/STATUS
```

### 2.2 STATUS 판단 기준
- **active**: 다른 프로젝트에서 import하거나 반복 사용 중
- **dormant**: 사용하지 않지만 버리기 아까워서 보존
- **archive**: 완료되어 참고만 하는 코드

## Phase 3: 중복 점검 (1주)

### 3.1 중복 파일 매핑 (삭제 아님)

| 공통 기능 | 현 위치 | 추천 공통 | 상태 |
|-----------|--------|----------|------|
| deploy | 여러 위치 | src/common_lib/azure/deploy.py | 기존 공통 활용 |
| config | 10+개 | src/common_lib/core/config.py | 기존 공통 활용 |
| logger | 여러 위치 | src/common_lib/core/logger.py | 기존 공통 활용 |
| utils | 여러 위치 | src/common_lib/core/utils.py | 기존 공통 활용 |

### 3.2 조치 방식
- 공통이 이미 있는 기능 → 프로젝트에서 `from common_lib.xxx` 로 변경 (삭제 아님)
- 공통에 없는 코드 → 그대로 보존, 나중에 harvest 검토

## Phase 4: 에이전트 가드레일 (지속)

### 4.1 에이전트 체크리스트 (CLAUDE.yaml)
```yaml
agent_rules:
  before_create:
    - "프로젝트? → 프로젝트 루트에 생성"
    - "공통? → 2번 사용된 코드만 src/common_lib/"
  before_edit:
    - "traceback 경로 확인"
    - "common-lib 경로 → 여기서 수정"
    - "프로젝트 경로 → 그 프로젝트에서 수정"
```

## Phase 5: Git 초기화 (Phase 1-4 이후)

```bash
cd /opt/workspace
git init
git add .
git commit -m "initial: 코드 정리 완료"
```

Git이 있으면 코드 이동/변경 이력을 추적 가능

---

## 일정

| Phase | 내용 | 기간 | 삭제 여부 |
|-------|------|------|-----------|
| 1 | 규칙 수립 | 1일 | 없음 |
| 2 | archive/ STATUS 태그 | 2일 | 없음 (STATUS만) |
| 3 | 중복 점검 | 1주 | 없음 (import 변경만) |
| 4 | 에이전트 가드레일 | 지속 | 없음 |
| 5 | Git 초기화 | 1일 | 없음 |

## 완료 후 구조

```
/opt/workspace/
├── common-lib/           ★ 공유 Python 라이브러리
│   ├── src/common_lib/   진짜 공통 (44 modules, 확장 가능)
│   │   ├── core/         config, logger, utils, http...
│   │   ├── azure/        Azure 인프라 자동화
│   │   ├── domain/       도메인 로직
│   │   └── oci/          OCI 래퍼
│   ├── CLAUDE.yaml       위치 규칙 + 에이전트 규칙
│   └── AGENTS.yaml       워크플로우
│
├── archive/              ★ 완료/보존 프로젝트 (코드 삭제 안 함)
│   ├── agora/ + STATUS
│   ├── isuflow/ + STATUS
│   ├── js-utils/ + STATUS
│   ├── make-vm/ + STATUS
│   ├── neisync/ + STATUS
│   ├── papertrail/ + STATUS
│   ├── schooldocs/ + STATUS
│   ├── axis/
│   ├── extentions/
│   └── schools/
│
├── minihome/             웹 프로젝트 모노레포
│   └── apps/
│       ├── cashbook/
│       ├── ebooklib/
│       ├── kuhwa/
│       ├── minihome/
│       ├── news/
│       └── timetable/
│
└── azure/                인프라 스크립트

/opt/projects/            ← 서버 시스템 (서버 로직 분석 대상)
```

## 주의사항
- **어떤 코드도 삭제하지 않음** — archive/ 내 코드는 보존만
- `workspace/archive/` 프로젝트들은 STATUS 파일로 분류 (active/dormant/archive)
- 새 코드는 프로젝트 루트에 생성, 2번 사용된 코드만 `src/common_lib/` 로 harvest
- 공통 기능은 기존 `src/common_lib/` 활용
- **minihome/apps/**: 6개 앱 모두 독립 (공유 로직 없음, harvest 대상 없음)
- **workspace/archive/**: 완료 프로젝트, 보존만 (harvest 대상 아님)
