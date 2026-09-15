#!/usr/bin/env bats
# cli/deploy.sh에 대한 Bats 테스트 (Python 위임 래퍼)

@test "deploy.sh 구문이 올바르다" {
    run bash -n "$BATS_TEST_DIRNAME/../../cli/deploy.sh"
    [ "$status" -eq 0 ]
    [ "$output" = "" ]
}

@test "deploy.sh가 Python 스크립트를 호출하는 래퍼이다" {
    # deploy.sh가 python3 명령어를 포함하는지 확인
    grep -q "python3.*deploy.py" "$BATS_TEST_DIRNAME/../../cli/deploy.sh"
}

@test "NON_INTERACTIVE=1일 때 대화형 프롬프트 없이 실행된다 (간접 검증)" {
    # 이 테스트는 실제로 스크립트를 실행하지 않고 환경 변수 설정을 확인만 합니다.
    # 스크립트를 실행하면 Azure 로그인 등으로 인해 실패할 수 있으므로 스킵.
    skip "실제 실행은 Azure 환경이 필요함"
}

@test "DEPLOY_WHAT_IF=1일 때 what-if 모드로 실행된다" {
    skip "실제 실행은 Azure 환경이 필요함"
}