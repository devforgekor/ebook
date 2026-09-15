# # 📘 **IsuFlow Backend – Developer Guide (Production Edition)**

> **Dynamic Hours + Serverless Architecture 기반 이수증 자동처리 시스템**  
> *Azure Functions · Python · Blob/Table Storage · Document Intelligence*

***

# ## ✅ 1. System Overview

IsuFlow는 **교육기관 이수증 제출/조회/관리의 전 과정을 자동화**한 서버리스 시스템이다.

### 🎯 핵심 목표

*   ✅ 이수증 제출 → 자동 PDF 처리 (DI → WebP → 비식별 저장)
*   ✅ OFF\_SCHEDULE 기반 **가변 운영시간(Dynamic Hours)**
*   ✅ 비식별(person\_id, record\_key) 데이터 모델
*   ✅ ShadowIndex 기반 초고속 조회
*   ✅ 3년 주기 Generation 아카이브

### 🧱 아키텍처 레이어

    [User/Admin UI] → [HTTP API] → [Queue: processPdf] → [Blob/Table Storage] → [Timer Functions]

***

# ## ✅ 2. Folder Structure

    isuflow-backend/
    │
    ├── api/
    │   ├── getSas/              # 사용자 SAS 발급
    │   ├── preview/             # PDF → WebP 프리뷰
    │   ├── checkList/           # 이력 조회
    │   ├── getWebp/             # WebP 스트리밍
    │   ├── getPdf/              # 관리자용 PDF 조회
    │   ├── uploadRoster/        # 명단 업로드
    │   ├── updateSchedule/      # 일정 업데이트
    │   ├── rebuildShadowIndex/
    │   ├── auditSearch/
    │   ├── submissions/
    │   ├── unknown/
    │   └── addToRosterFromUnknown/
    │
    ├── queue/
    │   └── processPdf/          # PDF 처리 엔진
    │
    ├── timer/
    │   ├── warmup_http/
    │   ├── warmup_queue/
    │   ├── close/
    │   ├── archive/
    │   └── midnight_fix/
    │
    ├── shared/
    │   ├── utils/
    │   │   ├── api_utils.py
    │   │   ├── time_utils.py
    │   │   ├── id_utils.py
    │   │   ├── pdf_utils.py
    │   │   ├── image_utils.py
    │   │   ├── tag_utils.py
    │   │   ├── roster_utils.py
    │   │   ├── shadowindex_utils.py
    │   │   ├── schedule_utils.py
    │   │   ├── archive_utils.py
    │   │   ├── audit_utils.py
    │   │   └── generation_utils.py
    │   │
    │   ├── auth/
    │   │   └── auth_utils.py     # 관리자 RBAC + Elevation
    │   │
    │   └── models/
    │       ├── shadowindex_model.py
    │       └── settings_model.py
    │
    ├── host.json
    ├── local.settings.json
    ├── requirements.txt
    └── README.md

***

# ## ✅ 3. Core Data Model

### ✅ `person_id`

*   `HMAC_SHA256(normalize(name) + "_" + yymmdd)` → 앞 16바이트
*   비식별
*   Roster(RowKey), ShadowIndex, Tags, 파일명에서 공통 사용

### ✅ `record_key`

*   `person_id + "_" + ssms()`
*   PDF/WebP 파일명 및 ShadowIndex RowKey
*   항상 사용자당 최신 1개만 유지

***

# ## ✅ 4. Storage Architecture

    Blob Storage
        ├── incoming/              # 사용자가 업로드한 원본 PDF
        ├── optimized-copies/      # 운영 WebP + PDF + Tags
        ├── archive/{gen}/         # 아카이브 WebP/JSONL
        └── archive/permanent/     # 영구 JSONL

    Table Storage
        ├── Roster                 # PII 포함 (유일)
        ├── ShadowIndex            # 조회 인덱스 (비식별)
        ├── UnknownLog
        ├── History
        ├── Settings
        └── AuditLog

***

# ## ✅ 5. Submission Flow (사용자 제출 → 자동 처리)

    User Upload PDF → SAS(incoming/)
           │
           ▼
    Blob Created → Queue(processPdf)
           │
           ├ validate_pdf_safety()
           ├ DI 파싱
           ├ generate_person_id(), generate_record_key()
           ├ PDF 메타데이터(person_id,record_key) 삽입
           ├ PDF/WebP → optimized-copies/
           ├ Blob Tags 9개 설정
           ├ remove_old_shadowindex_rows()
           ├ insert_shadowindex_row()
           ├ update_roster_after_submission()
           ├ write_history()
           └ delete incoming PDF

***

# ## ✅ 6. Dynamic Hours (운영시간 정책)

### ✅ 운영 ON 조건

    오늘이 토/일 아님
    오늘 ∉ OFF_SCHEDULE
    START_TIME ≤ 현재시간 < END_TIME

### ✅ 운영 OFF 시

*   SAS 발급 차단
*   preview, checkList 차단
*   API 403
*   TimerTrigger/QueueTrigger는 정상 실행

***

# ## ✅ 7. Archive Flow (Generation 마지막 해 12/20)

    timer/archive
      │
      ├ archive/{gen}/webp/ (흑백 변환)
      ├ roster.jsonl
      ├ summary.jsonl
      ├ audit.jsonl
      ├ append → archive/permanent/
      ├ Roster 삭제
      └ 무결성 검사(webp_count == roster_count)

***

# ## ✅ 8. RBAC (관리자 권한 체계)

    super-admin    → 모든 기능 허용
    admin          → Settings/PDF 조회는 Elevation 필요
    sub-admin      → 읽기 전용 (모든 Write 차단)

### ✅ Elevation

*   Microsoft Login → 30분 TTL
*   PDF 조회(getPdf)
*   Settings 변경(updateSchedule)

***

# ## ✅ 9. Coding Standards

### ✅ API 파일 규칙

```python
from shared.utils.api_utils import (
    success, bad_request, server_error, get_env
)
from shared.utils.time_utils import is_open

def main(req):
    try:
        if not is_open():
            return bad_request("현재 운영시간이 아닙니다.")
        ...
        return success({...})
    except ValueError as e:
        return bad_request(str(e))
    except Exception as e:
        return server_error(e)
```

### ✅ 환경 변수

*   `os.environ.get()` 사용 금지  
    → 반드시 `get_env()` 사용

***

# ## ✅ 10. Deployment

### ✅ Requirements

*   Python 3.11
*   Azure Functions Core Tools
*   Azure Storage Account
*   Azure Document Intelligence
*   Azure Table Storage (Table Endpoint)

### ✅ Deploy steps

    func azure functionapp publish <function-app-name>

***

# ## ✅ 11. local.settings.json Example

```json
{
  "IsEncrypted": false,
  "Values": {
    "FUNCTIONS_WORKER_RUNTIME": "python",
    "AzureWebJobsStorage": "UseDevelopmentStorage=true",
    "START_TIME": "08:30",
    "END_TIME": "17:30",
    "OFF_SCHEDULE_JSON": "[]",
    "STORAGE_ACCOUNT_NAME": "youraccount",
    "STORAGE_ACCOUNT_KEY": "xxxx",
    "DI_ENDPOINT": "https://di.cognitiveservices.azure.com/",
    "DI_KEY": "xxxx"
  }
}
```

***

# ## ✅ 12. Development Quickstart

### ✅ Run local

    func start

### ✅ Test API

    GET http://localhost:7071/api/isOpen
    GET http://localhost:7071/api/getSas?file=test
    POST http://localhost:7071/api/checkList

***

# ## ✅ 13. Useful Commands

### ✅ 테이블 전체 조회

    az storage entity query --table-name Roster ...

### ✅ Blob 확인

    az storage blob list -c optimized-copies

***

# ## ✅ 14. Logs & Monitoring

*   Azure Portal → Function App → Monitor
*   Application Insights (권장)
*   Slack Webhook 연동 가능 (DI 오류 / Archive 결과)

***

# ## ✅ 15. Maintenance Summary

✅ 매일 00:01 → midnight\_fix  
✅ 평일 08:25, 08:27, 08:31, 08:32 → Warmup  
✅ 평일 17:30 → Close Enforcement  
✅ Generation 마지막 해 12/20 → Archive  
✅ 매월 1일 → ShadowIndex ↔ Blob Tags diff 검사

***

# ## ✅ 16. Appendix

### ✅ 환경변수

*   START\_TIME / END\_TIME
*   OFF\_SCHEDULE\_JSON
*   STORAGE\_ACCOUNT\_NAME
*   DI\_KEY / DI\_ENDPOINT
*   SLACK\_WEBHOOK\_URL

### ✅ 9개 Blob Tags

    lookup_key (=person_id)
    person_id
    record_key
    year
    hours
    org_key
    position_key
    title_key
    cert_number
