# Operations And Monitoring

이 문서는 목표 설계 기준의 운영, 로깅, 모니터링, 테스트, 유지보수 정책을 정리한 계획 문서다.

## 운영 목표

- 무료 할당량 안에서 안정적으로 운영한다.
- 업무시간과 비업무시간의 특성을 구분해 운영한다.
- 공휴일과 야간에는 콜드 스타트를 허용한다.
- 운영자가 이해하기 쉬운 상태 메시지와 점검 절차를 제공한다.

## 스케일링 목표

- 기본은 HTTP 스케일링
- 목표 상태에서는 평일 08:30~17:30에만 최소 replica를 유지하는 Cron 스케일링을 추가 검토한다.
- 공휴일은 별도 예외 로직 없이 scale-to-zero 상태에서 자동 기동을 허용한다.

## 헬스체크 목표

- `/health`
  - 기본 상태 응답
  - 업무시간/비업무시간 안내 메시지 포함 가능
- `/health/deep`
  - Cosmos DB
  - Storage
  - 필요 시 외부 종속성

## 로깅 원칙

- 감사 로그와 디버그 로그를 분리한다.
- 구조화 로그(JSON)를 기본으로 한다.
- 카테고리 예시:
  - AUDIT
  - PDF_CONVERT
  - AI_PARSER
  - CLOSE_COHORT
  - ERROR

## 모니터링 목표

- Console 로그: 단기 운영 확인
- Log Analytics: 감사 로그 중심
- App Insights: 에러와 메트릭 중심
- 장기적으로 목적별 저장소를 분리한다.

## 비용 통제 원칙

- 무료 할당량을 우선 기준으로 한다.
- Log Analytics, App Insights 일일 상한을 별도로 관리할 수 있어야 한다.
- 구독 단위 Budget 알림을 설정할 수 있어야 한다.

## 테스트 목표

핵심 시나리오:

- 사용자 업로드 흐름
- 상태 조회 흐름
- 승인/반려 흐름
- 관리자 권한 차단
- AI 호출 상한
- 비업무시간 접근
- 낙관적 락 충돌
- PDF 변환 실패/파싱 실패 fallback

## 배포 전 체크리스트 (현재 구현 기준)

- [ ] Azure 리소스 상태 확인
  - Storage, Cosmos, Container Apps, Key Vault 접근 가능
- [ ] 시크릿/설정 확인
  - `STORAGE_CONNECTION_STRING`
  - `STORAGE_CONTAINER`
  - `COSMOS_DATABASE`
  - `COSMOS_CONTAINER`
  - `COSMOS_ADMINS_CONTAINER`
  - `COSMOS_REGISTRY_CONTAINER`
- [ ] 관리자 데이터 확인
  - 최소 1명 이상의 `super` 관리자 존재
  - `sub` 관리자의 `allowedDocumentTypes` 값 검증
- [ ] API 계약 확인
  - `submit`, `approve`, `view`가 구조화 에러(`code`, `message`) 반환
  - `pending` 응답에 `reviewRequirements`, `reviewPolicy` 존재
- [ ] 로컬 회귀 검증
  - `npm run reset:local`
  - `npm run seed:local`
  - `npm run host:start`
  - 핵심 E2E: submit -> pending -> approve -> view(download=true)

## 배포 후 체크리스트

- [ ] 헬스체크 확인
  - 앱 기동 직후 `/health` 또는 기본 엔드포인트 응답 확인
- [ ] 핵심 API 스모크 테스트
  - `POST /api/submit` (정상/필수값 누락)
  - `GET /api/manage/pending` (관리자 권한 확인)
  - `POST /api/manage/approve` (상태 전이 및 에러코드)
  - `GET /api/view/{cohortId}/{personId}` (본인 검증)
- [ ] 권한 경계 확인
  - `sub` 관리자의 비허용 문서 접근 403 확인
- [ ] 코호트 정책 확인
  - 종료된 코호트에 대한 제출 차단(`COHORT_CLOSED`) 확인
- [ ] 로그 확인
  - 5xx 에러 급증 여부
  - 승인/반려 감사 이벤트 누락 여부

## 장애 대응 런북 (초기 버전)

### 1) API 5xx 증가

- 증상
  - 다수 API에서 500/503 증가
- 1차 점검
  - Storage/Cosmos 연결 상태
  - 시크릿 값 오타 또는 누락
  - 최근 배포 시점과 에러 급증 시점 일치 여부
- 즉시 조치
  - 직전 정상 이미지로 롤백
  - 문제 구간 요청을 임시 제한(필요 시)

### 2) 관리자 승인 실패 급증

- 증상
  - `approve`가 400/403 비정상 증가
- 1차 점검
  - `pending`의 `reviewRequirements`, `reviewPolicy`와 프론트 입력값 일치 여부
  - `unknown` 상태의 `reviewReasonCode` 조합 규칙 위반 여부
  - 관리자 계정/권한(`allowedDocumentTypes`) 변경 이력
- 즉시 조치
  - 프론트 유효성 검증 룰과 서버 룰 동기화
  - 잘못 반영된 관리자 권한 되돌리기

### 3) 조회(view) 실패 증가

- 증상
  - `PERSON_VERIFICATION_REQUIRED`, `PERSON_VERIFICATION_FAILED`, `FILE_BLOB_NOT_FOUND` 증가
- 1차 점검
  - 사용자 입력(name/birthdate) 정규화 문제
  - records의 `blobName`과 실제 blob 존재 여부
- 즉시 조치
  - 데이터 정합성 점검 스크립트 실행
  - 누락 blob 복구 또는 레코드 재처리

## 운영 알림 우선순위

- P1
  - 제출/조회 전체 실패(5xx 대량)
  - 승인 API 전체 실패
- P2
  - 특정 문서유형만 승인 실패
  - 특정 cohort만 조회 실패
- P3
  - 경고성 지표(콜드스타트 증가, 응답 지연 증가)

## 문제 해결 기준

대표 점검 항목:

- 관리자 인증 헤더 누락
- admins 데이터 누락
- 부관리자 문서 종류 권한 누락
- 기수 종료 후 제출 차단 미적용
- PDF 파싱 타임아웃
- AI 상한 초과
- 비root 실행 누락

## 유지보수 정책

- 분기별 RU 사용량 점검
- Blob Lifecycle 정책 점검
- Key Vault 키 교체 정책 검토
- 부관리자 권한 정기 감사
- 정기 보고 체계는 추후 자동화 가능성을 열어 둔다.

## 데이터 정리 정책

- rejected 문서 정리 정책은 명확히 기록한다.
- 기수 종료 또는 정책 종료 시점 기준으로 +6년 후 폐기한다.
- ai_limits는 TTL 자동 정리를 유지한다.

## 장애복구 메모

- 장애복구 상세 절차는 아직 확정되지 않았다.
- 추후 최소 항목:
  - 재배포 절차
  - 시크릿 교체 절차
  - 직전 이미지 롤백 절차

## 원본 설계서와의 관계

- 이 문서는 `legacy/manage-docs.md`의 운영/모니터링 내용을 재구성한 계획 문서다.
- 실제 구현과 완전히 일치하는 운영 문서가 아니다.
