#!/bin/bash
set -e

# ==================== 사용자 설정 ====================
RG="Neuron_group"
VM_NAME="neuron-vm-auto"
ADMIN_USER="azureuser"
SSH_KEY_PATH="~/project/.privatekeys/neuron-vm-auto_key.pub"
IDENTITY_NAME="NeuronIdentity"
GALLERY_NAME="NeuronGallery"
IMAGE_DEFINITION="neuron-golden"
IMAGE_VERSION="1.0.0"

ACCOUNT_INDIA="incenstore"
ACCOUNT_KOREA="kocenstore"

SPOT_PRICE_INDIA="0.01478"
SPOT_PRICE_KOREA="0.02809"
SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
SUBSCRIPTION_ID="a942e898-e1ee-47f4-b9b3-d9475672ff4e"
IDENTITY_RESOURCE_ID="/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RG}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/${IDENTITY_NAME}"

PUBLIC_IP_ENABLED=false

# ==================== 함수 정의 ====================
get_expires() {
  if [[ "$OSTYPE" == "darwin"* ]]; then
    date -v+5H -v+30M -u +%Y-%m-%dT%H:%M:%SZ
  else
    date -d '+5 hours 30 minutes' -u +%Y-%m-%dT%H:%M:%SZ
  fi
}

send_slack_alert() {
  local LEVEL=$1
  local MESSAGE=$2
  local KST_TIME=$(TZ=Asia/Seoul date +"%Y-%m-%d %H:%M:%S")
  if [ "$LEVEL" = "CRITICAL" ]; then
    curl -X POST -H 'Content-type: application/json' --data "{\"text\":\"[$LEVEL] The Axis ($KST_TIME KST): $MESSAGE\"}" "$SLACK_WEBHOOK_URL" 2>/dev/null
  else
    echo "$(date -u) [WARNING] $MESSAGE" >> /tmp/warnings.log
    az storage blob upload --container logs --name warnings.log --file /tmp/warnings.log --account-name $ACCOUNT_INDIA 2>/dev/null
  fi
}

update_ondemand_counter() {
  local DATE=$(TZ=Asia/Seoul date +%Y-%m-%d)
  local COUNTER_FILE="/tmp/ondemand_counter.json"
  az storage blob download --container state --name ondemand_counter.json --file $COUNTER_FILE --account-name $ACCOUNT_INDIA 2>/dev/null || echo '{"count":0,"last_date":""}' > $COUNTER_FILE
  local COUNT=$(jq -r '.count' $COUNTER_FILE)
  local LAST_DATE=$(jq -r '.last_date' $COUNTER_FILE)
  if [ "$LAST_DATE" != "$DATE" ]; then
    COUNT=0
  fi
  COUNT=$((COUNT + 1))
  jq -n --arg date "$DATE" --argjson count "$COUNT" '{count: $count, last_date: $date}' > $COUNTER_FILE
  az storage blob upload --container state --name ondemand_counter.json --file $COUNTER_FILE --account-name $ACCOUNT_INDIA
  echo $COUNT
}

is_weekend_skip() {
  local KST_WEEKDAY=$(TZ=Asia/Seoul date +%u)
  if [ $KST_WEEKDAY -ge 6 ]; then
    local COUNTER_FILE="/tmp/ondemand_counter.json"
    az storage blob download --container state --name ondemand_counter.json --file $COUNTER_FILE --account-name $ACCOUNT_INDIA 2>/dev/null || echo '{"count":0}' > $COUNTER_FILE
    local COUNT=$(jq -r '.count' $COUNTER_FILE)
    if [ $COUNT -ge 2 ]; then
      return 0
    fi
  fi
  return 1
}

try_create_vm() {
  local REGION=$1
  local PRIORITY=$2
  local MAX_PRICE=$3
  local VM_NAME_FULL="${VM_NAME}-${REGION}-$(date +%Y%m%d-%H%M%S)"
  local EXPIRES=$(get_expires)

  local CMD="az vm create \
    --resource-group $RG \
    --name $VM_NAME_FULL \
    --location $REGION \
    --gallery-image $GALLERY_NAME/$IMAGE_DEFINITION/$IMAGE_VERSION \
    --size Standard_E2as_v4 \
    --admin-username $ADMIN_USER \
    --ssh-key-values \"$SSH_KEY_PATH\" \
    --os-disk-size-gb 256 \
    --os-disk-type PremiumSSD_LRS \
    --os-disk-caching ReadOnly \
    --os-disk-delete-option Delete \
    --tags Expires=\"$EXPIRES\" \
    --assign-identity \"$IDENTITY_RESOURCE_ID\" \
    --custom-data /tmp/cloud-init.yaml"

  if [ "$PUBLIC_IP_ENABLED" = "true" ]; then
    CMD="$CMD --public-ip-address Standard"
  else
    CMD="$CMD --public-ip-address ''"
  fi

  # 리전별 VNet 지정
  if [ "$REGION" = "koreacentral" ]; then
    CMD="$CMD --vnet-name neuron-vm-vnet-kr --subnet default"
  elif [ "$REGION" = "centralindia" ]; then
    CMD="$CMD --vnet-name neuron-vm-vnet-in --subnet default"
  fi

  if [ "$PRIORITY" = "spot" ]; then
    CMD="$CMD --priority Spot --eviction-policy Deallocate --max-price $MAX_PRICE"
  else
    CMD="$CMD --priority Regular --auto-shutdown-time 0140"
  fi

  eval $CMD
  return $?
}

# ==================== Cloud-init 파일 생성 ====================
cat > /tmp/cloud-init.yaml << 'EOF'
#cloud-config
package_upgrade: false
write_files:
  - path: /etc/axis-memory.sh
    permissions: '0755'
    content: |
      #!/bin/bash
      modprobe zram
      echo lz4 > /sys/block/zram0/comp_algorithm
      echo 4G > /sys/block/zram0/disksize
      mkswap /dev/zram0
      swapon /dev/zram0 -p 100
      echo 10 > /proc/sys/vm/swappiness
runcmd:
  - /etc/axis-memory.sh
  - mkdir -p /mnt/models /mnt/data /tmp/results
  - |
    timeout 600 az login --identity --username "${IDENTITY_RESOURCE_ID}"
    if [ $? -ne 0 ]; then
      echo "Cloud-init: az login 실패" > /dev/termination-log
      exit 1
    fi
  - |
    REGION=$(curl -s -H Metadata:true "http://169.254.169.254/metadata/instance/compute/location?api-version=2017-08-01&format=text")
    if [[ "$REGION" == "centralindia" ]]; then
      ACCOUNT="${ACCOUNT_INDIA}"
    else
      ACCOUNT="${ACCOUNT_KOREA}"
    fi
    timeout 300 az storage blob download --container binaries --name llama.cpp/latest/perplexity --file /usr/local/bin/perplexity --account-name $ACCOUNT
    chmod +x /usr/local/bin/perplexity
  - |
    DAY=$(TZ=Asia/Seoul date +%u)
    case $DAY in
      1) MODEL="13b_Q4_K_M.gguf" ;;
      2) MODEL="13b_IQ4_XS.gguf" ;;
      3) MODEL="8b_Q4_K_M.gguf" ;;
      4) MODEL="13b_Q5_K_M.gguf" ;;
      5) MODEL="8b_IQ4_XS.gguf" ;;
      *) MODEL="8b_Q4_K_M.gguf" ;;
    esac
    timeout 600 az storage blob download --container models --name "$MODEL" --file "/mnt/models/model.gguf" --account-name $ACCOUNT &
  - touch /tmp/ready
EOF

# ==================== 메인 배포 로직 ====================
if is_weekend_skip; then
  echo "주말 운영 스킵"
  send_slack_alert "CRITICAL" "주말 운영 스킵 (종량제 2회 이상)"
  exit 0
fi

VM_CREATED=""
for i in {1..4}; do
  echo "인도 중부 Spot 시도 $i/4"
  if try_create_vm "centralindia" "spot" "$SPOT_PRICE_INDIA"; then
    VM_CREATED="centralindia-spot"
    break
  fi
  sleep 300
done

if [ -z "$VM_CREATED" ]; then
  for i in {1..6}; do
    echo "한국 중부 Spot 시도 $i/6"
    if try_create_vm "koreacentral" "spot" "$SPOT_PRICE_KOREA"; then
      VM_CREATED="koreacentral-spot"
      break
    fi
    sleep 300
  done
fi

if [ -z "$VM_CREATED" ]; then
  echo "인도 종량제 VM 생성"
  if try_create_vm "centralindia" "regular" ""; then
    VM_CREATED="centralindia-ondemand"
    COUNT=$(update_ondemand_counter)
    send_slack_alert "CRITICAL" "인도 종량제 fallback (${COUNT}회)"
  fi
fi

if [ -z "$VM_CREATED" ]; then
  echo "한국 종량제 VM 생성"
  if try_create_vm "koreacentral" "regular" ""; then
    VM_CREATED="koreacentral-ondemand"
    COUNT=$(update_ondemand_counter)
    send_slack_alert "CRITICAL" "한국 종량제 fallback (${COUNT}회)"
  else
    send_slack_alert "CRITICAL" "모든 VM 생성 실패"
    exit 1
  fi
fi

IP=$(az vm show -d -g $RG -n $VM_NAME --query "publicIps" -o tsv)
echo "VM IP: $IP"

echo "Cloud-init 대기 중..."
TIMEOUT_SEC=600
START_WAIT=$(date +%s)
until ssh -o ConnectTimeout=5 -o BatchMode=yes -o StrictHostKeyChecking=no azureuser@$IP '[ -f /tmp/ready ]'; do
  if [ $(($(date +%s) - START_WAIT)) -gt $TIMEOUT_SEC ]; then
    az vm delete --resource-group $RG --name $VM_NAME --yes --force-deletion
    send_slack_alert "CRITICAL" "Cloud-init 실패"
    exit 1
  fi
  sleep 15
done

scp vm_run_analysis.sh azureuser@$IP:/tmp/
ssh azureuser@$IP "bash /tmp/vm_run_analysis.sh"
