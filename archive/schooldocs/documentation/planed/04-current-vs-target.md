# Current Vs Target

이 문서는 현재 구현과 목표 설계의 차이를 빠르게 비교하기 위한 문서다.

## 목적

- 현재 운영 기준과 계획 기준을 혼동하지 않는다.
- 아직 구현되지 않은 기능을 별도로 추적한다.
- 실제 이식 순서를 정할 때 참고한다.

## 한눈에 보는 비교

| 영역 | 현재 구현 | 목표 설계 |
|------|-----------|-----------|
| 런타임 | Azure Functions v4 단일 함수 | Container Apps 기반 확장형 API |
| 앱 구조 | submit 단일 엔드포인트 | 사용자 API + 관리자 API 분리 |
| 권한 | anonymous 중심 | admins 기반 super/sub 권한 모델 |
| 데이터 축 | records 중심, admins/registry/ai_limits 인프라 준비 | admins + records + registry 중심 구조 |
| 문서 종류 | recordType 수준의 단순 구분 | documentType 정책 기반 확장 구조 |
| 주기 정책 | 아직 코드에 정책 테이블 없음 | 안전교육 3년, 나머지 1년 |
| 명단 처리 | 미구현 | 신규/재직/퇴직 자동 판정 |
| AI 파이프라인 | 미구현 | 규칙 파싱 실패 시 AI fallback |
| 관리자 인증 | 미구현 | Easy Auth 또는 동등 체계 |
| 스케일링 | HTTP 스케일링만 존재 | HTTP + 필요 시 Cron 스케일링 |

## 현재 구현 기준 요약

- 함수 엔드포인트: submit
- 데이터 저장: Cosmos DB records 컨테이너
- 보조 컨테이너: admins, registry, ai_limits 인프라 정의 존재
- 파일 저장: Blob Storage record-files 컨테이너
- 권한 모델: 아직 API 레벨 구현 없음
- CORS, Free Tier, 시크릿 기본값 등 인프라 안정화는 일부 반영 완료

## 목표 설계 기준 요약

- 문서 종류별 정책 기반 처리
- admins를 통한 문서 종류별 권한 제어
- registry를 통한 연도별 명단 비교
- 안전교육 3년 기수제
- 알림톡/상태조회/승인 워크플로우 확장

## 우선 이식 대상

1. records 스키마에 documentType, validUntil, 상태 전이 필드 추가
2. admins 권한 모델 구현
3. registry 업로드 및 신규/재직/퇴직 비교 로직 구현
4. 안전교육 3년 기수 정책 구현

## 1차 구현 범위 확정안

이 단계에서는 목표 설계 전체를 한 번에 구현하지 않는다. 현재 코드와 가장 잘 연결되는 핵심 데이터 축과 정책만 우선 반영한다.

포함 범위:

1. records 스키마 확장
- documentType
- submittedYear
- validUntil
- fileHash
- status
- createdAt, updatedAt, updatedBy

2. admins 권한 모델
- super
- sub
- allowedDocumentTypes

3. registry 기본 흐름
- 연도별 명단 업로드
- 작년 대비 신규/재직/퇴직 판정

4. 문서 종류 3개 우선 지원
- safety
- integrity
- mandatory

5. 주기 정책
- safety만 3년 기수제
- 나머지는 1년 단위

비포함 범위:

- AI 보조 인식
- Easy Auth 실제 연동
- 관리자 전체 승인 UI/워크플로우
- Cron 스케일링
- App Insights와 정기 보고 자동화
- 장애복구 상세 절차

## 1차 구현 작업 순서

1. records 문서 구조 확정
- 현재 submit 저장 포맷을 목표 records 구조로 확장

2. documentType 정책 테이블 추가
- safety, integrity, mandatory의 유효기간과 처리 규칙 정의

3. submit 흐름 개편
- 업로드 시 documentType 반영
- validUntil 계산
- 덮어쓰기 정책 반영

4. admins 데이터 모델 반영
- super/sub 문서 구조 확정
- allowedDocumentTypes 규칙 추가

5. registry 비교 로직 설계
- 명단 업로드 포맷 확정
- 신규/재직/퇴직 판정 로직 정의

6. 안전교육 cohort 규칙 추가
- 2024-2026 형태의 3년 기수 식별 규칙 정의

## 1차 완료 조건

아래 조건을 만족하면 1차 구현 완료로 본다.

1. records에 문서 종류와 유효기간 정보가 저장된다.
2. 안전교육만 3년 기준으로 validUntil이 계산된다.
3. 나머지 문서는 1년 기준으로 validUntil이 계산된다.
4. admins 문서 구조가 확정되고 권한 체크 기준이 정리된다.
5. registry의 신규/재직/퇴직 판정 규칙이 문서와 코드 설계에 반영된다.

## 1차 이후 단계

1차가 끝난 뒤에야 다음 단계를 검토한다.

1. 관리자 인증 연동
2. 관리자 승인/반려 API 확장
3. 상태조회 API 확장
4. AI 보조 인식 추가
5. 운영 자동화 및 모니터링 확장

## 보류 항목

- 장애복구 상세 절차
- 추가 문서 타입의 세부 정책
- 2차 사용자 인증 보완 절차