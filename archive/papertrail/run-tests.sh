#!/usr/bin/env bash
# Papertrail 프로젝트 테스트 실행 스크립트
# Bats 프레임워크를 사용하여 모든 테스트를 실행합니다.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Bats가 설치되어 있는지 확인
if ! command -v bats &>/dev/null; then
    echo "오류: Bats가 설치되지 않았습니다. 설치 방법: brew install bats-core" >&2
    exit 1
fi

# 테스트 디렉토리
TEST_DIR="tests"

# 모든 .bats 파일 찾기
TEST_FILES=()
while IFS= read -r file; do
    TEST_FILES+=("$file")
done < <(find "$TEST_DIR" -name "*.bats" -type f)

if [[ ${#TEST_FILES[@]} -eq 0 ]]; then
    echo "경고: 테스트 파일이 없습니다."
    exit 0
fi

# Bats 실행
echo "모든 테스트를 실행합니다..."
if bats "${TEST_FILES[@]}"; then
    echo "성공: 모든 테스트가 성공했습니다."
    exit 0
else
    echo "실패: 일부 테스트가 실패했습니다."
    exit 1
fi