# The Neuron system 기술 문서

## 1. 사전 준비

### 1.1 Azure 리소스 생성

다음 리소스를 Azure Portal 또는 CLI로 생성한다. (실제 이름 기준)

- 리소스 그룹: `Neuron_group` (한국 중부)
- Storage Account (인도 중부): `incenstore`
- Storage Account (한국 중부): `kocenstore`
- Managed Identity: `NeuronIdentity` (User-Assigned)
- Compute Gallery: `NeuronGallery` (인도 중부)
- 이미지 정의: `neuron-golden` (Linux OS)
- 이미지 버전: `1.0.0`
- 가상 네트워크 (인도 중부): `neuron-vm-vnet-in`
- 가상 네트워크 (한국 중부): `neuron-vm-vnet-kr`

### 1.2 RBAC 권한 할당

Managed Identity `NeuronIdentity`에 다음 역할을 할당한다.

- Storage Account `incenstore`에 Storage Blob Data Contributor 및 Storage Blob Data Reader
- Storage Account `kocenstore`에 Storage Blob Data Contributor 및 Storage Blob Data Reader

Azure CLI 명령어 예시:
```bash
IDENTITY_PRINCIPAL_ID=$(az identity show --name NeuronIdentity --resource-group Neuron_group --query principalId -o tsv)

az role assignment create --assignee $IDENTITY_PRINCIPAL_ID --role "Storage Blob Data Contributor" --scope "/subscriptions/.../resourceGroups/Neuron_group/providers/Microsoft.Storage/storageAccounts/incenstore"
az role assignment create --assignee $IDENTITY_PRINCIPAL_ID --role "Storage Blob Data Reader" --scope "/subscriptions/.../resourceGroups/Neuron_group/providers/Microsoft.Storage/storageAccounts/incenstore"

az role assignment create --assignee $IDENTITY_PRINCIPAL_ID --role "Storage Blob Data Contributor" --scope "/subscriptions/.../resourceGroups/Neuron_group/providers/Microsoft.Storage/storageAccounts/kocenstore"
az role assignment create --assignee $IDENTITY_PRINCIPAL_ID --role "Storage Blob Data Reader" --scope "/subscriptions/.../resourceGroups/Neuron_group/providers/Microsoft.Storage/storageAccounts/kocenstore"
```

### 1.3 Golden Image 생성

1. 임시 VM을 `Standard_E2ads_v6`, Ubuntu 22.04 LTS로 생성한다.
2. 다음 스크립트를 실행하여 필요한 파일을 준비한다.
```bash
# 데이터셋 준비 (wikitext-2 다운로드 및 20개 청크로 분할, overlap 64 적용)
mkdir -p /usr/local/share/datasets
wget https://huggingface.co/datasets/ggml-org/ci/resolve/main/wikitext-2-raw/wiki.test.raw -O /tmp/wiki.test.raw
# 분할 및 overlap 처리는 Python 스크립트로 수행 (생략, 최종적으로 /usr/local/share/datasets/wikitext_chunk_*.txt 파일이 생성됨)

# 메모리 설정 스크립트
cat > /etc/neuron-memory.sh << 'EOF'
#!/bin/bash
modprobe zram
echo lz4 > /sys/block/zram0/comp_algorithm
echo 4G > /sys/block/zram0/disksize
mkswap /dev/zram0
swapon /dev/zram0 -p 100
echo 10 > /proc/sys/vm/swappiness
EOF
chmod +x /etc/neuron-memory.sh

# blobfuse2 설치 (필수 - 동일 리전 마운트용)
sudo apt update && sudo apt install -y blobfuse2
```
3. VM을 일반화(`sudo waagent -deprovision+user`)하고 이미지로 캡처한다.
4. 캡처한 이미지를 Azure Compute Gallery에 복제: `NeuronGallery/neuron-golden/1.0.0`, 대상 리전 `centralindia`, `koreacentral`

### 1.4 Blob Storage 초기 데이터 업로드

- `incenstore`의 `models` 컨테이너에 GGUF 모델 파일(13b_Q4_K_M.gguf 등)을 업로드한다.
- `incenstore`의 `binaries` 컨테이너에 `llama.cpp/latest/perplexity` 바이너리를 업로드한다.
- `kocenstore`의 `models` 컨테이너에도 동일한 모델 파일을 업로드한다 (초기 1회 수동 복사).

### 1.5 GitHub Secrets 설정

GitHub 저장소 → Settings → Secrets and variables → Actions 에 다음을 추가한다.

- `AZURE_CREDENTIALS`: Azure 서비스 주체 인증 JSON
- `SLACK_WEBHOOK_URL`: Slack 알림용 웹훅 URL

서비스 주체 생성 명령어:
```bash
az ad sp create-for-rbac --name NeuronDeploy --role Contributor --scopes /subscriptions/.../resourceGroups/Neuron_group --sdk-auth
```

## 2. 배포 스크립트 (deploy.sh)

파일을 생성하고 실행 권한을 부여한다.

```bash
#!/bin/bash
set -e

# ==================== 사용자 설정 ====================
RG="Neuron_group"
VM_NAME="neuron-vm-auto"
ADMIN_USER="azureuser"
SSH_KEY_PATH="~/project/.privatekeys/neuron-vm-key.pub"
IDENTITY_NAME="NeuronIdentity"
GALLERY_NAME="NeuronGallery"
IMAGE_DEFINITION="neuron-golden"
IMAGE_VERSION="1.0.0"

ACCOUNT_INDIA="incenstore"
ACCOUNT_KOREA="kocenstore"

SPOT_PRICE_INDIA="0.01733"      # E2ads_v6 Spot
SPOT_PRICE_KOREA="0.03308"      # E2ads_v6 Spot

SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
SUBSCRIPTION_ID="a942e898-e1ee-47f4-b9b3-d9475672ff4e"
IDENTITY_RESOURCE_ID="/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RG}/providers/Microsoft.ManagedIdentity/userAssignedIdentities/${IDENTITY_NAME}"

# ==================== 단계별 설정 ====================
# 초기 단계(개발/테스트): true (VM에 공용 IP 할당, 디버깅 편의)
# 안정화 단계(운영): false (IP 없음, 필요시 GitHub Actions로 임시 IP)
PUBLIC_IP_ENABLED=true   # 안정화 후 false로 변경

# ==================== 함수 정의 ====================

# Spot 가용성 확인 (할당량 및 재고)
# 참고: 할당량 이름 형식은 'StandardE2adsV6Spot' (대소문자 주의)
check_spot_availability() {
  local REGION=$1
  local SIZE="E2ads_v6"
  # 할당량 확인 - 실제 이름은 'StandardE2adsV6Spot' 형태
  local QUOTA=$(az vm list-usage --location $REGION \
    --query "[?name.value=='Standard${SIZE//_/}Spot' && currentValue < limit].currentValue" \
    -o tsv 2>/dev/null)
  if [ -n "$QUOTA" ]; then
    return 0  # 사용 가능
  else
    return 1  # 할당량 부족
  fi
}

get_expires() {
  # 분석 시작 시간 + (분석 시간 + 30분) 설정 (실제 값은 run_analysis.sh에서 생성하는 신호 파일 기준으로 나중에 조정)
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
    curl -X POST -H 'Content-type: application/json' --data "{\"text\":\"[$LEVEL] The Neuron system ($KST_TIME KST): $MESSAGE\"}" "$SLACK_WEBHOOK_URL" 2>/dev/null
  else
    echo "$(date -u) [WARNING] $MESSAGE" >> /tmp/warnings.log
    az storage blob upload --container logs --name warnings.log --file /tmp/warnings.log --account-name $ACCOUNT_INDIA 2>/dev/null
  fi
}

# 종량제 카운터 (현재 미사용, 향후 활성화 예정)
update_ondemand_counter() {
  echo "0"
}

is_weekend_skip() {
  # 종량제 fallback이 없으므로 항상 false
  return 1
}

try_create_vm() {
  local REGION=$1
  local PRIORITY=$2
  local MAX_PRICE=$3
  local CYCLE=$4
  local VM_NAME_FULL="${VM_NAME}-${REGION}-cycle${CYCLE}-$(date +%Y%m%d-%H%M%S)"
  local EXPIRES=$(get_expires)

  # VNet 선택
  if [ "$REGION" = "centralindia" ]; then
    VNET_NAME="neuron-vm-vnet-in"
  else
    VNET_NAME="neuron-vm-vnet-kr"
  fi

  local CMD="az vm create \
    --resource-group $RG \
    --name $VM_NAME_FULL \
    --location $REGION \
    --gallery-image $GALLERY_NAME/$IMAGE_DEFINITION/$IMAGE_VERSION \
    --size Standard_E2ads_v6 \
    --admin-username $ADMIN_USER \
    --ssh-key-values \"$SSH_KEY_PATH\" \
    --os-disk-size-gb 32 \
    --os-disk-type StandardSSD_LRS \
    --os-disk-caching ReadOnly \
    --os-disk-delete-option Delete \
    --tags Expires=\"$EXPIRES\" \
    --assign-identity \"$IDENTITY_RESOURCE_ID\" \
    --custom-data /tmp/cloud-init.yaml \
    --vnet-name $VNET_NAME --subnet default"

  if [ "$PUBLIC_IP_ENABLED" = "true" ]; then
    CMD="$CMD --public-ip-address Standard"
  else
    CMD="$CMD --public-ip-address ''"
  fi

  if [ "$PRIORITY" = "spot" ]; then
    CMD="$CMD --priority Spot --eviction-policy Deallocate --max-price $MAX_PRICE"
  else
    # 종량제는 현재 미지원, 이 함수는 spot 전용으로 사용
    echo "On-demand not supported for this VM size"
    return 1
  fi

  eval $CMD
  return $?
}

# ==================== Cloud-init 파일 생성 ====================
cat > /tmp/cloud-init.yaml << 'EOF'
#cloud-config
package_upgrade: false
write_files:
  - path: /etc/neuron-memory.sh
    permissions: '0755'
    content: |
      #!/bin/bash
      modprobe zram
      echo lz4 > /sys/block/zram0/comp_algorithm
      echo 4G > /sys/block/zram0/disksize
      mkswap /dev/zram0
      swapon /dev/zram0 -p 100
      echo 10 > /proc/sys/vm/swappiness
  - path: /etc/check-nvme.sh
    permissions: '0755'
    content: |
      #!/bin/bash
      if ! mountpoint -q /mnt; then
        sudo mount /dev/sdb1 /mnt || echo "NVMe mount failed" > /dev/termination-log
      fi
runcmd:
  - /etc/neuron-memory.sh
  - /etc/check-nvme.sh
  - mkdir -p /mnt/models /mnt/cache /tmp/results
  - |
    timeout 600 az login --identity --username "${IDENTITY_RESOURCE_ID}"
    if [ $? -ne 0 ]; then
      echo "Cloud-init: az login 실패" > /dev/termination-log
      exit 1
    fi
  - |
    REGION=$(curl -s -H Metadata:true "http://169.254.169.254/metadata/instance/compute/location?api-version=2017-08-01&format=text")
    if [[ "$REGION" == "centralindia" ]]; then
      ACCOUNT="incenstore"
      # 동일 리전: blobfuse2 마운트
      blobfuse2 mount /mnt/blob --container-name items --account-name $ACCOUNT --identity-client-id "${IDENTITY_RESOURCE_ID}" --tmp-path=/mnt/cache
    else
      ACCOUNT="kocenstore"
      # 타 리전: azcopy 사용 (마운트 안 함)
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
  echo "주말 운영 스킵 (종량제 fallback 없음)"
  exit 0
fi

VM_CREATED=""
VM_NAME_FINAL=""
MAX_CYCLES=2

for cycle in $(seq 1 $MAX_CYCLES); do
  echo "=== 사이클 $cycle/$MAX_CYCLES 시작 ==="
  
  # 인도 중부 Spot 시도 (최대 4회)
  for i in {1..4}; do
    echo "인도 중부 Spot 시도 $i/4 (사이클 $cycle)"
    if check_spot_availability "centralindia"; then
      if try_create_vm "centralindia" "spot" "$SPOT_PRICE_INDIA" "$cycle"; then
        VM_CREATED="centralindia-spot"
        VM_NAME_FINAL=$(az vm list --resource-group $RG --query "[?contains(name, 'neuron-vm-auto-centralindia-cycle${cycle}')] | sort_by(@, &name)[-1].name" -o tsv)
        break 2
      fi
    else
      echo "인도 중부 Spot 할당량 부족"
    fi
    sleep 300
  done
  
  # 한국 중부 Spot 시도 (최대 6회)
  for i in {1..6}; do
    echo "한국 중부 Spot 시도 $i/6 (사이클 $cycle)"
    if check_spot_availability "koreacentral"; then
      if try_create_vm "koreacentral" "spot" "$SPOT_PRICE_KOREA" "$cycle"; then
        VM_CREATED="koreacentral-spot"
        VM_NAME_FINAL=$(az vm list --resource-group $RG --query "[?contains(name, 'neuron-vm-auto-koreacentral-cycle${cycle}')] | sort_by(@, &name)[-1].name" -o tsv)
        break 2
      fi
    else
      echo "한국 중부 Spot 할당량 부족"
    fi
    sleep 300
  done
  
  if [ $cycle -lt $MAX_CYCLES ]; then
    echo "사이클 $cycle 실패, 5분 후 다음 사이클 재시도"
    sleep 300
  fi
done

if [ -z "$VM_CREATED" ]; then
  send_slack_alert "CRITICAL" "모든 VM 생성 실패 (2사이클 반복 후)"
  exit 1
fi

# IP 주소 가져오기 (초기 단계에서만)
if [ "$PUBLIC_IP_ENABLED" = "true" ]; then
  IP=$(az vm show -d -g $RG -n $VM_NAME_FINAL --query "publicIps" -o tsv)
  echo "VM IP: $IP"
else
  echo "VM created without public IP (stable phase)"
fi

echo "Cloud-init 대기 중..."
TIMEOUT_SEC=600
START_WAIT=$(date +%s)

# SSH 접속 (IP가 있을 때만)
if [ "$PUBLIC_IP_ENABLED" = "true" ]; then
  until ssh -o ConnectTimeout=5 -o BatchMode=yes -o StrictHostKeyChecking=no azureuser@$IP '[ -f /tmp/ready ]'; do
    if [ $(($(date +%s) - START_WAIT)) -gt $TIMEOUT_SEC ]; then
      az vm delete --resource-group $RG --name $VM_NAME_FINAL --yes --force-deletion
      send_slack_alert "CRITICAL" "Cloud-init 실패"
      exit 1
    fi
    sleep 15
  done
  scp run_analysis.sh azureuser@$IP:/tmp/
  ssh azureuser@$IP "bash /tmp/run_analysis.sh"
else
  # 안정화 단계: 분석 스크립트는 Cloud-init 내에서 실행된다고 가정
  echo "Stable phase: waiting for Cloud-init completion (no SSH)"
  sleep $TIMEOUT_SEC
fi
```

## 3. 분석 실행 스크립트 (run_analysis.sh)

분석 스크립트는 기존 `vm_run_analysis.sh`를 기반으로 하되, 다음 사항을 추가한다.

- **분석 시작 신호 파일 생성**: 분석을 실제로 시작하는 시점(첫 번째 청크 처리 직전)에 Blob Storage `state` 컨테이너에 `analysis_started_<YYYYMMDD>_<VM_NAME>.json` 파일을 생성한다. 파일 내용은 `{"start_time": "<ISO8601>", "vm_name": "<hostname>", "analysis_hours": <N>}` 형식을 사용한다.
- 각 청크 처리 완료 시 `last_incomplete.json` 업데이트 (기존 방식 유지)
- `state.json`은 사용하지 않음

주요 내용은 설계 문서의 9절과 일치하며, 구체적인 구현은 별도 파일로 제공한다.

## 4. GitHub Actions 워크플로우

### 4.1 강제 종료 (force-stop.yaml)

```yaml
name: Force Stop VM
on:
  schedule:
    - cron: '0 14 * * 1-5'     # 평일 1차 fallback: 14:00 KST (09:00 + 5시간)
    - cron: '0 3 * * 2-6'      # 평일 2차 fallback: 03:00 KST (다음날, 22:00 + 5시간)
    - cron: '0 15 * * 0'       # 일요일 fallback: 15:00 KST (09:00 + 6시간)
  workflow_dispatch:
env:
  TZ: Asia/Seoul
jobs:
  force-stop:
    runs-on: ubuntu-latest
    steps:
      - uses: azure/login@v1
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}
      - name: Check analysis start signal and force stop
        run: |
          RUNNING_VMS=$(az vm list --resource-group Neuron_group --query "[?powerState=='VM running'].name" -o tsv)
          for VM in $RUNNING_VMS; do
            # 분석 시작 신호 파일 확인 (예: analysis_started_$(date +%Y%m%d)_*.json)
            START_FILE=$(az storage blob list --container state --prefix "analysis_started_$(date +%Y%m%d)" --account-name incenstore --query "[].name" -o tsv 2>/dev/null | head -1)
            if [ -n "$START_FILE" ]; then
              START_TIME=$(az storage blob show --container state --name $START_FILE --account-name incenstore --query "properties.lastModified" -o tsv)
              ELAPSED=$(($(date +%s) - $(date -d "$START_TIME" +%s)))
              # 분석 시간이 4시간(또는 연장 시 5시간) + 15분이 지났는지 확인 (기본 4시간15분 = 15300초)
              if [ $ELAPSED -lt 15300 ]; then
                echo "Analysis running less than 4h15m. Skip force stop."
                continue
              fi
            else
              # 신호 파일 없음 → fallback 시간 기준 (cron 시간 자체가 fallback)
              echo "No start signal, forcing stop by fallback schedule."
            fi
            az vm deallocate --resource-group Neuron_group --name $VM --force
          done
      - name: Cleanup disks
        run: |
          TODAY=$(date +%Y-%m-%d)
          ORPHAN_DISKS=$(az disk list --resource-group Neuron_group --query "[?tags.Expires<'$TODAY'].id" -o tsv)
          for DISK in $ORPHAN_DISKS; do
            az disk delete --ids $DISK --yes --no-wait
          done
      - name: Cleanup any leftover temporary IP
        run: |
          az network public-ip delete -g Neuron_group -n temp-debug-ip --yes || true
```

### 4.2 가격 모니터링 (price-monitor.yaml)

Azure API 기반으로 수정 (cloudprice.net 크롤링 제거)

```yaml
name: Spot Price Monitor
on:
  schedule:
    - cron: '0 0 */3 * *'
  workflow_dispatch:
jobs:
  monitor:
    runs-on: ubuntu-latest
    steps:
      - uses: azure/login@v1
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}
      - name: Check spot prices
        run: |
          INDIA_PRICE=$(az vm spot-price list --location centralindia --size Standard_E2ads_v6 --query "[0].price" -o tsv 2>/dev/null)
          KOREA_PRICE=$(az vm spot-price list --location koreacentral --size Standard_E2ads_v6 --query "[0].price" -o tsv 2>/dev/null)
          echo "India spot price: $INDIA_PRICE, Korea spot price: $KOREA_PRICE"
          # 기준 가격 대비 10% 이상 변동 시 Slack 알림 (기준 가격은 환경 변수로 관리)
          # 알림 로직은 필요 시 구현
```

### 4.3 임시 디버깅 IP (temp-ip.yaml) - 안정화 단계용

```yaml
name: Attach Temporary IP for Debugging

on:
  workflow_dispatch:

jobs:
  debug:
    runs-on: ubuntu-latest
    steps:
      - name: Azure Login
        uses: azure/login@v1
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}

      - name: Get running VM
        id: vm
        run: |
          VM_NAME=$(az vm list --resource-group Neuron_group --query "[?powerState=='VM running'].name" -o tsv)
          if [ -z "$VM_NAME" ]; then
            echo "No running VM found. Exiting."
            exit 1
          fi
          echo "name=$VM_NAME" >> $GITHUB_OUTPUT

      - name: Create and attach temporary IP
        run: |
          az network public-ip create -g Neuron_group -n temp-debug-ip --sku Basic --allocation-method Dynamic
          NIC_ID=$(az vm show -g Neuron_group -n ${{ steps.vm.outputs.name }} --query networkProfile.networkInterfaces[0].id -o tsv)
          az network nic ip-config update --nic-id $NIC_ID --name ipconfig1 --public-ip-address temp-debug-ip
          IP=$(az network public-ip show -g Neuron_group -n temp-debug-ip --query ipAddress -o tsv)
          echo "IP=$IP" >> $GITHUB_ENV
          echo "=========================================="
          echo "Temporary IP: $IP"
          echo "SSH command: ssh azureuser@$IP"
          echo "=========================================="

      - name: Wait for analysis start signal (up to 10 min)
        run: |
          for i in {1..60}; do
            if az storage blob exists --container state --name "analysis_started_$(date +%Y%m%d)_${{ steps.vm.outputs.name }}.json" --account-name incenstore &>/dev/null; then
              echo "Analysis started. Start monitoring eviction."
              break
            fi
            sleep 10
          done

      - name: Wait 30 minutes or until VM evicted (after analysis start)
        run: |
          for i in {1..180}; do
            if ! az vm show -g Neuron_group -n ${{ steps.vm.outputs.name }} &>/dev/null; then
              echo "VM evicted. Cleaning up IP immediately."
              break
            fi
            sleep 10
          done

      - name: Cleanup IP (unconditional)
        if: always()
        run: |
          if az vm show -g Neuron_group -n ${{ steps.vm.outputs.name }} &>/dev/null; then
            NIC_ID=$(az vm show -g Neuron_group -n ${{ steps.vm.outputs.name }} --query networkProfile.networkInterfaces[0].id -o tsv)
            az network nic ip-config update --nic-id $NIC_ID --name ipconfig1 --public-ip-address "" || true
          fi
          az network public-ip delete -g Neuron_group -n temp-debug-ip --yes || true

      - name: Verify IP deleted
        if: always()
        run: |
          if az network public-ip show -g Neuron_group -n temp-debug-ip &>/dev/null; then
            echo "WARNING: IP still exists! Forcing deletion again..."
            az network public-ip delete -g Neuron_group -n temp-debug-ip --yes
          else
            echo "IP successfully deleted."
          fi
```

## 5. 실행 방법

1. `deploy.sh`와 `run_analysis.sh`를 같은 디렉토리에 저장한다.
2. `deploy.sh`의 사용자 설정 변수를 실제 환경에 맞게 수정한다.
3. `chmod +x deploy.sh`
4. `./deploy.sh`
5. GitHub Actions를 통해 매일 자동 실행하려면 `deploy.sh`를 GitHub 저장소에 커밋하고 워크플로우에서 호출한다.

## 6. 문제 해결

- Cloud-init 실패: `/var/log/cloud-init-output.log` 확인, NVMe 마운트 오류 확인
- Managed Identity 권한 오류(403): RBAC 할당 확인, blobfuse2 인증 설정 확인
- 모델 다운로드 실패: Storage Account 이름(`incenstore`, `kocenstore`)과 컨테이너 존재 여부 확인
- 분석 시간 초과: 청크 수 조정 또는 baseline 조정 고려
- 할당량 부족: `az vm list-usage`로 Spot vCPU 할당량 확인, 필요 시 지원 요청
