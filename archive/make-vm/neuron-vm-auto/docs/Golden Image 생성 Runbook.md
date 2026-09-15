# Golden Image 생성 Runbook

이 문서는 The Axis 시스템의 Golden Image를 재현 가능하게 생성하는 절차를 설명한다. 이미지가 오래되었거나 변경이 필요할 때 이 문서대로 실행하면 동일한 환경을 복원할 수 있다.

**참고**: 실제 생성된 Golden Image는 데이터셋(wikitext-2 청크 파일)을 포함하지 않는다. 데이터셋은 Cloud-init에서 동적으로 다운로드 및 분할된다. 이미지에는 OS, 메모리 설정 스크립트, zram 모듈 설정, crontab, **blobfuse2(필수)** 가 포함된다.

## 사전 조건

- Azure CLI 설치 및 로그인 (`az login`)
- 구독: Azure for Students
- 리소스 그룹: `Neuron_group` (이미 존재해야 함)
- Compute Gallery: `NeuronGallery` (이미 존재해야 함)
- 이미지 정의: `neuron-golden` (이미 존재해야 함)

## 1. 임시 VM 생성

```bash
az vm create \
  --resource-group Neuron_group \
  --name temp-golden-builder \
  --location centralindia \
  --image UbuntuMinimal2204 \
  --size Standard_E2ads_v6 \
  --admin-username azureuser \
  --ssh-key-values ~/.ssh/id_rsa.pub
```

## 2. VM 접속 및 설치

```bash
ssh azureuser@<VM_IP>
```

### 2.1 메모리 설정 스크립트

```bash
sudo tee /etc/axis-memory.sh << 'EOF'
#!/bin/bash
modprobe zram
echo lz4 > /sys/block/zram0/comp_algorithm
echo 4G > /sys/block/zram0/disksize
mkswap /dev/zram0
swapon /dev/zram0 -p 100
echo 10 > /proc/sys/vm/swappiness
EOF
sudo chmod +x /etc/axis-memory.sh
```

### 2.2 zram 모듈 자동 로드 설정

```bash
echo "zram" | sudo tee /etc/modules-load.d/zram.conf
```

### 2.3 부팅 시 메모리 스크립트 실행 등록 (crontab)

```bash
(sudo crontab -l 2>/dev/null; echo "@reboot /etc/axis-memory.sh") | sudo crontab -
```

### 2.4 blobfuse2 설치 (필수 - 동일 리전 마운트용)

```bash
sudo apt update
sudo apt install -y blobfuse2
```

### 2.5 불필요한 패키지 제거 (용량 최적화)

```bash
sudo apt remove -y python3-pip unzip   # 데이터셋 생성을 위해 pip는 필요 없음
sudo apt autoremove --purge -y
sudo apt autoclean
sudo apt clean
sudo journalctl --vacuum-size=10M
sudo rm -rf /var/log/*.log /var/log/apt/*.log
sudo rm -rf /tmp/* /var/tmp/*
sudo rm -rf /home/azureuser/.cache/*
sudo rm -rf /root/.cache/*
```

### 2.6 확인

```bash
df -h /
cat /etc/axis-memory.sh | head -5
cat /etc/modules-load.d/zram.conf
sudo crontab -l | grep axis-memory
which blobfuse2   # 설치 확인
```

## 3. VM 일반화 및 이미지 생성

```bash
exit   # VM 접속 종료
az vm deallocate --resource-group Neuron_group --name temp-golden-builder
az vm generalize --resource-group Neuron_group --name temp-golden-builder
az image create \
  --resource-group Neuron_group \
  --name neuron-golden-image \
  --source temp-golden-builder \
  --os-type Linux
```

## 4. Compute Gallery에 이미지 버전 생성 (여러 리전 복제)

이미지 생성이 완료되면 (몇 분 소요), Gallery에 이미지 버전을 생성하고 인도 중부, 한국 중부, East US에 복제한다.

```bash
SUBSCRIPTION_ID=$(az account show --query id -o tsv)
az sig image-version create \
  --resource-group Neuron_group \
  --gallery-name NeuronGallery \
  --gallery-image-definition neuron-golden \
  --gallery-image-version 1.0.0 \
  --managed-image "/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/Neuron_group/providers/Microsoft.Compute/images/neuron-golden-image" \
  --target-regions centralindia koreacentral eastus \
  --replica-count 1
```

## 5. 임시 VM 삭제

```bash
az vm delete --resource-group Neuron_group --name temp-golden-builder --yes --force-deletion
```

## 6. 주의사항

- 이미지 버전은 변경 시마다 `1.0.0` → `1.0.1` 처럼 올려야 한다. 배포 스크립트(`deploy.sh`)의 `IMAGE_VERSION` 변수도 함께 수정한다.
- 데이터셋 구성(청크 개수, overlap 등)이 바뀌면 Golden Image를 다시 빌드할 필요 없이, `deploy.sh`의 `cloud-init.yaml` 내 Python 코드만 수정하면 된다. (데이터셋은 Cloud-init에서 동적으로 생성되므로)
- 이미지 갱신 주기는 3개월에 한 번 또는 보안 패치 필요 시로 한다. (Ubuntu Minimal의 커널/보안 업데이트 반영)
- **blobfuse2는 반드시 포함**해야 한다. 설치되지 않으면 인도 리전 VM에서 Blob 마운트에 실패하여 Cloud-init이 완료되지 않는다.

## 7. 검증

생성된 이미지로 테스트 VM을 만들어 Cloud-init이 정상 완료되고 `/tmp/ready` 파일이 생성되는지 확인한다. (Cloud-init 내용은 `deploy.sh`에 포함된 것을 사용)

```bash
# cloud-init.yaml 파일 준비 (배포 스크립트에서 필요한 부분만 추출)
az vm create \
  --resource-group Neuron_group \
  --name test-golden \
  --location centralindia \
  --gallery-image NeuronGallery/neuron-golden/1.0.0 \
  --size Standard_E2ads_v6 \
  --admin-username azureuser \
  --ssh-key-values ~/.ssh/id_rsa.pub \
  --custom-data @cloud-init.yaml
```

VM 접속 후 다음 항목을 확인한다.

```bash
# 1. Cloud-init 완료 신호
ls -la /tmp/ready

# 2. 데이터셋 청크 파일 (20개)
ls -la /usr/local/share/datasets/wikitext_chunk_*.txt | wc -l

# 3. NVMe 마운트 확인
mountpoint -q /mnt && echo "NVMe mounted" || echo "NVMe not mounted"

# 4. blobfuse2 마운트 확인 (인도 리전 VM인 경우)
mountpoint -q /mnt/blob && echo "blobfuse2 mounted" || echo "blobfuse2 not mounted"
```

모든 확인 항목이 정상이면 Golden Image가 올바르게 생성된 것이다.

