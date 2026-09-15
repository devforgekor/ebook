# School Deploy 초보자용 따라하기 가이드 (Azure 2025 UI 기준)

이 문서는 "처음 하는 사람" 기준입니다.
설계 설명보다 "무엇을, 어디서, 어떤 순서로 클릭/입력"할지만 안내합니다.

목표:
- 1차: 인프라만 배포
- 2차: Key Vault 시크릿 직접 입력
- 3차: 런타임 시크릿 연결 활성화
- 4차: Azure DevOps 파이프라인으로 이미지 배포

추가로, Azure 없이 로컬 API만 먼저 시험할 수도 있습니다.

### 로컬 API만 먼저 실행하는 방법

프로젝트 API 폴더로 이동:

```powershell
cd apps/records-api
```

Node 버전 맞추기 (권장: 22):

```powershell
nvm use
```

`nvm use`가 실패하면:

```powershell
nvm install 22
nvm use 22
```

버전 확인:

```powershell
node -v
```

출력 예시는 `v22.x.x` 형태여야 합니다.

참고:
- Node 22가 권장입니다.
- Node 22 설치 전이라면 `v20.x.x`도 임시로 실행 가능합니다.

처음 한 번 설치:

```powershell
npm install
```

샘플 데이터 넣기:

```powershell
npm run reset:local
npm run seed:local
```

설명:
- 이 프로젝트는 `LOCAL_DATA_STORE=true` 상태에서 Cosmos Emulator 없이 `.localdata` 폴더를 사용합니다.
- `npm run reset:local` 을 먼저 실행하면 이전 테스트 데이터와 blob 파일까지 같이 비워집니다.
- 즉, Azure 없이도 제출/승인/조회 흐름을 로컬에서 테스트할 수 있습니다.

함수 실행:

```powershell
npm run host:start
```

포트 충돌이 있으면:

```powershell
npm run host:start:7072
```

팁:
- 이제 루트 폴더에서도 `npm run host:start` / `npm run host:start:7072`를 그대로 실행할 수 있습니다.
- `npm run host:start`는 사용 가능한 포트를 자동으로 골라서 실행합니다.
- 현재 Node가 미지원 버전이면 실행 스크립트가 Node 22/20 경로를 자동으로 찾아 시도합니다.

---

## 0. 시작 전 체크

필수 준비:
- Azure 계정 로그인 가능
- Azure 구독 1개 이상
- Azure DevOps 프로젝트 접근 가능
- 이 저장소가 로컬에 있음

현재 폴더 구조(중요):
- infra/main.bicep
- azure-pipelines.yml

---

## 1. 작업 폴더 먼저 만들기 (Windows 기준)

중요:
- 특정 PC 경로에 맞추지 않습니다.
- 먼저 본인이 관리하기 쉬운 폴더를 만들고, 그 폴더를 기준으로 진행합니다.

### 1-1. Windows Terminal에서 PowerShell 탭 열기
1. 시작 메뉴에서 `Windows Terminal` 실행
2. 상단 탭 옆 `▼` 클릭 -> `Windows PowerShell` 선택
3. 이미 CMD 탭으로 열렸다면 PowerShell 탭으로 바꾼 뒤 진행
4. 아래 명령어 그대로 입력

관리자 권한 팝업(UAC) 안내:
- `이 앱이 장치에 변경을 가하도록 허용하시겠습니까?` 창이 뜨면 `예` 눌러 진행
- 회사 정책으로 `예`를 누를 수 없으면, IT 관리자에게 Windows Terminal/PowerShell 실행 권한 요청 후 진행

```powershell
New-Item -ItemType Directory -Path C:\school-deploy -Force
Set-Location C:\school-deploy
```

### 1-2. 파일 옮기기
이 폴더 안에 아래 항목이 오도록 옮기세요.

- infra 폴더
- azure-pipelines.yml

예시 (다운로드 폴더에서 옮길 때):

```powershell
Move-Item "C:\Users\$env:USERNAME\Downloads\infra" "C:\school-deploy\infra" -Force
Move-Item "C:\Users\$env:USERNAME\Downloads\azure-pipelines.yml" "C:\school-deploy\azure-pipelines.yml" -Force
```

확인:

```powershell
Get-ChildItem
Get-ChildItem .\infra
```

결과에 `azure-pipelines.yml`, `infra\main.bicep`가 보이면 정상입니다.

### 1-3. VS Code로 폴더 열기

```powershell
code C:\school-deploy
```

`code` 명령이 안 되면 VS Code에서 수동으로 `C:\school-deploy` 폴더를 열어도 됩니다.

---

## 2. Azure 로그인 + 구독 선택

아래를 순서대로 입력하세요.

```powershell
az login
```

브라우저가 열리면 로그인 완료.

로그인 후 구독 목록 확인:

```powershell
az account list -o table
```

쓸 구독 선택:

```powershell
az account set --subscription "구독ID또는구독이름"
```

확인:

```powershell
az account show -o table
```

---

## 3. 리소스 그룹 만들기 (없으면)

운영 예시 리소스 그룹 생성:

```powershell
az group create --name rg-seoul-hs-prod-krc01 --location koreacentral
```

---

## 4. 1차 배포 (인프라만)

중요:
- 이 단계에서는 `configureRuntimeSecrets=false`
- 즉, 앱 시크릿 연결은 아직 안 붙입니다.

PowerShell 기호 안내:
- 명령어 끝의 ` 기호(백틱)는 "다음 줄로 명령어를 이어서 입력"한다는 뜻입니다.
- 복붙 시 백틱이 빠지면 명령이 중간에서 끊겨 실패할 수 있습니다.

명령어 그대로 복붙:

```powershell
az deployment group create `
  --resource-group rg-seoul-hs-prod-krc01 `
  --template-file infra/main.bicep `
  --parameters `
    location=koreacentral `
    schoolNameToken=seoul `
    schoolLevel=hs `
    envSuffix=prod `
    deployNum=01 `
    enableCosmosFreeTier=false `
    configureRuntimeSecrets=false `
    enableIpRestriction=false `
    allowedCidrs='[]' `
    corsAllowedOrigins='[]'
```

성공 기준:
- 출력 JSON 안에 `"provisioningState": "Succeeded"` 보임

---

## 5. Azure Portal에서 Key Vault 시크릿 직접 입력

이 단계는 "반드시 Portal UI"에서 합니다.

### 5-1. Key Vault 열기
1. https://portal.azure.com 접속
2. 상단 검색창에 Key Vault 이름 입력
   - 예: `kv-seoul-hs-prod-krc01`
3. 해당 Key Vault 클릭

### 5-2. Secrets 메뉴 이동
1. 왼쪽 메뉴에서 `Objects` 섹션 찾기
2. `Secrets` 클릭
3. `+ Generate/Import` 클릭

### 5-3. 아래 시크릿 각각 생성
각 시크릿마다:
- Upload options: `Manual`
- Name: 아래 이름 그대로
- Value: 실제 운영 값 입력
- `Create` 클릭

필수 수동 시크릿 목록:
- api-key-ai
- azure-openai-endpoint
- api-key-sms
- api-secret-sms
- sms-sender-phone
- encryption-key-aes
- encryption-key-hmac

참고:
- `connection-string-storage`
- `connection-string-database`
는 템플릿이 자동 생성합니다.

---

## 6. 2차 배포 (시크릿 연결 활성화)

이제 `configureRuntimeSecrets=true` 로 다시 배포합니다.

```powershell
az deployment group create `
  --resource-group rg-seoul-hs-prod-krc01 `
  --template-file infra/main.bicep `
  --parameters `
    location=koreacentral `
    schoolNameToken=seoul `
    schoolLevel=hs `
    envSuffix=prod `
    deployNum=01 `
    enableCosmosFreeTier=false `
    configureRuntimeSecrets=true `
    enableIpRestriction=false `
    allowedCidrs='[]' `
    corsAllowedOrigins='[]'
```

중요:
- 런타임 env는 반드시 `secretref`로 연결되어야 합니다.
- `WEBSITES_INCLUDE_CLOUD_CERTS=true`가 포함되어야 TLS 오류를 줄일 수 있습니다.

---

## 7. Azure DevOps 파이프라인 실행

### 7-1. 파일 확인
- azure-pipelines.yml
- 변수 값이 실제 리소스명과 일치하는지 확인

기본 확인 항목:
- azureServiceConnection
- rgName (`rg-seoul-hs-prod-krc01`)
- appName (`app-seoul-hs-prod-krc01`)
- acrName (`acrseoulhsprodkrc01`)
- imageRepository (`records-api`)

### 7-2. 파이프라인 생성/실행
1. Azure DevOps 프로젝트 진입
2. 왼쪽 `Pipelines` -> `Pipelines`
3. `New pipeline` 클릭
4. 저장소 선택
5. YAML 파일로 `azure-pipelines.yml` 선택
6. `Run` 클릭

---

## 8. 완료 확인

터미널에서 앱 URL 확인:

```powershell
az containerapp show `
  --name app-seoul-hs-prod-krc01 `
  --resource-group rg-seoul-hs-prod-krc01 `
  --query properties.configuration.ingress.fqdn -o tsv
```

출력된 주소로 접속:
- `https://<출력된-fqdn>`

관리자 API 확인 순서:
1. `https://<FQDN>/.auth/login/aad` 먼저 로그인
2. 같은 브라우저 세션에서 `https://<FQDN>/api/manage/pending` 호출

---

## 9. 자주 막히는 오류

### 오류 A: Key Vault secret not found
원인:
- Portal에서 시크릿 이름 오타
해결:
- 섹션 5 목록과 이름 100% 일치 확인

### 오류 B: RBAC 전파 지연
원인:
- 권한은 생성됐지만 즉시 반영 안 됨
해결:
- 5~10분 후 2차 배포 또는 파이프라인 재실행

### 오류 C: 학교명 길이로 리소스명 실패
원인:
- schoolNameToken 길거나 특수문자 포함
해결:
- 영문/숫자, 7자 이내 권장

### 오류 D: Cosmos free tier 충돌
원인:
- 구독당 free tier 1개 제한
해결:
- enableCosmosFreeTier 파라미터 재검토

---

## 10. 운영 전환 시 IP 제한 적용 (지금은 비활성 유지 권장)

개발 단계에서는 그대로 비활성:
- enableIpRestriction=false

운영에서만 활성화 예시:

```powershell
az deployment group create `
  --resource-group rg-seoul-hs-prod-krc01 `
  --template-file infra/main.bicep `
  --parameters `
    schoolNameToken=seoul `
    schoolLevel=hs `
    envSuffix=prod `
    deployNum=01 `
    enableCosmosFreeTier=false `
    configureRuntimeSecrets=true `
    enableIpRestriction=true `
    allowedCidrs='["203.0.113.0/24","198.51.100.10/32"]' `
    corsAllowedOrigins='["https://school.example.kr"]'
```

주의:
- CIDR 틀리면 정상 사용자도 차단됩니다.
- 운영 적용 전 테스트 환경 검증 권장.

---

## 11. 진짜 최소 순서 (요약)

1. PowerShell에서 작업 폴더 만들고 이동 (`C:\school-deploy`)
2. `az login`
3. `az account set --subscription ...`
4. 1차 배포 (`configureRuntimeSecrets=false`)
5. Azure Portal에서 Key Vault 시크릿 입력
6. 2차 배포 (`configureRuntimeSecrets=true`)
7. Azure DevOps 파이프라인 실행
8. 앱 URL 접속 확인
