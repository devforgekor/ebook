# 비전문가 개발자를 위한 AI 기반 모듈형 개발 참고서

<br>
<br>

```
graph TD
    subgraph "1. 기능 정의 및 품질 기준"
        A[DeepSeek Web<br>입출력 규격 정의] --> B[bkit<br>Given-When-Then 체크리스트 작성]
    end

    subgraph "2. Draft 실험 공간"
        C[GitHub Copilot / Cursor Pro] --> D[papertrail/draft/ 에서<br>블록 초안 작성]
        D --> E{2회 이상<br>재사용 발생?}
    end

    subgraph "3. 정식 구조로 승격"
        E -- Yes --> F[core/ infra/ domain/<br>적절한 위치로 이동]
        F --> G[프로젝트 전체<br>import 경로 수정]
    end

    subgraph "4. 통합 및 배포"
        H[Cursor Pro / Cline] --> I[services/ 에서<br>블록 조립]
        I --> J[runners/ 에서<br>실행 흐름 제어]
        J --> K[GitHub Actions<br>Azure Container Apps 배포]
    end

    D -.-> E
    F --> I

```

<br>
1\. 핵심 방법론: 기능 블록의 점진적 조립  
<br>
1.1. 기본 개념  
\- 블록(Module): 가장 작은 재사용 가능 기능 단위. 특정 입력을 받아 특정 출력을 반환하는 독립 실행 가능한 코드.  
\- 서비스(Service): 여러 블록을 조합하여 하나의 완결된 비즈니스 기능을 수행하는 중간 조립 단위.  
\- 러너(Runner): 서비스와 블록을 호출하여 전체 실행 흐름을 제어하는 최종 실행 진입점.  
<br>
1.2. 디렉토리 구조  
<br>
이 Git 저장소에서는 아래 표의 디렉터리 이름에 **papertrail/** 을 붙인 경로에 둔다 (예: `papertrail/draft/`, `papertrail/domain/`).  
<br>
| 디렉토리 | 목적 | 설명 |  
| :--- | :--- | :--- |  
| draft/ | 작업 중인 초안 코드 | 아직 완성되지 않았거나 재사용이 확인되지 않은 실험적 코드를 보관. |  
| core/ | 순수 유틸리티 블록 | 클라우드나 특정 도메인에 종속되지 않는 범용 기능(로깅, 검증, 변환 등). |  
| infrastructure/ | 외부 시스템 연동 블록 | Azure, AWS, OCI 등 특정 클라우드나 외부 API와 통신하는 코드. |  
| domain/ | 비즈니스 로직 블록 | 특정 업무 규칙(예: 학교별 명명 규칙, 할인 정책)을 구현한 코드. |  
| services/ | 블록 조립 서비스 | core, infrastructure, domain의 블록을 조합하여 하나의 완성된 기능 제공. |  
| runners/ | 실행 진입점 | 서비스를 호출하고 실행 순서를 제어하는 메인 스크립트 또는 CLI. |  
| tests/ | 테스트 코드 | 각 블록과 서비스에 대한 단위 테스트 및 통합 테스트 코드. |  
<br>
1.3. 블록 승격 규칙  
\- 최초 구현: draft 디렉토리에 파일을 생성하고 기능 구현에 집중한다. 파일명은 기능을 직관적으로 나타내며 접두사나 접미사 규칙을 강제하지 않는다.  
\- 재사용 발생: 동일한 draft 파일을 두 곳 이상에서 import 하여 사용하게 되면, 해당 파일을 적절한 정식 디렉토리(core, infrastructure, domain)로 이동한다. 이동 시 파일명은 변경하지 않으며, import 경로만 전체 프로젝트에서 수정한다.  
\- 장기 미사용: draft에 30일 이상 사용되지 않은 파일은 archive 디렉토리로 이동하거나 삭제한다.  
<br>
1.4. 의존성 방향 규칙  
\- core는 어떤 다른 디렉토리의 코드에도 의존하지 않는다.  
\- infrastructure는 core만 의존할 수 있다.  
\- domain은 core와 infrastructure에 의존할 수 있다.  
\- services는 core, infrastructure, domain을 자유롭게 조합한다.  
\- runners는 services를 호출하며, 하위 블록을 직접 호출하지 않는다.  
<br>
<br>
2\. 개발 워크플로우  
<br>
2.1. 기능 정의  
\- 도구: DeepSeek (무료 웹 인터페이스)  
\- 작업: 구현할 기능을 문장으로 기술하고, 입력과 출력 데이터의 형식을 정의한다. 기능 실패 시나리오도 함께 질의하여 대비한다.  
<br>
2.2. 품질 기준 정의  
\- 도구: bkit  
\- 작업: 정의된 입출력 규격을 바탕으로 Given-When-Then 형식의 체크리스트를 작성한다. 이 체크리스트는 추후 자동 검증의 기준이 된다.  
<br>
2.3. 블록 초안 작성  
2.3. 블록 초안 작성  
\- 도구: GitHub Copilot, Cursor Pro, Cline 또는 Roo Code  
\- 위치: papertrail/draft/  
\- 절차:  
  1. AI에게 단일 기능을 수행하는 Python 모듈 작성을 요청한다.  
  2. 생성된 파일을 papertrail/draft 디렉토리에 저장한다.  
  3. 파일 하단의 \`if \_\_name\_\_ == "\_\_main\_\_":\` 블록을 실행하여 독립 동작을 검증한다.  
  4. 실패 시 AI에게 오류 내용을 전달하여 수정하고, 성공할 때까지 반복한다.  
<br>
\- AI 요청 템플릿 (core 블록 예시):  
  "papertrail/draft 디렉토리에 들어갈 순수 Python 함수를 작성해줘.  
   입력은 dict 또는 Pydantic 모델이고, 출력도 Pydantic 모델이야.  
   함수 아래에는 pytest 대신 실행 가능한 테스트 코드를 if \_\_name\_\_ == '\_\_main\_\_': 블록 안에 넣어줘.  
   함수와 테스트 코드에 한글로 상세한 주석을 포함해줘."  
<br>
2.4. 블록 승격 및 통합  
\- 조건: 동일한 draft 파일이 두 곳 이상의 서비스 또는 다른 블록에서 import 되어 사용될 때.  
\- 절차:  
  1. draft 파일을 적절한 정식 디렉토리(core, infrastructure, domain)로 이동한다.  
  2. 프로젝트 전체에서 해당 파일을 import 하는 모든 경로를 새 위치로 수정한다.  
  3. tests 디렉토리에 해당 블록의 단위 테스트 파일을 추가한다.  
<br>
2.5. 서비스 조립  
\- 도구: Cursor Pro 또는 Cline  
\- 위치: services/  
\- 절차:  
  1. AI에게 필요한 블록들을 조합하여 특정 비즈니스 기능을 수행하는 서비스 코드 작성을 요청한다.  
  2. 서비스 파일 내에서 core, infrastructure, domain의 블록을 import 하여 사용한다.  
  3. 서비스 파일 하단에 독립 실행 테스트 블록을 포함하여 검증한다.  
<br>
2.6. 러너 구성 및 실행  
\- 위치: runners/  
\- 절차:  
  1. 서비스를 호출하고 전체 워크플로우 순서를 정의하는 메인 스크립트를 작성한다.  
  2. 환경 변수나 설정 파일을 통해 실행 환경(Docker, VM 등)에 따른 차이를 흡수한다.  
<br>
2.7. 테스트 실행  
\- 도구: pytest  
\- 위치: tests/  
\- 절차:  
  1. 각 블록과 서비스에 대응하는 테스트 파일을 작성한다.  
  2. CI 환경(GitHub Actions)에서 커밋 시 자동으로 테스트가 실행되도록 구성한다.  
<br>
<br>
3\. AI 도구 운영 전략  
<br>
3.1. 도구별 역할 분담  
\- GitHub Copilot: 코드 자동 완성 및 단순 반복 코드 생성에 사용. 교사 베네핏으로 무료 이용.  
\- Cursor Pro: Composer 기능을 활용한 다중 파일 동시 편집, 복잡한 리팩토링, 서비스 조립에 전략적으로 사용. 월 $20 크레딧 한도 내에서 운영.  
\- Cline / Roo Code: DeepSeek 또는 Qwen API를 직접 연결하여 사용. 복잡한 디버깅이나 자동화 작업이 필요할 때 투입. 종량제 과금.  
<br>
3.2. API 구매 및 연결  
\- DeepSeek API: 공식 홈페이지(platform.deepseek.com)에서 크레딧을 구매하여 사용. 캐시 적중 시 90% 할인 적용. $10 충전으로 일반적인 사용량 기준 2~3개월 사용 가능.  
\- Qwen API: 알리바바 클라우드 백련 플랫폼(bailian.aliyun.com)에서 신규 가입 시 무료 토큰을 제공받아 사용. 대규모 컨텍스트 분석이 필요한 경우에 활용.  
\- 연결 방식: Cline 또는 Roo Code 설정에서 Provider를 OpenAI Compatible로 선택하고 각 API의 엔드포인트와 키를 입력.  
<br>
3.3. 채팅 세션 관리  
3.3. 채팅 세션 관리  
\- Cursor: 하나의 작업(블록 생성, 서비스 조립)이 완료되면 새 채팅을 시작한다. 대화가 길어지면 토큰 소모가 증가하고 환각 가능성이 높아진다.  
\- Cline/Roo Code (DeepSeek API): 동일한 컨텍스트가 유지되는 작업은 채팅을 길게 유지하여 캐시 할인 효과를 극대화한다. 맥락이 바뀌면 새 채팅을 시작한다.  
  - 캐시 효율을 높이기 위한 구체적 지시 방법:  
    - "현재 [파일(@file:papertrail/draft/my\_module.py)만](mailto:파일\(@file:papertrail/draft/my_module.py\)만) 보고 수정해줘." 와 같이 대화 컨텍스트에 불필요한 파일이 포함되지 않도록 명시한다.  
    - 동일한 시스템 프롬프트와 프로젝트 규칙이 유지되는 동안에는 대화를 종료하지 않고 연이어 작업을 요청한다.  
<br>
<br>
4\. 모듈 설계 원칙  
<br>
4.1. 단일 책임  
하나의 블록은 하나의 명확한 기능만 수행한다. 두 가지 이상의 역할이 발견되면 분리한다.  
<br>
4.2. 명시적 인터페이스  
함수의 입력과 출력은 타입 힌트와 Pydantic 모델 또는 TypedDict를 사용하여 명확히 정의한다. 사전 합의된 스키마 외의 데이터는 전달하지 않는다.  
<br>
4.3. 불변성  
입력받은 데이터를 직접 수정하지 않고, 항상 새로운 객체를 생성하여 반환한다.  
<br>
4.4. 자체 테스트 포함  
모든 블록과 서비스 파일 하단에는 \`if \_\_name\_\_ == "\_\_main\_\_":\` 블록을 두어 해당 파일을 직접 실행했을 때 기본 동작을 검증할 수 있도록 한다.  
<br>
4.5. 문서화  
모든 함수와 클래스에는 한글 독스트링을 작성하여 기능, 인자, 반환값, 발생 가능한 예외를 상세히 설명한다.  
<br>
<br>
5\. 환경 및 배포  
<br>
5.1. 개발 환경  
\- Docker: .devcontainer 설정을 통해 일관된 개발 환경을 제공한다. 의존성 패키지와 실행 환경이 컨테이너 내부에 격리된다.  
\- VM: 특정 하드웨어 요구사항이나 보안 정책으로 인해 Docker만으로 충분하지 않은 경우 Azure VM을 활용한다. VM 생성 시 cloud-init을 사용하여 Docker 및 필요 패키지를 자동 설치하고, 모든 실행은 VM 내부에서도 Docker 컨테이너를 통해 이루어지도록 구성한다.  
<br>
5.2. 배포  
\- 저장소: GitHub Private Repository (교육자 혜택)  
\- 배포 대상: Azure Container Apps (교육자 혜택 $100 크레딧 활용)  
\- 배포 자동화: GitHub Actions의 워크플로우 파일을 작성하여 main 브랜치 푸시 시 Azure Container Apps로 자동 배포되도록 설정한다.  
<br>
<br>
6\. 주의사항  
<br>
6.1. draft 디렉토리 관리  
papertrail/draft는 임시 작업 공간이므로 정기적으로 사용 여부를 점검하여 승격 또는 삭제한다. 방치 시 기술 부채가 누적된다. 장기 미사용 초안은 papertrail/archive 로 옮긴다.  
<br>
6.2. 의존성 순환 금지  
core → infrastructure → domain → services 방향을 엄격히 준수한다. 역방향 참조는 허용하지 않는다.  
<br>
6.3. 환경 변수 및 보안  
Azure 연결 문자열, API 키 등 민감 정보는 코드에 하드코딩하지 않고 환경 변수 또는 Azure Key Vault를 통해 주입한다.  
<br>
6.4. Azure 크레딧 보호  
Azure VM을 사용할 경우 반드시 자동 종료 일정을 설정하여 불필요한 과금을 방지한다. Container Apps는 유휴 상태 시 자동으로 과금이 중단되므로 장기 실행 서비스가 아닌 경우 Container Apps 사용을 권장한다.  
<br>
6.5. 버전 관리  
GitHub Desktop을 사용하여 변경 사항을 자주 커밋한다. AI가 예상치 못한 코드 변경을 가했을 때 Discard Changes 기능으로 빠르게 복구할 수 있도록 준비한다.  
<br>
<br>
7\. 종합 도구 매트릭스  
<br>
| 단계 | 도구 | 비용 | 주요 활동 |  
| :--- | :--- | :--- | :--- |  
| 기능 정의 | DeepSeek (Web) | 무료 | 입출력 규격 정의, 실패 시나리오 분석 |  
| 품질 기준 | bkit | 보유 | 체크리스트 기반 품질 시나리오 작성 |  
| 블록 초안 | GitHub Copilot + Cursor Pro | 무료(교사) + $20/월 | draft 디렉토리에 기능 블록 작성 |  
| 복잡한 생성 | Cline / Roo Code | 종량제 | API 직접 연결, 자율 에이전트 작업 |  
| 블록 승격 | 수동 + AI 보조 | - | draft → 정식 디렉토리 이동 및 경로 수정 |  
| 서비스 조립 | Cursor Pro | - | 블록 조합 및 서비스 테스트 |  
| 테스트 | pytest + GitHub Actions | 무료 | 자동화된 단위 및 통합 테스트 |  
| 배포 | GitHub + Azure Container Apps | 무료(교육) | CI/CD 파이프라인을 통한 자동 배포 |  
<br>
이 문서는 비전문가 개발자가 AI 도구와 모듈형 설계 원칙을 결합하여 복잡한 시스템을 점진적으로 구축하기 위한 완전한 실무 지침을 제공한다.