#!/usr/bin/env bash

set -euo pipefail

USE_COLOR="false"
if [[ -t 1 ]]; then
  USE_COLOR="true"
fi

if [[ "$USE_COLOR" == "true" ]]; then
  C_RED=$'\033[31m'
  C_GREEN=$'\033[32m'
  C_YELLOW=$'\033[33m'
  C_BLUE=$'\033[34m'
  C_BOLD=$'\033[1m'
  C_RESET=$'\033[0m'
else
  C_RED=""
  C_GREEN=""
  C_YELLOW=""
  C_BLUE=""
  C_BOLD=""
  C_RESET=""
fi

log_info() { echo "${C_BLUE}[INFO]${C_RESET} $*"; }
log_warn() { echo "${C_YELLOW}[WARN]${C_RESET} $*"; }
log_ok() { echo "${C_GREEN}[OK]${C_RESET} $*"; }
log_error() { echo "${C_RED}[ERROR]${C_RESET} $*"; }

CURRENT_STEP="startup"
on_error() {
  local line_no="$1"
  local exit_code="$2"
  log_error "Failed at step: ${CURRENT_STEP} (line ${line_no}, exit ${exit_code})"
}

trap 'on_error "$LINENO" "$?"' ERR

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
API_PATH="${REPO_ROOT}/apps/records-api"

# One-shot post-deploy setup for test/prod environment.
# This script:
# 1) validates required Key Vault secrets
# 2) wires Key Vault refs to Container App secrets
# 3) applies runtime env vars (secretref + cloud cert flag)
# 4) builds/pushes records-api image for linux/amd64 and updates Container App image

require_command() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    log_error "Required command not found: $cmd"
    exit 1
  fi
}

confirm_yn() {
  local prompt="$1"
  local answer=""
  read -r -p "$prompt" answer
  [[ "$answer" == "y" || "$answer" == "Y" ]]
}

need_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    log_error "Missing required env var: $name"
    exit 1
  fi
}

has_role_assignment() {
  local assignee="$1"
  local scope="$2"
  local role_name="$3"

  local count
  count="$(az role assignment list \
    --assignee "$assignee" \
    --scope "$scope" \
    --include-inherited \
    --query "[?roleDefinitionName=='${role_name}'] | length(@)" \
    -o tsv 2>/dev/null || echo 0)"

  [[ "$count" != "0" && -n "$count" ]]
}

ensure_any_role() {
  local assignee="$1"
  local scope="$2"
  local description="$3"
  shift 3

  local role
  for role in "$@"; do
    if has_role_assignment "$assignee" "$scope" "$role"; then
      log_ok "$description role check passed ($role)"
      return 0
    fi
  done

  log_error "$description role check failed"
  echo "        assignee: $assignee"
  echo "        scope: $scope"
  echo "        required one of: $*"
  return 1
}

secret_exists() {
  local vault="$1"
  local secret_name="$2"
  az keyvault secret show --vault-name "$vault" --name "$secret_name" --query id -o tsv >/dev/null 2>&1
}

require_command az
require_command docker
require_command openssl

if ! docker buildx version >/dev/null 2>&1; then
  log_error "docker buildx is required. Enable buildx and retry."
  exit 1
fi

if ! az account show >/dev/null 2>&1; then
  log_error "Azure login required. Run: az login"
  exit 1
fi

if [[ ! -d "$API_PATH" ]]; then
  log_error "records-api path not found: $API_PATH"
  exit 1
fi

# ---------- User-configurable inputs ----------
SCHOOL_TOKEN="${SCHOOL_TOKEN:-kuhwa}"
SCHOOL_LEVEL="${SCHOOL_LEVEL:-sc}"
DEPLOY_NUM="${DEPLOY_NUM:-01}"
ENV_SUFFIX="${ENV_SUFFIX:-prod}"
LOCATION="${LOCATION:-koreacentral}"
IMAGE_TAG="${IMAGE_TAG:-1.0.0}"
INCLUDE_SMS_SECRETS="${INCLUDE_SMS_SECRETS:-false}"
SKIP_CONFIRM="${SKIP_CONFIRM:-false}"
SKIP_PERMISSION_CHECK="${SKIP_PERMISSION_CHECK:-false}"

# Required when setting AI secrets (if they already exist in Key Vault, these can be omitted)
AI_SERVICE_KEY="${AI_SERVICE_KEY:-}"
AZURE_OPENAI_ENDPOINT="${AZURE_OPENAI_ENDPOINT:-}"

# Optional SMS values (used only when INCLUDE_SMS_SECRETS=true)
SMS_API_KEY="${SMS_API_KEY:-}"
SMS_API_SECRET="${SMS_API_SECRET:-}"
SMS_SENDER_PHONE="${SMS_SENDER_PHONE:-}"

# ---------- Guardrails ----------
if [[ "$ENV_SUFFIX" != "test" && "$ENV_SUFFIX" != "prod" ]]; then
  log_error "ENV_SUFFIX must be 'test' or 'prod' (current: $ENV_SUFFIX)"
  exit 1
fi

# ---------- Derived names ----------
RG="rg-${SCHOOL_TOKEN}-${SCHOOL_LEVEL}-${ENV_SUFFIX}-krc${DEPLOY_NUM}"
APP="app-${SCHOOL_TOKEN}-${SCHOOL_LEVEL}-${ENV_SUFFIX}-krc${DEPLOY_NUM}"
KV="kv-${SCHOOL_TOKEN}-${SCHOOL_LEVEL}-${ENV_SUFFIX}-krc${DEPLOY_NUM}"
UAMI_NAME="id-${SCHOOL_TOKEN}-${SCHOOL_LEVEL}-${ENV_SUFFIX}-krc${DEPLOY_NUM}"
ACR="acr${SCHOOL_TOKEN}${SCHOOL_LEVEL}${ENV_SUFFIX}krc${DEPLOY_NUM}"
IMAGE="${ACR}.azurecr.io/records-api:${IMAGE_TAG}"

echo "----------------------------------------"
echo "${C_BOLD}Post-Deploy Setup${C_RESET}"
echo "----------------------------------------"
echo "environment: $ENV_SUFFIX"
echo "location: $LOCATION"
echo "resource group: $RG"
echo "container app: $APP"
echo "key vault: $KV"
echo "acr: $ACR"
echo "image: $IMAGE"
echo "----------------------------------------"

# ---------- Azure context and target checks ----------
CURRENT_STEP="azure-context-check"
SUB_ID="$(az account show --query id -o tsv)"
SUB_NAME="$(az account show --query name -o tsv)"

echo "subscription: $SUB_NAME ($SUB_ID)"

echo
echo "Preflight checklist"
echo "- [ ] Correct subscription selected"
echo "- [ ] Target environment (test/prod) is intended"
echo "- [ ] Resource names match expected school token/level"
echo "- [ ] Required Key Vault secrets are prepared"
echo "- [ ] records-api image tag is correct"
echo

if ! az group show --name "$RG" >/dev/null 2>&1; then
  log_error "Resource group not found: $RG"
  echo "        Run infra deployment first, then rerun this script."
  exit 1
fi

if ! az containerapp show --name "$APP" --resource-group "$RG" >/dev/null 2>&1; then
  log_error "Container App not found: $APP"
  exit 1
fi

if ! az keyvault show --name "$KV" --resource-group "$RG" >/dev/null 2>&1; then
  log_error "Key Vault not found: $KV"
  exit 1
fi

if ! az identity show --name "$UAMI_NAME" --resource-group "$RG" >/dev/null 2>&1; then
  log_error "User-assigned identity not found: $UAMI_NAME"
  exit 1
fi

if ! az acr show --name "$ACR" --resource-group "$RG" >/dev/null 2>&1; then
  log_error "ACR not found: $ACR"
  exit 1
fi

log_ok "Target resource checks passed"

if [[ "$SKIP_PERMISSION_CHECK" != "true" ]]; then
  CURRENT_STEP="permission-check"
  UAMI_PRINCIPAL_ID="$(az identity show --name "$UAMI_NAME" --resource-group "$RG" --query principalId -o tsv)"
  KV_ID="$(az keyvault show --name "$KV" --resource-group "$RG" --query id -o tsv)"
  ACR_ID="$(az acr show --name "$ACR" --resource-group "$RG" --query id -o tsv)"

  ensure_any_role "$UAMI_PRINCIPAL_ID" "$KV_ID" "Key Vault access" \
    "Key Vault Secrets User" \
    "Key Vault Administrator" \
    "Key Vault Secrets Officer"

  ensure_any_role "$UAMI_PRINCIPAL_ID" "$ACR_ID" "ACR pull access" \
    "AcrPull" \
    "AcrPush" \
    "Owner" \
    "Contributor"
fi

if [[ "$SKIP_CONFIRM" != "true" ]]; then
  echo
  echo "Target summary"
  echo "- environment: $ENV_SUFFIX"
  echo "- resource group: $RG"
  echo "- container app: $APP"
  echo "- key vault: $KV"
  echo "- image: $IMAGE"
  echo

  if [[ "$ENV_SUFFIX" == "prod" ]]; then
    typed=""
    read -r -p "Prod environment detected. Type PROD to continue: " typed
    if [[ "$typed" != "PROD" ]]; then
      echo "Cancelled."
      exit 0
    fi
  else
    if ! confirm_yn "Proceed with $ENV_SUFFIX post-deploy setup? (y/N): "; then
      echo "Cancelled."
      exit 0
    fi
  fi
fi

# ---------- Resolve IDs ----------
CURRENT_STEP="resolve-ids"
UAMI_ID="$(az identity show -g "$RG" -n "$UAMI_NAME" --query id -o tsv)"
KV_URI="$(az keyvault show -g "$RG" -n "$KV" --query properties.vaultUri -o tsv)"

# ---------- Ensure required secrets exist ----------
CURRENT_STEP="validate-keyvault-secrets"
# connection-string-* are expected from infra deployment, but we still validate.
REQUIRED_SECRETS=(
  connection-string-database
  connection-string-storage
  encryption-key-aes
  encryption-key-hmac
  api-key-ai
  azure-openai-endpoint
)

# Auto-create encryption keys if missing.
if ! secret_exists "$KV" encryption-key-aes; then
  log_warn "Creating missing secret: encryption-key-aes"
  az keyvault secret set --vault-name "$KV" --name encryption-key-aes --value "$(openssl rand -hex 32)" >/dev/null
fi

if ! secret_exists "$KV" encryption-key-hmac; then
  log_warn "Creating missing secret: encryption-key-hmac"
  az keyvault secret set --vault-name "$KV" --name encryption-key-hmac --value "$(openssl rand -hex 32)" >/dev/null
fi

# Create/overwrite AI secrets only when values are provided.
if [[ -n "$AI_SERVICE_KEY" ]]; then
  az keyvault secret set --vault-name "$KV" --name api-key-ai --value "$AI_SERVICE_KEY" >/dev/null
fi
if [[ -n "$AZURE_OPENAI_ENDPOINT" ]]; then
  az keyvault secret set --vault-name "$KV" --name azure-openai-endpoint --value "$AZURE_OPENAI_ENDPOINT" >/dev/null
fi

for s in "${REQUIRED_SECRETS[@]}"; do
  if ! secret_exists "$KV" "$s"; then
    log_error "Missing Key Vault secret: $s"
    echo "        Create it first, then rerun this script."
    exit 1
  fi
done

log_ok "Required Key Vault secrets are ready"

if [[ "$INCLUDE_SMS_SECRETS" == "true" ]]; then
  need_env SMS_API_KEY
  need_env SMS_API_SECRET
  need_env SMS_SENDER_PHONE

  az keyvault secret set --vault-name "$KV" --name api-key-sms --value "$SMS_API_KEY" >/dev/null
  az keyvault secret set --vault-name "$KV" --name api-secret-sms --value "$SMS_API_SECRET" >/dev/null
  az keyvault secret set --vault-name "$KV" --name sms-sender-phone --value "$SMS_SENDER_PHONE" >/dev/null
fi

# ---------- Register Container App secrets with keyvaultref ----------
CURRENT_STEP="register-container-secrets"
SECRET_ARGS=(
  "connection-string-database=keyvaultref:${KV_URI}secrets/connection-string-database,identityref:${UAMI_ID}"
  "connection-string-storage=keyvaultref:${KV_URI}secrets/connection-string-storage,identityref:${UAMI_ID}"
  "encryption-key-aes=keyvaultref:${KV_URI}secrets/encryption-key-aes,identityref:${UAMI_ID}"
  "encryption-key-hmac=keyvaultref:${KV_URI}secrets/encryption-key-hmac,identityref:${UAMI_ID}"
  "api-key-ai=keyvaultref:${KV_URI}secrets/api-key-ai,identityref:${UAMI_ID}"
  "azure-openai-endpoint=keyvaultref:${KV_URI}secrets/azure-openai-endpoint,identityref:${UAMI_ID}"
)

if [[ "$INCLUDE_SMS_SECRETS" == "true" ]]; then
  SECRET_ARGS+=(
    "api-key-sms=keyvaultref:${KV_URI}secrets/api-key-sms,identityref:${UAMI_ID}"
    "api-secret-sms=keyvaultref:${KV_URI}secrets/api-secret-sms,identityref:${UAMI_ID}"
    "sms-sender-phone=keyvaultref:${KV_URI}secrets/sms-sender-phone,identityref:${UAMI_ID}"
  )
fi

az containerapp secret set --name "$APP" --resource-group "$RG" --secrets "${SECRET_ARGS[@]}" >/dev/null
log_ok "Container App secrets synced"

# ---------- Apply runtime env vars with secretref ----------
CURRENT_STEP="apply-runtime-env"
ENV_ARGS=(
  "DATABASE_CONNECTION_STRING=secretref:connection-string-database"
  "STORAGE_CONNECTION_STRING=secretref:connection-string-storage"
  "ENCRYPTION_KEY_AES=secretref:encryption-key-aes"
  "ENCRYPTION_KEY_HMAC=secretref:encryption-key-hmac"
  "AI_SERVICE_KEY=secretref:api-key-ai"
  "AZURE_OPENAI_ENDPOINT=secretref:azure-openai-endpoint"
  "COSMOS_DATABASE=CertificateSystem"
  "COSMOS_CONTAINER=records"
  "COSMOS_ADMINS_CONTAINER=admins"
  "COSMOS_REGISTRY_CONTAINER=registry"
  "STORAGE_CONTAINER=record-files"
  "WEBSITES_INCLUDE_CLOUD_CERTS=true"
)

if [[ "$INCLUDE_SMS_SECRETS" == "true" ]]; then
  ENV_ARGS+=(
    "SMS_API_KEY=secretref:api-key-sms"
    "SMS_API_SECRET=secretref:api-secret-sms"
    "SMS_SENDER_PHONE=secretref:sms-sender-phone"
  )
fi

az containerapp update --name "$APP" --resource-group "$RG" --set-env-vars "${ENV_ARGS[@]}" >/dev/null
log_ok "Runtime env vars applied"

# ---------- Build/push image and update app ----------
CURRENT_STEP="build-push-and-deploy-image"
log_info "Building and pushing image: $IMAGE"
az acr login --name "$ACR" >/dev/null
docker buildx build --platform linux/amd64 -t "$IMAGE" --push "$API_PATH" >/dev/null
az containerapp update --name "$APP" --resource-group "$RG" --image "$IMAGE" >/dev/null

FQDN="$(az containerapp show -n "$APP" -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)"

echo
log_ok "$ENV_SUFFIX post-deploy setup completed."
echo "FQDN: https://${FQDN}"
echo
echo "Run quick checks:"
echo "  az containerapp show -n $APP -g $RG --query \"properties.template.containers[0].env\" -o table"
echo "  az containerapp revision list -n $APP -g $RG --query \"[].{name:name,weight:properties.trafficWeight,active:properties.active}\" -o table"
echo "  curl -X POST https://${FQDN}/api/status -H \"Content-Type: application/json\" -d '{\"name\":\"홍길동\",\"birthdate\":\"1990-01-01\"}'"
echo
echo "Post-run checklist"
echo "- [ ] Latest revision has traffic weight 100"
echo "- [ ] Env table shows SecretRef for DB/Storage/AI secrets"
echo "- [ ] /api/status returns JSON (not storage unavailable)"
echo "- [ ] Admin login works via /.auth/login/aad"
echo "- [ ] /api/manage/pending returns JSON"
echo
echo "Admin login URL:"
echo "  https://${FQDN}/.auth/login/aad"
