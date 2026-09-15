# 아키텍처 결정 기록: Container Apps vs Azure Functions

## 상태
제안 (Proposed)

## 날짜
2026‑04‑18

## 결정자
팀 내 기술 검토 회의

## 문제
학교 기록 관리 시스템의 배포 후 모니터링 및 로그 수집 기능을 구현할 때, 서버리스(Functions)와 컨테이너 기반(Container Apps) 중 어느 것을 선택할지 결정해야 합니다.

## 고려 사항

### Azure Functions
- **장점**: 이벤트 기반, 초기 비용 저렴, 자동 스케일링, 관리 오버헤드 낮음
- **단점**: 최대 실행 시간 제한(10분), Cold Start 지연, VNet 통합 복잡도

### Container Apps
- **장점**: 제한 없는 실행 시간, 사용자 정의 컨테이너 이미지, 내부 VNet 통합 용이, 다중 리비전 배포
- **단점**: 기본적으로 항상 실행되므로 비용이 높을 수 있음, 컨테이너 이미지 빌드/관리 필요

## 결정
**Container Apps**를 선택합니다.

이유:
1. 모니터링 및 로그 수집 작업은 장시간 실행될 수 있으며, Functions의 시간 제한을 우회해야 합니다.
2. 학교별로 격리된 환경(VNet)에서 실행해야 하므로 Container Apps의 네트워킹 기능이 더 적합합니다.
3. 향후 머신러닝 모델 서빙 등 컨테이너 기반 확장이 용이합니다.

## 영향
- 배포 스크립트(`infrastructure/azure/containerapps.sh`)를 사용하여 Container Apps 환경을 프로비저닝해야 합니다.
- 기존 Functions 관련 코드(`infrastructure/azure/functions.sh`)는 다른 단기 작업에만 사용됩니다.

## 참조
- [Azure Container Apps 문서](https://learn.microsoft.com/ko-kr/azure/container-apps/)
- [Azure Functions 한계](https://learn.microsoft.com/ko-kr/azure/azure-functions/functions-scale)