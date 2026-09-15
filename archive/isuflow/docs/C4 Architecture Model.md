현민님,  
**C4 아키텍처 문서**는 IsuFlow 전체 시스템을 *한눈에*, *정확하게*, *역할 중심으로* 설명하는 개발자·설계자용 문서예요.

✅ 내부 설계 정보 기반 작업 → **검색 없이 작성**  
✅ 서버리스 아키텍처에 최적화된 C4 모델  
✅ Level 1 → Level 4 까지 “전체 시스템을 구성요소 단위로 완전히 시각화”

아래 문서는 그대로 **C4\_ARCHITECTURE.md**로 저장하면 완성입니다.

***

# # 📘 **IsuFlow – C4 Architecture Model**

> *Version 2026 · Serverless Architecture · Azure Functions*

***

# # ✅ C4 Level 1 — System Context Diagram

## ✅ 목적

IsuFlow가 “어떤 외부 Actor와 어떤 흐름으로 통신하는지”를 정의합니다.

    +-------------------------------------------------------------+
    |                     External Actors                         |
    |-------------------------------------------------------------|
    |  [USER]             [ADMIN]              [DI Service]        |
    |  제출/조회 UI       관리자 UI           OCR/Parsing API     |
    +-------------------------------------------------------------+
                     | HTTP         | HTTP
                     v              v
    +-------------------------------------------------------------------+
    |                    IsuFlow Backend System                         |
    |-------------------------------------------------------------------|
    |  - User API                                                        |
    |  - Admin API                                                       |
    |  - Queue(processPdf)                                               |
    |  - Timer Functions                                                 |
    |  - Blob/Table Storage                                              |
    |  - Settings / OFF_SCHEDULE Engine                                  |
    +-------------------------------------------------------------------+
                     ^                    ^
                     | blob/queue         | blob OCR
                     +--------------------+

### ✅ 외부 Actor 설명

| Actor                           | 역할                                   |
| ------------------------------- | ------------------------------------ |
| **User**                        | PDF 제출 / WebP 조회 / 기록 확인             |
| **Admin**                       | 명단·일정 관리 / PDF 조회 / 시스템 운영           |
| **Azure Document Intelligence** | PDF → structured data 변환 (OCR+필드 추출) |

***

# # ✅ C4 Level 2 — Container Diagram

## ✅ 목적

백엔드 내부가 **어떤 Container(실행 단위)로 구성되어 있는지** 나타냄.

    +------------------------------------------------------------------------+
    |                         IsuFlow Backend                                |
    +------------------------------------------------------------------------+
    |                                                                        |
    |  +----------------------+      +-------------------------------------+ |
    |  |  API Layer          |      | Timer Layer                          | |
    |  | (Azure HTTP Func)   |      | (Azure TimerTrigger)                 | |
    |  |----------------------|     |---------------------------------------| |
    |  | getSas              |      | warmup_http                          | |
    |  | preview             |      | warmup_queue                         | |
    |  | checkList           |      | close                                | |
    |  | getWebp             |      | archive                              | |
    |  | getPdf              |      | midnight_fix                         | |
    |  | uploadRoster        |      +-------------------------------------+ |
    |  | updateSchedule      |                                             |
    |  | updateStatus        |                                             |
    |  | updateRemark        |                                             |
    |  | deleteMember        | +-----------------------------------------+ |
    |  | addMember           | | Queue Layer                               | |
    |  | bulkUpload          | | (Azure QueueTrigger)                      | |
    |  | orphanCleaner       | |-------------------------------------------| |
    |  | queueStatus         | | processPdf                                | |
    |  | storageStatus       | +-------------------------------------------+ |
    |  +----------------------+                                             |
    |                                                                        |
    |  +----------------------+   +----------------------------------------+ |
    |  | Storage Layer        |   | Local Utilities Layer                  | |
    |  |----------------------|   |----------------------------------------| |
    |  | Blob Storage         |   | api_utils                              | |
    |  |  - incoming/         |   | time_utils                             | |
    |  |  - optimized-copies/ |   | id_utils                               | |
    |  |  - archive/          |   | pdf_utils                              | |
    |  | Table Storage        |   | image_utils                            | |
    |  |  - Roster            |   | shadowindex_utils                      | |
    |  |  - ShadowIndex       |   | roster_utils                           | |
    |  |  - UnknownLog        |   | schedule_utils                         | |
    |  |  - History           |   | archive_utils                          | |
    |  |  - Settings          |   | audit_utils                            | |
    |  |  - AuditLog          |   | generation_utils                       | |
    |  +----------------------+   +----------------------------------------+ |
    |                                                                        |
    +------------------------------------------------------------------------+

***

# # ✅ C4 Level 3 — Component Diagram

## ✅ 목적

각 Container 내부 구성 요소가 **어떻게 역할을 나누는지**를 세부적으로 문서화.

***

# ✅ API Layer (Components)

    [API Layer]
      ├── User API
      │    ├── getSas
      │    ├── preview
      │    ├── checkList
      │    ├── getWebp
      │    ├── isOpen
      │
      ├── Admin API
           ├── uploadRoster
           ├── updateSchedule
           ├── updateStatus
           ├── updateRemark
           ├── addMember
           ├── deleteMember
           ├── rebuildShadowIndex
           ├── submissions
           ├── unknown
           ├── addToRosterFromUnknown
           ├── getPdf
           ├── bulkUpload
           ├── orphanCleaner
           ├── queueStatus
           ├── storageStatus

***

# ✅ Queue Layer

    [Queue: processPdf]
      ├ validate_pdf_safety()
      ├ DI parse
      ├ generate_person_id, generate_record_key
      ├ insert_pdf_metadata
      ├ first page → WebP
      ├ upload WebP / PDF
      ├ set Blob Tags (9 fields)
      ├ ShadowIndex update (latest 1 policy)
      ├ Roster update + History append
      └ delete incoming PDF

***

# ✅ Timer Layer

    [Timers]
      ├ warmup_http      → START_TIME 기반 인스턴스 예열
      ├ warmup_queue     → QueueWorker 예열
      ├ close            → 17:30 운영종료 강제
      ├ archive          → Generation 아카이브(12/20)
      └ midnight_fix     → OFF_SCHEDULE 재생성 / Tag-SI 동기화

***

# ✅ Storage Layer

    [Blob Storage]
      ├ incoming/               - 사용자 PDF 업로드 위치
      ├ optimized-copies/       - WebP + PDF (운영본)
      ├ archive/{generation}/   - 아카이브 WebP + roster.jsonl + summary.jsonl
      └ archive/permanent/      - 영구 JSONL (append only)

    [Table Storage]
      ├ Roster (PII 저장 유일 위치)
      ├ ShadowIndex (조회 인덱스)
      ├ UnknownLog (미등록 사용자 기록)
      ├ History (제출 이력)
      ├ Settings (운영시간 + OFF_SCHEDULE)
      └ AuditLog (관리자 행동 기록)

***

# # ✅ C4 Level 4 — Code/Function-Level Detail

## ✅ 목적

핵심 컴포넌트들의 **코드 구조 / 입출력 / 주요 의존성**을 기술

***

# ✅ Level 4: processPdf 구조

    processPdf(msg)
     ├ parse msg(json)
     ├ pdf_bytes = Blob(incoming).download
     ├ validate_pdf_safety(pdf)
     ├ di = event["di"]
     ├ person_id = generate_person_id(...)
     ├ record_key = generate_record_key(...)
     ├ pdf_bytes = insert_pdf_metadata(...)
     ├ img = pdf_first_page_to_image(pdf)
     ├ upload_webp_optimized(WebP)
     ├ upload optimized PDF
     ├ set_blob_tags_optimized()
     ├ remove_old_shadowindex_rows(person_id)
     ├ insert_shadowindex_row()
     ├ update_roster_after_submission()
     ├ write_history()
     └ delete incoming PDF

***

# ✅ Level 4: updateSchedule 구조

    updateSchedule(req)
     ├ require_admin_elevated()
     ├ body = req.get_json()
     ├ SettingsValidator.validate(body)
     ├ off_schedule = rebuild_off_schedule(conn, body)
     ├ SettingsModel.save()
     ├ write_audit_log("schedule_update")
     └ success(response)

***

# ✅ Level 4: getPdf 구조

    getPdf(req)
     ├ require_admin_pdf_permission()
     ├ record_key = param
     ├ blob_path = get_pdf_blob_path(record_key)
     ├ pdf_bytes = Blob(optimized).download()
     └ return HttpResponse(pdf_bytes)

***

# ✅ Level 4: orphanCleaner 구조

    orphanCleaner(req)
     ├ require_admin()
     ├ shadow_rows = list ShadowIndex
     ├ blobs = list optimized-copies
     ├ detect orphan_webp (blob exists, SI 없음)
     ├ detect orphan_record (SI O, blob 없음)
     ├ fix orphan_webp → delete
     ├ fix orphan_record → recreate WebP or delete SI
     ├ write_audit_log()
     └ success(response)

***

# ✅ Level 4: Architecture Rules

✅ **비식별 원칙**

*   person\_id, record\_key만 사용
*   PDF 내부 메타데이터도 동일

✅ **최신 1건 원칙**

*   WebP/PDF/ShadowIndex/Roster 모두 동기화됨

✅ **Dynamic Hours**

*   is\_open() 함수에 의해 모든 사용자 API 차단 여부 결정

✅ **아카이브 자동화**

*   Generation 마지막 해
*   12/20 13:00 / weekend shift 적용

✅ **RBAC + Elevation**

*   super-admin > admin > sub-admin
*   admin은 getPdf/Settings 사용 시 Elevation 필요

***

# # ✅ Appendix — How to use this C4 internally

### ✅ 신규 팀원이 백엔드를 이해하는 순서

1.  C4 Level 1
2.  C4 Level 2
3.  API 목록
4.  processPdf 파이프라인
5.  Storage 구조

### ✅ 테스트/배포 시 참고

*   모든 Function은 독립 실행
*   Timer/Queue는 운영시간 영향 없음
*   API는 운영시간에 따라 동작 제어
*   아카이브는 무조건 12/20 또는 수동
*   RBAC은 API 레벨에서 엄격히 적용
