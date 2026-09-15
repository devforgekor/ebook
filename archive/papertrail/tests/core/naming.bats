#!/usr/bin/env bats
# core/naming.sh에 대한 Bats 테스트

load '../../../core/naming.sh'

setup() {
    # 각 테스트 전에 전역 변수 초기화
    unset BASE_NAME SAFE_BASE RESOURCE_GROUP STORAGE_ACCOUNT KEYVAULT \
          CONTAINER_APP FUNCTION_APP ACR LOG_ANALYTICS IDENTITY \
          SHARED_RG SHARED_COSMOS SHARED_ENV \
          LEGACY_RG LEGACY_KV LEGACY_STORAGE LEGACY_COSMOS LEGACY_ACR LEGACY_ENV_NAME LEGACY_APP
}

@test "generate_resource_names가 올바른 BASE_NAME을 생성한다" {
    generate_resource_names "test" "sen" "hs" "t" "01"
    [ "$BASE_NAME" = "testsenhst01" ]
}

@test "generate_resource_names가 올바른 SAFE_BASE를 생성한다" {
    generate_resource_names "test" "sen" "hs" "t" "01"
    [ "$SAFE_BASE" = "testsenhst01" ]
}

@test "generate_resource_names가 올바른 RESOURCE_GROUP을 생성한다" {
    generate_resource_names "test" "sen" "hs" "t" "01"
    [ "$RESOURCE_GROUP" = "rg-testsenhst01" ]
}

@test "generate_resource_names가 올바른 STORAGE_ACCOUNT을 생성한다" {
    generate_resource_names "test" "sen" "hs" "t" "01"
    [ "$STORAGE_ACCOUNT" = "sttestsenhst01" ]
}

@test "generate_resource_names가 올바른 KEYVAULT을 생성한다" {
    generate_resource_names "test" "sen" "hs" "t" "01"
    [ "$KEYVAULT" = "kv-testsenhst01" ]
}

@test "generate_resource_names가 올바른 CONTAINER_APP을 생성한다" {
    generate_resource_names "test" "sen" "hs" "t" "01"
    [ "$CONTAINER_APP" = "app-testsenhst01" ]
}

@test "generate_resource_names가 올바른 FUNCTION_APP을 생성한다" {
    generate_resource_names "test" "sen" "hs" "t" "01"
    [ "$FUNCTION_APP" = "func-testsenhst01" ]
}

@test "generate_resource_names가 올바른 ACR을 생성한다" {
    generate_resource_names "test" "sen" "hs" "t" "01"
    [ "$ACR" = "acrtestsenhst01" ]
}

@test "generate_resource_names가 올바른 LOG_ANALYTICS을 생성한다" {
    generate_resource_names "test" "sen" "hs" "t" "01"
    [ "$LOG_ANALYTICS" = "law-testsenhst01" ]
}

@test "generate_resource_names가 올바른 IDENTITY을 생성한다" {
    generate_resource_names "test" "sen" "hs" "t" "01"
    [ "$IDENTITY" = "id-testsenhst01" ]
}

@test "generate_shared_names가 올바른 SHARED_RG을 생성한다" {
    generate_shared_names "test" "sen" "hs" "krc"
    [ "$SHARED_RG" = "rg-shared-infra-testsenhs-krc00" ]
}

@test "generate_shared_names가 올바른 SHARED_COSMOS을 생성한다" {
    generate_shared_names "test" "sen" "hs" "krc"
    [ "$SHARED_COSMOS" = "cosmos-ssot-testsenhs-krc00" ]
}

@test "generate_shared_names가 올바른 SHARED_ENV을 생성한다" {
    generate_shared_names "test" "sen" "hs" "krc"
    [ "$SHARED_ENV" = "env-ssot-testsenhs-krc00" ]
}

@test "generate_legacy_school_names가 올바른 LEGACY_RG을 생성한다" {
    generate_legacy_school_names "test" "krc"
    [ "$LEGACY_RG" = "rg-school-test-krc" ]
}

@test "generate_legacy_school_names가 올바른 LEGACY_KV을 생성한다" {
    generate_legacy_school_names "test" "krc"
    [ "$LEGACY_KV" = "kv-school-test-krc01" ]
}

@test "generate_legacy_school_names가 올바른 LEGACY_STORAGE을 생성한다" {
    generate_legacy_school_names "test" "krc"
    # 하이픈 제거 후 st 접두사 추가
    [ "$LEGACY_STORAGE" = "stschooltestkrc02" ]
}

@test "generate_legacy_school_names가 올바른 LEGACY_COSMOS을 생성한다" {
    generate_legacy_school_names "test" "krc"
    [ "$LEGACY_COSMOS" = "cosmos-school-test-krc01" ]
}

@test "generate_legacy_school_names가 올바른 LEGACY_ACR을 생성한다" {
    generate_legacy_school_names "test" "krc"
    [ "$LEGACY_ACR" = "acrschooltestkrc01" ]
}

@test "generate_legacy_school_names가 올바른 LEGACY_ENV_NAME을 생성한다" {
    generate_legacy_school_names "test" "krc"
    [ "$LEGACY_ENV_NAME" = "env-school-test-krc01" ]
}

@test "generate_legacy_school_names가 올바른 LEGACY_APP을 생성한다" {
    generate_legacy_school_names "test" "krc"
    [ "$LEGACY_APP" = "app-school-test-krc01" ]
}