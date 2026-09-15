#!/usr/bin/env bats
# domain/school.sh에 대한 Bats 테스트

load '../../../domain/school.sh'

@test "select_nice_code 함수가 정의되어 있다" {
    run declare -f select_nice_code
    [ "$status" -eq 0 ]
}

@test "input_school_info 함수가 정의되어 있다" {
    run declare -f input_school_info
    [ "$status" -eq 0 ]
}

@test "save_school_info 함수가 정의되어 있다" {
    run declare -f save_school_info
    [ "$status" -eq 0 ]
}

@test "select_nice_code에서 서울(sen)을 선택한다 (모의 입력)" {
    # select는 사용자 입력을 기다리므로 테스트하기 어려움
    skip "대화형 함수 테스트는 복잡함"
}