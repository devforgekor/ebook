#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ============================================================
# Azure 인프라 배포 스크립트 v10.4 (운영 최종판)
# - Health Probe: 현재 설정을 읽어 YAML 병합 후 적용
# - 모든 CLI 명령어 실제 지원 여부 확인 완료
# ============================================================

LOCATION="${LOCATION:-koreacentral}"
DEPLOY_ENV="${DEPLOY_ENV:-}"
RG=""
KV=""
STORAGE=""
COSMOS=""
ACR=""
ENV_NAME=""
APP=""

ALLOW_DEFAULT_SECRETS="${ALLOW_DEFAULT_SECRETS:-false}"

# ----- 모드 선택 -----
MODE="${MODE:-}"
if [ -z "$MODE" ]; then
    prompt_deployment_mode
fi

# 리소스 이름 생성 (모듈화)
# 리소스 이름 생성
suffix="school-${DEPLOY_ENV}-krc"
safe_suffix=$(echo "$suffix" | tr -d '-')

LEGACY_RG="rg-${suffix}"
LEGACY_KV="kv-${suffix}01"
LEGACY_STORAGE="st${safe_suffix}02"
LEGACY_COSMOS="cosmos-${suffix}01"
LEGACY_ACR="acr${safe_suffix}01"
LEGACY_ENV_NAME="env-${suffix}01"
LEGACY_APP="app-${suffix}01"

RG="$LEGACY_RG"
KV="$LEGACY_KV"
STORAGE="$LEGACY_STORAGE"
COSMOS="$LEGACY_COSMOS"
ACR="$LEGACY_ACR"
ENV_NAME="$LEGACY_ENV_NAME"
APP="$LEGACY_APP"

# 프로덕션 모드 필수 환경변수 확인
if [ "$ALLOW_DEFAULT_SECRETS" = "false" ]; then
    echo ""
    echo "프로덕션 환경 필수 환경변수 확인 중..."
    
    missing_vars=""
    
    if [ -z "${AZURE_OPENAI_ENDPOINT:-}" ]; then
        missing_vars="$missing_vars\n  - AZURE_OPENAI_ENDPOINT"
    fi
    if [ -z "${API_KEY_AI:-}" ]; then
        missing_vars="$missing_vars\n  - API_KEY_AI"
    fi
    if [ -z "${API_KEY_SMS:-}" ]; then
        missing_vars="$missing_vars\n  - API_KEY_SMS"
    fi
    if [ -z "${API_SECRET_SMS:-}" ]; then
        missing_vars="$missing_vars\n  - API_SECRET_SMS"
    fi
    if [ -z "${SMS_SENDER_PHONE:-}" ]; then
        missing_vars="$missing_vars\n  - SMS_SENDER_PHONE"
    fi
    
    if [ -n "$missing_vars" ]; then
        echo ""
        echo "오류: 다음 환경변수가 설정되지 않았습니다."
        echo -e "$missing_vars"
        echo ""
        echo "사용법:"
        echo "  export AZURE_OPENAI_ENDPOINT=\"https://...openai.azure.com/\""
        echo "  export API_KEY_AI=\"your-api-key\""
        echo "  export API_KEY_SMS=\"your-sms-key\""
        echo "  export API_SECRET_SMS=\"your-sms-secret\""
        echo "  export SMS_SENDER_PHONE=\"01012345678\""
        echo "  ./$0"
        exit 1
    fi
    
    echo "프로덕션 환경 필수값 확인 완료"
fi

echo ""
echo ">>> 선택된 모드: MODE=$MODE, DEPLOY_ENV=$DEPLOY_ENV, ALLOW_DEFAULT_SECRETS=$ALLOW_DEFAULT_SECRETS"
echo ">>> 배포 대상: RG=$RG, KV=$KV, STORAGE=$STORAGE, COSMOS=$COSMOS, ACR=$ACR, ENV=$ENV_NAME, APP=$APP, LOCATION=$LOCATION"
echo ""

LIFECYCLE_TMP=""
APP_CONFIG_TMP=""
trap 'rm -f "$LIFECYCLE_TMP" "$APP_CONFIG_TMP"' EXIT

# ----- 초기화 모드 -----
if [ "$MODE" = "refresh" ]; then
    echo ">>> 리소스 그룹 삭제 중..."
    az group delete --name "$RG" --yes 2>/dev/null || true

    echo ">>> 리소스 그룹 삭제 완료 대기 (최대 3분)..."
    for i in {1..36}; do
        az group show --name "$RG" &>/dev/null || break
        sleep 5
    done
    spinner ">>> 삭제 안정화 추가 대기" 10

    echo ">>> Storage Account purge 중..."
    SUB_ID=$(az account show --query id -o tsv)
    az rest --method post \
        --url "https://management.azure.com/subscriptions/$SUB_ID/providers/Microsoft.Storage/locations/$LOCATION/deletedAccounts/$STORAGE/purge?api-version=2022-09-01" \
        --headers "Content-Type=application/json" 2>/dev/null || true

    echo ">>> Key Vault purge 중..."
    az keyvault purge --name "$KV" --location "$LOCATION" 2>/dev/null || true
    spinner ">>> Purge 완료 대기 중" 15
fi

# ----- 1. 리소스 그룹 -----
az group create --name "$RG" --location "$LOCATION" --output none

# ----- 2. Key Vault -----
echo ">>> 2. Key Vault 상태 확인 중: $KV"

DELETED_VAULT=$(az keyvault list-deleted --query "[?name=='$KV'].name" -o tsv 2>/dev/null || echo "")
if [ -n "$DELETED_VAULT" ]; then
    echo "[오류] Key Vault '$KV' 가 Soft-Delete 상태입니다."
    echo "  az keyvault purge --name $KV --location $LOCATION"
    exit 1
fi

if ! az keyvault show --name "$KV" -g "$RG" &>/dev/null; then
    echo "Key Vault 생성 중..."
    az keyvault create --name "$KV" -g "$RG" -l "$LOCATION" --sku standard \
      --enable-rbac-authorization false --output none
    spinner ">>> Key Vault DNS 전파 대기 중" 15
else
    echo "Key Vault가 존재합니다."
    spinner ">>> Key Vault 연결 확인 중" 2
fi

EXISTING_AES=$(az keyvault secret show --vault-name "$KV" --name ENCRYPTION-KEY-AES --query value -o tsv 2>/dev/null || echo "")
if [ -z "$EXISTING_AES" ]; then
    az keyvault secret set --vault-name "$KV" --name ENCRYPTION-KEY-AES --value "$(openssl rand -hex 32)" --output none
fi

EXISTING_HMAC=$(az keyvault secret show --vault-name "$KV" --name ENCRYPTION-KEY-HMAC --query value -o tsv 2>/dev/null || echo "")
if [ -z "$EXISTING_HMAC" ]; then
    az keyvault secret set --vault-name "$KV" --name ENCRYPTION-KEY-HMAC --value "$(openssl rand -hex 32)" --output none
fi

# ----- 3. Storage Account -----
if ! az storage account show --name "$STORAGE" -g "$RG" &>/dev/null; then
    echo "Storage Account 생성 중..."
    az storage account create \
        --name "$STORAGE" \
        --resource-group "$RG" \
        --location "$LOCATION" \
        --sku Standard_LRS \
        --kind StorageV2 \
        --https-only true \
        --allow-blob-public-access false \
        --min-tls-version TLS1_2 \
        --output none
else
    echo "Storage Account가 이미 존재합니다."
fi

key=$(az storage account keys list --account-name "$STORAGE" --resource-group "$RG" --query "[0].value" -o tsv)
az storage container create --name "webps" --account-name "$STORAGE" --account-key "$key" --output none 2>/dev/null || true

az storage account blob-service-properties update \
    --account-name "$STORAGE" \
    --resource-group "$RG" \
    --enable-delete-retention true \
    --delete-retention-days 30 \
    --output none

LIFECYCLE_TMP=$(mktemp)
cat > "$LIFECYCLE_TMP" <<'EOF'
{
  "rules": [{
    "enabled": true, "name": "archive-policy", "type": "Lifecycle",
    "definition": {
      "actions": {
        "baseBlob": {
          "tierToCool": {"daysAfterModificationGreaterThan": 1095},
          "delete": {"daysAfterModificationGreaterThan": 3285}
        }
      },
      "filters": {"blobTypes": ["blockBlob"], "prefixMatch": ["webps/"]}
    }
  }]
}
EOF

if az storage account management-policy show \
    --account-name "$STORAGE" \
    --resource-group "$RG" &>/dev/null; then
    echo "[INFO] 기존 수명 주기 정책 업데이트" >&2
    az storage account management-policy update \
        --account-name "$STORAGE" \
        --resource-group "$RG" \
        --policy "@$LIFECYCLE_TMP" \
        --output none
else
    echo "[INFO] 수명 주기 정책 생성" >&2
    az storage account management-policy create \
        --account-name "$STORAGE" \
        --resource-group "$RG" \
        --policy "@$LIFECYCLE_TMP" \
        --output none
fi
rm -f "$LIFECYCLE_TMP"

# ----- 4. Cosmos DB -----
if ! az cosmosdb show --name "$COSMOS" --resource-group "$RG" &>/dev/null; then
    echo "[INFO] Cosmos DB 계정($COSMOS) 생성 (약 5~10분)" >&2
    free_tier_option="--enable-free-tier true"
    if ! az cosmosdb create \
        --name "$COSMOS" \
        --resource-group "$RG" \
        --locations regionName="$LOCATION" \
        --default-consistency-level Session \
        $free_tier_option \
        --output none; then
        echo "[ERROR] Cosmos DB 생성 실패" >&2
        echo "힌트: --enable-free-tier true 는 구독당 1개만 허용됩니다." >&2
        echo "이미 Free Tier를 사용 중이면 해당 옵션을 제거하거나 기존 계정을 사용하세요." >&2
        exit 1
    fi
else
    echo "[INFO] Cosmos DB 계정($COSMOS)이 이미 존재합니다." >&2
fi

if ! az cosmosdb sql database show \
    --account-name "$COSMOS" \
    --resource-group "$RG" \
    --name "CertificateSystem" &>/dev/null; then
    echo "[INFO] SQL 데이터베이스(CertificateSystem) 생성" >&2
    az cosmosdb sql database create \
        --account-name "$COSMOS" \
        --resource-group "$RG" \
        --name "CertificateSystem" \
        --throughput 400 \
        --output none
else
    echo "[INFO] SQL 데이터베이스(CertificateSystem)이 이미 존재합니다." >&2
fi

if ! az cosmosdb sql container show \
    --account-name "$COSMOS" \
    --resource-group "$RG" \
    --database-name "CertificateSystem" \
    --name "registry" &>/dev/null; then
    echo "[INFO] SQL 컨테이너(registry) 생성" >&2
    az cosmosdb sql container create \
        --account-name "$COSMOS" \
        --resource-group "$RG" \
        --database-name "CertificateSystem" \
        --name "registry" \
        --partition-key-path "/cohortId" \
        --throughput 400 \
        --output none
else
    echo "[INFO] SQL 컨테이너(registry)이 이미 존재합니다." >&2
fi

if ! az cosmosdb sql container show \
    --account-name "$COSMOS" \
    --resource-group "$RG" \
    --database-name "CertificateSystem" \
    --name "admins" &>/dev/null; then
    echo "[INFO] SQL 컨테이너(admins) 생성" >&2
    az cosmosdb sql container create \
        --account-name "$COSMOS" \
        --resource-group "$RG" \
        --database-name "CertificateSystem" \
        --name "admins" \
        --partition-key-path "/email" \
        --throughput 400 \
        --output none
else
    echo "[INFO] SQL 컨테이너(admins)이 이미 존재합니다." >&2
fi

if ! az cosmosdb sql container show \
    --account-name "$COSMOS" \
    --resource-group "$RG" \
    --database-name "CertificateSystem" \
    --name "ai_limits" &>/dev/null; then
    echo "[INFO] SQL 컨테이너(ai_limits) 생성" >&2
    az cosmosdb sql container create \
        --account-name "$COSMOS" \
        --resource-group "$RG" \
        --database-name "CertificateSystem" \
        --name "ai_limits" \
        --partition-key-path "/id" \
        --throughput 400 \
        --output none
else
    echo "[INFO] SQL 컨테이너(ai_limits)이 이미 존재합니다." >&2
fi

az cosmosdb sql container update -a "$COSMOS" -g "$RG" -d CertificateSystem -n ai_limits --ttl -1 --output none
az cosmosdb sql container update -a "$COSMOS" -g "$RG" -d CertificateSystem -n registry \
  --idx '{"indexingMode":"consistent","automatic":true,"includedPaths":[{"path":"/*"}],"excludedPaths":[{"path":"/nameEncrypted/*"},{"path":"/webpUrl/*"},{"path":"/\"_etag\"/?"}]}' --output none

# ----- 5. ACR -----
if ! az acr show --name "$ACR" --resource-group "$RG" &>/dev/null; then
    echo "[INFO] ACR($ACR) 생성" >&2
    az acr create \
        --name "$ACR" \
        --resource-group "$RG" \
        --sku Basic \
        --location "$LOCATION" \
        --admin-enabled false \
        --output none
else
    echo "[INFO] ACR($ACR)이 이미 존재합니다." >&2
fi

# ----- 6. Container Apps Environment -----
az provider register -n Microsoft.OperationalInsights --wait --output none
if ! az containerapp env show --name "$ENV_NAME" --resource-group "$RG" &>/dev/null; then
    echo "[INFO] Container Apps Environment($ENV_NAME) 생성" >&2
    az containerapp env create \
        --name "$ENV_NAME" \
        --resource-group "$RG" \
        --location "$LOCATION" \
        --output none
else
    echo "[INFO] Container Apps Environment($ENV_NAME)이 이미 존재합니다." >&2
fi

# ----- 7. Container App -----
if ! az containerapp show --name "$APP" --resource-group "$RG" &>/dev/null; then
    echo "[INFO] Container App($APP) 생성" >&2
    az containerapp create \
        --name "$APP" \
        --resource-group "$RG" \
        --environment "$ENV_NAME" \
        --image "mcr.microsoft.com/azuredocs/containerapps-helloworld:latest" \
        --target-port 80 \
        --ingress external \
        --min-replicas 0 \
        --max-replicas 2 \
        --system-assigned \
        --output none
else
    echo "[INFO] Container App($APP)이 이미 존재합니다." >&2
fi

# ----- 8. 역할 할당 -----
echo ">>> Managed Identity 준비 확인 중..."
for i in {1..3}; do
    PRINCIPAL_ID=$(az containerapp show --name "$APP" -g "$RG" --query identity.principalId -o tsv 2>/dev/null || echo "")
    if [ -n "$PRINCIPAL_ID" ] && [ "$PRINCIPAL_ID" != "null" ]; then
        echo "Managed Identity: $PRINCIPAL_ID"
        break
    fi
    echo "Principal ID 아직 준비되지 않음. 재시도 $i/3..."
    sleep 10
done

if [ -z "$PRINCIPAL_ID" ] || [ "$PRINCIPAL_ID" = "null" ]; then
    echo "오류: Container App의 Managed Identity를 가져올 수 없습니다."
    exit 1
fi

ACR_ID=$(az acr show --name "$ACR" -g "$RG" --query id -o tsv)
STORAGE_ID=$(az storage account show --name "$STORAGE" -g "$RG" --query id -o tsv)

ACR_ROLE_EXISTS=$(az role assignment list --assignee "$PRINCIPAL_ID" --role AcrPull --scope "$ACR_ID" --query "length(@)" -o tsv 2>/dev/null || echo "0")
if [ "$ACR_ROLE_EXISTS" -eq 0 ]; then
  if ! az role assignment create --assignee "$PRINCIPAL_ID" --role AcrPull --scope "$ACR_ID" --output none; then
    echo "오류: AcrPull 역할 할당에 실패했습니다. (전파 지연/권한 문제 가능)"
    exit 1
  fi
fi

STORAGE_ROLE_EXISTS=$(az role assignment list --assignee "$PRINCIPAL_ID" --role "Storage Blob Data Contributor" --scope "$STORAGE_ID" --query "length(@)" -o tsv 2>/dev/null || echo "0")
if [ "$STORAGE_ROLE_EXISTS" -eq 0 ]; then
  if ! az role assignment create --assignee "$PRINCIPAL_ID" --role "Storage Blob Data Contributor" --scope "$STORAGE_ID" --output none; then
    echo "오류: Storage Blob Data Contributor 역할 할당에 실패했습니다. (전파 지연/권한 문제 가능)"
    exit 1
  fi
fi

KV_POLICY_EXISTS=$(az keyvault show --name "$KV" -g "$RG" --query "properties.accessPolicies[?objectId=='$PRINCIPAL_ID'].objectId" -o tsv 2>/dev/null || echo "")
if [ -z "$KV_POLICY_EXISTS" ]; then
  if ! az keyvault set-policy --name "$KV" -g "$RG" --object-id "$PRINCIPAL_ID" --secret-permissions get list --output none; then
    echo "오류: Key Vault 정책 설정에 실패했습니다. (전파 지연/권한 문제 가능)"
    exit 1
  fi
fi

sleep 30

# ----- 9. Key Vault Secrets -----
echo ">>> Key Vault Secrets 확인 중..."

STORAGE_CONN=$(az storage account show-connection-string --name "$STORAGE" -g "$RG" -o tsv)
az keyvault secret set --vault-name "$KV" --name "CONNECTION-STRING-STORAGE" --value "$STORAGE_CONN" --output none

COSMOS_CONN=$(az cosmosdb keys list --name "$COSMOS" -g "$RG" --type connection-strings --query "connectionStrings[0].connectionString" -o tsv)
az keyvault secret set --vault-name "$KV" --name "CONNECTION-STRING-DATABASE" --value "$COSMOS_CONN" --output none

set_secret_if_missing() {
    local secret_name=$1
    local default_value=$2
    local existing=$(az keyvault secret show --vault-name "$KV" --name "$secret_name" --query value -o tsv 2>/dev/null || echo "")
    if [ -z "$existing" ]; then
        if [[ "$default_value" == "CHANGE_ME" || "$default_value" == "01012345678" || "$default_value" == "https://your-openai.openai.azure.com/" ]]; then
            if [ "$ALLOW_DEFAULT_SECRETS" != "true" ]; then
                echo "오류: 비밀 '$secret_name' 에 기본값(플레이스홀더)이 설정되었습니다."
                echo "운영 환경에 맞는 실제 값으로 변경하거나 ALLOW_DEFAULT_SECRETS=true 로 실행하세요."
                exit 1
            else
                echo "경고: 비밀 '$secret_name' 이 기본값으로 생성되었습니다."
            fi
        fi
        az keyvault secret set --vault-name "$KV" --name "$secret_name" --value "$default_value" --output none
        echo "  - $secret_name 생성"
    else
        echo "  - $secret_name (기존 값 유지)"
    fi
}

set_secret_if_missing "AZURE-OPENAI-ENDPOINT" "${AZURE_OPENAI_ENDPOINT:-https://your-openai.openai.azure.com/}"
set_secret_if_missing "SMS-SENDER-PHONE" "${SMS_SENDER_PHONE:-01012345678}"
set_secret_if_missing "API-KEY-AI" "${API_KEY_AI:-CHANGE_ME}"
set_secret_if_missing "API-KEY-SMS" "${API_KEY_SMS:-CHANGE_ME}"
set_secret_if_missing "API-SECRET-SMS" "${API_SECRET_SMS:-CHANGE_ME}"

# ----- 10. YAML 일괄 적용 전 권한 전파 대기 -----
sleep 30
KV_URI="https://${KV}.vault.azure.net/secrets"

# ----- 11. 환경변수 + Health Probe + Scale (YAML 일괄 적용) -----
echo ">>> 환경변수·헬스 프로브·스케일 YAML 적용 중..."

# 현재 앱 설정 조회 (값이 null이면 Azure CLI가 빈 문자열 반환 → :- 기본값으로 보호)
CURRENT_IMAGE=$(az containerapp show --name "$APP" -g "$RG" \
  --query "properties.template.containers[0].image" -o tsv 2>/dev/null || true)
CURRENT_IMAGE=${CURRENT_IMAGE:-mcr.microsoft.com/azuredocs/containerapps-helloworld:latest}

CONTAINER_NAME=$(az containerapp show --name "$APP" -g "$RG" \
  --query "properties.template.containers[0].name" -o tsv 2>/dev/null || true)
CONTAINER_NAME=${CONTAINER_NAME:-$APP}

MIN_REPLICAS=$(az containerapp show --name "$APP" -g "$RG" \
  --query "properties.template.scale.minReplicas" -o tsv 2>/dev/null || true)
MIN_REPLICAS=${MIN_REPLICAS:-0}

MAX_REPLICAS=$(az containerapp show --name "$APP" -g "$RG" \
  --query "properties.template.scale.maxReplicas" -o tsv 2>/dev/null || true)
MAX_REPLICAS=${MAX_REPLICAS:-2}

INGRESS_EXTERNAL=$(az containerapp show --name "$APP" -g "$RG" \
  --query "properties.configuration.ingress.external" -o tsv 2>/dev/null || true)
INGRESS_EXTERNAL=${INGRESS_EXTERNAL:-true}

TARGET_PORT=$(az containerapp show --name "$APP" -g "$RG" \
  --query "properties.configuration.ingress.targetPort" -o tsv 2>/dev/null || true)
TARGET_PORT=${TARGET_PORT:-80}

INGRESS_FQDN=$(az containerapp show --name "$APP" -g "$RG" \
  --query "properties.configuration.ingress.fqdn" -o tsv 2>/dev/null || true)

APP_CONFIG_TMP=$(mktemp)
cat > "$APP_CONFIG_TMP" <<EOF
location: $LOCATION
properties:
  configuration:
    ingress:
      external: ${INGRESS_EXTERNAL}
      targetPort: ${TARGET_PORT}
    secrets:
      - name: encryption-key-aes
        keyVaultUrl: ${KV_URI}/ENCRYPTION-KEY-AES
        identity: system
      - name: encryption-key-hmac
        keyVaultUrl: ${KV_URI}/ENCRYPTION-KEY-HMAC
        identity: system
      - name: conn-db
        keyVaultUrl: ${KV_URI}/CONNECTION-STRING-DATABASE
        identity: system
      - name: conn-storage
        keyVaultUrl: ${KV_URI}/CONNECTION-STRING-STORAGE
        identity: system
      - name: api-key-ai
        keyVaultUrl: ${KV_URI}/API-KEY-AI
        identity: system
      - name: api-key-sms
        keyVaultUrl: ${KV_URI}/API-KEY-SMS
        identity: system
      - name: api-secret-sms
        keyVaultUrl: ${KV_URI}/API-SECRET-SMS
        identity: system
      - name: sms-sender-phone
        keyVaultUrl: ${KV_URI}/SMS-SENDER-PHONE
        identity: system
      - name: openai-endpoint
        keyVaultUrl: ${KV_URI}/AZURE-OPENAI-ENDPOINT
        identity: system
  template:
    containers:
      - name: ${CONTAINER_NAME}
        image: ${CURRENT_IMAGE}
        env:
          - name: ENCRYPTION_KEY_AES
            secretRef: encryption-key-aes
          - name: ENCRYPTION_KEY_HMAC
            secretRef: encryption-key-hmac
          - name: DATABASE_CONNECTION_STRING
            secretRef: conn-db
          - name: STORAGE_CONNECTION_STRING
            secretRef: conn-storage
          - name: AI_SERVICE_KEY
            secretRef: api-key-ai
          - name: AZURE_OPENAI_ENDPOINT
            secretRef: openai-endpoint
          - name: SMS_API_KEY
            secretRef: api-key-sms
          - name: SMS_API_SECRET
            secretRef: api-secret-sms
          - name: SMS_SENDER_PHONE
            secretRef: sms-sender-phone
        probes:
          - type: Liveness
            httpGet:
              path: /
              port: ${TARGET_PORT}
            initialDelaySeconds: 30
            periodSeconds: 10
          - type: Readiness
            httpGet:
              path: /
              port: ${TARGET_PORT}
            initialDelaySeconds: 5
            periodSeconds: 5
    scale:
      minReplicas: ${MIN_REPLICAS}
      maxReplicas: ${MAX_REPLICAS}
      rules:
        - name: http-rule
          http:
            metadata:
              concurrentRequests: "50"
EOF

az containerapp update --name "$APP" -g "$RG" --yaml "$APP_CONFIG_TMP" --output none

echo ">>> 리비전 준비 대기 중..."
max_wait=120
waited=0
while [ $waited -lt $max_wait ]; do
    STATUS=$(az containerapp revision list -g "$RG" -n "$APP" \
        --query "sort_by([*], &properties.createdTime)[-1].properties.provisioningState" -o tsv 2>/dev/null || echo "Unknown")
    if [ "$STATUS" = "Provisioned" ]; then
        echo "리비전 준비 완료"
        break
    elif [ "$STATUS" = "Failed" ]; then
        echo "오류: 리비전 프로비저닝 실패"
        exit 1
    fi
    sleep 5
    waited=$((waited + 5))
done
if [ $waited -ge $max_wait ]; then
    echo "오류: 리비전 대기 시간 초과"
    exit 1
fi

# ----- 12. 완료 -----
FQDN=${INGRESS_FQDN:-$(az containerapp show --name "$APP" -g "$RG" --query "properties.configuration.ingress.fqdn" -o tsv)}
echo ""
echo "============================================================"
echo "배포 완료: https://${FQDN}"
echo "============================================================"
echo ""
echo "[수동 설정 필요]"
echo "1. Cron Scale Rule: Portal > Container App > Scale > Add cron rule"
echo "2. 실제 앱 배포 후 probe 경로 /health 로 변경"
echo "============================================================"
