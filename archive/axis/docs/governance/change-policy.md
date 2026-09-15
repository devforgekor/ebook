# Axis Change Policy (Post v4.0.0)

## Principle

본 문서는 Axis v4.0.0 이후의 변경 범위를 제한하여
구조적 일관성과 장기 안정성을 보장하기 위한 기준을 정의한다.

본 문서는 구현 상세를 설명하지 않는다.
본 문서는 변경 가능 범위를 고정한다.


## Branch Policy
- main 브랜치
  - 유지보수 및 문서 보강만 허용
  - 파이프라인 구조 변경 금지
- feature/*, experiment/*
  - 실험 및 기능 확장은 반드시 별도 브랜치에서 수행
  - 검증 전 main 병합 금지


## Allowed Changes on main
- 문서 보강 및 오탈자 수정
- Runbook 절차 설명 추가
- RESULT 소비자(읽기 전용) 출력 형식 개선


## Not Allowed on main
- 파이프라인 단계 추가/삭제
- 자동 실행(스케줄러, TTL, 재시도 정책)
- Control‑Plane 구현
- 저장 수명 규칙 변경
- 판단/점수/정책 로직 추가


## Versioning Rule
- 구조 변경: `v4.1+`
- 소비자 확장(읽기 전용): `v4.x`
- 운영 정책 변경은 릴리스 노트에 명시

## Enforcement
- 구조적 변경은 반드시 문서 변경을 동반해야 한다
- 문서 없는 구조 변경은 허용되지 않는다
- 작은 변경이 구조를 바꾸지 않도록 한다
- 자동화는 최후 단계에서만 도입한다