#!/usr/bin/env bash
# collector/utils/retry.sh – 재시도 유틸리티
# collector 스크립트에서 일시적 오류를 재시도할 때 사용합니다.
# 라이브러리 파일이므로 set -euo pipefail은 함수 내부에서만 적용됩니다.

# 재시도 실행
# 사용법: retry <최대시도횟수> <초기지연> <백오프인자> <명령어>
retry() {
    set -euo pipefail
    local max_attempts=$1
    local initial_delay=$2
    local backoff_factor=$3
    shift 3
    local command=("$@")
    local attempt=1
    local delay=$initial_delay

    while [[ $attempt -le $max_attempts ]]; do
        echo "[재시도 $attempt/$max_attempts] 실행: ${command[*]}" >&2
        if "${command[@]}"; then
            return 0
        fi
        echo "[재시도 $attempt/$max_attempts] 실패, $delay초 후 재시도..." >&2
        sleep $delay
        delay=$((delay * backoff_factor))
        ((attempt++))
    done

    echo "[재시도] 최대 시도 횟수($max_attempts) 초과, 명령어 실패: ${command[*]}" >&2
    return 1
}

# 간단한 재시도 (기본값: 3회 시도, 5초 시작, 백오프 2)
# 사용법: retry_default <명령어>
retry_default() {
    set -euo pipefail
    retry 3 5 2 "$@"
}

# 독립 실행 테스트
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    set -euo pipefail
    echo "=== collector/utils/retry.sh 테스트 ===" >&2
    # 실패할 명령어 (항상 실패)
    if retry_default false; then
        echo "테스트 실패: 재시도가 성공했지만 예상대로 실패해야 합니다." >&2
        exit 1
    else
        echo "재시도 테스트 통과: 명령어가 예상대로 실패했습니다." >&2
    fi
    # 성공할 명령어
    if retry_default echo "테스트 성공"; then
        echo "재시도 테스트 통과: 명령어가 성공했습니다." >&2
    else
        echo "테스트 실패: 성공해야 하는 명령어가 실패했습니다." >&2
        exit 1
    fi
fi
