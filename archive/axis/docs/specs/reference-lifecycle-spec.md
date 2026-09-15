# Reference Lifecycle Specification

## 0. Scope

본 문서는 Axis 시스템에서 말하는 **참조(reference)**의
생성, 유지, 소멸에 이르는 **생애주기(lifecycle)** 규칙을 정의한다.

이 문서는 다음을 정의한다.
- 무엇이 참조로 인정되는가
- 참조가 데이터의 생존에 어떤 영향을 미치는가
- 참조 정보가 어떻게 기록되는가

이 문서는 다음을 정의하지 않는다.
- 데이터의 가치 판단
- 참조의 중요도 평가
- 자동 삭제 또는 자동 보호 정책
- 운영자의 판단 기준

참조는 판단이 아니라 **관측 사건**이다.

## 1. Definition of Reference

Axis에서 참조(reference)란,
데이터가 **의미를 생성하거나 소비하는 과정에 실제로 사용된 사건**을 의미한다.

참조는 데이터의 존재를 확인하는 행위가 아니라,
데이터가 **분석·해석·의사결정 흐름에 참여한 사실**을 기록한다.

## 2. Reference-Producing Events

다음 사건은 참조로 인정된다.
아래 항목 중 하나라도 발생하면, 해당 데이터는 참조된 것으로 기록된다.

### 2.1 Analysis and Derivation

- MET 생성 시 RAW 참조
- MET(META), OVW(OVERVIEW), IST(INSIGHT)의 읽기 또는 갱신
- 기존 데이터로부터 파생 데이터 생성

### 2.2 Interpretation and Decision

- IST 생성
- IST 조회 또는 수정
- IST 기반 보고, 분석, 의사결정

### 2.3 Explicit Human Interaction

- 수동 쿼리
- 다운로드
- 감사, 재현, 조사 목적 접근

### 2.4 Lifecycle Boundary Access

- purge-marker 상태의 데이터 접근
- 삭제 후보 데이터의 검토 또는 확인

## 3. Non-Reference Events

다음 사건은 참조로 인정되지 않는다.

- 스토리지 객체 목록 조회
- 라이프사이클 작업에 의한 접근
- 단순 존재 확인
- 티어 이동 또는 재배치
- 시스템 정리 및 백그라운드 작업

참조는 시스템 유지를 위한 접근이 아니라,
**의미 생성에 직접 참여한 접근**에서만 발생한다.

## 4. Reference Metadata

참조는 다음 메타 정보로 기록된다.

- last_referenced_at  
  마지막 참조 발생 시각

- reference_count  
  누적 참조 횟수

- last_reference_type  
  마지막 참조의 유형 (예: MET_READ, IST_CREATE)

- last_reference_source  
  참조가 발생한 경로 또는 주체 (예: analysis_api, manual_query)

이 중 **데이터의 생존 판단에는 오직 시간 정보(last_referenced_at)만 사용된다**.
참조 횟수는 설명용 수치이며, 판단 조건이 아니다.

## 5. Lifecycle Interaction Rule

참조는 데이터의 삭제를 **지연시키는 방향으로만 작용한다**.

- 애매한 경우에는 참조로 간주한다
- 단 한 번의 참조도 데이터 생존을 연장한다
- 참조는 삭제를 유발하지 않는다

Axis는 참조 부족을 즉시 삭제 사유로 사용하지 않는다.
삭제는 항상 별도의 시간 기반 규칙을 거친다.

## 6. Reset on Reference

삭제 대기 상태(purge-marker)에 있는 데이터라도,
유예 기간 중 참조가 발생할 경우 다음 규칙이 적용된다.

- purge-marker는 즉시 해제된다
- 데이터는 active 상태로 복귀한다
- 생애주기 타이머는 재설정된다

삭제는 항상 유예 단계를 거치며,
참조가 발생한 데이터는 예외 없이 되돌아간다.

## 7. Stability Guarantee

참조 규칙은 다음 원칙을 따른다.

- 참조 정의는 확장될 수 있으나, 축소되지 않는다
- 과거에 참조로 인정된 사건은 이후에도 참조로 유지된다
- 새로운 사건 유형이 추가되더라도 기존 데이터의 의미는 변경되지 않는다

참조 규칙은 데이터의 비교 가능성을 보존하기 위해
장기적으로 안정성을 유지해야 한다.
