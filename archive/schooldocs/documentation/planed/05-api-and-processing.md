# API And Processing

이 문서는 목표 설계 기준의 API 구조와 문서 처리 파이프라인을 정리한 계획 문서다.

## 사용자 API 목표

- `POST /api/submit`
  - 문서 업로드
  - PDF 검증
  - 규칙 파싱
  - 필요 시 AI 보조 인식
  - WebP 변환
  - Blob 업로드
  - records 저장
- `POST /api/status`
  - 이름 + 생년월일 기준 상태 조회
- `GET /api/view/{cohortId}/{personId}`
  - 승인 완료 문서 조회

## 관리자 API 목표

- `GET /api/manage/pending`
- `POST /api/manage/approve`
- `POST /api/manage/upload-members`
- `GET,POST /api/manage/cohorts`
- `GET,POST /api/manage/admins`
- `POST /api/manage/close-cohort`

## 관리자 권한 처리 원칙

- 관리자 API는 admins 컨테이너를 통해 권한을 확인한다.
- super 관리자는 모든 문서를 처리할 수 있다.
- sub 관리자는 allowedCertificateTypes 또는 allowedDocumentTypes에 포함된 문서만 처리할 수 있다.
- 관리자 API는 인증 헤더를 신뢰하기 전에 인증 계층(Easy Auth 또는 동등 체계)을 통과해야 한다.

## 상태 전이 원칙

- `pending` -> `approved` 또는 `rejected`
- `pending_ai` -> `approved` 또는 `rejected`
- `unknown` -> `approved` 또는 `rejected`
- 이미 종료된 상태에 대한 잘못된 재처리는 막는다.
- 동시 승인/반려는 낙관적 락으로 제어한다.

## PDF 검증 목표

- 최대 크기 제한 적용
- PDF 헤더 검증 적용
- EOF 마커 존재 여부 확인
- 스트림 또는 버퍼 검증 실패 시 즉시 중단

## 규칙 기반 파싱 목표

- 기본 파서는 규칙 기반으로 시작한다.
- 필수 필드 예시:
  - 이름
  - 이수 연도
  - 발급기관
  - 문서 번호 또는 시리얼
- 규칙 기반 파싱 실패 시 AI 보조 파이프라인으로 넘긴다.

## AI 보조 인식 목표

- 규칙 파싱 실패 시에만 호출한다.
- 동일 파일 해시 기준으로 호출 상한을 둔다.
- 상한 관리는 ai_limits 컨테이너 TTL 문서로 관리한다.
- AI 실패 시 `unknown`으로 안전하게 fallback 한다.

## 관리자 검수 흐름 목표

- `pending_ai` 또는 `unknown` 문서는 관리자 검수 대상으로 간주한다.
- 관리자 화면에는 원본 이미지 또는 변환 이미지와 추천값을 함께 보여준다.
- 수정 전/후 값과 수정자, 수정 시각을 남긴다.

## 파일 처리 목표

- PDF 원본을 검증한다.
- 첫 페이지 기준 변환을 우선 적용한다.
- PNG 또는 중간 버퍼를 거쳐 WebP로 변환한다.
- Blob Storage 경로는 문서 종류별로 분리한다.

## Blob 경로 규칙

예시:

- `documents/safety/2026/{personId}/{fileName}`
- `documents/integrity/2026/{personId}/{fileName}`
- `documents/mandatory/2026/{personId}/{fileName}`

경로 생성 원칙:

- 최상위 경로는 문서 종류
- 다음은 연도 또는 기수
- 마지막은 내부 식별값 기반 파일 경로

## 알림 흐름 목표

- 제출 독려는 휴대폰 번호 기준 알림톡을 사용한다.
- 크리티컬 운영 알림도 알림톡을 사용할 수 있다.
- 알림 전송 이력은 장기적으로 감사 로그와 연결할 수 있어야 한다.

## 현재 구현 현황 (2026-04-11)

- 사용자 API
  - `POST /api/submit` 구현 완료
  - `POST /api/status` 구현 완료
  - `GET /api/view/{cohortId}/{personId}` 구현 완료
- 관리자 API
  - `GET /api/manage/pending` 구현 완료
  - `POST /api/manage/approve` 구현 완료
  - `POST /api/manage/upload-members` 구현 완료
  - `GET,POST /api/manage/cohorts` 구현 완료
  - `GET,POST /api/manage/admins` 구현 완료
  - `POST /api/manage/close-cohort` 구현 완료
- 로컬 개발 흐름
  - `npm run reset:local` + `npm run seed:local` + `npm run host:start`
  - `LOCAL_DATA_STORE=true` 기준 파일 기반 저장소 + Azurite blob 검증 가능

## 최종 검증 체크리스트 (완료)

- [x] E2E: `submit -> pending -> approve -> view(download=true)`
- [x] 권한 경계: sub 관리자 문서 타입 제한 검증
- [x] 코호트 종료 후 제출 차단 (`COHORT_CLOSED`)
- [x] `status` 응답 형태 분리
  - 기본: 상세 맵/컬렉션 제외
  - `includeDetails=true`: 최신 상세 맵 포함
  - `includeCollections=true`: `registry`, `records` 포함

## API 에러코드 표 (현재 구현)

### submit

- `MISSING_REQUIRED_FIELDS`
- `INVALID_DOCUMENT_TYPE`
- `MISSING_STUDENT_ID`
- `COHORT_CLOSED`
- `STORAGE_UNAVAILABLE`
- `INTERNAL_SERVER_ERROR`

### approve

- `MISSING_REQUIRED_FIELDS`
- `INVALID_TARGET_STATUS`
- `REVIEW_NOTE_REQUIRED`
- `REVIEW_REASON_CODE_REQUIRED`
- `INVALID_REVIEW_REASON_CODE`
- `INVALID_REASON_CODE_FOR_TARGET_STATUS`
- `RECORD_INVALID_STATE`

### view

- `MISSING_PATH_PARAMS`
- `PERSON_VERIFICATION_REQUIRED`
- `APPROVED_RECORD_NOT_FOUND`
- `PERSON_VERIFICATION_FAILED`
- `FILE_BLOB_NOT_FOUND`
- `VIEW_STORAGE_UNAVAILABLE`
- `INTERNAL_SERVER_ERROR`
