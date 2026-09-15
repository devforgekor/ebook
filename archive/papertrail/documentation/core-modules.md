# Core 모듈 API 문서

Core 모듈은 Papertrail 프로젝트의 기반 유틸리티로, 리소스명 생성, 입력 검증, 환경 설정 등을 제공합니다.

## core/naming.py

리소스명 생성 유틸리티 (Python).

### 함수

#### `generate_resource_names(school_token, nice, level, env, num)`

주어진 학교 정보로 Azure 리소스 이름을 생성합니다.

**매개변수:**
- `school_token`: 학교 토큰 (소문자+숫자 2~10자)
- `nice`: 교육청 코드 (예: sen, goe)
- `level`: 학교급 코드 (예: hs, ms, es)
- `env`: 환경 코드 (t=테스트, p=운영)
- `num`: 배포 번호 (두 자리 숫자)

**설정되는 전역 변수:**
- `BASE_NAME`: 기본 이름 (토큰+코드+레벨+환경+번호)
- `SAFE_BASE`: 하이픈이 제거된 BASE_NAME
- `RESOURCE_GROUP`: 리소스 그룹 이름 (`rg-${BASE_NAME}`)
- `STORAGE_ACCOUNT`: 스토리지 계정 이름 (`st${SAFE_BASE}`)
- `KEYVAULT`: 키 자격 증명 모음 이름 (`kv-${BASE_NAME}`)
- `CONTAINER_APP`: 컨테이너 앱 이름 (`app-${BASE_NAME}`)
- `FUNCTION_APP`: 함수 앱 이름 (`func-${BASE_NAME}`)
- `ACR`: 컨테이너 레지스트리 이름 (`acr${SAFE_BASE}`)
- `LOG_ANALYTICS`: 로그 분석 작업 영역 이름 (`law-${BASE_NAME}`)
- `IDENTITY`: 관리 ID 이름 (`id-${BASE_NAME}`)

#### `generate_shared_names(token, nice, level, region)`

공유 인프라 리소스 이름을 생성합니다.

**매개변수:**
- `token`: 학교 토큰
- `nice`: 교육청 코드
- `level`: 학교급 코드
- `region`: 지역 코드 (예: krc)

**설정되는 전역 변수:**
- `SHARED_RG`: 공유 리소스 그룹 이름 (`rg-shared-infra-${suffix}-${region}00`)
- `SHARED_COSMOS`: 공유 Cosmos DB 계정 이름 (`cosmos-ssot-${suffix}-${region}00`)
- `SHARED_ENV`: 공유 컨테이너 환경 이름 (`env-ssot-${suffix}-${region}00`)

#### `generate_legacy_school_names(env, loc)`

레거시 학교 배포용 고정 리소스명을 생성합니다.

**매개변수:**
- `env`: 환경 (test/prod)
- `loc`: 위치 코드 (예: krc)

**설정되는 전역 변수:**
- `LEGACY_RG`: 레거시 리소스 그룹 이름
- `LEGACY_KV`: 레거시 키 자격 증명 모음 이름
- `LEGACY_STORAGE`: 레거시 스토리지 계정 이름
- `LEGACY_COSMOS`: 레거시 Cosmos DB 계정 이름
- `LEGACY_ACR`: 레거시 컨테이너 레지스트리 이름
- `LEGACY_ENV_NAME`: 레거시 컨테이너 환경 이름
- `LEGACY_APP`: 레거시 앱 이름

### 사용 예시

```python
from common_lib.core import naming

names = naming.generate_resource_names("test", "sen", "hs", "t", "01")
print(f"리소스 그룹: {names['RESOURCE_GROUP']}")
```

## core/validator.py

입력값 검증 함수 (Python).

### 함수

#### `validate_school_token(token)`

학교 토큰이 소문자와 숫자로 2~10자 사이인지 검증합니다. 유효하지 않으면 예외를 발생시킵니다.

#### `validate_deploy_num(num)`

배포 번호가 두 자리 숫자인지 검증합니다.

#### `validate_base_name_length(base_name)`

기본 이름이 22자를 초과하지 않는지 검증합니다.

#### `validate_production_secrets()`

프로덕션 모드에서 필수 환경 변수(`AZURE_OPENAI_ENDPOINT`, `API_KEY_AI` 등)가 설정되었는지 확인합니다. `ALLOW_DEFAULT_SECRETS`가 `false`일 때만 검사를 수행합니다.

### 사용 예시

```python
from common_lib.core import validator

validator.validate_school_token("myschool123")
```
```

## core/config.sh

환경 변수 및 설정 관리.

### 주요 기능

- `load_config`: `.env` 파일을 읽어 환경 변수로 설정합니다.
- `LOCATION`, `REGION_CODE`, `TEMPLATE_FILE` 등의 기본값 제공.

### 사용 예시

```bash
source ../common-lib/core/config.sh
echo "위치: $LOCATION"
```

## core/utils.sh

공통 Bash 유틸리티.

### 함수

- `log_info`, `log_warn`, `log_error`: 로깅 함수.
- `is_azure_cli_installed`: Azure CLI 설치 여부 확인.
- `ensure_tool`: 필수 도구가 설치되었는지 확인.

### 사용 예시

```bash
source ../common-lib/core/utils.sh
log_info "작업 시작"
```

---

**다음 문서:** [Infrastructure 모듈 API](infrastructure-modules.md)