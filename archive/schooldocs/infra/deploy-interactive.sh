#!/usr/bin/env bash
# SchoolDocs Azure 배포 스크립트 (모듈화 버전 호출)
# 기존 스크립트는 papertrail/runners/deploy.sh로 대체되었습니다.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

exec "$REPO_ROOT/papertrail/runners/deploy.sh" "$@"
