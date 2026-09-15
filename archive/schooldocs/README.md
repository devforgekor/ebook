# School Deploy 관리자 런북 (개발 -> 운영 전환)

이 문서는 관리자가 처음 프로젝트를 받아서 Azure 인프라를 만들고, 앱을 배포하고, 운영 설정을 적용하는 전체 절차를 안내합니다.

초보자라면 먼저 아래 문서부터 진행하세요.

- BEGINNER_README.md (완전 초보자용, 터미널 명령어 그대로 따라하기)

## 0. 로컬 API 빠른 시작

Azure 배포 전에 로컬 API만 먼저 확인할 수 있습니다.

위치:
- apps/records-api

핵심 포인트:
- local.settings.json 에서 LOCAL_DATA_STORE=true 이면 Cosmos Emulator 없이 .localdata 를 사용합니다.
- npm run reset:local 명령으로 .localdata 와 Azurite blob 을 함께 초기화할 수 있습니다.
- npm run seed:local 명령으로 항상 같은 샘플 데이터를 다시 넣을 수 있습니다.

예시:

cd apps/records-api
nvm use || nvm install 22
node -v
npm install
npm run reset:local
npm run seed:local
npm run host:start

참고:
- Node 22가 권장입니다.
- Node 22를 바로 준비할 수 없으면 Node 20도 임시로 실행 가능합니다.
- `npm run host:start`는 7072 -> 7071 -> 7073 순서로 사용 가능한 포트를 자동 선택합니다.
- 포트를 고정하고 싶으면 `npm run host:start:7072`를 사용하세요.
- `npm run host:start*`는 현재 Node가 25처럼 미지원 버전이면 Homebrew Node 22/20으로 자동 전환을 시도합니다.

루트 폴더에서도 아래처럼 바로 실행할 수 있습니다:
- `npm run reset:local`
- `npm run seed:local`
- `npm run host:start`
- `npm run host:start:7072`

주요 확인 API 예시:
- POST /api/status
- GET /api/manage/pending
- POST /api/manage/approve
- GET /api/view/{cohortId}/{personId}

## 1. 현재 배포 구조

- 인프라 코드: infra/main.bicep
- 앱 배포 파이프라인: azure-pipelines.yml
- 레거시 스크립트(참고용): legacy 폴더

원칙:
- 인프라 생성/변경은 Bicep이 담당
- 앱 이미지 배포는 Azure DevOps 파이프라인이 담당
- 시크릿 실제 값은 Key Vault에서만 관리

## 2. 사전 준비

필수 권한:
- Azure 구독에 리소스 그룹 배포 권한
- 역할 할당 생성 권한 (roleAssignments)
- Azure DevOps 프로젝트 관리자 또는 파이프라인 편집 권한

필수 도구:
- Azure CLI
- Bicep (Azure CLI에 포함)

로그인:
1. az login
2. az account set --subscription <SUBSCRIPTION_ID_OR_NAME>

## 2-1. 기본 운영 값 (현재 리포지토리 기준)

아래 값을 기본값으로 사용합니다.

- location: koreacentral
- envSuffix: prod
- deployNum: 01
- rgName: rg-seoul-hs-prod-krc01
- appName: app-seoul-hs-prod-krc01
- acrName: acrseoulhsprodkrc01

Azure DevOps 파이프라인 변수도 동일한 값으로 맞춰야 합니다.

## 2-2. 학생 계정 제약과 현재 설계 이유

이 프로젝트는 Azure for Students 구독 제약을 반영해 배포 로직을 설계했습니다.

제약:
- 구독/리전별 Container Apps Environment 한도 때문에 같은 리전에서 테스트 환경을 여러 개 유지하기 어렵습니다.
- 학생 계정에서는 사용 가능한 리전이 제한되어 운영과 테스트를 단순한 규칙으로 관리해야 합니다.

현재 적용 규칙:
- `infra/deploy-interactive.sh`에서 먼저 `test/prod`를 선택합니다.
- `test`는 허용된 테스트 리전(centralindia/japaneast/eastasia)에서 선택합니다.
- 배포 실패 시 `cin → jpe → eas → krc` 순서로 자동 대체합니다.
- 대체 리전은 what-if 성공 후에만 사용자 재승인을 요청합니다.
- `prod`는 반드시 `koreacentral`을 사용합니다.
- `prod` 배포 직전에는 같은 학교/레벨의 `test` 리소스 그룹을 확인하고, 필요하면 삭제를 유도합니다.
- 삭제 대상은 `rg-{school}-{level}-test-{regionCode}{NN}` 형식을 기준으로 잡습니다.
- soft-delete 리소스는 purge를 자동 강제하지 않습니다.
- 이름 충돌은 `deployNum`과 리전 코드 분리로 회피합니다.

이유:
- 테스트 리소스 누적 비용을 줄이기 위해서입니다.
- 리전 정보를 이름에 넣어 추적성과 충돌 회피를 높이기 위해서입니다.

## 3. 리소스 이름 규칙

main.bicep 파라미터:
- schoolNameToken (예: seoul)
- schoolLevel (es, ms, hs, sc, kg)
- envSuffix (test 또는 prod)
- deployNum (두 자리, 예: 01)
- regionCode (리전 약자, 예: krc/cin/eas/jpe)

주의:
- Storage, Key Vault 이름 제한 때문에 schoolNameToken 길이는 짧게 유지
- 이전 경험상 7자 이내 권장

## 4. 최초 배포는 반드시 2단계

핵심 이유:
- RBAC 전파 지연
- Key Vault 수동 시크릿 입력 타이밍

### 4-1) 1차 배포 (인프라만)

아래는 예시입니다.

az deployment group create \
  --resource-group rg-seoul-hs-prod-krc01 \
  --template-file infra/main.bicep \
  --parameters \
    location=koreacentral \
    schoolNameToken=seoul \
    schoolLevel=hs \
    envSuffix=prod \
    deployNum=01 \
    enableCosmosFreeTier=false \
    configureRuntimeSecrets=false \
    enableIpRestriction=false \
    allowedCidrs='[]' \
    corsAllowedOrigins='[]'

결과:
- 리소스(ACR, Storage, Cosmos, Key Vault, Container Apps Env, App 등) 생성
- 자동 생성 가능한 Key Vault 시크릿 일부 생성
- 앱 런타임 시크릿 연결은 아직 비활성

### 4-2) Key Vault 수동 입력

Azure Portal -> 생성된 Key Vault -> Secrets 에 아래 시크릿 실제 값 입력:
- api-key-ai
- azure-openai-endpoint
- api-key-sms
- api-secret-sms
- sms-sender-phone
- encryption-key-aes
- encryption-key-hmac

참고:
- connection-string-storage
- connection-string-database
는 템플릿에서 자동 생성됨

### 4-3) 2차 배포 (런타임 시크릿 연결 활성화)

az deployment group create \
  --resource-group rg-seoul-hs-prod-krc01 \
  --template-file infra/main.bicep \
  --parameters \
    location=koreacentral \
    schoolNameToken=seoul \
    schoolLevel=hs \
    envSuffix=prod \
    deployNum=01 \
    enableCosmosFreeTier=false \
    configureRuntimeSecrets=true \
    enableIpRestriction=false \
    allowedCidrs='[]' \
    corsAllowedOrigins='[]'

## 5. Azure DevOps 파이프라인 설정

파일: azure-pipelines.yml

중요 전제:
- 파이프라인은 기존 RG를 대상으로 인프라를 갱신합니다.
- 최초 RG 생성(처음 배포)은 `infra/deploy-interactive.sh`로 먼저 수행해야 합니다.

필수 변수 확인:
- azureServiceConnection
- rgName
- location
- schoolNameToken
- schoolLevel
- envSuffix
- deployNum
- appName
- acrName

권장 운영 방식:
1. 인프라 변경 시: Infra 스테이지 실행
2. 앱 코드 변경 시: App 스테이지로 이미지 빌드/배포

파이프라인은 다음을 수행:
- az acr build 로 이미지 빌드 및 푸시
- az containerapp update 로 이미지 교체
- 리비전 상태를 60초 간격, 최대 10회 재시도 확인

운영 표준(반드시 유지):
- 이미지 저장소 이름은 `records-api`로 통일
- Key Vault 참조는 `az containerapp secret set` 단계에서만 `keyvaultref` 사용
- 런타임 env 주입은 반드시 `secretref` 형식 사용
- `WEBSITES_INCLUDE_CLOUD_CERTS=true`를 런타임 env에 포함

## 6. 학교 IP 제한 (개발에서는 비활성 유지)

현재 템플릿 파라미터:
- enableIpRestriction (기본 false)
- allowedCidrs (기본 [])
- corsAllowedOrigins (기본 [])

운영에서만 활성화 예시:

az deployment group create \
  --resource-group rg-seoul-hs-prod-krc01 \
  --template-file infra/main.bicep \
  --parameters \
    schoolNameToken=seoul \
    schoolLevel=hs \
    envSuffix=prod \
    deployNum=01 \
    enableCosmosFreeTier=false \
    configureRuntimeSecrets=true \
    enableIpRestriction=true \
    allowedCidrs='["203.0.113.0/24","198.51.100.10/32"]' \
    corsAllowedOrigins='["https://school.example.kr"]'

주의:
- CIDR 오입력 시 정상 사용자도 차단됨
- 운영 전환 전 테스트 환경에서 먼저 검증 권장

## 7. 장애 대응 체크리스트

1. 배포 실패 시
- az deployment group create 오류 메시지 확인
- RBAC 전파 지연이면 5~10분 후 재시도

2. 앱 기동 실패 시
- az containerapp revision list 로 provisioningState 확인
- Key Vault 시크릿 이름 오타/누락 여부 확인
- ACR 이미지 태그 존재 여부 확인
- `WEBSITES_INCLUDE_CLOUD_CERTS=true` 누락 여부 확인
- env에 DB/Storage 연결이 `secretref`로 연결되었는지 확인

3. Key Vault 접근 실패 시
- User-Assigned Identity 역할 확인
- Key Vault RBAC 역할(Secrets User) 확인

## 8. 운영 변경 원칙

- 인프라/보안/런타임 설정: main.bicep에서 관리
- 애플리케이션 버전: azure-pipelines.yml에서 관리
- 비밀값 교체: Key Vault에서 값 버전 교체

배포 후 최종 검증(권장 5종):
1. env SecretRef 확인: `az containerapp show -n <APP> -g <RG> --query "properties.template.containers[0].env" -o table`
2. 최신 revision weight 100 확인: `az containerapp revision list -n <APP> -g <RG> --query "[].{name:name,weight:properties.trafficWeight,active:properties.active}" -o table`
3. status API 확인: `curl -X POST https://<FQDN>/api/status -H "Content-Type: application/json" -d '{"name":"홍길동","birthdate":"1990-01-01"}'`
4. 관리자 로그인 후 pending 확인: `https://<FQDN>/.auth/login/aad` 후 `https://<FQDN>/api/manage/pending`
5. 시스템 로그 점검: `az containerapp logs show -n <APP> -g <RG> --type system --tail 100`

## 9. 빠른 실행 순서 요약

1. Azure 로그인 + 구독 선택
2. 1차 배포 (configureRuntimeSecrets=false)
3. Key Vault 시크릿 수동 입력
4. 2차 배포 (configureRuntimeSecrets=true)
5. 파이프라인으로 이미지 배포
6. 필요 시 운영에서만 IP 제한 활성화

## 10. 학교별 실행 예시

### 예시 A) 서울 고등학교 운영(prod)

az deployment group create \
  --resource-group rg-seoul-hs-prod-krc01 \
  --template-file infra/main.bicep \
  --parameters \
    location=koreacentral \
    schoolNameToken=seoul \
    schoolLevel=hs \
    envSuffix=prod \
    deployNum=01 \
    enableCosmosFreeTier=false \
    configureRuntimeSecrets=false \
    enableIpRestriction=false \
    allowedCidrs='[]' \
    corsAllowedOrigins='[]'

### 예시 B) 부산 중학교 테스트(test)

az deployment group create \
  --resource-group rg-busan-ms-test-krc \
  --template-file infra/main.bicep \
  --parameters \
    location=koreacentral \
    schoolNameToken=busan \
    schoolLevel=ms \
    envSuffix=test \
    deployNum=01 \
    enableCosmosFreeTier=false \
    configureRuntimeSecrets=false \
    enableIpRestriction=false \
    allowedCidrs='[]' \
    corsAllowedOrigins='[]'

참고:
- test에서도 실제 Secret 연결을 쓸 경우 2차 배포에서 configureRuntimeSecrets=true로 다시 실행
- schoolNameToken은 길이 제한 때문에 7자 이내 권장
