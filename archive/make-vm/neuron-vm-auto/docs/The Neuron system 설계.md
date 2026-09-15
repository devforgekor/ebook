# The Neuron system 설계

## 1. 목표 및 제약

- Azure for Students 구독을 사용하며 연간 예산은 $100이다.
- 목표는 13B급 LLM의 성능 분석(Perplexity, bench, embedding 등)을 자동화하는 것이다.
- 매일 VM을 생성하고 작업이 완료되면 VM과 디스크를 완전히 삭제하는 Stateless 방식으로 운영한다.
- 사용 가능한 VM 크기는 **Standard_E2ads_v6** (2 vCPU, 16GB RAM, 110GB NVMe 임시 디스크)를 사용한다.
- 주 운영 리전은 Central India(인도 중부)이며, 장애 조치 리전은 Korea Central(한국 중부)이다.
- 모든 시간 정책은 KST(한국 표준시) 기준으로 판단하되, 시스템 내부 시간은 UTC로 처리한다.

## 2. 운영 시간 정책

- **평일(월~금)**: 오전 9시, 오후 10시 두 번 실행한다. 각 실행 기본 분석 시간은 3시간이며, 전날 미완료 청크가 존재하면 4시간으로 연장한다.
- **토요일**: 실행하지 않는다. (금요일 오후 10시 실행으로 커버)
- **일요일**: 오전 9시 한 번 실행한다. 기본 분석 시간은 4시간이며, 미완료 청크가 존재하면 5시간으로 연장한다.
- **VM 생성 재시도**:
  - 1사이클: 인도 중부 Spot VM을 최대 **2회(3분 간격)** 시도 → 실패 시 한국 중부 Spot VM을 최대 **2회(3분 간격)** 시도
  - 사이클 간 대기: **없음** (연속 시도)
  - **최대 2사이클** 반복 (최대 VM 생성 시도 시간: 약 24분)
- **Graceful 종료**:
  - 분석 상한 시간 **15분 전**이 되면 현재 진행 중인 청크를 완료한 후 분석을 종료한다. (추가 청크 미처리)
- **좀비 VM 정리 (안전장치)**:
  - 분석 스크립트(`run_analysis.sh`)가 정상 종료 시 `az vm delete --os-disk-delete-option Delete`로 VM과 OS 디스크를 완전 삭제한다.
  - 만약 정상 종료에 실패하면 GitHub Actions `force-stop.yaml`이 **분석 시작 후 (분석 상한 시간 + 10분)** 이 지난 VM을 좀비로 간주하고 강제 삭제한다.
  - 구체적인 강제 종료 시각(KST):
    - 평일 기본 (09:00 시작): **12:10 KST** (3h + 10m)
    - 평일 연장 (09:00 시작): **13:10 KST** (4h + 10m)
    - 평일 기본 2차 (22:00 시작): **01:10 KST** (다음날)
    - 평일 연장 2차 (22:00 시작): **02:10 KST** (다음날)
    - 일요일 기본 (09:00 시작): **13:10 KST**
    - 일요일 연장 (09:00 시작): **14:10 KST**

## 3. 장애 조치 흐름

- **할당량 확인 없음**: VM 생성 실패 시 바로 재시도 (별도 사전 확인 없음)
- **1사이클**: 인도 중부 Spot VM을 최대 2회(3분 간격) 시도 → 실패 시 한국 중부 Spot VM을 최대 2회(3분 간격) 시도
- **최대 2사이클** 반복 (사이클 간 대기 없음)
- 2사이클 후에도 VM 생성에 실패하면 CRITICAL 알림을 보내고 **해당 실행을 종료**한다.
- 종료된 실행은 **같은 날의 다음 실행(오후 10시) 또는 다음날 오전 9시에 재시도**한다.
- (참고: `Standard_E2ads_v6` 크기는 현재 종량제로 제공되지 않으므로 종량제 fallback은 수행하지 않음. 추후 종량제 VM이 제공되면 별도 계획 수립)

## 4. 종량제 카운터 정책 (향후 적용 예정)

> **현재 상태**: Azure for Students 구독에서는 `Standard_E2ads_v6` 크기의 종량제 VM을 생성할 수 없다. 따라서 아래 정책은 현재 적용되지 않으며, 추후 종량제 VM을 사용할 수 있게 되면 활성화한다.

**원래 계획 (장애 조치 순서)**:
1. 인도 중부 Spot
2. 한국 중부 Spot
3. 인도 중부 종량제
4. 한국 중부 종량제

이 순서에 따라 종량제 fallback이 발생하면 카운터를 증가시키고, 주중 2회 이상 발생 시 해당 주 주말 운영을 자동으로 건너뛴다.

## 5. 저장소 구성

- 인도 중부 Storage Account `incenstore`에 `items` 컨테이너를 둔다.
- 한국 중부 Storage Account `kocenstore`에 `items` 컨테이너를 둔다.
- 모델 파일은 인도 중부를 기준으로 하며, 한국 중부는 초기 1회 수동 복사한다.
- 분석 결과는 매일 인도 중부에서 한국 중부로 AzCopy를 통해 복제한다.
- 상태 파일(last_incomplete.json)은 인도 중부에 저장하며, 이력 파일(meta/YYYYMMDD.json)을 통해 복구 가능하다.

## 6. 디스크 정책

- OS 디스크는 **Standard SSD 32GB**를 사용한다. VM 삭제 시 `--os-disk-delete-option Delete` 옵션으로 함께 삭제한다.
- VM에 포함된 **Local NVMe 임시 디스크(110GB)**를 작업 디스크로 사용하며, `/mnt`에 마운트된다. 분석 중 생성되는 청크, 모델 캐시, 임시 결과를 저장한다.
- VM 생성 시 Expires 태그를 **분석 시작 시간 + (분석 시간 + 10분)** 으로 설정한다. (예: 3시간 분석 시 3시간 10분 후 만료)
- VM 삭제 후 **40초** 대기 후 재확인하여 삭제 실패 시 재시도한다.
- GitHub Actions에서 매일 만료된 디스크를 정리한다.

## 6.5 네트워크 및 공용 IP 정책 (단계별)

Spot VM은 수명이 짧고(최대 3~4시간) 매일 삭제되므로, IP 관리는 단계별로 단순하게 접근한다.

### 6.5.1 초기 단계 (개발/테스트)
- VM 생성 시 `--public-ip-address Standard` 옵션으로 임시 공용 IP를 자동 생성한다.
- VM이 삭제될 때 Azure가 해당 IP를 자동으로 함께 삭제하므로 별도의 IP 제거 로직은 필요 없다.
- 목적: SSH 직접 접속으로 디버깅, 로그 확인, 수동 개입.
- 설정: 배포 스크립트(`deploy.sh`) 내 `PUBLIC_IP_ENABLED=true`

### 6.5.2 안정화 단계 (운영)
- VM 생성 시 공용 IP를 할당하지 않는다 (`PUBLIC_IP_ENABLED=false`).
- 일상적인 분석에서는 IP가 전혀 필요 없으므로 비용 $0.
- 필요시(긴급 디버깅): GitHub Actions 수동 워크플로우(`temp-ip.yaml`)를 실행하여 임시 IP를 생성/연결/자동 제거한다.
  - 대기 시간: 30분 (VM이 중간에 회수되면 즉시 정리)
  - IP 리소스는 어떤 경우에도 남기지 않음 (무조건 삭제)

### 6.5.3 전환 조건
- 2주 연속 CRITICAL 알림 없이 모든 분석이 SUCCESS로 완료되면 안정화 단계로 전환한다.
- 전환 시 배포 스크립트(`deploy.sh`)의 `PUBLIC_IP_ENABLED`를 `false`로 변경한다.

## 7. 인증 및 권한

- User-Assigned Managed Identity `NeuronIdentity`를 사용한다.
- Managed Identity에 `incenstore`와 `kocenstore`에 대해 Storage Blob Data Reader와 Storage Blob Data Contributor 권한을 할당한다.
- VM 생성 시 `--assign-identity`로 Managed Identity를 할당한다.
- Cloud-init 내에서 `az login --identity`로 인증한다.

## 8. 성능 자동 튜닝

- 매일 분석 완료 후 평균 청크 처리 시간(avg_chunk_sec)을 계산한다.
- 성공적인 실행일(SUCCESS)의 avg_chunk_sec을 baseline으로 저장한다(performance_baseline.json).
- 2일 연속 avg_chunk_sec이 baseline 대비 30% 이상 증가하면 tuning_flag.json을 생성한다.
- 다음날 분석 시작 시 tuning_flag.json이 존재하면 perplexity 실행 시 -t 2 대신 -t 1을 사용한다.
- 튜닝 적용 후 baseline은 성공 시 자연스럽게 갱신된다.

## 9. 증분 처리 및 상태 복구

- 분석 중 시간 초과로 PARTIAL이 발생하면 미완료 청크 인덱스를 last_incomplete.json에 저장한다.
- 다음날 분석 시작 시 last_incomplete.json을 읽어 미완료 청크부터 우선 처리한다.
- last_incomplete.json이 없거나 손상된 경우, 최근 3일간의 meta/YYYYMMDD.json 파일을 스캔하여 마지막 성공/실패 지점을 복구한다.

## 10. Cloud-init 설정

- VM 부팅 시 zRAM(4GB, lz4, priority 100)을 활성화한다.
- Managed Identity로 로그인한다(타임아웃 10분).
- 리전에 맞는 Storage Account에서 llama.cpp 바이너리와 요일별 모델 파일을 다운로드한다.
- 동일 리전(인도)에서는 **blobfuse2**(Golden Image에 포함, 필수 설치)를 사용하여 `incenstore`의 `items` 컨테이너를 `/mnt/blob`에 마운트하고, NVMe 캐시(`/mnt/cache`)를 활용한다.
  - (참고: blobfuse2 마운트 실패율이 높을 경우 추후 `az storage blob download` 방식으로 fallback할 수 있음)
- 모든 준비가 완료되면 /tmp/ready 파일을 생성한다.
- 배포 스크립트(`deploy.sh`)는 /tmp/ready 파일이 생성될 때까지 최대 10분간 대기하며, 실패 시 VM을 삭제하고 CRITICAL 알림을 보낸다.

## 11. GitHub Actions

- **강제 종료 (`force-stop.yaml`)**:
  - 분석 시작 신호 파일(`analysis_started_*.json`)을 확인하여, 분석 시작 후 (분석 상한 시간 + 10분)이 지났을 때 VM을 강제 종료한다.
  - 신호 파일이 없는 경우, fallback 시간(오전 9시 + (분석 상한 시간 + 10분) 등)이 지나면 무조건 VM을 강제 종료한다.
  - 만료 태그가 지난 디스크와 남은 임시 IP도 정리한다.
- **가격 모니터링 (`price-monitor.yaml`)**: 3일 주기로 Azure API(`az vm spot-price list`)를 통해 인도/한국 Spot 가격을 조회하여 10% 이상 변동 시 Slack CRITICAL 알림을 보낸다.
- **임시 디버깅 IP (`temp-ip.yaml`)**: 안정화 단계에서 수동 실행하여 30분간 임시 공용 IP를 VM에 연결하고, VM 회수 또는 시간 만료 시 자동으로 IP를 삭제한다. (분석 시작 신호 파일 생성 후부터 10초 간격으로 회수 감지)

## 12. 메타데이터 및 알림

- 매일 분석 결과는 meta/YYYYMMDD.json에 저장하며, region, vm_priority, analysis_hours, status, total_chunks, completed_chunks, avg_chunk_sec, rss_peak_mb, swap_in_kb 등의 필드를 포함한다.
- Slack 알림은 CRITICAL 등급만 보낸다: VM 생성 완전 실패, Cloud-init 실패, 2일/3일 연속 PARTIAL, 성능 저하 2일 연속, 강제 종료 실행, 주말 운영 스킵 (종량제 fallback 알림은 현재 없음)
- WARNING 수준 알림은 Blob 로그(warnings.log)에만 기록한다.
- 월간 리포트는 GitHub Actions로 주 1회 생성하여 Slack에 요약을 전송한다.

## 13. 배포 전 확인 사항

- Storage Account 이름: `incenstore`(인도 중부), `kocenstore`(한국 중부)
- 구독 ID, 리소스 그룹명(`Neuron_group`), Managed Identity(`NeuronIdentity`) 확인
- Managed Identity에 두 Storage Account에 대해 Storage Blob Data Reader와 Storage Blob Data Contributor 권한이 할당되었는지 확인
- Golden Image: `NeuronGallery/neuron-golden/1.0.0`이 인도/한국 리전에 복제되었는지 확인
- VNet: 인도 중부 `neuron-vm-vnet-in`, 한국 중부 `neuron-vm-vnet-kr`
- Slack Webhook URL 설정
- GitHub Actions secrets에 AZURE_CREDENTIALS와 SLACK_WEBHOOK_URL 등록
- Azure Cost Management에 $6.50 경고, $8.00 재경고 알림 설정
- 배포 스크립트 실행 환경의 date 명령어 호환성 확인

## 14. 배포 스크립트 구조

- `deploy.sh`: VM 생성, 장애 조치, Cloud-init 전달, 분석 스크립트 전송, 종료 처리
- `run_analysis.sh`: 상태 복구, 분석 실행, 메타데이터 저장, 성능 모니터링, 튜닝 플래그 설정, 분석 시작 신호 파일 생성
- `force-stop.yaml` (GitHub Actions): 강제 종료, 고아 디스크 정리, 임시 IP 정리
- `price-monitor.yaml` (GitHub Actions): Spot 가격 모니터링 (Azure API 기반)
- `temp-ip.yaml` (GitHub Actions, 안정화 단계용): 임시 디버깅 IP 생성/연결/자동 정리

## 15. 파일 및 디렉터리 구조(Golden Image)

- /usr/local/share/datasets/wikitext_chunk_*.txt: 분할된 표준 데이터셋(Overlap 적용, 20개 청크)
- /etc/neuron-memory.sh: zRAM 및 스왑 설정 스크립트
- /usr/local/bin/perplexity: llama.cpp 바이너리(Blob에서 다운로드)
- /mnt/models/: 모델 파일 저장 위치(Blob에서 다운로드)
- /tmp/results/: 분석 결과 임시 저장 위치
- /tmp/ready: Cloud-init 완료 신호 파일

이상으로 The Neuron system 설계 문서를 마칩니다.
