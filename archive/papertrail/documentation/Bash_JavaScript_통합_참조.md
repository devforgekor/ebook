# Bash‑JavaScript 통합 참조 문서

## 개요

이 문서는 Papertrail 방법론에서 Bash 스크립트 모듈과 JavaScript 모듈이 어떻게 함께 동작하는지를 설명합니다. 두 계층은 각각 인프라 배포 자동화와 웹 애플리케이션 비즈니스 로직을 담당하며, 상호 연계하여 전체 배포 워크플로우를 구성합니다.

## 디렉토리 구조

```
papertrail/
├── core/                     # 순수 Python 유틸리티
│   ├── naming.py
│   ├── validator.py
│   ├── config.sh
│   └── utils.py
├── infrastructure/azure/     # Azure 연동 Python 모듈
│   ├── deploy.py
│   ├── deploy_monitor.py
│   ├── logging.py
│   ├── ai_foundry.py
│   ├── acr.py
│   ├── containerapps.py
│   ├── test.py
│   └── utils.py
├── domain/                   # 비즈니스 로직 Python 모듈
│   ├── school.py
│   ├── deploy_selector.py
│   └── resource_selector.py
├── cli/                     # 실행 진입점 Python 스크립트
│   ├── deploy.py
│   └── deploy-app.py
├── core/js/utils/            # 순수 JavaScript 유틸리티
│   ├── auditTrail.js
│   ├── auth.js
│   ├── cryptoUtils.js
│   └── core.js
├── infrastructure/azure/js/  # Azure 연동 JavaScript 유틸리티
│   ├── aiUtils.js
│   ├── pdfUtils.js
│   ├── cosmos.js
│   ├── keyvault.js
│   └── storage.js
└── domain/records/           # 비즈니스 로직 JavaScript 모듈
    ├── functions/
    ├── routes/
    ├── access/
    ├── models/
    ├── audit/
    └── utils/
```

## Bash 모듈 개요

### core/
- **`naming.sh`** – 리소스명 생성 (`generate_resource_names`, `generate_shared_names`)
- **`validator.sh`** – 입력값 검증 (`validate_school_token`, `validate_deploy_num`)
- **`config.sh`** – 환경 변수 및 설정 값 관리 (`load_config`, `show_config`)
- **`utils.sh`** – 공통 Bash 유틸리티 (`require_command`, `confirm_yn`, `select_from_list`)

### infrastructure/azure/
- **`deploy.sh`** – Bicep 배포 실행 (`bicep_build`, `run_whatif`, `run_deployment`)
- **`deploy_monitor.sh`** – 배포 모니터링 (`monitor_deployment_with_spinner`, `stream_deployment_logs`)
- **`logging.sh`** – JSON 로깅 (`init_json_logging`, `write_json_log`)
- **`ai_foundry.sh`** – OpenAI 리소스 생성 및 관리
- **`acr.sh`** – ACR 이미지 빌드 및 푸시 (`acr_build_and_push`)
- **`containerapps.sh`** – 컨테이너 앱 업데이트 (`update_container_app_image`, `wait_for_revision_ready`)
- **`test.sh`** – 배포 후 HTTP 스모크 테스트

### domain/
- **`school.sh`** – 학교 정보 입력 (`select_nice_code`, `input_school_info`)
- **`deploy_selector.sh`** – 배포 번호 결정 (`next_available_deploy_num`)
- **`resource_selector.sh`** – 배포된 리소스 그룹 선택 및 파싱

### cli/
- **`deploy.sh`** – 전체 인프라 배포 워크플로우 (모든 모듈을 소스로 로드)
- **`deploy‑app.sh`** – 앱 이미지 빌드 및 컨테이너 앱 업데이트 전용 CLI 진입점

## JavaScript 모듈 개요

### core/js/utils/
- **`auditTrail.js`** – 감사 로그 기록 유틸리티
- **`auth.js`** – 인증 및 권한 검사
- **`cryptoUtils.js`** – 암호화 관련 헬퍼
- **`core.js`** – 범용 유틸리티 함수

### infrastructure/azure/js/
- **`aiUtils.js`** – Azure OpenAI 및 Cosmos DB 연동 (의존성: `@azure/openai`, `@azure/cosmos`)
- **`pdfUtils.js`** – Ghostscript 기반 PDF 처리 (의존성: `ghostscript`)
- **`cosmos.js`** – Cosmos DB 클라이언트 구성
- **`keyvault.js`** – Key Vault 비밀 조회
- **`storage.js`** – Azure Blob Storage 작업

### domain/records/
- **`functions/`** – Azure Functions 핸들러
- **`routes/`** – Express.js 라우트 정의 (예: `submit.js`)
- **`access/`** – 관리자 접근 제어 로직
- **`models/`** – 데이터 모델 및 스키마
- **`audit/`** – 도메인 감사 추적
- **`utils/`** – 도메인 특화 유틸리티

## 의존성 및 상호작용

### 의존성 방향
1. **Bash → JavaScript**: Bash 스크립트가 Node.js 스크립트를 자식 프로세스로 실행하여 비즈니스 로직 수행
2. **JavaScript → Bash**: Node.js가 `child_process`를 통해 배포 스크립트 호출 (드물게 사용)
3. **계층적 규칙**: 
   - Bash 모듈은 동일 계층 또는 하위 계층의 다른 Bash 모듈만 참조
   - JavaScript 모듈은 동일 계층 또는 하위 계층의 다른 JavaScript 모듈만 참조
   - 인프라 계층(`infrastructure/azure/js/`)은 코어 계층(`core/js/utils/`)을 참조 가능
   - 도메인 계층(`domain/records/`)은 코어 및 인프라 계층을 참조 가능

### 상호작용 패턴
- **배포 시나리오**: `runners/deploy.sh` → `infrastructure/azure/deploy.sh` (Bash) → `infrastructure/azure/js/cosmos.js` (JavaScript)를 통해 Cosmos DB 리소스 생성
- **앱 배포 시나리오**: `runners/deploy‑app.sh` → `infrastructure/azure/acr.sh` (Bash) → `infrastructure/azure/js/storage.js` (JavaScript)를 통해 빌드된 이미지 메타데이터 저장
- **데이터 처리 시나리오**: `domain/records/routes/submit.js` (JavaScript) → `infrastructure/azure/js/aiUtils.js` (JavaScript)를 통해 OpenAI 호출

## 사용 예시

### 예시 1: Bash에서 JavaScript 유틸리티 호출
```bash
#!/usr/bin/env bash
# 배포 후 Cosmos DB 초기 데이터 삽입
source ../common-lib/core/utils.sh
require_command node

node -e "
const cosmos = require('../../infrastructure/azure/js/cosmos');
async function init() {
  await cosmos.ensureDatabase();
  console.log('Cosmos DB 초기화 완료');
}
init().catch(console.error);
"
```

### 예시 2: JavaScript에서 Bash 배포 스크립트 실행
```javascript
// domain/records/functions/deployTrigger.js
const { execSync } = require('child_process');
const path = require('path');

function triggerInfraDeploy(schoolCode) {
  const deployScript = path.resolve(__dirname, '../../../runners/deploy.sh');
  const command = `bash ${deployScript} --school ${schoolCode} --what-if`;
  try {
    const output = execSync(command, { stdio: 'inherit' });
    return { success: true, output: output.toString() };
  } catch (error) {
    return { success: false, error: error.message };
  }
}
```

### 예시 3: 통합 배포 워크플로우
1. 사용자 `./infra/deploy-interactive.sh` 실행 (Bash 러너)
2. `domain/school.sh`로 학교 정보 입력
3. `infrastructure/azure/deploy.sh`로 Bicep 템플릿 배포
4. 배포가 완료되면 `infrastructure/azure/js/cosmos.js`로 Cosmos DB 컬렉션 생성
5. `infrastructure/azure/js/aiUtils.js`로 OpenAI 리소스 프로비저닝
6. `infrastructure/azure/test.sh`로 HTTP 엔드포인트 스모크 테스트

## API 참조

### Bash 주요 함수
| 모듈 | 함수 | 설명 |
|------|------|------|
| `core/naming.sh` | `generate_resource_names` | 학교 코드로 Azure 리소스명 생성 |
| `core/validator.sh` | `validate_school_token` | 학교 토큰 형식 검증 |
| `infrastructure/azure/deploy.sh` | `run_deployment` | Bicep 배포 실행 |
| `infrastructure/azure/containerapps.sh` | `update_container_app_image` | 컨테이너 앱 이미지 업데이트 |
| `domain/deploy_selector.sh` | `next_available_deploy_num` | 다음 사용 가능 배포 번호 계산 |

### JavaScript 주요 함수
| 모듈 | 함수 | 설명 |
|------|------|------|
| `core/js/utils/auth.js` | `verifyToken` | JWT 토큰 검증 |
| `infrastructure/azure/js/aiUtils.js` | `createChatCompletion` | OpenAI 채팅 완성 호출 |
| `infrastructure/azure/js/pdfUtils.js` | `mergePdfs` | 여러 PDF 파일 병합 |
| `domain/records/routes/submit.js` | `submitRecord` | 기록 제출 라우트 핸들러 |
| `domain/records/audit/auditTrail.js` | `logAction` | 감사 로그 기록 |

## 테스트 및 검증

### Bash 테스트
- 각 모듈 하단의 독립 실행 테스트 블록: `bash papertrail/core/naming.sh`
- 문법 검사: `bash -n papertrail/core/naming.sh`
- 통합 테스트: `./infra/deploy-interactive.sh --what-if`

### JavaScript 테스트
- 단위 테스트: `npm test` (해당 프로젝트 내)
- 통합 테스트: `node infrastructure/azure/js/cosmos.test.js`
- 라우트 테스트: Supertest를 이용한 Express 앱 테스트

### 통합 테스트
- 전체 배포 파이프라인을 what‑if 모드로 실행하여 두 계층의 상호작용 검증
- 실제 Azure 리소스를 사용하지 않는 모의(mock) 테스트 환경 구성 가능

## 향후 작업

1. **Bash‑JavaScript 통합 테스트 스크립트** 작성
2. **자동화된 참조 문서 생성** (JSDoc + Bash 주석 파싱)
3. **모듈 간 호출 표준화** (예: JSON IPC 채널)
4. **모니터링 대시보드**에서 두 계층의 로그 통합

---

*이 문서는 Papertrail 방법론의 Bash‑JavaScript 통합을 설명하는 참조 자료입니다. 최종 업데이트: 2026‑04‑18.*