#!/usr/bin/env bash
# schooldocs -> papertrail 마이그레이션 스크립트
# 파일 매핑 테이블에 따라 디렉토리 생성 및 파일 이동
# 주의: 기존 파일을 덮어쓰지 않으며, 원본 파일은 유지합니다 (복사).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "마이그레이션 시작: schooldocs -> papertrail 구조"

# 1. 필요한 디렉토리 생성
echo "디렉토리 생성 중..."
mkdir -p core/js/utils
mkdir -p core/data/schools
mkdir -p infrastructure/azure/js
mkdir -p infrastructure/azure/bicep/cosmos
mkdir -p infrastructure/azure/bicep/deploy
mkdir -p infrastructure/azure/bicep/rbac
mkdir -p domain/records/functions
mkdir -p domain/records/routes
mkdir -p domain/records/access
mkdir -p domain/records/models
mkdir -p domain/records/audit
mkdir -p domain/records/utils
mkdir -p cli/deploy
mkdir -p cli/api
mkdir -p cli/data
mkdir -p documentation/planed
mkdir -p documentation/prod-kuhwa-docs
mkdir -p draft/architecture
mkdir -p draft/prototypes
mkdir -p draft/meetings
mkdir -p collector/scripts
mkdir -p collector/config
mkdir -p collector/utils
mkdir -p analyzer/scripts
mkdir -p analyzer/reports
mkdir -p analyzer/models
mkdir -p analyzer/visualizations

# 2. core/js/utils/ 이동 (순수 유틸리티)
echo "core/js/utils/ 파일 복사..."
cp -n apps/records-api/src/utils/aiUtils.js core/js/utils/ 2>/dev/null || true
cp -n apps/records-api/src/utils/auditTrail.js core/js/utils/ 2>/dev/null || true
cp -n apps/records-api/src/utils/auth.js core/js/utils/ 2>/dev/null || true
cp -n apps/records-api/src/utils/cryptoUtils.js core/js/utils/ 2>/dev/null || true
cp -n apps/records-api/src/utils/pdfUtils.js core/js/utils/ 2>/dev/null || true

# 3. infrastructure/azure/js/ 이동 (Azure 연동)
echo "infrastructure/azure/js/ 파일 복사..."
cp -n apps/records-api/src/utils/cosmos.js infrastructure/azure/js/ 2>/dev/null || true
cp -n apps/records-api/src/utils/keyvault.js infrastructure/azure/js/ 2>/dev/null || true
cp -n apps/records-api/src/utils/storage.js infrastructure/azure/js/ 2>/dev/null || true
cp -n apps/records-api/src/cosmos.js infrastructure/azure/js/ 2>/dev/null || true
cp -n apps/records-api/src/localCosmos.js infrastructure/azure/js/ 2>/dev/null || true

# 4. domain/records/functions/ 이동
echo "domain/records/functions/ 파일 복사..."
cp -n apps/records-api/src/functions/*.js domain/records/functions/ 2>/dev/null || true

# 5. domain/records/routes/ 이동
echo "domain/records/routes/ 파일 복사..."
cp -n apps/records-api/src/routes/*.js domain/records/routes/ 2>/dev/null || true

# 6. domain/records/ 기타 파일 이동
echo "domain/records/ 기타 파일 복사..."
cp -n apps/records-api/src/adminAccess.js domain/records/access/ 2>/dev/null || true
cp -n apps/records-api/src/admins.js domain/records/models/ 2>/dev/null || true
cp -n apps/records-api/src/auditTrail.js domain/records/audit/ 2>/dev/null || true
cp -n apps/records-api/src/cohortUtils.js domain/records/utils/ 2>/dev/null || true
cp -n apps/records-api/src/documentTypes.js domain/records/models/ 2>/dev/null || true
cp -n apps/records-api/src/registry.js domain/records/models/ 2>/dev/null || true

# 7. infrastructure/azure/bicep/ 이동
echo "infrastructure/azure/bicep/ 파일 복사..."
cp -n infra/main.bicep infrastructure/azure/bicep/ 2>/dev/null || true
cp -n infra/main.subscription.bicep infrastructure/azure/bicep/ 2>/dev/null || true
cp -n infra/cosmos/cosmos.database.bicep infrastructure/azure/bicep/cosmos/ 2>/dev/null || true
cp -n infra/rbac/rbac.roleAssignment.bicep infrastructure/azure/bicep/rbac/ 2>/dev/null || true
cp -n infra/main.json infrastructure/azure/bicep/ 2>/dev/null || true
cp -n infra/main.subscription.json infrastructure/azure/bicep/ 2>/dev/null || true

# 8. cli/ 이동
echo "cli/ 파일 복사..."
cp -n infra/deploy-interactive.sh cli/deploy/interactive.sh 2>/dev/null || true
cp -n infra/deploy-app.sh cli/deploy/app.sh 2>/dev/null || true
cp -n apps/records-api/scripts/host-start.js cli/api/ 2>/dev/null || true
cp -n apps/records-api/scripts/check-node-version.js cli/api/ 2>/dev/null || true
cp -n apps/records-api/scripts/reset-local-data.js cli/data/ 2>/dev/null || true
cp -n apps/records-api/scripts/seed-local-data.js cli/data/ 2>/dev/null || true

# 9. documentation/ 이동
echo "documentation/ 파일 복사..."
cp -n planed/*.md documentation/planed/ 2>/dev/null || true
cp -n prod-kuhwa-docs/*.md documentation/prod-kuhwa-docs/ 2>/dev/null || true

# 10. schools 데이터 이동
echo "schools/ 데이터 복사..."
cp -n schools/*.json core/data/schools/ 2>/dev/null || true

echo "마이그레이션 완료. 파일이 papertrail 구조로 복사되었습니다."
echo "참고: 원본 파일은 그대로 유지됩니다. 필요시 삭제하세요."
echo "다음 단계: 이동된 파일 내부의 참조 경로를 업데이트하세요."