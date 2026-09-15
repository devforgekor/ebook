# Project The Axis

## Documentation System — One‑Page Map

이 문서는 Project The Axis의 **문서 체계 전체를 한 장으로 고정**한다.  
각 문서는 역할이 다르며, **서로를 대체하거나 침범하지 않는다.**

Axis의 문서 체계는 다음 질문에 답하도록 설계되어 있다:

*   왜 이런 시스템인가
*   구조적으로 어디까지 허용되는가
*   언제 판단이 일어나는가
*   무엇을 관측할 수 있는가
*   코드에서 어디를 넘으면 망가지는가

***

## 1. 규범 문서 (Normative / Constitutional)

이 문서들은 **Axis의 정체성과 판단 책임을 고정**한다.  
이 세트는 **닫혀 있으며**, 원칙적으로 **추가되지 않는다**.

### README.md — Why

Axis의 헌장.  
무엇을 하지 않는 시스템인지, 판단 책임이 어디에 있는지를 선언한다.

### OVERVIEW\.md — What

전체 구성 요소와 데이터 흐름의 큰 그림.  
운영·구현 세부는 포함하지 않는다.

### ARCHITECTURE.md — Where

책임과 경계의 헌법.  
Control / Execution / Judgment가 섞이면 망가지는 지점을 고정한다.

### RUNBOOK.md — When

운영자가 **언제, 어떤 순서로 판단해야 하는지**를 정의한다.  
결론·권고·조치는 포함하지 않는다.

### STATISTICS.md — How far

무엇을 관측할 수 있고, 어디까지 해석이 허용되는지를 규정한다.  
수치를 판단으로 바꾸는 것을 금지한다.

### DEVELOPMENT.md — Do Not Cross

구현 단계의 가드레일.  
코드에서 이 선을 넘으면 Axis가 아니다.

***

## 2. 하위 계층 문서 (Non‑Normative)

아래 문서들은 **이미 정의된 규범을 전제로**,  
운영·형식·기술·기록을 분리하여 관리한다.

***

### specs/ — 규칙·형식·표준

성격:

*   네이밍, 포맷, 구조
*   해석·판단 없음
*   변경 시 영향 범위 명확

예시:

*   metric‑naming.md
*   operational‑identifier.md
*   event‑error‑codes.md
*   log‑format.md

***

### ops/ — 운영 실무 문서

성격:

*   사람이 무엇을 보고 어떤 순서로 판단하는지
*   자동화, 임계값, 권고 없음
*   RUNBOOK을 보완하지만 대체하지 않음

예시:

*   metric‑checklist.md
*   playbooks/index.md

***

### control‑plane/ — 제어/UI 기술 문서

성격:

*   Bot, Control Plane, UI의 기술적 역할
*   전달 규칙과 제약
*   판단 책임은 포함하지 않음

예시:

*   bot‑architecture.md

***

### history/ — 설계 이력·과거 맥락

성격:

*   왜 이런 선택을 했는지에 대한 기록
*   초기 통합 문서, 과거 가이드
*   현재 규칙의 근거로 사용 금지

예시:

*   design‑rationale.md
*   project‑origin.txt
*   low‑cost‑architecture‑guide.md

***

## 3. 문서 체계의 핵심 원칙

*   규범 문서는 **줄어들 수는 있어도 다시 커지지 않는다**
*   하위 문서는 **규범을 설명하거나 재정의하지 않는다**
*   규칙(specs), 판단 보조(ops), 기술(control), 기록(history)은 **섞이지 않는다**
*   “애매한 위치”의 문서는 허용되지 않는다

문서의 수는 늘 수 있다.  
그러나 **문서의 종류와 위치는 늘지 않는다.**

***

## 4. 한 문장 정리

Axis 문서 체계는  
**판단을 자동화하지 않기 위해, 문서의 역할부터 자동으로 고정하는 구조**다.
