# Data And Policy

이 문서는 데이터 구조와 운영 정책의 기준안을 정리한 계획 문서다.

## 핵심 데이터 축

### 1. admins

권한의 진실 소스.

필수 필드 예시:

- id
- email
- type: super | sub
- name
- allowedDocumentTypes

원칙:

- 관리자 API는 항상 admins를 먼저 조회한다.
- sub 관리자는 allowedDocumentTypes에 포함된 문서만 처리할 수 있다.

### 2. records

제출 및 처리 이력의 진실 소스.

필수 필드 예시:

- id
- personId
- documentType
- submittedYear
- cohortId
- validUntil
- status
- blobName
- fileHash
- createdAt
- updatedAt
- updatedBy

원칙:

- 중복 제출은 덮어쓰기
- 승인/반려 상태 전이 규칙을 유지
- 문서 유효기간은 타입 정책에 따라 계산
- 안전교육은 3년 기수 기준을 적용할 수 있다.
- 같은 사람의 같은 문서 종류에 대한 연도별 최신 상태는 records에서 판정한다.

### 3. registry

연도별 구성원 상태의 진실 소스.

핵심 역할:

- 신규
- 재직
- 퇴직

원칙:

- registry는 기본적으로 1년 단위로 움직인다.
- 매년 명단 업로드 후 작년 명단과 비교한다.
- 사람 상태는 다음 세 가지로만 확정한다.
  - 신규: 작년 없음, 올해 있음
  - 재직: 작년 있음, 올해 있음
  - 퇴직: 작년 있음, 올해 없음
- registry의 기본 책임은 인사 상태 판정이다.
- 문서 유효기간 정책은 records에서 따로 계산한다.

## 사람 식별 기준

고정 기준:

- 이름
- 생년월일
- 휴대폰 번호

조회 기준:

- 이름 + 생년월일

알림 기준:

- 휴대폰 번호로 알림톡 발송

personId 생성 원칙:

- 이름과 생년월일의 정규화 규칙을 먼저 고정한다.
- personId 규칙이 바뀌면 과거 데이터와 연결이 깨지므로 이후 변경하지 않는다.

휴대폰 번호 원칙:

- 휴대폰 번호는 알림 발송에 사용한다.
- 가능하면 원문 저장과 검색용 값을 분리한다.
- 장기적으로는 암호화 저장 + 검색용 해시를 함께 두는 방식을 우선 검토한다.

## 문서 주기 정책

- 안전교육만 3년 기수제 적용
- 나머지 문서는 기본 1년 단위
- 안전교육 예시: 2024-2026 = 1기

## 보존/폐기 정책

- 기준 시점:
  - 기수 종료 또는
  - 1년 경과
- 폐기 시점:
  - 기준 시점 + 6년

## Blob 경로 원칙

문서 종류별 업로드 경로 분리.

예시:

- documents/safety/2026/{personId}/{fileName}
- documents/integrity/2026/{personId}/{fileName}
- documents/mandatory/2026/{personId}/{fileName}

경로 생성 원칙:

- 문서 종류가 경로 최상단에 온다.
- 연도 또는 기수 정보가 그 다음에 온다.
- 개인 식별값은 직접 식별정보 대신 내부 personId를 사용한다.

## 상태 전이 원칙

- pending -> approved 또는 rejected
- pending_ai -> approved 또는 rejected
- unknown -> approved 또는 rejected
- 이미 종료된 상태에 대한 잘못된 재처리는 막는다.

## 보존/폐기 상세 메모

- 1년 문서는 해당 연도 기준 정책 종료 시점을 계산한다.
- 3년 문서는 기수 종료 시점을 기준으로 한다.
- 폐기 기준은 종료 시점 + 6년으로 통일한다.

## 미래 확장 원칙

- 문서 종류는 늘어날 수 있다.
- 비슷한 문서는 같은 패밀리 로직을 공유한다.
- DB는 공통으로 사용하되, 컨테이너 책임을 명확히 유지한다.
