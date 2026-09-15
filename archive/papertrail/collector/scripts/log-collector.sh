#!/usr/bin/env bash
# collector/scripts/log‑collector.sh – Azure Monitor 로그 수집
# 이 스크립트는 컨테이너 앱의 최근 로그를 쿼리하여 JSON 파일로 저장합니다.

set -euo pipefail

# core 및 infrastructure 유틸리티 로드
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
source "$REPO_ROOT/core/utils.sh"
source "$REPO_ROOT/infrastructure/azure/logging.sh"

# 설정 변수
LOG_CATEGORY="${LOG_CATEGORY:-ContainerAppConsoleLogs}"
QUERY_TIME="${QUERY_TIME:-1h}"
OUTPUT_DIR="${OUTPUT_DIR:-collected}"
mkdir -p "$OUTPUT_DIR"

# Azure Log Analytics 작업 영역 확인
if [[ -z "${LOG_ANALYTICS_WORKSPACE:-}" ]]; then
    echo "[ERROR] LOG_ANALYTICS_WORKSPACE 환경 변수가 설정되지 않았습니다." >&2
    exit 1
fi

# 수집 시작 로깅
write_json_log "collector" "info" "로그 수집 시작" "category=$LOG_CATEGORY query_time=$QUERY_TIME"

# 쿼리 실행
TIMESTAMP=$(date -u +"%Y%m%dT%H%M%S")
OUTPUT_FILE="$OUTPUT_DIR/logs-$TIMESTAMP.json"

if az monitor log-analytics query \
    --workspace "$LOG_ANALYTICS_WORKSPACE" \
    --analytics-query "$LOG_CATEGORY | where TimeGenerated > ago($QUERY_TIME)" \
    --output json > "$OUTPUT_FILE"; then
    # 수집 성공
    COUNT=$(jq length "$OUTPUT_FILE" 2>/dev/null || echo "0")
    write_json_log "collector" "info" "로그 수집 완료" "file=$OUTPUT_FILE count=$COUNT"
    echo "수집 완료: $OUTPUT_FILE ($COUNT개 레코드)"
else
    # 실패
    write_json_log "collector" "error" "로그 수집 실패" "category=$LOG_CATEGORY"
    echo "[ERROR] 로그 쿼리 실패" >&2
    exit 1
fi

# 다음 단계: analyzer가 이 파일을 처리할 수 있도록 힌트 남기기
echo "다음 명령어로 분석을 실행하세요:"
echo "  node ../analyzer/scripts/trend-analysis.js $OUTPUT_FILE"