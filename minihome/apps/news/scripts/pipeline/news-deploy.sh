#!/usr/bin/env bash
set -euo pipefail

# DevForge 체인 파이프라인 - 뉴스 프로젝트 빌드/배포
# usage: news-deploy.sh [build|test|prod]

WEB="/opt/workspace/minihome/apps/news/web"
cd "$WEB"

ACTION=${1:-build}
export NEXT_TELEMETRY_DISABLED=1

case "$ACTION" in
  build)
    echo "[pipeline] building Next.js ..."
    npm ci --silent && npm run build
    echo "[pipeline] build done."
    ;;
  test)
    echo "[pipeline] lint + typecheck ..."
    npm run lint && npx tsc --noEmit
    echo "[pipeline] tests passed."
    ;;
  prod)
    echo "[pipeline] deploying to Vercel production ..."
    vercel --prod --confirm
    echo "[pipeline] deploy done: https://mini-news.vercel.app"
    ;;
  *)
    echo "usage: $0 [build|test|prod]"; exit 1
    ;;
esac
