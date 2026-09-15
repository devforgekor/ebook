#!/usr/bin/env bats
# infrastructure/azure/deploy.py에 대한 Bats 테스트 (구문 검증)

@test "deploy.py 구문이 올바르다" {
  run python3 -m py_compile "../../../../infrastructure/azure/deploy.py"
  [ "$status" -eq 0 ]
}

@test "deploy.py 모듈 임포트 가능" {
  run python3 -c "import sys; sys.path.insert(0, '../../../../'); from infrastructure.azure.deploy import bicep_build; print('ok')"
  [ "$status" -eq 0 ]
  [ "$output" = "ok" ]
}

@test "deploy_main_bicep 함수는 Python 모듈로 이동했으므로 스킵" {
  skip "기존 Bash 함수는 Python 모듈로 이전됨"
}