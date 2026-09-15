# CLI 모듈 API 문서

최종 사용자 실행 진입점(Command‑Line Interface)입니다.

## cli/deploy.sh

전체 배포 워크플로우를 실행하는 Bash 래퍼 스크립트 (내부적으로 cli/deploy.py를 호출).

### 개요

대화형으로 학교 정보를 입력받아 Azure 인프라를 배포합니다. 내부적으로 core, infrastructure, domain 모듈을 조합합니다.

### 사용법

```bash
cd papertrail/cli
./deploy.sh
```

### 환경 변수

- `NON_INTERACTIVE=1`: 대화형 프롬프트를 건너뜁니다. 필요한 값은 환경 변수로 설정해야 합니다.
- `DEPLOY_WHAT_IF=1`: 실제 배포 대신 what‑if 시뮬레이션을 실행합니다.

### 주요 단계

1. Azure 로그인 확인
2. 환경 선택 (테스트/운영)
3. 학교 정보 입력
4. 배포 번호 결정
5. 공유 인프라 배포 (선택)
6. 메인 Bicep 템플릿 배포
7. RBAC 할당
8. 추가 기능 배포 (Functions, OpenAI 등)
9. 로깅 초기화

## cli/deploy-app.sh

앱 이미지 빌드 및 컨테이너 앱 업데이트를 위한 Bash 래퍼 스크립트 (내부적으로 cli/deploy-app.py를 호출).

### 개요

기존 인프라가 배포된 후 애플리케이션 코드 변경 시 컨테이너 이미지를 빌드하고 업데이트합니다.

### 사용법

```bash
cd papertrail/cli
./deploy-app.sh
```

### 환경 변수

- `NON_INTERACTIVE=1`: 대화형 입력 없이 실행합니다.

### 주요 단계

1. Azure 로그인 확인
2. 환경 및 학교 선택
3. ACR 로그인
4. Docker 이미지 빌드 및 푸시
5. 컨테이너 앱 업데이트
6. 로깅

## cli/deploy.py

Python CLI 진입점 (전체 배포).

### 개요

참조 문서 권장사항에 따라 CLI 진입점을 Python으로 통일한 스크립트입니다. 내부적으로 common‑lib 모듈을 직접 호출하여 배포를 수행합니다.

### 함수

#### `find_repo_root()`

프로젝트 루트 디렉토리(papertrail/의 부모)를 반환합니다.

#### `load_config(repo_root)`

`.env` 파일에서 환경 변수를 로드합니다.

#### `setup_logging()`

기본 로깅을 구성합니다.

#### `run_python_deploy(what_if, non_interactive)`

Python 모듈을 사용하여 배포 워크플로우를 실행합니다.

### 사용법

```bash
cd papertrail/cli
python deploy.py [--what-if] [--non-interactive]
```

### 명령줄 옵션

- `--what-if`: what‑if 모드 실행
- `--non-interactive`: 대화형 입력 없이 실행
- `--version`: 버전 출력

## cli/deploy-app.py

Python CLI 진입점 (앱 배포).

### 개요

앱 배포 워크플로우를 실행하는 Python 스크립트입니다. 내부적으로 common‑lib 모듈을 직접 호출합니다.

### 함수

#### `run_python_deploy_app(non_interactive)`

Python 모듈을 사용하여 앱 배포 워크플로우를 실행합니다.

### 사용법

```bash
cd papertrail/cli
python deploy-app.py [--non-interactive]
```

### 명령줄 옵션

- `--non-interactive`: 대화형 입력 없이 실행
- `--version`: 버전 출력

---

**문서 통합:** [README.md](../README.md)에서 전체 모듈 구조를 확인할 수 있습니다.