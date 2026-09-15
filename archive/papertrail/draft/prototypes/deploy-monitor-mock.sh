#!/usr/bin/env bash
# 프로토타입: 배포 모니터링 로직 모의 실행
# 이 스크립트는 draft/prototypes/에 있으며, 검증 후 infrastructure/azure/deploy_monitor.sh로 이동할 수 있습니다.

set -euo pipefail

# 모의 배포 ID 생성
DEPLOYMENT_ID="mock-deploy-$(date +%s)"
echo "모의 배포 시작: $DEPLOYMENT_ID"

# 가짜 진행 단계 시뮬레이션
steps=("리소스 그룹 생성" "Bicep 템플릿 검증" "배포 실행" "컨테이너 앱 프로비저닝" "스모크 테스트")
for i in "${!steps[@]}"; do
    echo "단계 $((i+1))/${#steps[@]}: ${steps[$i]}"
    sleep 1
    # 20% 확률로 실패 시뮬레이션
    if (( RANDOM % 5 == 0 )); then
        echo "  [실패] 모의 오류 발생"
        exit 1
    fi
done

echo "모의 배포 완료: $DEPLOYMENT_ID"
echo "결과: SUCCESS"

# 이 스크립트의 목적:
# 1. 배포 모니터링 중 각 단계의 로깅 형식을 정의
# 2. 실패 처리 흐름을 실험
# 3. 실제 Azure CLI 호출 전 로직 검증
#
# 검증 후 다음 작업:
# - infrastructure/azure/deploy_monitor.sh의 monitor_deployment_with_spinner 함수에 통합
# - JSON 로깅 포맷 적용 (logging.sh 참조)