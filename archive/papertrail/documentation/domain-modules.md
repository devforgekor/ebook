# Domain 모듈 API 문서

학교 정보 입력, 배포 선택 등 비즈니스 로직을 담당하는 모듈입니다.

## domain/school.py

학교 정보 입력 및 저장 (Python).

### 함수

#### `select_nice_code()`

교육청 코드를 선택하는 대화형 프롬프트를 표시합니다. 사용자에게 번호를 입력받아 해당 코드(예: sen, goe)를 출력합니다.

#### `input_school_info()`

학교 이름(한글), 학교 토큰, 학교급(초등학교/중학교/고등학교)을 입력받아 딕셔너리로 반환합니다.

#### `save_school_info(school_token, nice_code, school_level, env_short, deploy_num)`

학교 정보를 파일에 저장합니다. 기본 위치는 `data/schools/${school_token}.json`입니다.

### 사용 예시

```python
from common_lib.domain import school

info = school.input_school_info()
print(f"학교 토큰: {info['school_name_token']}")
```

## domain/deploy_selector.py

배포 번호 결정 로직 (Python).

### 함수

#### `resolve_deploy_num(pattern_prefix, location)`

기존 리소스 그룹 이름 패턴을 기반으로 새 배포 번호를 결정합니다. Azure CLI를 사용하여 리소스 그룹을 조회합니다.

**매개변수:**
- `pattern_prefix`: 리소스 그룹 이름 패턴 (예: `rg-testsenhst`)
- `location`: 지역 (예: `koreacentral`)

**반환값:** 두 자리 숫자 문자열 (예: `01`, `02`)

### 사용 예시

```python
from common_lib.domain import deploy_selector

deploy_num = deploy_selector.resolve_deploy_num("rg-testsenhst", "koreacentral")
```

## domain/mode_selector.py

배포 모드 선택 (Python).

### 함수

#### `select_deploy_mode()`

배포 모드(전체 배포, 앱만 배포, 모니터링만 배포 등)를 선택하는 대화형 프롬프트를 제공합니다.

#### `get_mode_description(mode)`

지정된 모드의 설명을 반환합니다.

### 사용 예시

```python
from common_lib.domain import mode_selector

mode = mode_selector.select_deploy_mode()
```

## domain/resource_selector.py

리소스 선택 유틸리티 (Python).

### 함수

#### `select_existing_resource_group()`

구독 내 기존 리소스 그룹 목록을 표시하고 사용자가 선택할 수 있게 합니다.

#### `select_existing_storage_account(resource_group)`

지정된 리소스 그룹 내 스토리지 계정 목록을 표시하고 선택합니다.

### 사용 예시

```python
from common_lib.domain import resource_selector

rg = resource_selector.select_existing_resource_group()
```

---

**다음 문서:** [CLI 모듈 API](cli-modules.md)