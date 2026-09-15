# Infrastructure/Azure 모듈 API 문서

Azure 인프라 배포 및 관리와 관련된 스크립트 모듈입니다.

## infrastructure/azure/utils.py (Python 버전)

Azure CLI 헬퍼 함수.

### 함수

#### `ensure_azure_login()`

Azure CLI에 로그인되어 있는지 확인합니다. 로그인되어 있지 않으면 오류 메시지를 출력하고 종료합니다.

#### `wait_for_rg_deletion(rg, [timeout])`

리소스 그룹 삭제가 완료될 때까지 대기합니다. 기본 타임아웃은 1800초(30분)입니다.

#### `get_current_user_object_id()`

현재 로그인된 사용자의 Azure AD Object ID를 반환합니다.

#### `ensure_extension(ext)`

지정된 Azure CLI 확장이 설치되어 있는지 확인하고, 없으면 설치합니다.

### 사용 예시

```python
from common_lib.infrastructure.azure import utils

utils.ensure_azure_login()
user_id = utils.get_current_user_object_id()
```

## infrastructure/azure/shared_infra.py (Python 버전)

공유 인프라 배포 함수 (Python).

### 함수

#### `deploy_shared_infra(resource_group, cosmos_account, location)`

공유 Cosmos DB 계정 및 컨테이너 환경을 배포합니다.

#### `wait_for_shared_infra(resource_group, timeout)`

공유 인프라 배포가 완료될 때까지 대기합니다.

### 사용 예시

```python
from common_lib.infrastructure.azure import shared_infra

shared_infra.deploy_shared_infra(SHARED_RG, SHARED_COSMOS, LOCATION)
```

## infrastructure/azure/deploy.py (Python 버전)

주요 Azure 리소스 배포 함수 (Python).

### 함수

#### `deploy_main_bicep(resource_group, template_file, parameters, location)`

Bicep 템플릿을 사용하여 리소스 그룹에 리소스를 배포합니다.

#### `validate_bicep(template_file)`

Bicep 파일의 구문을 검증합니다.

### 사용 예시

```python
from common_lib.infrastructure.azure import deploy

deploy.deploy_main_bicep(RESOURCE_GROUP, TEMPLATE_FILE, PARAMETERS, LOCATION)
```

## infrastructure/azure/deploy_monitor.py (Python 버전)

배포 모니터링 및 로깅 설정 (Python).

### 함수

#### `setup_monitoring(resource_group, log_analytics_workspace, location)`

Log Analytics 작업 영역 및 진단 설정을 구성합니다.

#### `enable_container_insights(resource_group, container_app_environment)`

컨테이너 인사이트를 활성화합니다.

### 사용 예시

```python
from common_lib.infrastructure.azure import deploy_monitor

deploy_monitor.setup_monitoring(RESOURCE_GROUP, LOG_ANALYTICS, LOCATION)
```

## infrastructure/azure/rbac.py (Python 버전)

역할 기반 접근 제어(RBAC) 할당 (Python).

### 함수

#### `auto_assign_rbac_from_outputs(deploy_name, admin_object_id)`

배포 출력에서 리소스 ID를 읽고 지정된 관리자에게 역할을 할당합니다.

#### `assign_role(scope, principal_id, role_name)`

특정 범위에 역할을 할당합니다.

### 사용 예시

```python
from common_lib.infrastructure.azure import rbac

rbac.auto_assign_rbac_from_outputs(deploy_name, SUPER_ADMIN_OBJECT_ID)
```

## infrastructure/azure/logging.py (Python 버전)

JSON 형식 로깅 유틸리티 (Python).

### 함수

#### `init_json_logging(category, operation)`

JSON 로그 파일을 초기화하고 파일 경로를 반환합니다.

#### `write_json_log(log_file, level, message, extra)`

JSON 형식으로 로그 항목을 작성합니다.

### 사용 예시

```python
from common_lib.infrastructure.azure import logging

LOG_FILE = logging.init_json_logging("school", "deploy")
logging.write_json_log(LOG_FILE, "INFO", "배포 완료", {"school": school_korean_name})
```

## infrastructure/azure/functions.py (Python 버전)

Azure Functions 배포 함수 (Python).

### 함수

#### `deploy_functions(resource_group, function_app, location, storage_account)`

함수 앱을 배포하고 필요한 설정을 구성합니다.

#### `publish_function_code(function_app, project_path)`

로컬 함수 코드를 Azure에 게시합니다.

### 사용 예시

```python
from common_lib.infrastructure.azure import functions

functions.deploy_functions(RESOURCE_GROUP, FUNCTION_APP, LOCATION, STORAGE_ACCOUNT)
```

## infrastructure/azure/ai_foundry.py (Python 버전)

Azure OpenAI 리소스 배포 (Python).

### 함수

#### `create_openai_account(account_name, resource_group, location)`

OpenAI 계정을 생성합니다.

#### `deploy_openai_model(account_name, resource_group, model)`

지정된 모델을 OpenAI 계정에 배포합니다.

### 사용 예시

```python
from common_lib.infrastructure.azure import ai_foundry

ai_foundry.create_openai_account(f"openai-{BASE_NAME}", RESOURCE_GROUP, LOCATION)
```

---

**다음 문서:** [Domain 모듈 API](domain-modules.md)