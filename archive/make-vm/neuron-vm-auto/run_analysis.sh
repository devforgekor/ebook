#!/bin/bash
set -e

# ==================== 환경 감지 ====================
KST_WEEKDAY=$(TZ=Asia/Seoul date +%u)
if [ $KST_WEEKDAY -le 5 ]; then
  BASE_HOURS=3
else
  BASE_HOURS=2
fi

REGION=$(curl -s -H Metadata:true "http://169.254.169.254/metadata/instance/compute/location?api-version=2017-08-01&format=text")
if [[ "$REGION" == "centralindia" ]]; then
  ACCOUNT="${ACCOUNT_INDIA}"
else
  ACCOUNT="${ACCOUNT_KOREA}"
fi

SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."

send_slack_alert() {
  local LEVEL=$1
  local MESSAGE=$2
  local KST_TIME=$(TZ=Asia/Seoul date +"%Y-%m-%d %H:%M:%S")
  if [ "$LEVEL" = "CRITICAL" ]; then
    curl -X POST -H 'Content-type: application/json' --data "{\"text\":\"[$LEVEL] The Axis ($KST_TIME KST): $MESSAGE\"}" "$SLACK_WEBHOOK_URL" 2>/dev/null
  else
    echo "$(date -u) [WARNING] $MESSAGE" >> /tmp/warnings.log
    az storage blob upload --container logs --name warnings.log --file /tmp/warnings.log --account-name $ACCOUNT 2>/dev/null
  fi
}

# ==================== 상태 복구 ====================
recover_state() {
  if az storage blob exists --container state --name last_incomplete.json --account-name $ACCOUNT; then
    az storage blob download --container state --name last_incomplete.json --file /tmp/last_incomplete.json --account-name $ACCOUNT
    PENDING_COUNT=$(jq '.incomplete_chunks | length' /tmp/last_incomplete.json 2>/dev/null || echo 0)
    if [ "$PENDING_COUNT" -gt 0 ]; then
      echo "$PENDING_COUNT"
      return
    fi
  fi
  for DAY in 1 2 3; do
    META_FILE="meta/$(date -d "-$DAY days" +%Y%m%d).json"
    if az storage blob exists --container results --name $META_FILE --account-name $ACCOUNT; then
      STATUS=$(az storage blob download --file - --name $META_FILE --account-name $ACCOUNT | jq -r '.status')
      if [ "$STATUS" = "PARTIAL" ]; then
        LAST_CHUNK=$(az storage blob download --file - --name $META_FILE --account-name $ACCOUNT | jq -r '.last_completed_chunk_index')
        PENDING=$((20 - LAST_CHUNK - 1))
        echo "$PENDING"
        return
      fi
    fi
  done
  echo "0"
}

PENDING=$(recover_state)
if [ $PENDING -gt 0 ]; then
  ANALYSIS_HOURS=$((BASE_HOURS + 1))
else
  ANALYSIS_HOURS=$BASE_HOURS
fi

THREADS=2
if az storage blob exists --container state --name tuning_flag.json --account-name $ACCOUNT; then
  az storage blob download --file /tmp/tuning_flag.json --name tuning_flag.json --account-name $ACCOUNT
  if [ "$(jq -r '.need_tuning' /tmp/tuning_flag.json)" = "true" ]; then
    THREADS=1
    az storage blob delete --container state --name tuning_flag.json --account-name $ACCOUNT
  fi
fi

ANALYSIS_TIMEOUT_SEC=$((ANALYSIS_HOURS * 3600))

# ==================== 분석 실행 ====================
CHUNK_DIR="/usr/local/share/datasets"
CHUNK_LIST=($(ls $CHUNK_DIR/wikitext_chunk_*.txt | sort))
TOTAL_CHUNKS=${#CHUNK_LIST[@]}
RESULT_DIR="/tmp/results"
mkdir -p $RESULT_DIR

START_TIME=$(date +%s)
COMPLETED=0
INCOMPLETE_ARRAY=()
RSS_PEAK_MB=0
SWAP_IN_KB=0

for i in "${!CHUNK_LIST[@]}"; do
  if [ $(($(date +%s) - START_TIME)) -ge $ANALYSIS_TIMEOUT_SEC ]; then
    STATUS="PARTIAL"
    break
  fi
  CHUNK="${CHUNK_LIST[$i]}"
  CHUNK_NAME=$(basename "$CHUNK" .txt)
  BEFORE_RSS=$(awk '/^VmRSS:/ {print $2}' /proc/self/status 2>/dev/null || echo 0)
  nice -n -10 perplexity -m "/mnt/models/model.gguf" -f "$CHUNK" -t $THREADS -c 2048 --ctk q4_0 --ctv q4_0 -b 256 > "$RESULT_DIR/${CHUNK_NAME}.txt"
  AFTER_RSS=$(awk '/^VmRSS:/ {print $2}' /proc/self/status 2>/dev/null || echo 0)
  CHUNK_RSS=$((AFTER_RSS - BEFORE_RSS))
  if [ $CHUNK_RSS -gt $RSS_PEAK_MB ]; then
    RSS_PEAK_MB=$CHUNK_RSS
  fi
  SWAP_BEFORE=$(awk '/^Swap:/ {print $2}' /proc/self/status 2>/dev/null || echo 0)
  SWAP_AFTER=$(awk '/^Swap:/ {print $2}' /proc/self/status 2>/dev/null || echo 0)
  SWAP_IN_KB=$((SWAP_IN_KB + SWAP_AFTER - SWAP_BEFORE))
  gzip -c "$RESULT_DIR/${CHUNK_NAME}.txt" > "$RESULT_DIR/${CHUNK_NAME}.txt.gz"
  nice -n 19 ionice -c 3 az storage blob upload --container results --file "$RESULT_DIR/${CHUNK_NAME}.txt.gz" --name "result_$(date +%Y%m%d)_${CHUNK_NAME}.txt.gz" --account-name $ACCOUNT
  COMPLETED=$((i+1))
done

if [ $COMPLETED -eq $TOTAL_CHUNKS ]; then
  STATUS="SUCCESS"
else
  STATUS="PARTIAL"
  for j in $(seq $COMPLETED $((TOTAL_CHUNKS-1))); do
    INCOMPLETE_ARRAY+=($j)
  done
fi

# ==================== 상태 저장 ====================
if [ "$STATUS" = "PARTIAL" ]; then
  jq -n --argjson chunks "$(echo ${INCOMPLETE_ARRAY[@]} | jq -R 'split(" ") | map(tonumber)')" '{date: "'$(date +%Y-%m-%d)'", incomplete_chunks: $chunks}' > /tmp/last_incomplete.json
  az storage blob upload --container state --name last_incomplete.json --file /tmp/last_incomplete.json --account-name $ACCOUNT
  PREV_STATUS=$(az storage blob download --file - --name "meta/$(date -d 'yesterday' +%Y%m%d).json" --account-name $ACCOUNT 2>/dev/null | jq -r '.status')
  if [ "$PREV_STATUS" = "PARTIAL" ]; then
    send_slack_alert "CRITICAL" "2일 연속 PARTIAL ($COMPLETED/$TOTAL_CHUNKS)"
    PREV2_STATUS=$(az storage blob download --file - --name "meta/$(date -d '2 days ago' +%Y%m%d).json" --account-name $ACCOUNT 2>/dev/null | jq -r '.status')
    if [ "$PREV2_STATUS" = "PARTIAL" ]; then
      send_slack_alert "CRITICAL" "3일 연속 PARTIAL - 데이터 양 조절 필요"
    fi
  fi
fi

# ==================== 성능 모니터링 ====================
if [ $COMPLETED -gt 0 ]; then
  AVG_CHUNK_SEC=$(( ( $(date +%s) - START_TIME ) / COMPLETED ))
  BASELINE=150
  LATEST_SUCCESS=$(az storage blob list --container results --prefix meta/ --account-name $ACCOUNT --query "[?contains(name, 'meta/')] | sort_by(@, &name)[-1]" -o tsv 2>/dev/null)
  if [ -n "$LATEST_SUCCESS" ]; then
    BASELINE=$(az storage blob download --file - --name "$LATEST_SUCCESS" --account-name $ACCOUNT | jq -r '.avg_chunk_sec // 150')
  fi
  if [ $AVG_CHUNK_SEC -gt $((BASELINE * 130 / 100)) ]; then
    if [ -f /tmp/tuning_pending ]; then
      jq -n '{need_tuning: true, reason: "2일 연속 성능 저하", date: "'$(date +%Y-%m-%d)'"}' > /tmp/tuning_flag.json
      az storage blob upload --container state --name tuning_flag.json --file /tmp/tuning_flag.json --account-name $ACCOUNT
      send_slack_alert "CRITICAL" "성능 저하 2일 연속 - 튜닝 적용 예정"
      rm -f /tmp/tuning_pending
    else
      touch /tmp/tuning_pending
    fi
  else
    rm -f /tmp/tuning_pending
  fi
fi

# ==================== 메타데이터 저장 ====================
cat > $RESULT_DIR/meta_$(date +%Y%m%d).json << EOF
{
  "date": "$(date +%Y-%m-%d)",
  "region": "$REGION",
  "analysis_hours": $ANALYSIS_HOURS,
  "threads": $THREADS,
  "status": "$STATUS",
  "total_chunks": $TOTAL_CHUNKS,
  "completed_chunks": $COMPLETED,
  "avg_chunk_sec": $AVG_CHUNK_SEC,
  "rss_peak_mb": $RSS_PEAK_MB,
  "swap_in_kb": $SWAP_IN_KB
}
EOF
az storage blob upload --container results --name "meta/$(date +%Y%m%d).json" --file "$RESULT_DIR/meta_$(date +%Y%m%d).json" --account-name $ACCOUNT

# ==================== 종료 ====================
sleep 120
az vm stop --resource-group $RG --name $(hostname) --no-wait
