# SchoolDocs 운영 Runbook (내일 실행용)

이 문서는 내일 바로 실행할 수 있도록 명령어 중심으로 구성했습니다.
원칙은 인프라 + 파이프라인 중심 운영입니다.

## 0) 실행 전 준비

- Azure 로그인 가능한 계정
- 대상 구독 선택 권한
- Azure DevOps 파이프라인 실행 권한
- 로컬에 이 저장소 최신 코드

실행:

az login
az account show -o table

구독 변경이 필요하면:

az account set --subscription "<SUBSCRIPTION_ID_OR_NAME>"
az account show -o table

---

## 1) 기본 변수 (내일 테스트 그룹 생성 시 먼저 수정)

아래 변수는 복붙 후 값만 바꿔서 사용하세요.

export LOCATION="koreacentral"
export SCHOOL_TOKEN="kuhwa"
export SCHOOL_LEVEL="sc"            # kg/es/ms/hs/sc
export ENV_SUFFIX="test"            # 내일 테스트면 test, 운영이면 prod
export DEPLOY_NUM="01"

export RG="rg-${SCHOOL_TOKEN}-${SCHOOL_LEVEL}-${ENV_SUFFIX}-krc${DEPLOY_NUM}"
export APP="app-${SCHOOL_TOKEN}-${SCHOOL_LEVEL}-${ENV_SUFFIX}-krc${DEPLOY_NUM}"
export KV="kv-${SCHOOL_TOKEN}-${SCHOOL_LEVEL}-${ENV_SUFFIX}-krc${DEPLOY_NUM}"
export ACR="acr${SCHOOL_TOKEN}${SCHOOL_LEVEL}${ENV_SUFFIX}krc${DEPLOY_NUM}"

확인:

echo "$RG"
echo "$APP"
echo "$KV"
echo "$ACR"

---

## 2) 1차 배포 (인프라만)

핵심: configureRuntimeSecrets=false

az group create --name "$RG" --location "$LOCATION"

az deployment group create \
  --resource-group "$RG" \
  --template-file infra/main.bicep \
  --parameters \
    location="$LOCATION" \
    schoolNameToken="$SCHOOL_TOKEN" \
    schoolLevel="$SCHOOL_LEVEL" \
    envSuffix="$ENV_SUFFIX" \
    deployNum="$DEPLOY_NUM" \
    enableCosmosFreeTier=false \
    configureRuntimeSecrets=false \
    enableIpRestriction=false \
    allowedCidrs='[]' \
    corsAllowedOrigins='[]'

성공 기준:
- provisioningState: Succeeded

---

## 3) Key Vault 필수 시크릿 입력

먼저 Key Vault 이름 확인:

az keyvault show -g "$RG" -n "$KV" --query name -o tsv

필수 수동 시크릿:
- api-key-ai
- azure-openai-endpoint
- encryption-key-aes
- encryption-key-hmac

선택(SMS):
- api-key-sms
- api-secret-sms
- sms-sender-phone

예시:

az keyvault secret set --vault-name "$KV" --name encryption-key-aes --value "$(openssl rand -hex 32)"
az keyvault secret set --vault-name "$KV" --name encryption-key-hmac --value "$(openssl rand -hex 32)"
az keyvault secret set --vault-name "$KV" --name api-key-ai --value "<YOUR_AI_KEY>"
az keyvault secret set --vault-name "$KV" --name azure-openai-endpoint --value "https://<YOUR_RESOURCE>.openai.azure.com/"

시크릿 목록 확인:

az keyvault secret list --vault-name "$KV" -o table

---

## 4) 2차 배포 (런타임 시크릿 연결 활성화)

핵심: configureRuntimeSecrets=true

az deployment group create \
  --resource-group "$RG" \
  --template-file infra/main.bicep \
  --parameters \
    location="$LOCATION" \
    schoolNameToken="$SCHOOL_TOKEN" \
    schoolLevel="$SCHOOL_LEVEL" \
    envSuffix="$ENV_SUFFIX" \
    deployNum="$DEPLOY_NUM" \
    enableCosmosFreeTier=false \
    configureRuntimeSecrets=true \
    enableIpRestriction=false \
    allowedCidrs='[]' \
    corsAllowedOrigins='[]'

---

## 5) 파이프라인으로 앱 배포

파일 기준:
- azure-pipelines.yml

현재 운영 기준:
- imageRepository는 records-api
- 런타임 env 검증 단계 포함

실행:
- Azure DevOps에서 azure-pipelines.yml 파이프라인 Run
- 필요 시 configureRuntimeSecrets 파라미터 true 확인

---

## 6) 배포 후 최종 검증 (필수 5개)

1. 환경변수 연결 확인 (SecretRef)

az containerapp show -n "$APP" -g "$RG" --query "properties.template.containers[0].env" -o table

2. 최신 리비전 트래픽 확인 (weight 100)

az containerapp revision list -n "$APP" -g "$RG" --query "[].{name:name,weight:properties.trafficWeight,active:properties.active}" -o table

3. 상태 API 확인

FQDN=$(az containerapp show -n "$APP" -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)

curl -X POST "https://${FQDN}/api/status" \
  -H "Content-Type: application/json" \
  -d '{"name":"홍길동","birthdate":"1990-01-01"}'

4. 관리자 API 확인 (로그인 선행)

브라우저 1:
https://${FQDN}/.auth/login/aad

브라우저 2 (같은 세션):
https://${FQDN}/api/manage/pending

5. 시스템 로그 확인

az containerapp logs show -n "$APP" -g "$RG" --type system --tail 100

---

## 7) 자주 발생하는 오류와 즉시 조치

1. Records storage is unavailable
- env가 secretref로 연결되었는지 확인
- WEBSITES_INCLUDE_CLOUD_CERTS=true 확인
- 시스템 로그에서 Key Vault sync 오류 확인

2. Unauthorized (관리자 API)
- 먼저 /.auth/login/aad 로그인
- admins 컨테이너에 관리자 이메일 문서 존재 확인

3. Resource group not found
- 변수 값(SCHOOL_TOKEN, SCHOOL_LEVEL, ENV_SUFFIX, DEPLOY_NUM) 재확인
- 1차 배포 완료 여부 확인

4. 이미지 반영 안 됨
- revision list에서 최신 리비전 weight 확인
- 파이프라인 App stage 성공 여부 확인

---

## 8) 내일 실행 순서 요약 (짧게)

1. 구독 확인
2. 변수 설정
3. 1차 배포
4. Key Vault 시크릿 입력
5. 2차 배포
6. 파이프라인 실행
7. 검증 5개 완료

끝.
