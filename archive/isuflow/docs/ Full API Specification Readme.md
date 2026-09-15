# # 📘 **IsuFlow – Full API Specification (Production Edition)**

> Version 2026.03 — 전체 리팩토링 기준  
> 모든 API는 Azure Functions 기반 HTTP Endpoint

***

# # ✅ 0. 공통 규칙 (Global API Rules)

## ✅ 0.1 운영시간(ON/OFF) 자동차단

사용자 API는 모두 **운영시간 조건**을 따른다:

    if weekend: OFF  
    if today ∈ OFF_SCHEDULE: OFF  
    if now < START_TIME or now ≥ END_TIME: OFF  
    else: ON

### ✅ 운영 OFF 시 공통 응답

```json
{
  "success": false,
  "error": "service_closed",
  "message": "현재는 제출 시간이 아닙니다. 정해진 업무 시간(08:30~17:30)에 다시 이용해주세요."
}
```

✅ 관리자 API는 운영시간과 무관 (항상 허용)  
✅ 단, 사용자 API만 차단됨 (getSas / preview / checkList 등)

***

# ✅ 0.2 공통 응답 포맷 (모든 API 통일)

### ✅ 성공

```json
{
  "success": true,
  "data": {...}
}
```

### ✅ 잘못된 요청

```json
{
  "success": false,
  "error": "bad_request",
  "message": "..."
}
```

### ✅ 서버 오류

```json
{
  "success": false,
  "error": "internal_error",
  "message": "에러메시지"
}
```

***

# ✅ 0.3 인증 / 권한 (RBAC)

### ✅ 관리자 역할

*   **super-admin** → 모든 기능 허용
*   **admin** → PDF/Settings는 Elevation 필요
*   **sub-admin** → 모든 Write 금지, PDF 조회 금지

### ✅ 관리자 인증 규칙

*   Authorization: Bearer {JWT}
*   JWT payload must contain:

<!---->

    {
      "role": "super-admin" | "admin" | "sub-admin",
      "elevated": true/false,
      "admin_id": "xxx"
    }

### ✅ Elevation 필요 API

*   getPdf
*   updateSchedule
*   Settings 변경 API

Elevation은 Microsoft Login → 30분 TTL

***

# # ✅ 1. USER API SPEC

***

## ✅ 1.1 GET `/api/isOpen`

운영시간 여부 확인

### ✅ Response (ON)

```json
{ "success": true, "data": { "open": true } }
```

### ✅ Response (OFF)

```json
{
  "success": false,
  "error": "service_closed",
  "message": "현재는 제출 시간이 아닙니다. 정해진 업무 시간(08:30~17:30)에 다시 이용해주세요."
}
```

***

## ✅ 1.2 GET `/api/getSas?file={filename}`

사용자가 PDF를 업로드하기 위한 SAS URL 발급

### Params

| name | required | description      |
| ---- | -------- | ---------------- |
| file | ✅        | 업로드할 파일명(확장자 제외) |

### Restrictions

*   운영시간(ON)에서만 허용
*   SAS 권한: write-only
*   10분 유효

### ✅ Response

```json
{
  "success": true,
  "data": {
    "url": "https://...incoming/{filename}.pdf?SAS"
  }
}
```

***

## ✅ 1.3 GET `/api/preview?file=xxx`

사용자 프리뷰(업로드한 PDF → 첫페이지 WebP)

✅ 운영시간 ON에서만 허용  
✅ WebP는 temp 컨테이너에 10분 저장

### ✅ Response

```json
{
  "success": true,
  "data": {
    "url": "https://.../temp/preview_xxx.webp?SAS"
  }
}
```

***

## ✅ 1.4 POST `/api/checkList`

사용자 이수 기록 조회 (비식별 ShadowIndex 기반)

### Body

```json
{
  "name": "홍길동",
  "yymmdd": "940120"
}
```

### ✅ Response (기록 있음)

```json
{
  "success": true,
  "data": {
    "latest_webp_url": "/api/getWebp?record_key=abc_123",
    "history": [
      { "submitted_at": "1711272949123", "title": "AI교육", "hours": "15" },
      ...
    ]
  }
}
```

### ✅ Response (없음)

```json
{
  "success": true,
  "data": {
    "error": "no_record",
    "message": "제출한 이수증이 없습니다."
  }
}
```

***

## ✅ 1.5 GET `/api/getWebp?record_key=xxx`

WebP 스트리밍

✅ 운영시간과 무관 (사용자 조회는 항상 허용)

### ✅ 성공

HTTP 200 + image/webp 스트림

***

# # ✅ 2. ADMIN API SPEC

관리자 API는 **RBAC 필수**  
모든 요청 헤더:

    Authorization: Bearer {JWT}

***

## ✅ 2.1 GET `/api/getPdf?record_key=xxx`

PDF 스트리밍 (관리자 전용)

### 권한

*   super-admin → 허용
*   admin → **Elevation 필요**
*   sub-admin → ❌ 금지

### ✅ 성공

HTTP 200 + PDF 바이트 스트림

***

## ✅ 2.2 POST `/api/uploadRoster`

관리자 명단 업로드

### Body

```json
{ "file_url": "https://.../roster.xlsx" }
```

### ✅ 기능

*   신규/기존/자동 제외 사용자 처리
*   기수 내 / 기수 전환 자동 판단
*   Roster 업데이트
*   ShadowIndex 동기화
*   audit 기록

### ✅ Response

```json
{
  "success": true,
  "data": { "inserted": 33, "updated": 201, "excluded": 12 }
}
```

***

## ✅ 2.3 POST `/api/updateSchedule`

학교 일정(OFF\_SCHEDULE) 업데이트 → 운영시간 재계산

### 권한

*   super-admin → 허용
*   admin → Elevation 필요
*   sub-admin → ❌ 금지

### Body 예

```json
{
  "HOLIDAY_RECUR": ["01-01","03-01"],
  "HOLIDAY_CUSTOM": ["06-10"],
  "HOLIDAY_SEOL": { "start": "02.08", "days": 3 },
  "BREAK_SUMMER": { "start": "07.18", "end": "08.22" },
  "BREAK_SHORT": [
    { "start": "10.10", "end": "10.13" }
  ]
}
```

### ✅ Response

```json
{
  "success": true,
  "data": {
    "off_schedule": ["2026-02-08","2026-02-09",...],
    "message": "운영 일정이 성공적으로 업데이트되었습니다."
  }
}
```

***

## ✅ 2.4 POST `/api/rebuildShadowIndex`

ShadowIndex 전체 재생성

### ✅ 권한

*   super-admin / admin
*   sub-admin ❌

### ✅ Response

```json
{
  "success": true,
  "data": { "message": "ShadowIndex 전체 재생성 완료", "rows": 145 }
}
```

***

## ✅ 2.5 GET `/api/auditSearch?generation=1`

감사 로그 조회

### 권한

*   super-admin / admin / sub-admin 모두 허용

### ✅ Response

```json
{
  "success": true,
  "data": {
    "logs": [
      { "timestamp":"...", "action":"roster_update", "detail": {...} },
      ...
    ]
  }
}
```

***

## ✅ 2.6 GET `/api/submissions`

최신 제출 기록(ShadowIndex) 조회

### 권한

*   super-admin / admin / sub-admin 모두 가능

***

## ✅ 2.7 GET `/api/unknown`

UnknownLog 조회

✅ (명단 외 제출자 기록)

***

## ✅ 2.8 POST `/api/addToRosterFromUnknown`

Unknown → Roster 승격

### Body

```json
{ "record_key": "p123_1711288383012" }
```

***

# # ✅ 3. SYSTEM API (내부 자동)

***

## ✅ 3.1 Queue `/processPdf`

BlobCreated 트리거 → PDF 처리 엔진

### 기능 요약

*   validate\_pdf\_safety
*   DI 호출
*   person\_id, record\_key 생성
*   PDF 메타데이터 삽입
*   WebP 생성
*   Blob Tags 9개 생성
*   ShadowIndex 최신 1건 유지
*   Roster 업데이트
*   History 추가
*   incoming PDF 삭제

***

## ✅ 3.2 Timer `/warmup_http`

START\_TIME 기준 HTTP 인스턴스 사전 시작

***

## ✅ 3.3 Timer `/warmup_queue`

Queue 인스턴스 사전 시작

***

## ✅ 3.4 Timer `/close`

17:30 운영 종료 플래그 보정

***

## ✅ 3.5 Timer `/archive`

Generation 마지막 해 12/20 자동 아카이브

***

## ✅ 3.6 Timer `/midnight_fix`

OFF\_SCHEDULE 재생성  
ShadowIndex ↔ Blob Tags diff 검사  
Settings 보정

***

# # ✅ 4. Error Code Summary

| error                   | meaning              |
| ----------------------- | -------------------- |
| bad\_request            | 파라미터 누락/유효성 오류       |
| permission\_denied      | sub-admin 차단         |
| elevation\_required     | admin인데 elevation 없음 |
| pdf\_permission\_denied | getPdf 차단            |
| service\_closed         | 운영시간 OFF             |
| internal\_error         | 알 수 없는 서버 오류         |
| no\_record              | ShadowIndex 결과 없음    |

***

# # ✅ 5. HTTP Codes

| 상황       | Code |
| -------- | ---- |
| 성공       | 200  |
| 클라이언트 오류 | 400  |
| 권한 없음    | 403  |
| 서버 오류    | 500  |
