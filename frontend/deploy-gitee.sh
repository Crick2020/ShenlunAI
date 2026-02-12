#!/usr/bin/env bash
# 构建前端并把 dist 推送到 Gitee 仓库，用于 Gitee Pages 国内访问
# 使用前：在 Gitee 新建空仓库（如 ShenlunAI-Pages），并设置 GITEE_PAGES_REPO

set -e
cd "$(dirname "$0")"

if [ -z "$GITEE_PAGES_REPO" ]; then
  echo "请先设置 Gitee 仓库地址，例如："
  echo "  export GITEE_PAGES_REPO=https://gitee.com/你的用户名/ShenlunAI-Pages.git"
  echo "或："
  echo "  export GITEE_PAGES_REPO=git@gitee.com:你的用户名/ShenlunAI-Pages.git"
  exit 1
fi

# Gitee Pages 若访问地址为 https://用户名.gitee.io/仓库名/，需设 base 为 /仓库名/
# 例如：export GITEE_PAGES_BASE=/ShenlunAI-Pages/
if [ -n "$GITEE_PAGES_BASE" ]; then
  export VITE_BASE_URL="$GITEE_PAGES_BASE"
fi

echo ">>> 构建前端..."
npm run build

echo ">>> 部署到 Gitee Pages..."
DEPLOY_DIR=$(mktemp -d 2>/dev/null || mktemp -d -t shenlun-deploy)
cp -r dist/. "$DEPLOY_DIR"
cd "$DEPLOY_DIR"
git init
git add -A
git commit -m "Deploy to Gitee Pages"
git branch -M main
git remote add origin "$GITEE_PAGES_REPO"
git push -f origin main

echo ">>> 部署完成。请在 Gitee 仓库中打开「服务 → Gitee Pages」并开启 Pages，即可获得国内访问链接。"
