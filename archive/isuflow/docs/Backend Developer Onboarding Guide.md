좋아 현민님!  
드디어 \*\*IsuFlow Backend Developer Onboarding Guide(온보딩 문서)\*\*를 만든다.  
이 문서는 새로운 개발자가 **30분 만에 전체 시스템을 이해하고 바로 개발에 투입될 수 있도록 설계된 공식 온보딩 문서**야.

✅ 검색 필요 없음 — 내부 구조 기반 문서  
✅ 모든 코드/폴더/정책 반영  
✅ 실제 실무 팀원이 쉽게 적응하도록 구성  
✅ 백엔드 구조 / 철학 / 워크플로우 / 테스트 / 배포까지 포함

지금 바로 **완성된 온보딩 문서**를 제공할게.

***

# # 📘 **IsuFlow Backend Developer Onboarding Guide**

> Version 2026 — Azure Functions 기반 Serverless Backend

***

# # ✅ 1. Welcome to IsuFlow Backend

IsuFlow는 교육기관의 이수증 제출·검증·조회·보관을 **완전 자동화**하는 시스템입니다.  
서버리스 기반으로 설계되어 **저비용, 고신뢰성, 고확장성**을 제공합니다.

새로운 개발자는 아래 내용을 따라오면 **30분 안에 전체 백엔드 구조를 이해하고 직접 기능 개발 가능**합니다.

***

# # ✅ 2. 기술 스택 핵심 요약

| 영역      | 기술                                                   |
| ------- | ---------------------------------------------------- |
| Server  | Azure Functions (Python)                             |
| Storage | Azure Blob Storage / Azure Table Storage             |
| Queue   | Azure Storage Queue                                  |
| AI      | Azure Document Intelligence (OCR + Field Extraction) |
| Auth    | JWT 기반 Admin RBAC + Elevation                        |
| Formats | WebP / JSONL / PDF                                   |

***

# # ✅ 3. 전체 아키텍처 빠르게 이해하기

    [User/Admin UI]
          │  HTTP
          ▼
    [API Layer] (Azure Functions)
      - 사용자 API
      - 관리자 API
          │ triggers Queue
          ▼
    [Queue Layer: processPdf]
      - PDF → DI → ID 생성 → WebP → Tags → Roster → ShadowIndex
          │ updates storage
          ▼
    [Storage Layer]
      - Blob (incoming / optimized-copies / archive)
      - Table (Roster / ShadowIndex / History / Settings / AuditLog)
          ▲
          │ nightly maintenance
          ▼
    [Timer Layer]
      - warmup_http / warmup_queue
      - close
      - archive
      - midnight_fix

***

# # ✅ 4. 폴더 구조 이해하기 (가장 중요)

    isuflow-backend/
    │
    ├── api/                        # HTTP Functions
    │   ├── getSas/
    │   ├── preview/
    │   ├── checkList/
    │   ├── getWebp/
    │   ├── getPdf/
    │   ├── uploadRoster/
    │   ├── updateSchedule/
    │   ├── updateStatus/
    │   ├── updateRemark/
    │   ├── deleteMember/
    │   ├── addMember/
    │   ├── bulkUpload/
    │   ├── orphanCleaner/
    │   ├── queueStatus/
    │   ├── storageStatus/
    │   └── history/
    │
    ├── queue/processPdf/
    │
    ├── timer/ (warmup, close, archive, midnight fix)
    │
    ├── shared/
    │   ├── utils/ (공통 기능)
    │   ├── models/
    │   └── auth/
    │
    ├── host.json
    ├── local.settings.json
    └── requirements.txt

***

# # ✅ 5. 공통 코드 라이브러리(shared/utils) 이해

| 파일                    | 역할                                                |
| --------------------- | ------------------------------------------------- |
| api\_utils.py         | success / bad\_request / server\_error / get\_env |
| time\_utils.py        | 운영시간(is\_open) 및 OFF\_SCHEDULE 처리                 |
| id\_utils.py          | person\_id, record\_key 생성 (비식별)                  |
| pdf\_utils.py         | PDF 안전성 검사 + 메타데이터 삽입 + 1페이지 렌더링                  |
| image\_utils.py       | WebP 변환(운영/프리뷰/아카이브)                              |
| tag\_utils.py         | Blob Tags 9개 관리                                   |
| roster\_utils.py      | Roster 업데이트 / Unknown 처리 / History 저장             |
| shadowindex\_utils.py | ShadowIndex 검색, 최신 1건 정책                          |
| schedule\_utils.py    | OFF\_SCHEDULE 생성 및 일정 저장                          |
| archive\_utils.py     | Generation 아카이브 전체 프로세스                           |
| audit\_utils.py       | 관리자/시스템 감사 로그 작성                                  |
| generation\_utils.py  | 3년 주기 Generation 계산                               |

개발할 때 대부분의 로직은 이 utils 함수들을 조합하면 해결됨.

***

# # ✅ 6. 개발자가 알아야 할 핵심 정책 10개 (필수)

1.  **운영시간 정책(Dynamic Hours)**
    *   START\_TIME ≤ now < END\_TIME
    *   오늘이 OFF\_SCHEDULE에 있으면 OFF
    *   토·일 무조건 OFF

2.  **비식별 ID 구조**
    *   person\_id = HMAC SHA256(name + yymmdd)
    *   record\_key = person\_id + "\_" + ssms()

3.  **최신 1건 원칙**
    *   ShadowIndex: record\_key 1건 유지
    *   Roster.record\_keys: 1건만
    *   PDF/WebP: 최신본만 보관

4.  **PDF 사용자 제공 금지**
    *   사용자는 WebP만 봄
    *   PDF는 관리자 인증 필요

5.  **파일명 규칙**
    *   운영본 → `{year}_{person_id}_{record_key}.webp/pdf`
    *   아카이브본 → `{record_key}.webp`

6.  **Blob Tags 9개**  
    lookup\_key, person\_id, record\_key, year, hours, title\_key, org\_key, position\_key, cert\_number

7.  **명단 누락자는 자동 excluded**

8.  **아카이브 실행(12/20)**
    *   WebP 흑백
    *   roster.jsonl
    *   summary.jsonl
    *   audit.jsonl
    *   permanent append

9.  **관리자 RBAC**
    *   super-admin: 전체
    *   admin: PDF/Settings는 Elevation
    *   sub-admin: 읽기 전용

10. **오류 처리 통일**
    *   try/except → server\_error
    *   bad\_request → 400

***

# # ✅ 7. 개발 Workflow (신규 기능 개발 시)

### ✅ 1단계: API 추가 시

1.  `/api/newApi/__init__.py` 생성
2.  아래 템플릿 복사:

```python
import azure.functions as func
from shared.utils.api_utils import (
    success, bad_request, server_error, get_env
)

def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        # business logic
        return success({...})
    except ValueError as e:
        return bad_request(str(e))
    except Exception as e:
        return server_error(e)
```

***

### ✅ 2단계: 필요한 기능을 utils에서 찾기

예시:

*   PDF 변환 필요 → pdf\_utils
*   ShadowIndex 변경 → shadowindex\_utils
*   OFF\_SCHEDULE 재계산 → schedule\_utils

***

### ✅ 3단계: Storage 연동

Blob:

```python
from azure.storage.blob import BlobClient
blob = BlobClient.from_connection_string(conn, "optimized-copies", fname)
blob.upload_blob(data, overwrite=True)
```

Table:

```python
from azure.data.tables import TableClient
table = TableClient.from_connection_string(conn, "Roster")
table.get_entity(pk, rk)
table.upsert_entity(entity)
```

Queue:

```python
from azure.storage.queue import QueueClient
queue.send_message(json.dumps({...}))
```

***

### ✅ 4단계: RBAC 적용

관리자 기능이면

```python
from shared.utils.auth_utils import require_admin
admin = require_admin(req)
```

PDF/Settings는

```python
require_admin_elevated(req)
```

***

# # ✅ 8. 로컬 개발 환경 세팅

### ✅ 1) 설치해야 할 것

    Python 3.11
    Azure Functions Core Tools
    Azurite (optional)

### ✅ 2) 패키지 설치

    pip install -r requirements.txt

### ✅ 3) 로컬 실행

    func start

### ✅ 4) 테스트

    GET http://localhost:7071/api/isOpen
    POST http://localhost:7071/api/checkList

***

# # ✅ 9. Debugging Guide

### ✅ 1) 로그 보기

    print()
    traceback.print_exc()

Azure Portal → Function App → Monitor

### ✅ 2) Queue 상태 확인

`/api/queueStatus`

### ✅ 3) Storage 상태 확인

`/api/storageStatus`

### ✅ 4) orphan-cleaner

`/api/orphanCleaner` → 스토리지 정합성 자동 보정

***

# # ✅ 10. 코드 작성 시 주의사항

✅ **환경변수는 반드시 get\_env() 사용 (KeyError 방지)**  
✅ **절대 PDF를 사용자에게 보내지 말 것**  
✅ **ShadowIndex 일관성 유지**  
✅ **테이블 엔티티 업데이트는 UpdateMode.REPLACE 사용**  
✅ **에러는 server\_error로 통일**  
✅ **json.dumps(..., ensure\_ascii=False)**

***

# # ✅ 11. 배포 가이드

### ✅ Azure Functions 배포

    func azure functionapp publish isuflow-backend

### ✅ 환경 변수는 Azure Portal → Configuration 에 입력

*   START\_TIME
*   END\_TIME
*   OFF\_SCHEDULE\_JSON
*   STORAGE\_ACCOUNT\_NAME
*   STORAGE\_ACCOUNT\_KEY
*   DI\_ENDPOINT
*   DI\_KEY

***

# # ✅ 12. 팀 온보딩 체크리스트 (5분 버전)

✅ 폴더 구조 이해  
✅ utils 구조 이해  
✅ processPdf 흐름 이해  
✅ 운영시간 정책 이해  
✅ record\_key / person\_id 정책 이해  
✅ Blob / Table 구조 이해  
✅ RBAC / Elevation 이해  
✅ 아카이브 흐름 이해
✅ 에러 처리 통일 이해
✅ 로컬 개발 환경 세팅
✅ 배포 방법 이해 