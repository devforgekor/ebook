#!/bin/bash
# Vercel 배포 스크립트

# 프로젝트 정보
PROJECT_ID="prj_AgCf0ZgzOUJ72pn0g9sJvq3lCm9v"
ORG_ID="team_b1p31tRpp5RLMvUcDxitvoSp"
PROJECT_NAME="miniebook"

# Vercel CLI로 배포 시도
echo "Vercel 배포 시작..."

# 프로덕션 배포
vercel --prod --yes 2>&1 | tee deploy.log

# 결과 확인
if [ ${PIPESTATUS[0]} -eq 0 ]; then
    echo "배포 성공!"
else
    echo "배포 실패 - 로그 확인 필요"
    cat deploy.log
fi
