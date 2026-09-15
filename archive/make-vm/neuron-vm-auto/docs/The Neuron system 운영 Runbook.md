# The Neuron system 운영 Runbook

## 1. 일일 운영

이 시스템은 매일 정해진 스케줄에 따라 자동으로 시작된다. 별도의 수동 조작은 필요하지 않다. 다만 아래 상황에서는 운영자가 확인하고 조치해야 한다.

**실행 스케줄**:
- 평일(월~금): 오전 9시, 오후 10시 (2회)
- 토요일: 실행 없음
- 일요일: 오전 9시 (1회)

## 2. Slack 알림 종류와 대응

CRITICAL 알림만 Slack으로 전송된다. WARNING은 Blob 로그에만 기록된다.

> **참고**: 현재 Azure for Students 구독에서는 `Standard_E2ads_v6` 종량제 VM을 생성할 수 없으므로, 종량제 fallback 관련 알림은 발생하지 않는다. 아래 알림은 향후 종량제 VM 사용 가능 시 활성화 예정이다.

### 2.1 종량제 fallback 발생 (현재 미사용)

메시지: [CRITICAL] 인도 종량제 fallback (1회) 또는 한국 종량제 fallback (1회)

- 의미: Spot VM을 생성하지 못하고 비싼 종량제 VM으로 대체 실행됨.
- 영향: 당일 분석 비용이 평소보다 약 5배 증가한다.
- 조치: 2회 이상 반복되면 주말 운영이 자동 스킵된다. 주중에 2회 이상 발생하면 운영자가 다음 주 월요일에 인도 리전의 Spot 가용성을 확인한다.

### 2.2 VM 생성 완전 실패

메시지: [CRITICAL] 모든 VM 생성 실패

- 의미: 인도 Spot, 한국 Spot 순으로 2사이클(최대 1시간 50분)을 반복했으나 VM을 생성하지 못함.
- 영향: 당일 분석이 전혀 이루어지지 않음.
- 조치: Azure Portal에서 직접 VM을 수동으로 생성한다. (생성 스크립트 `deploy.sh`의 파라미터 참고) 다음 실행 시간(오후 10시 또는 다음날 오전 9시)에 자동 재시도된다.

### 2.3 Cloud-init 실패

메시지: [CRITICAL] Cloud-init 실패

- 의미: VM은 만들어졌지만 내부 초기화(로그인, 바이너리 다운로드)에 실패함.
- 영향: VM이 바로 삭제되므로 분석이 진행되지 않음.
- 조치: 다음날 자동 재시도를 기다린다. 2회 이상 반복되면 Golden Image(`NeuronGallery/neuron-golden/1.0.0`)를 재확인한다.

### 2.4 2일 연속 PARTIAL

메시지: [CRITICAL] 2일 연속 PARTIAL (완료 15/20)

- 의미: 이틀 연속으로 분석 시간 내에 모든 청크를 처리하지 못함.
- 영향: 미완료 청크가 계속 누적될 수 있음.
- 조치: 로그에서 평균 청크 처리 시간(avg_chunk_sec)을 확인한다. 성능 저하가 지속되면 청크 수를 20개에서 15개로 줄이는 것을 고려한다.

### 2.5 3일 연속 PARTIAL

메시지: [CRITICAL] 3일 연속 PARTIAL - 데이터 양 조절 필요

- 의미: 시스템이 지속적으로 시간 내 분석을 완료하지 못함.
- 영향: 미완료 청크 누적이 심각해짐.
- 조치: 반드시 운영자가 개입해야 한다. 데이터셋 청크 수를 줄이거나 모델 양자화 수준을 낮춘다.

### 2.6 성능 저하 2일 연속

메시지: [CRITICAL] 성능 저하 2일 연속 - 튜닝 적용 예정

- 의미: 평균 청크 처리 시간이 기준 대비 30% 이상 느려짐.
- 영향: 다음날 분석 시 스레드 수가 2개에서 1개로 줄어든다. 분석 시간은 늘어나지만 CPU 경합이 줄어든다.
- 조치: 특별한 조치가 필요하지 않다. 3일 후에도 개선되지 않으면 zRAM 크기를 2GB로 줄이는 것을 고려한다.

### 2.7 강제 종료 실행

메시지: [CRITICAL] 강제 종료(force) 실행됨

- 의미: 분석 시작 후 4시간(연장 시 5시간) + 15분이 지났거나, fallback 시간(예: 오전 9시 + 5시간 15분)이 지나도록 VM이 종료되지 않아 GitHub Actions(`force-stop.yaml`)가 강제로 VM을 종료함.
- **구체적인 강제 종료 시각(KST)**:
  - 평일 1차 (09:00 시작): **12:15** (기본), 연장 시 **13:15**
  - 평일 2차 (22:00 시작): **01:15** (다음날), 연장 시 **02:15**
  - 일요일 (09:00 시작): **13:15** (기본), 연장 시 **14:15**
- 영향: 분석이 중간에 잘렸을 수 있으며, 완료된 청크까지만 결과가 저장됨.
- 조치: 다음날 증분 처리가 자동으로 재개된다. 3일 연속 발생하면 분석 시간 정책을 재검토한다.

### 2.8 주말 운영 스킵 (현재 미사용)

메시지: [CRITICAL] 주말 운영 스킵 (종량제 2회 이상)

- 의미: 주중에 종량제 fallback이 2회 이상 발생하여 해당 주의 토요일, 일요일 운영을 자동으로 건너뜀.
- 영향: 주말 분석이 없음.
- 조치: 다음주 월요일에 종량제 fallback 원인을 분석한다(인도 Spot 가용성 문제인지, 모델 크기 문제인지).

## 3. 월간 점검 사항

### 3.1 비용 확인

- Azure Cost Management에서 월 누적 비용을 확인한다.
- 목표: 월 $6.50 미만. $6.50 초과 시 경고, $8.00 초과 시 재경고.
- 비용이 높으면 운영 시간을 줄이거나(주중 3시간→2.5시간) 주말 운영을 수동으로 중단한다.

### 3.2 성능 리뷰

- `incenstore`의 `results/meta/*.json` 파일들을 다운로드하여 `avg_chunk_sec`의 추이를 확인한다.
- 30일 평균 대비 20% 이상 증가하면 청크 수 조정 또는 모델 양자화 수준 변경을 검토한다.

### 3.3 Spot 가격 변동 확인

- GitHub Actions의 가격 모니터링(`price-monitor.yaml`) 리포트를 확인한다.
- 인도 중부 Spot 가격이 $0.020 이상으로 상승하면 한국 중부 Spot으로 임시 전환을 고려한다.

### 3.5 단계 전환: 초기(IP 할당) → 안정화(IP 미할당)

- **전환 기준**: 2주 연속 CRITICAL 알림 없이 모든 분석이 SUCCESS로 완료
- **전환 방법**:
  1. 배포 스크립트(`deploy.sh`) 내 `PUBLIC_IP_ENABLED` 값을 `true`에서 `false`로 변경
  2. GitHub Actions 워크플로우 `temp-ip.yaml`이 정상 동작하는지 확인
  3. 필요시 수동 IP attach/detach 절차(4.5절) 숙지
- **예상 절감 효과**: IP 예약 및 사용 비용 연간 약 $35

## 4. 수동 개입 절차

### 4.1 VM 수동 생성

```bash
# 초기 단계(IP 할당)
az vm create --resource-group Neuron_group --name manual-vm --location centralindia --gallery-image NeuronGallery/neuron-golden/1.0.0 --size Standard_E2ads_v6 --admin-username azureuser --ssh-key-values ~/.ssh/id_rsa.pub --os-disk-size-gb 32 --os-disk-type StandardSSD_LRS --priority Regular --public-ip-address Standard

# 안정화 단계(IP 없음)
az vm create --resource-group Neuron_group --name manual-vm --location centralindia --gallery-image NeuronGallery/neuron-golden/1.0.0 --size Standard_E2ads_v6 --admin-username azureuser --ssh-key-values ~/.ssh/id_rsa.pub --os-disk-size-gb 32 --os-disk-type StandardSSD_LRS --priority Regular --public-ip-address ""
```

### 4.2 모델 파일 교체

- 새 모델 GGUF 파일을 `incenstore`의 `models` 컨테이너에 업로드한다.
- `kocenstore`의 `models` 컨테이너에도 동일 파일을 수동으로 복사한다.

### 4.3 데이터셋 청크 수 변경

- Golden Image를 다시 빌드해야 한다.
- `/usr/local/share/datasets/` 디렉토리 내 `wikitext_chunk_*.txt` 파일 개수를 15개로 줄인다.
- 이미지를 다시 만들고 Azure Compute Gallery(`NeuronGallery/neuron-golden/1.0.0`)에 복제한다.

### 4.4 zRAM 크기 조정 (임시)

VM이 실행 중일 때 SSH로 접속하여 다음 명령어를 실행한다.

```bash
sudo swapoff /dev/zram0
echo 2G > /sys/block/zram0/disksize
sudo swapon /dev/zram0 -p 100
```

### 4.5 GitHub Actions 임시 디버깅 IP (안정화 단계)

안정화 단계에서 긴급 디버깅이 필요하면 GitHub Actions 워크플로우 `temp-ip.yaml`을 수동 실행한다.

1. GitHub 저장소 → Actions → **"Attach Temporary IP for Debugging"** → **"Run workflow"**
2. 워크플로우가 실행 중인 VM을 찾아 임시 IP를 생성하고 연결함
3. 로그에 출력된 IP 주소 확인 (`Temporary IP: x.x.x.x`)
4. SSH 접속: `ssh azureuser@<IP>`
5. 워크플로우는 **30분 동안 대기**하며, VM이 회수(삭제)되면 즉시 IP를 정리함 (단, 분석 시작 신호 파일 생성 후부터 감지 시작)
6. 30분이 지나거나 VM이 사라지면 IP를 **자동으로 삭제**하여 비용 발생 방지
7. 워크플로우 마지막에 IP 삭제를 재확인함

**참고**: VM이 실행 중이지 않으면 워크플로우가 실패한다. 이 경우 수동으로 VM을 먼저 실행하거나 `deploy.sh`를 실행한 후 워크플로우를 다시 실행한다.

## 5. 복구 시나리오

### 5.1 last_incomplete.json 손실

시스템은 최근 3일간의 meta 파일에서 자동으로 복구한다. 수동 조치 불필요.

### 5.2 performance_baseline.json 손실

기본값 150초를 사용한다. 최초 SUCCESS 발생 시 새 baseline이 저장된다.

### 5.3 Storage Account 접근 불가

Managed Identity(`NeuronIdentity`)의 RBAC 권한을 확인한다. 필요시 재할당한다.

### 5.4 GitHub Actions 실패

로컬에서 `deploy.sh`를 수동 실행한다. 크론 일정은 GitHub 웹 콘솔에서 재설정한다.
