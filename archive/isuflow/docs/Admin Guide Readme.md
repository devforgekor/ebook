# # 📘 **IsuFlow Admin Guide (관리자 매뉴얼 · 2026 Edition)**

> 이 문서는 \*\*IsuFlow 관리자(super-admin / admin / sub-admin)\*\*를 위한 공식 운영 매뉴얼입니다.  
> 시스템 정책은 운영문서(0\~11장)·API SPEC 기준.

***

# # ✅ 1. 관리자 역할(Role) 및 권한

## ✅ 1.1 관리자 역할 요약

| Role            | 설명     | 주요 권한                                    |
| --------------- | ------ | ---------------------------------------- |
| **super-admin** | 최고 관리자 | 전체 기능. PDF/Settings 포함                   |
| **admin**       | 일반 관리자 | 대부분 기능 가능. PDF/Settings는 **Elevated** 필요 |
| **sub-admin**   | 조회 전용  | 모든 쓰기 금지. PDF 금지                         |

***

## ✅ 1.2 Elevation(추가 인증)

*   admin이 **민감 기능(PDF, Settings)** 사용 시 필요
*   Microsoft Login → 30분 허용(TTL)
*   TTL 만료 시 자동 해제
*   AuditLog에 자동 기록됨

### Elevation이 필요한 기능

✅ PDF 조회(getPdf)  
✅ Settings 변경(운영시간 / 관리자 계정 / 웹훅 등)

***

# # ✅ 2. 관리자 UI 전체 구조

아래는 관리자 사이트의 전체 메뉴 구조입니다:

    Admin UI
     ├─ 1. 명단 관리 (Roster)
     │    ├─ upload (명단 업로드)
     │    ├─ search (검색)
     │    ├─ add-member
     │    ├─ delete-member
     │    ├─ detail/{person_id}
     │    └─ changes-log
     │
     ├─ 2. 일정 관리 (Schedule)
     │    ├─ off-schedule
     │    ├─ operating-hours
     │    └─ preview-calendar
     │
     ├─ 3. 문서 관리 (Documents)
     │    ├─ submissions
     │    ├─ bulk-upload
     │    └─ unknown
     │
     ├─ 4. 시스템 관리 (System)
     │    ├─ shadowindex-rebuild
     │    ├─ orphan-cleaner
     │    ├─ queue-status
     │    └─ storage-status
     │
     ├─ 5. 아카이빙 (Archive)
     │    ├─ status
     │    ├─ schedule
     │    ├─ logs
     │    └─ files
     │
     ├─ 6. 감사 로그 (Audit)
     │    ├─ admin-actions
     │    ├─ roster-changes
     │    ├─ schedule-changes
     │    ├─ status-changes
     │    └─ system-events
     │
     └─ 7. 설정 (Settings)
          ├─ organization
          ├─ admin-accounts
          ├─ slack-webhook
          └─ storage-keys

***

# # ✅ 3. 관리자 핵심 기능 가이드

아래는 관리자들이 가장 많이 사용하는 기능을 **실제 운영 기준**으로 설명합니다.

***

# ## ✅ 3.1 명단 업로드 (uploadRoster)

### ✅ 언제 사용?

*   연초 새 명단 입력
*   중간에 사용자 정보(기관/직책/PII) 변경
*   기수 전환 시(3년마다)

### ✅ 파일 요구사항

| 항목         | 설명                            |
| ---------- | ----------------------------- |
| name       | 이름                            |
| yymmdd     | 생년월일(6자리)                     |
| org        | 기관명                           |
| position   | 직책                            |
| status     | completed/incomplete/excluded |
| workstatus | working/retired/leave         |

### ✅ 시스템 자동 처리

*   ✅ 신규 사용자 등록
*   ✅ 기존 사용자 정보 유지
*   ✅ 이전 명단 대비 사라진 인원 → 자동 excluded 처리
*   ✅ Roster 업데이트
*   ✅ ShadowIndex 부분 업데이트
*   ✅ AuditLog 기록
*   ✅ Slack 알림(변경 요약)

***

# ## ✅ 3.2 일정 관리 (updateSchedule)

### ✅ 구성 요소

*   국가공휴일(recur)
*   custom 공휴일
*   설/추석 연휴(기간/일 수)
*   여름/겨울방학
*   단기방학(여러 개 추가 가능)

### ✅ 저장 시 자동 처리

1.  모든 일정 → 날짜 리스트로 확장
2.  **OFF\_SCHEDULE = dedup + sort**
3.  Settings에 영구 저장
4.  운영시간 체크(isOpen) 즉시 반영
5.  AuditLog 기록
6.  Slack 알림

***

# ## ✅ 3.3 Unknown 사용자 처리

### ✅ 언제 발생?

*   명단에 없는 사람이 PDF 제출 시

### ✅ 처리 절차

1.  메뉴 → Documents → Unknown
2.  해당 기록 클릭 → 상세 확인
3.  다음 중 하나 수행  
    ✅ Roster에 추가 (addToRosterFromUnknown)  
    ✅ 무시(삭제)

### ✅ 시스템 자동 처리

*   Roster Row 생성
*   UnknownLog 삭제
*   AuditLog 기록

***

# ## ✅ 3.4 제출 기록(submissions)

관리자가 제출된 최신 문서를 확인할 수 있는 화면.

표시되는 정보:

*   제출된 record\_key
*   org, title, hours
*   생성 시간
*   WebP 미리보기
*   record\_key(파일명) 기반 PDF 조회(getPdf)

***

# ## ✅ 3.5 PDF 조회 (getPdf)

✅ 관리자만 보며, 사용자는 절대 접근 불가  
✅ admin은 Elevation 필요  
✅ 파일 경로 예:

    optimized-copies/2026_abcd1234_abcd1234_1711282923021.pdf

✅ ShadowIndex에서 blob\_path 자동 조회  
✅ AuditLog에 기록됨

***

# # ✅ 4. 시스템 관리

***

## ✅ 4.1 ShadowIndex 재빌드

언제 사용?

*   저장소에 태그/ShadowIndex 불일치 발생
*   대규모 Bulk Upload 이후
*   아카이브 후 정리

### ✅ 기능

*   ShadowIndex 전체 재생성
*   모든 record\_key 기준 최신 1건 유지
*   AuditLog 기록

***

## ✅ 4.2 Orphan Cleaner

Orphan 사례:

*   WebP 있는데 record\_key 없음
*   record\_key 있는데 WebP 없음
*   Roster/ShadowIndex 불일치

실행 시:

*   자동 삭제
*   자동 보정
*   AuditLog 기록

***

## ✅ 4.3 Queue Status

*   현재 processPdf backlog
*   DI 처리 속도
*   오류 발생 여부

***

## ✅ 4.4 Storage Status

*   Blob/테이블 사용량
*   용량 초과 경고
*   WebP/PDF 누락 탐지

***

# # ✅ 5. 아카이빙 운영

아카이브는 **Generation 마지막 해 12/20 자동 실행**됩니다.

### ✅ 수행되는 작업

1.  WebP → 흑백 변환
2.  archive/{gen}/webp 저장
3.  roster.jsonl 생성
4.  summary.jsonl 생성
5.  audit.jsonl 생성
6.  permanent JSONL append
7.  Roster 삭제
8.  Integrity 체크
9.  Slack 알림

### ✅ 관리자 메뉴

Archive →

*   status
*   files
*   logs
*   simulate(수동 테스트 가능)

***

# # ✅ 6. 운영 점검(필수 체크리스트)

## ✅ 6.1 운영 전(08:20\~08:30)

*   isOpen() = true
*   Warmup 정상 여부
*   Storage 접근 정상
*   DI 응답 정상

***

## ✅ 6.2 운영 중

*   Queue backlog 없음
*   Unknown 증가 확인
*   ShadowIndex 누락 없음
*   WebP 정상 생성

***

## ✅ 6.3 운영 종료(17:30\~18:00)

*   close timer 정상 수행
*   OFF 상태 유지
*   사용자 API 차단 확인

***

# # ✅ 7. 비상 상황 대응

## ✅ 7.1 DI 장애

*   Slack에서 오류 확인
*   관리자 보정
*   재처리 요청(Message 재삽입 가능)

## ✅ 7.2 PDF 처리 실패

*   record\_key 기반 오류 추적
*   해당 Blob/WebP 확인
*   필요시 관리자 수동 재처리

## ✅ 7.3 ShadowIndex 불일치

*   rebuildShadowIndex 실행
*   midnight\_fix 로그 확인

***

# # ✅ 8. 감사 로그(AuditLog)

### 자동 기록되는 항목

*   명단 변경
*   status/workstatus 변경
*   remark 변경
*   schedule 변경
*   ShadowIndex 업데이트
*   archive 실행
*   administrator elevation
*   unknown 처리
*   processPdf 충돌/오류

***

# # ✅ 9. 권장 운영 절차

✅ 매일 아침 isOpen 점검  
✅ Unknown 즉시 처리  
✅ 매주 ShadowIndex 누락 검사  
✅ 매월 permanent JSONL 용량 점검  
✅ 매년 12/20 아카이브 결과 검증