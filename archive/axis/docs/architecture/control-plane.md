# Control-Plane

## Purpose
Control-Plane은 Axis 파이프라인을 제어하지 않는다.
Control-Plane은 파이프라인의 상태와 결과를 **노출**한다.

본 문서는 구현을 정의하지 않는다.
자동화, 정책, 판단을 포함하지 않는다.

핵심 원칙:
**Control-Plane은 제어 계층이 아니라 노출 계층이다.**

## Responsibilities
- 결과(RESULT) 가시화
- 실행 이력 확인
- 수동(one-shot) 트리거의 범위 정의

## Allowed
- RESULT 목록 조회
- RESULT 단건 조회
- 최근 실행 완료 여부 확인
- 수동 실행 트리거(명시적 호출)

## Explicitly Not Allowed
- 자동 판단
- 자동 실행
- 정책/임계치 기반 제어
- 파이프라인 내부 상태 수정
- 재시도/우선순위 결정

## Data Boundary
- Control-Plane은 **RESULT만 읽는다**
- RAW / MET / OVW에는 접근하지 않는다
- working / staging / archive 경로를 제어하지 않는다

## Non-Goals
- 스케줄러
- 워크플로우 엔진
- 추천/점수 시스템
- 성능 튜닝/자원 관리

## Evolution Rule
- 가시성 범위 확장은 허용한다
- 자동화는 금지한다
- 구현은 별도 문서에서 다룬다

