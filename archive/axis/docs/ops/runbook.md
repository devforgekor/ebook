# Axis Runbook (Manual Operations)

## Scope
본 Runbook은 Axis를 수동으로 운영하는 절차만을 정의한다.
자동 실행, 자동 판단, 정책 변경은 다루지 않는다.

## Daily Check
- results/engram/에 새로운 RESULT가 생성되었는지 확인
- staging/ 디렉터리에 파일이 과도하게 쌓이지 않았는지 확인
- archive/ 구조가 예상과 동일한지 확인

## Manual Execution Order
1. Synapse 실행
   python3 src/synapse/run_once.py

2. Cortex 실행
   python3 src/cortex/run_once.py

3. Engram 실행
   python3 src/engram/run_once.py

4. Staging 정리
   python3 src/cortex/staging_rotate.py

5. (선택) purge-edge 수동 정리
   python3 src/cortex/purge_edge_once.py --apply

## When NOT to Act
- 입력(RAW)이 없는 경우 → 아무 것도 하지 않는다
- staging/warm 만 차있는 경우 → 삭제하지 않는다
- RESULT가 없다고 해서 재실행하지 않는다
- 실패(RAW_FAIL)가 존재해도 자동 재시도하지 않는다

## Failure Principle
실패는 상태로 기록된다.
실패를 되돌리기 위한 자동 행동은 수행하지 않는다.

## Notes
이 Runbook은 절차를 정의하며,
판단과 해석은 시스템 외부에서 이루어진다.
운영 판단에 대한 자세한 철학과 시간 축은 docs/RUNBOOK.md를 참조한다.

## Result Export (Read-Only)

### Purpose
RESULT Export는 Axis의 결과를 외부로 전달하기 위한
읽기 전용 수동 절차다.

Export는 파이프라인을 변경하지 않으며,
어떠한 실행 제어도 수행하지 않는다.

### When to Run
- 새로운 RESULT가 생성된 이후
- 외부 공유, 리포트, 검토가 필요한 경우

### How to Run
```bash
python3 src/consumers/export_csv.py
``
이 명령은 results/engram/에서 최신 RESULT를 읽어와 CSV 파일로 변환하여 exports/ 디렉터리에 저장한다.
CSV 파일은 수동으로 검토하거나 외부로 공유할 수 있다. 
