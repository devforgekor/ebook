#!/bin/bash
export LC_ALL=en_US.UTF-8
export LANG=en_US.UTF-8
export PYTHONIOENCODING=utf-8
export PYTHONUTF8=1

# ----- 사용자 환경에 맞게 수정된 변수들 -----
RG="Neuron_group"
VM_NAME="neuron-vm-auto"
LOCATION="koreacentral"
ADMIN_USER="azureuser"
SSH_KEY_PATH="~/project/.privatekeys/neuron-vm-auto_key.pub"
# ------------------------------------------

echo "Spot VM ($VM_NAME) 생성을 시작합니다..."

az vm create \
  --resource-group $RG \
  --name $VM_NAME \
  --location $LOCATION \
  --image "Canonical:0001-com-ubuntu-minimal-jammy:minimal-22_04-lts-gen2:latest" \
  --size Standard_FX2mds_v2 \
  --priority Spot \
  --eviction-policy Delete \
  --admin-username $ADMIN_USER \
  --ssh-key-values "$SSH_KEY_PATH" \
  --ephemeral-os-disk true \
  --ephemeral-os-disk-placement NvmeDisk \
  --os-disk-caching ReadOnly \
  --os-disk-delete-option Delete \
  --vnet-name neuron-vnet \
  --subnet default

if [ $? -eq 0 ]; then
    echo "✅ VM 생성 요청 성공!"
    az vm show -d -g $RG -n $VM_NAME --query "publicIps" -o tsv
else
    echo "❌ VM 생성 실패. 오류 메시지를 확인하세요."
    exit 1
fi
