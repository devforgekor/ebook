#!/bin/bash
set -euo pipefail

# ============================================================
# Azure 인프라 배포 스크립트 (학생용 무료 베네핏 최적화)
# - School_Name, School_Level 환경변수 기반 동적 리소스명 생성
# - 활성/Soft-Deleted 리소스 충돌 시 사용자 입력으로 회피
# - Storage Account 24자 제한 자동 대응
# - 테스트/프로덕션 환경 분리, 프로덕션은 환경변수 검증
# ============================================================

# ----- 필수 환경변수 확인 -----
if [ -z "${School_Name:-}" ] || [ -z "${School_Level:-}" ]; then
    echo "오류: School_Name 및 School_Level 환경변수를 먼저 설정하세요."
    echo "예시: export School_Name=seoul School_Level=hs"
    echo ""
    echo "School_Level 구분자: es(초등), ms(중등), hs(고등), sc(특수/각종), kg(유치원)"
    exit 1
fi

SCHOOL_NAME_TOKEN=$(printf '%s' "$School_Name" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9')
if [ -z "$SCHOOL_NAME_TOKEN" ]; then
  echo "오류: School_Name은 영문/숫자로 변환 가능한 값이어야 합니다."
  exit 1
fi

# 24글자 제한에 맞춰 School_Name 부분만 축약
if [ ${#SCHOOL_NAME_TOKEN} -gt 7 ]; then
  SCHOOL_NAME_TOKEN="${SCHOOL_NAME_TOKEN:0:7}"
fi

LOCATION="${LOCATION:-koreacentral}"
ALLOW_DEFAULT_SECRETS="${ALLOW_DEFAULT_SECRETS:-false}"

# ----- 구독 선택 (선택 사항) -----
echo ""
echo "============================================================"
echo "사용 가능한 Azure 구독 목록"
echo "============================================================"
az account list --query "[].{Name:name, ID:id, IsDefault:isDefault}" -o table
echo ""
read -p "사용할 구독 ID를 입력하세요 (기본값: 현재 구독): " SUB_ID_INPUT

if [ -n "$SUB_ID_INPUT" ]; then
    az account set --subscription "$SUB_ID_INPUT"
    echo ">>> 구독이 변경되었습니다: $SUB_ID_INPUT"
fi

# ----- 학생용 구독 안내 -----
echo ""
echo "============================================================"
echo "학생용 Azure 구독(Azure for Students) 호환 모드"
echo "============================================================"
echo "- Cosmos DB: 무료 티어 활성화 (400 RU/s)"
echo "- Storage: Standard_LRS (5GB 무료)"
echo "- ACR: Basic SKU (무료 제공량 내)"
echo "- Container Apps: 소비 플랜 (월 180,000 vCPU초 무료)"
echo ""
echo "주의: 크레딧 소진 방지를 위해 불필요한 리소스는 배포 완료 후 삭제하세요."
echo "============================================================"

# ----- 실행 전 최종 확인 -----
echo ""
read -p "위 사항을 확인하셨습니까? (y/N): " ready
if [[ ! "$ready" =~ ^[Yy] ]]; then
    echo "배포를 취소합니다."
    exit 0
fi

# ----- 모드 선택 -----
MODE="${MODE:-}"
DEPLOY_ENV="${DEPLOY_ENV:-}"

if [ -z "$MODE" ]; then
    cat << 'MENU'

════════════════════════════════════════════════════════════
           Azure 인프라 배포 - 모드 선택
════════════════════════════════════════════════════════════

Test (기본값 적용)        Prod (실제값 필수)
  1. 업데이트             11. 업데이트
  2. 초기화 [주의]         22. 초기화 [주의]

  3. 종료
MENU
    read -p "선택 (1/2/11/22/3): " choice
    case $choice in
        1) MODE="update"; ALLOW_DEFAULT_SECRETS="true"; DEPLOY_ENV="test" ;;
        2) MODE="refresh"; ALLOW_DEFAULT_SECRETS="true"; DEPLOY_ENV="test" ;;
        11) MODE="update"; ALLOW_DEFAULT_SECRETS="false"; DEPLOY_ENV="prod" ;;
        22) MODE="refresh"; ALLOW_DEFAULT_SECRETS="false"; DEPLOY_ENV="prod" ;;
        3) echo "종료합니다."; exit 0 ;;
        *)
            echo ""
            echo "값을 잘못 입력하였습니다. 재 실행해 주세요."
            exit 1
            ;;
    esac

    # 초기화 재확인
    if [ "$MODE" = "refresh" ]; then
        echo ""
        read -p "[주의] 초기화 후 복구 불가능합니다. 진행? (y/N): " confirm
        if [[ ! "$confirm" =~ ^[Yy] ]]; then
            echo "취소되었습니다. 재 실행해 주세요."
            exit 0
        fi
    fi
fi

if [ -z "$DEPLOY_ENV" ]; then
  if [ "$ALLOW_DEFAULT_SECRETS" = "true" ]; then
    DEPLOY_ENV="test"
  else
    DEPLOY_ENV="prod"
  fi
fi

# ----- 프로덕션 환경변수 검증 (빈 문자열도 불허) -----
if [ "$ALLOW_DEFAULT_SECRETS" = "false" ]; then
    echo ""
    echo "프로덕션 환경 필수 환경변수 확인 중..."

    MISSING_VARS=""

    if [ -z "${AZURE_OPENAI_ENDPOINT:-}" ] || [ "${AZURE_OPENAI_ENDPOINT}" = "" ]; then
        MISSING_VARS="$MISSING_VARS\n  - AZURE_OPENAI_ENDPOINT"
    fi
    if [ -z "${API_KEY_AI:-}" ] || [ "${API_KEY_AI}" = "" ]; then
        MISSING_VARS="$MISSING_VARS\n  - API_KEY_AI"
    fi
    if [ -z "${API_KEY_SMS:-}" ] || [ "${API_KEY_SMS}" = "" ]; then
        MISSING_VARS="$MISSING_VARS\n  - API_KEY_SMS"
    fi
    if [ -z "${API_SECRET_SMS:-}" ] || [ "${API_SECRET_SMS}" = "" ]; then
        MISSING_VARS="$MISSING_VARS\n  - API_SECRET_SMS"
    fi
    if [ -z "${SMS_SENDER_PHONE:-}" ] || [ "${SMS_SENDER_PHONE}" = "" ]; then
        MISSING_VARS="$MISSING_VARS\n  - SMS_SENDER_PHONE"
    fi

    if [ -n "$MISSING_VARS" ]; then
        echo ""
        echo "오류: 다음 환경변수가 설정되지 않았거나 빈 값입니다."
        echo -e "$MISSING_VARS"
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

# ----- 배포 번호 (기본값 01, 충돌 시 사용자 입력으로 변경) -----
DEPLOY_NUM="${DEPLOY_NUM:-01}"

# ----- 리소스명 생성 함수 (24자 제한 대응) -----
generate_name() {
    local type=$1
    local env_suffix="$2"

    case $type in
    rg)      echo "rg-${SCHOOL_NAME_TOKEN}-${School_Level}-${env_suffix}-krc" ;;
    kv)      echo "kv-${SCHOOL_NAME_TOKEN}-${School_Level}-${env_suffix}-krc${DEPLOY_NUM}" ;;
    storage) echo "st${SCHOOL_NAME_TOKEN}${School_Level}${env_suffix}krc${DEPLOY_NUM}" ;;
    cosmos)  echo "cosmos-${SCHOOL_NAME_TOKEN}-${School_Level}-${env_suffix}-krc${DEPLOY_NUM}" ;;
    acr)     echo "acr${SCHOOL_NAME_TOKEN}${School_Level}${env_suffix}krc${DEPLOY_NUM}" ;;
    env)     echo "env-${SCHOOL_NAME_TOKEN}-${School_Level}-${env_suffix}-krc${DEPLOY_NUM}" ;;
    app)     echo "app-${SCHOOL_NAME_TOKEN}-${School_Level}-${env_suffix}-krc${DEPLOY_NUM}" ;;
        *)
            echo "unknown type: $type" >&2
            return 1
            ;;
    esac
}

# ----- 초기 리소스명 생성 -----
RG=$(generate_name rg "$DEPLOY_ENV")
KV=$(generate_name kv "$DEPLOY_ENV")
STORAGE=$(generate_name storage "$DEPLOY_ENV")
COSMOS=$(generate_name cosmos "$DEPLOY_ENV")
ACR=$(generate_name acr "$DEPLOY_ENV")
ENV_NAME=$(generate_name env "$DEPLOY_ENV")
APP=$(generate_name app "$DEPLOY_ENV")

# ----- 이름 충돌 확인 함수 (동일 RG는 허용, 다른 RG/Soft-Deleted만 차단) -----
get_active_resource_group() {
  local name=$1
  local type=$2

  case $type in
    storage)
      az storage account list --query "[?name=='$name'].resourceGroup | [0]" -o tsv 2>/dev/null || true
      ;;
    kv)
      az keyvault list --query "[?name=='$name'].resourceGroup | [0]" -o tsv 2>/dev/null || true
      ;;
    cosmos)
      az cosmosdb list --query "[?name=='$name'].resourceGroup | [0]" -o tsv 2>/dev/null || true
      ;;
    acr)
      az acr list --query "[?name=='$name'].resourceGroup | [0]" -o tsv 2>/dev/null || true
      ;;
  esac
}

check_name_conflict() {
  local name=$1
  local type=$2
  local active_rg=""

  active_rg=$(get_active_resource_group "$name" "$type")
  if [ -n "$active_rg" ] && [ "$active_rg" != "$RG" ]; then
    echo "다른 리소스 그룹에서 이미 사용 중: $active_rg"
    return 0
  fi

  case $type in
    storage)
      if az storage account list-deleted --query "[?name=='$name'].name" -o tsv 2>/dev/null | grep -q .; then
        echo "Soft-Deleted 상태"
        return 0
      fi
      ;;
    kv)
      if az keyvault list-deleted --query "[?name=='$name'].name" -o tsv 2>/dev/null | grep -q .; then
        echo "Soft-Deleted 상태"
        return 0
      fi
      ;;
  esac

  return 1
}

# ----- 충돌 확인 및 사용자 입력 루프 -----
while true; do
    CONFLICT_FOUND=false
    CONFLICT_LIST=""
  CONFLICT_REASON=""

  if CONFLICT_REASON=$(check_name_conflict "$STORAGE" storage); then
        CONFLICT_FOUND=true
    CONFLICT_LIST="$CONFLICT_LIST\n  - Storage Account: $STORAGE ($CONFLICT_REASON)"
    fi

  if CONFLICT_REASON=$(check_name_conflict "$KV" kv); then
        CONFLICT_FOUND=true
    CONFLICT_LIST="$CONFLICT_LIST\n  - Key Vault: $KV ($CONFLICT_REASON)"
    fi

  if CONFLICT_REASON=$(check_name_conflict "$COSMOS" cosmos); then
        CONFLICT_FOUND=true
    CONFLICT_LIST="$CONFLICT_LIST\n  - Cosmos DB: $COSMOS ($CONFLICT_REASON)"
    fi

  if CONFLICT_REASON=$(check_name_conflict "$ACR" acr); then
        CONFLICT_FOUND=true
    CONFLICT_LIST="$CONFLICT_LIST\n  - ACR: $ACR ($CONFLICT_REASON)"
    fi

    if [ "$CONFLICT_FOUND" = true ]; then
        echo ""
        echo "============================================================"
        echo "⚠️  다음 리소스 이름이 이미 존재합니다 (활성 또는 삭제됨)."
        echo -e "$CONFLICT_LIST"
        echo "============================================================"
        echo ""
        read -p "새로운 배포 번호(두 자리 숫자, 예: 02, 03)를 입력하세요 (취소: q): " new_num

        if [[ "$new_num" == "q" || "$new_num" == "Q" ]]; then
            echo "배포를 취소합니다."
            exit 0
        fi

        if [[ ! "$new_num" =~ ^[0-9]{2}$ ]]; then
            echo "잘못된 형식입니다. 두 자리 숫자(예: 05)를 입력하세요."
            continue
        fi

        DEPLOY_NUM="$new_num"
        RG=$(generate_name rg "$DEPLOY_ENV")
        KV=$(generate_name kv "$DEPLOY_ENV")
        STORAGE=$(generate_name storage "$DEPLOY_ENV")
        COSMOS=$(generate_name cosmos "$DEPLOY_ENV")
        ACR=$(generate_name acr "$DEPLOY_ENV")
        ENV_NAME=$(generate_name env "$DEPLOY_ENV")
        APP=$(generate_name app "$DEPLOY_ENV")

        echo ""
        echo ">>> 새 리소스 이름:"
        echo "    Storage: $STORAGE"
        echo "    Key Vault: $KV"
        echo "    Cosmos DB: $COSMOS"
        echo "    ACR: $ACR"
        echo ""

        continue
    else
        break
    fi
done

echo "✅ 모든 리소스 이름 사용 가능 확인 완료."
echo ""

echo ">>> 선택된 모드: MODE=$MODE, DEPLOY_ENV=$DEPLOY_ENV, ALLOW_DEFAULT_SECRETS=$ALLOW_DEFAULT_SECRETS"
echo ">>> 배포 정보: School_Name=$School_Name, School_Name_Token=$SCHOOL_NAME_TOKEN, School_Level=$School_Level, DEPLOY_NUM=$DEPLOY_NUM, LOCATION=$LOCATION"
echo ">>> 리소스 그룹: $RG"
echo ">>> Key Vault: $KV"
echo ">>> Storage: $STORAGE"
echo ">>> Cosmos DB: $COSMOS"
echo ">>> ACR: $ACR"
echo ">>> Container Env: $ENV_NAME"
echo ">>> Container App: $APP"
echo ""

# ----- 유틸리티 함수 -----
wait_for_revision_ready() {
    local app=$1
    local rg=$2
    echo ">>> 리비전 준비 대기 중..."
    local max_wait=120
    local waited=0
    while [ $waited -lt $max_wait ]; do
        local STATUS
        STATUS=$(az containerapp revision list -g "$rg" -n "$app" \
            --query "sort_by([*], &properties.createdTime)[-1].properties.provisioningState" -o tsv 2>/dev/null || echo "Unknown")
        if [ "$STATUS" = "Provisioned" ]; then
            echo "리비전 준비 완료"
            return 0
        elif [ "$STATUS" = "Failed" ]; then
            echo "오류: 리비전 프로비저닝 실패"
            return 1
        fi
        sleep 5
        waited=$((waited + 5))
    done
    echo "오류: 리비전 대기 시간 초과"
    return 1
}

spinner() {
    local message="$1"
    local duration="$2"
    local spinstr='|/-\'
    local end=$((SECONDS + duration))

    while [ $SECONDS -lt $end ]; do
        local temp=${spinstr#?}
        printf "\r%s [%c]" "$message" "$spinstr"
        spinstr=$temp${spinstr%"$temp"}
        sleep 0.1
    done
    printf "\r%s [완료]\n" "$message"
}

retry_command() {
    local max_attempts=$1
    local sleep_seconds=$2
    shift 2

    local attempt=1
    until "$@"; do
      if [ "$attempt" -ge "$max_attempts" ]; then
        return 1
      fi
      echo "재시도 중... ($attempt/$max_attempts)"
      attempt=$((attempt + 1))
      sleep "$sleep_seconds"
    done
}

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
    az storage account create --name "$STORAGE" -g "$RG" -l "$LOCATION" \
      --sku Standard_LRS --kind StorageV2 --https-only true \
      --allow-blob-public-access false --min-tls-version TLS1_2 --output none
fi

STORAGE_KEY=$(az storage account keys list --account-name "$STORAGE" -g "$RG" --query "[0].value" -o tsv)
az storage container create --name webps --account-name "$STORAGE" --account-key "$STORAGE_KEY" --output none 2>/dev/null || true

az storage account blob-service-properties update --account-name "$STORAGE" \
  --enable-delete-retention true --delete-retention-days 30 --output none

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
if az storage account management-policy show --account-name "$STORAGE" -g "$RG" &>/dev/null; then
    az storage account management-policy update --account-name "$STORAGE" -g "$RG" --policy "@$LIFECYCLE_TMP" --output none
else
    az storage account management-policy create --account-name "$STORAGE" -g "$RG" --policy "@$LIFECYCLE_TMP" --output none
fi

# ----- 4. Cosmos DB -----
if ! az cosmosdb show --name "$COSMOS" -g "$RG" &>/dev/null; then
    if ! az cosmosdb create --name "$COSMOS" -g "$RG" --locations regionName="$LOCATION" \
      --enable-free-tier true --default-consistency-level Session --output none; then
        echo "오류: Cosmos DB 생성 실패"
        echo "힌트: --enable-free-tier true 는 구독당 1개만 허용됩니다."
        echo "이미 Free Tier를 사용 중이면 해당 옵션을 제거하거나 기존 계정을 사용하세요."
        exit 1
    fi
fi

if ! az cosmosdb sql database show -a "$COSMOS" -g "$RG" -n CertificateSystem &>/dev/null; then
    az cosmosdb sql database create -a "$COSMOS" -g "$RG" -n CertificateSystem --throughput 400 --output none
fi

if ! az cosmosdb sql container show -a "$COSMOS" -g "$RG" -d CertificateSystem -n registry &>/dev/null; then
    az cosmosdb sql container create -a "$COSMOS" -g "$RG" -d CertificateSystem -n registry -p "/cohortId" --output none
fi
if ! az cosmosdb sql container show -a "$COSMOS" -g "$RG" -d CertificateSystem -n admins &>/dev/null; then
    az cosmosdb sql container create -a "$COSMOS" -g "$RG" -d CertificateSystem -n admins -p "/email" --output none
fi
if ! az cosmosdb sql container show -a "$COSMOS" -g "$RG" -d CertificateSystem -n ai_limits &>/dev/null; then
    az cosmosdb sql container create -a "$COSMOS" -g "$RG" -d CertificateSystem -n ai_limits -p "/id" --output none
fi

az cosmosdb sql container update -a "$COSMOS" -g "$RG" -d CertificateSystem -n ai_limits --ttl -1 --output none
az cosmosdb sql container update -a "$COSMOS" -g "$RG" -d CertificateSystem -n registry \
  --idx '{"indexingMode":"consistent","automatic":true,"includedPaths":[{"path":"/*"}],"excludedPaths":[{"path":"/nameEncrypted/*"},{"path":"/webpUrl/*"},{"path":"/\"_etag\"/?"}]}' --output none

# ----- 5. ACR -----
if ! az acr show --name "$ACR" -g "$RG" &>/dev/null; then
    az acr create --name "$ACR" -g "$RG" --sku Basic -l "$LOCATION" --admin-enabled false --output none
fi

# ----- 6. Container Apps Environment -----
az provider register -n Microsoft.OperationalInsights --wait --output none
if ! az containerapp env show --name "$ENV_NAME" -g "$RG" &>/dev/null; then
    az containerapp env create --name "$ENV_NAME" -g "$RG" -l "$LOCATION" --output none
fi

# ----- 7. Container App -----
if ! az containerapp show --name "$APP" -g "$RG" &>/dev/null; then
    az containerapp create --name "$APP" -g "$RG" --environment "$ENV_NAME" \
      --image mcr.microsoft.com/azuredocs/containerapps-helloworld:latest \
      --target-port 80 --ingress external --min-replicas 0 --max-replicas 2 \
      --system-assigned --output none
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
  if ! retry_command 5 5 az role assignment create --assignee "$PRINCIPAL_ID" --role AcrPull --scope "$ACR_ID" --output none; then
    echo "오류: AcrPull 역할 할당에 실패했습니다."
    exit 1
  fi
fi

STORAGE_ROLE_EXISTS=$(az role assignment list --assignee "$PRINCIPAL_ID" --role "Storage Blob Data Contributor" --scope "$STORAGE_ID" --query "length(@)" -o tsv 2>/dev/null || echo "0")
if [ "$STORAGE_ROLE_EXISTS" -eq 0 ]; then
  if ! retry_command 5 5 az role assignment create --assignee "$PRINCIPAL_ID" --role "Storage Blob Data Contributor" --scope "$STORAGE_ID" --output none; then
    echo "오류: Storage Blob Data Contributor 역할 할당에 실패했습니다."
    exit 1
  fi
fi

KV_POLICY_EXISTS=$(az keyvault show --name "$KV" -g "$RG" --query "properties.accessPolicies[?objectId=='$PRINCIPAL_ID'].objectId" -o tsv 2>/dev/null || echo "")
if [ -z "$KV_POLICY_EXISTS" ]; then
  if ! retry_command 5 5 az keyvault set-policy --name "$KV" -g "$RG" --object-id "$PRINCIPAL_ID" --secret-permissions get list --output none; then
    echo "오류: Key Vault 정책 설정에 실패했습니다."
    exit 1
  fi
fi

spinner ">>> 역할 할당 전파 대기 중" 30

# ----- 9. Key Vault Secrets -----
echo ">>> Key Vault Secrets 확인 중..."

STORAGE_CONN=$(az storage account show-connection-string --name "$STORAGE" -g "$RG" -o tsv)
az keyvault secret set --vault-name "$KV" --name CONNECTION-STRING-STORAGE --value "$STORAGE_CONN" --output none

COSMOS_CONN=$(az cosmosdb keys list --name "$COSMOS" -g "$RG" --type connection-strings --query "connectionStrings[0].connectionString" -o tsv)
az keyvault secret set --vault-name "$KV" --name CONNECTION-STRING-DATABASE --value "$COSMOS_CONN" --output none

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
spinner ">>> Key Vault 권한 전파 대기 중" 30
KV_URI="https://${KV}.vault.azure.net/secrets"

# ----- 11. 환경변수 + Health Probe + Scale (YAML 일괄 적용) -----
echo ">>> 환경변수·헬스 프로브·스케일 YAML 적용 중..."

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

wait_for_revision_ready "$APP" "$RG" || exit 1

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