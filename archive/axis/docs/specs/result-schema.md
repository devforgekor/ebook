# RESULT Schema

## 0. Purpose

본 문서는 Axis Engram 단계에서 생성되는 RESULT 산출물의
최소 스키마와 의미를 정의한다.

RESULT는 판단 결과가 아니라,
판단에 사용할 수 있는 집계 결과를 제공하는 산출물이다.

본 문서는 생성 주기, 보존 기간, 삭제 정책을 정의하지 않는다.

## 1. What RESULT Is / Is Not

### RESULT Is
- 사고 산출물(OVW)로부터 생성된 **집계 결과**
- 외부 소비(리포트, 비교, 내보내기)의 기준점
- 재생성 가능한 산출물

### RESULT Is Not
- 정답, 결론, 추천
- 점수 또는 등급
- 정책이나 임계치를 내포한 데이터

## 2. Minimal Schema

RESULT는 아래의 최소 스키마를 따른다.

```json
{
  "source_ovw": "OVW_<identifier>.jsonl",
  "generated_at": "<UTC timestamp>",
  "summary": { }
}
```

## 3. Location and Lifecycle

- RESULT는 `results/engram/`에 저장된다
- RESULT는 RAW/MET/OVW를 이동하거나 삭제하지 않는다
- RESULT 삭제는 운영 정책의 영역이며,
  본 문서의 범위를 벗어난다

## 4. Regeneration Principle

RESULT는 원본 데이터(RAW)가 존재할 경우
언제든 재생성 가능해야 한다.

RESULT는 기억(archive)이 아니라
결과(reference output)로 취급된다.

## 5. Non‑Goals

다음은 RESULT 스키마의 비목표다.

- 실시간 판단
- 자동 정책 반영
- 상태 머신 표현
- 실행 제어 신호 제공
