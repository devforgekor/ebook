```markdown
# The Neuron system 시스템 - 추가 기술 문서

다음은 본 문서에서 누락되었거나 추가로 명시해야 할 사항을 정리한다.

## 1. 연간 비용 계산 (Standard_E2ads_v6 기준)

| 항목 | 계산 | 비용 (USD) |
|------|------|------------|
| VM (인도 중부 Spot, 2,119시간) | 2,119 × $0.01733 | $36.73 |
| OS 디스크 (Standard SSD 32GB, 2,119시간) | 2,119 × ($0.00044) | $0.93 |
| Golden Image 저장 (10GB, 두 리전) | 10 × $0.018 × 12 × 2 | $4.32 |
| Blob Storage (20GB, `incenstore`) | 20 × $0.0208 × 12 | $4.99 |
| Blob Storage (20GB, `kocenstore`) | 20 × $0.0208 × 12 | $4.99 |
| 결과 복제 Egress (200MB/일) | 73GB × $0.05 | $3.65 |
| **합계** | | **$55.61** |
| 예산 대비 여유 | | $44.39 |

> **참고**: 현재 `Standard_E2ads_v6` 크기는 종량제로 제공되지 않으므로 종량제 fallback 비용은 발생하지 않는다. 위 비용은 순수 Spot VM 사용 기준이며, 실제로는 한국 Spot fallback(15% 가정 시 약 $10 추가)이 발생할 수 있으나 예산 내 충분하다.

### 1.1 공용 IP 분리 전략을 통한 추가 비용 절감 (안정화 단계)

- 안정화 단계에서 VM에 공용 IP를 할당하지 않음 (`PUBLIC_IP_ENABLED=false`)
- 필요할 때만 GitHub Actions로 임시 IP를 30분간 사용하고 자동 삭제 (`temp-ip.yaml`)
- 기존(초기 단계) 대비 연간 약 $0.5~1.0 절감 (IP 사용 시간 감소)
- IP 리소스를 남기지 않으므로 예기치 않은 비용 발생 없음

## 2. Golden Image 생성 상세 단계

### 2.1 임시 VM 생성

```bash
az vm create --resource-group Neuron_group --name temp-golden --location koreacentral --image Ubuntu2204 --size Standard_E2ads_v6 --admin-username azureuser --ssh-key-values ~/.ssh/id_rsa.pub
```

### 2.2 데이터셋 준비 (Python)

```python
import requests
import textwrap

# wikitext-2 다운로드
url = "https://huggingface.co/datasets/ggml-org/ci/resolve/main/wikitext-2-raw/wiki.test.raw"
text = requests.get(url).text

# Overlap 64, 청크 크기 512 토큰 (간략화)
chunk_size = 512
overlap = 64
stride = chunk_size - overlap
chunks = [text[i:i+chunk_size] for i in range(0, len(text), stride)]

for idx, chunk in enumerate(chunks[:20]):
    with open(f"/usr/local/share/datasets/wikitext_chunk_{idx:02d}.txt", "w") as f:
        f.write(chunk)
```

### 2.3 이미지 캡처 및 Gallery 복제

```bash
# VM 일반화
az vm deallocate --resource-group Neuron_group --name temp-golden
az vm generalize --resource-group Neuron_group --name temp-golden

# 이미지 생성
az image create --resource-group Neuron_group --name neuron-golden-image --source temp-golden --os-type Linux

# Gallery에 복제 (실제 Gallery 이름: NeuronGallery, 이미지 정의: neuron-golden)
az sig image-version create --resource-group Neuron_group --gallery-name NeuronGallery --gallery-image-definition neuron-golden --gallery-image-version 1.0.0 --managed-image /subscriptions/.../resourceGroups/Neuron_group/providers/Microsoft.Compute/images/neuron-golden-image --target-regions centralindia koreacentral --replica-count 1
```

## 3. Managed Identity 및 RBAC 설정 상세

### 3.1 Managed Identity 생성

```bash
az identity create --name NeuronIdentity --resource-group Neuron_group
```

### 3.2 역할 할당

```bash
IDENTITY_PRINCIPAL_ID=$(az identity show --name NeuronIdentity --resource-group Neuron_group --query principalId -o tsv)

# 인도 중부 Storage Account (incenstore)
az role assignment create --assignee $IDENTITY_PRINCIPAL_ID --role "Storage Blob Data Contributor" --scope "/subscriptions/.../resourceGroups/Neuron_group/providers/Microsoft.Storage/storageAccounts/incenstore"
az role assignment create --assignee $IDENTITY_PRINCIPAL_ID --role "Storage Blob Data Reader" --scope "/subscriptions/.../resourceGroups/Neuron_group/providers/Microsoft.Storage/storageAccounts/incenstore"

# 한국 중부 Storage Account (kocenstore)
az role assignment create --assignee $IDENTITY_PRINCIPAL_ID --role "Storage Blob Data Contributor" --scope "/subscriptions/.../resourceGroups/Neuron_group/providers/Microsoft.Storage/storageAccounts/kocenstore"
az role assignment create --assignee $IDENTITY_PRINCIPAL_ID --role "Storage Blob Data Reader" --scope "/subscriptions/.../resourceGroups/Neuron_group/providers/Microsoft.Storage/storageAccounts/kocenstore"
```

## 4. 리전 간 데이터 복제 (AzCopy)

매일 분석 완료 후 인도 중부(`incenstore`)에서 한국 중부(`kocenstore`)로 결과를 복제한다. `deploy.sh` 마지막에 추가할 수 있다.

```bash
# 결과 복제
azcopy copy "https://incenstore.blob.core.windows.net/results/$(date +%Y%m%d)/*" "https://kocenstore.blob.core.windows.net/results-backup/$(date +%Y%m%d)/" --recursive
```

## 5. 문제 해결 가이드

### 5.1 VM 생성 실패 (QuotaExceeded / 할당량 부족)

- 증상: Spot VM 생성 시 "QuotaExceeded" 오류
- 원인: 해당 리전의 Spot vCPU 할당량 소진
- 해결: `az vm list-usage`로 할당량 확인. 인도→한국 순으로 최대 2사이클 반복 후 실패 시 CRITICAL 알림. 다음 실행(오후 10시 또는 다음날)에 재시도.

### 5.2 Cloud-init 내 az login 실패

- 증상: VM은 생성되었으나 `/tmp/ready` 파일 없음
- 원인: Managed Identity(`NeuronIdentity`) 권한 없음 또는 네트워크 문제
- 해결: RBAC 할당 확인. VM의 `/var/log/cloud-init-output.log` 확인. blobfuse2 마운트 실패 여부도 확인.

### 5.3 모델 다운로드 403 Forbidden

- 증상: `az storage blob download` 실패 (403)
- 원인: Managed Identity에 Storage Blob Data Reader 권한 없음
- 해결: RBAC 할당 재확인. 역할 할당 후 5분 정도 대기.

### 5.4 분석 시간 초과 지속

- 증상: 3일 이상 PARTIAL 발생
- 원인: 13B 모델이 2 vCPU에서 너무 느리거나, 강제 종료 시간이 너무 짧음
- 해결: 청크 수를 20 → 15로 줄임. Golden Image(`NeuronGallery/neuron-golden/1.0.0`) 재빌드 필요. 또는 분석 시작 신호 기반 강제 종료 시간 조정.

### 5.5 Spot VM 생성 실패 (모든 사이클)

- 증상: 인도/한국 Spot VM을 2사이클 반복 후에도 생성 실패
- 원인: 양 리전 모두 Spot 가용성 부족 또는 할당량 소진
- 해결: CRITICAL 알림 확인. 다음 실행(오후 10시 또는 다음날)에서 재시도. 장기적 문제 발생 시 Azure 지원 문의.

## 6. 모니터링 지표 설명

| 지표 | 단위 | 의미 | 임계값 |
|------|------|------|--------|
| avg_chunk_sec | 초 | 청크당 평균 처리 시간 | 기준 대비 +30% 이상 시 튜닝 |
| completed_chunks | 개 | 완료된 청크 수 | 20개 미만 시 PARTIAL |
| rss_peak_mb | MB | 최대 물리 메모리 사용량 | 14000 초과 시 OOM 위험 |
| swap_in_kb | KB | 스왑 사용량 | 100000 초과 시 메모리 부족 |
| pending_from_prev | 개 | 전날 미완료 청크 수 | 5개 이상 시 시간 연장 적용 |

## 7. GitHub Actions Secrets 설정

GitHub 저장소 → Settings → Secrets and variables → Actions 에 다음을 추가한다.

- `AZURE_CREDENTIALS`: Azure 서비스 주체 인증 JSON (`az ad sp create-for-rbac --name NeuronDeploy --role Contributor --scopes /subscriptions/... --sdk-auth`)
- `SLACK_WEBHOOK_URL`: Slack Incoming Webhook URL

서비스 주체 생성 명령어:
```bash
az ad sp create-for-rbac --name NeuronDeploy --role Contributor --scopes /subscriptions/.../resourceGroups/Neuron_group --sdk-auth
```

## 8. 배포 자동화 (GitHub Actions 워크플로우)

`.github/workflows/deploy.yaml`

```yaml
name: Daily Deploy
on:
  schedule:
    # 평일 1차: KST 09:00 → UTC 00:00 (겨울) / 23:00 (여름) - 단순화
    - cron: '0 0 * * 1-5'
    # 평일 2차: KST 22:00 → UTC 13:00
    - cron: '0 13 * * 1-5'
    # 일요일 1차: KST 09:00 → UTC 00:00
    - cron: '0 0 * * 0'
  workflow_dispatch:
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: azure/login@v1
        with:
          creds: ${{ secrets.AZURE_CREDENTIALS }}
      - name: Run deploy script
        run: |
          chmod +x deploy.sh
          ./deploy.sh
```

## 9. 추가: 안정화 단계 임시 디버깅 IP 워크플로우 (분석 시작 신호 기반)

`.github/workflows/temp-ip.yaml` (수동 실행)

```yaml
name: Attach Temporary IP for Debugging

on:
  workflow_dispatch:

jobs:
  debug:
    runs-on: ubuntu-latest
    steps:
      - uses: azure/login@v1
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
          echo "Temporary IP: $IP"
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
      - name: Cleanup IP unconditionally
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

## 10. 대용량 파일 처리 파이프라인 (향후 확장 옵션)

현재 The Neuron system은 대부분의 데이터가 100MB 미만이므로 아래 기술을 도입하지 않았다. 향후 대용량(수백 MB~GB) 파일을 처리해야 할 때 다음 기준과 기술을 적용할 수 있다.

### 10.1 파일 크기별 처리 기준

| 파일 크기 | 처리 방식 | 비고 |
|-----------|-----------|------|
| **< 100MB** | zstd 압축 + `az storage blob upload` (CLI) | 단순 유지, gzip 대신 zstd 사용 |
| **≥ 100MB** | zstd 압축 + **azcopy** (단일 파일, 내부 병렬 전송) | 사용자 직접 청킹 불필요. azcopy가 내부적으로 분할/병렬 전송 |

### 10.2 구현 예시 (의사 코드)

```python
file_size_mb = get_file_size_mb(file_path)

if file_size_mb >= 100:
    # 대용량: zstd 압축 + azcopy 병렬 전송
    compress_zstd(file_path)
    azcopy_copy(file_path, destination)
else:
    # 소/중용량: zstd 압축 + CLI 업로드
    compress_zstd(file_path)
    az storage blob upload --file file_path.zst --container items --account-name $ACCOUNT
```

### 10.3 고급 기술 (필요 시 추가 검토)

- **Overlap Chunking**: 파일 분할 시 앞뒤 중복 구간 포함. 네트워크 불안정 시 복원력 향상
- **SHA256 체크섬**: 전송 후 무결성 검증. Azure MD5 기본 검증으로 충분하므로 선택 사항
- **state.json 상세 관리**: 청크별 상태, 체크섬, 압축 정보 저장. `last_incomplete.json`으로 충분하므로 필요 시에만 도입

적용 조건: 파일 크기가 **100MB 이상**이고, 네트워크 불안정이 자주 발생하거나 전송 실패율이 높을 때 위 기술들을 단계적으로 도입한다.
```
