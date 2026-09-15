#!/usr/bin/env bash
# runners/deploy.sh - 전체 배포 워크플로우 실행 (Python 위임)
# 이 스크립트는 Python CLI로 위임합니다. 기존 Bash 모듈 소싱을 중단합니다.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Python 스크립트 실행
exec python3 "$SCRIPT_DIR/deploy.py" "$@"