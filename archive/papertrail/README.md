# Papertrail 프로젝트

AI 기반 모듈형 개발 참고서를 구현한 오픈소스 프로젝트입니다. 학교 환경에 맞춰 Azure 리소스를 배포하고, 로그 수집, 분석, 저장 파이프라인을 제공합니다.

## 주요 기능

- **모듈형 아키텍처**: core, infrastructure, domain, collector, analyzer, storage 계층으로 분리된 책임 분리
- **Azure 자동 배포**: Bicep 템플릿을 이용한 리소스 일괄 배포 (리소스 그룹, Cosmos DB, Container Apps, Functions, OpenAI 등)
- **데이터 파이프라인**: 로그 수집(collector), 분석(analyzer), 저장(storage)을 위한 Python/Bash 스크립트
- **통합 CLI**: `cli/deploy.sh` (또는 `cli/deploy.py`)로 전체 배포 워크플로우 실행
- **테스트 자동화**: Bats 프레임워크 기반 단위 테스트
- **CI/CD**: GitHub Actions를 통한 테스트 및 배포 자동화

## 프로젝트 구조

```
papertrail/
├── core/                 # 공통 유틸리티 (도메인/인프라 독립적)
│   ├── naming.sh        # 리소스 이름 생성 규칙
│   ├── validator.sh     # 입력 검증
│   └── config.sh        # 환경 설정 로드
├── infrastructure/       # Azure 인프라 연동
│   └── azure/
│       ├── deploy.py    # Bicep 배포 실행
│       ├── shared_infra.py # 공유 인프라 관리
│       ├── rbac.py      # 역할 기반 접근 제어
│       └── logging.py   # JSON 로깅
├── domain/              # 비즈니스 로직
│   ├── school.py        # 학교 정보 처리
│   └── deploy_selector.py # 배포 선택기
├── collector/           # 로그 수집 계층
├── analyzer/            # 분석 계층
├── storage/             # 저장 계층
├── cli/                 # 최종 실행 스크립트
├── tests/               # Bats 테스트
├── deploy/              # 배포 관련 파일 (Docker, Bicep)
└── documentation/       # 모듈 참고 문서
```

## 시작하기

### 필수 조건

- **Azure CLI**: `az` 명령어가 설치되고 로그인되어 있어야 합니다.
- **Bicep**: Azure Bicep 템플릿 빌드 도구 (`az bicep install`)
- **Bash 4+** 또는 **Python 3.11+**
- **Bats-core**: 테스트 실행을 위해 (`brew install bats-core`)

### 설치

```bash
git clone https://github.com/your-org/papertrail.git
cd papertrail
```

환경 변수 설정 (선택):
```bash
cp .env.example .env
# .env 파일을 필요한 값으로 수정
```

### 배포 실행

대화형 배포 (CLI):
```bash
./cli/deploy.py
```

비대화형 모드:
```bash
NON_INTERACTIVE=1 ./cli/deploy.py
```

What‑if 모드 (실제 배포 없이 변경 사항 확인):
```bash
DEPLOY_WHAT_IF=1 ./cli/deploy.py
```

### 테스트 실행

모든 테스트:
```bash
./run-tests.sh
```

특정 테스트 파일:
```bash
bats tests/core/validator.bats
```

## 모듈 상세

각 모듈의 상세한 사용법은 `documentation/` 디렉토리의 문서를 참고하세요.

- [Core 모듈](documentation/core-modules.md) – 공통 유틸리티
- [Infrastructure 모듈](documentation/infrastructure-modules.md) – Azure 연동
- [Domain 모듈](documentation/domain-modules.md) – 비즈니스 로직
- [CLI 모듈](documentation/cli-modules.md) – 실행 스크립트

## Docker 컨테이너 빌드 및 배포

이 프로젝트는 Docker 컨테이너로 패키징할 수 있습니다.

### 빌드

```bash
docker build -t papertrail:latest -f deploy/docker/Dockerfile .
```

### 로컬 실행

```bash
docker run --rm -it papertrail:latest
```

### Azure Container Registry에 푸시

1. ACR 로그인:
   ```bash
   az acr login --name <acr-name>
   ```
2. 이미지 태그 지정:
   ```bash
   docker tag papertrail:latest <acr-name>.azurecr.io/papertrail:latest
   ```
3. 푸시:
   ```bash
   docker push <acr-name>.azurecr.io/papertrail:latest
   ```

## CI/CD

GitHub Actions 워크플로우가 구성되어 있습니다.

- **test.yml**: PR 시 모든 테스트를 자동 실행
- **deploy.yml**: main 브랜치 푸시 시 Azure에 배포 (수동 트리거 가능)

## 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참고하세요.

## 기여 방법

버그 리포트, 기능 제안, 풀 리퀘스트는 GitHub 이슈 트래커를 이용해 주세요.

1. 이슈를 생성하거나 할당받은 이슈를 확인합니다.
2. feature 브랜치를 생성하고 변경 사항을 커밋합니다.
3. 테스트를 실행하여 기존 기능이 깨지지 않았는지 확인합니다.
4. 풀 리퀘스트를 작성하고 리뷰를 요청합니다.

## 연락처

프로젝트 관리자: [이메일 또는 GitHub 프로필 링크]

---

*이 문서는 프로젝트의 최신 상태를 반영하기 위해 지속적으로 업데이트됩니다.*