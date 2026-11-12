#!/usr/bin/env bash
# 一键构建 Debug APK。
#
# 用法：cd frontend/android && ./build-debug.sh
#
# JDK 查找顺序：
#   1. 已导出的 JAVA_HOME
#   2. 项目内 JDK（frontend/node_modules/.cache/jdk，被 .gitignore 忽略）
#   3. macOS 常见安装位置
# Android SDK 查找顺序：ANDROID_HOME → ~/Library/Android/sdk，并写入 local.properties。
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
FRONTEND="$(cd "$HERE/.." && pwd)"

find_java_home() {
  if [ -n "${JAVA_HOME:-}" ] && [ -x "$JAVA_HOME/bin/java" ]; then
    echo "$JAVA_HOME"; return 0
  fi
  local candidate
  candidate="$(find "$FRONTEND/node_modules/.cache/jdk" -maxdepth 5 -type f -path "*/bin/java" 2>/dev/null | head -1 || true)"
  if [ -n "$candidate" ]; then
    (cd "$(dirname "$candidate")/.." && pwd); return 0
  fi
  for candidate in \
    "/Applications/Android Studio.app/Contents/jbr/Contents/Home" \
    "/Library/Java/JavaVirtualMachines/temurin-17.jdk/Contents/Home" \
    "/opt/homebrew/opt/openjdk@17"; do
    if [ -x "$candidate/bin/java" ]; then echo "$candidate"; return 0; fi
  done
  return 1
}

if ! JAVA_HOME="$(find_java_home)"; then
  echo "未找到 JDK 17。请任选其一："
  echo "  1) 安装 Android Studio（自带 JDK）"
  echo "  2) 下载 Temurin 17 并解压到 frontend/node_modules/.cache/jdk/"
  echo "  3) export JAVA_HOME=/path/to/jdk-17"
  exit 1
fi
export JAVA_HOME
export PATH="$JAVA_HOME/bin:$PATH"

SDK_DIR="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$HOME/Library/Android/sdk}}"
if [ ! -d "$SDK_DIR" ]; then
  echo "未找到 Android SDK（$SDK_DIR）。请安装 Android Studio 或设置 ANDROID_HOME。"
  exit 1
fi
if [ ! -f "$HERE/local.properties" ]; then
  echo "sdk.dir=$SDK_DIR" > "$HERE/local.properties"
  echo "已写入 local.properties（sdk.dir=$SDK_DIR）"
fi

# Web 资源需先同步：npm run android:sync（或 build:mobile + cap sync）
if [ ! -f "$HERE/app/src/main/assets/public/index.html" ]; then
  echo "警告：Android 工程里还没有 Web 资源，请先在 frontend 执行 npm run android:sync"
fi

echo "JAVA_HOME=$JAVA_HOME"
echo "SDK=$SDK_DIR"
cd "$HERE"
./gradlew assembleDebug --no-daemon --console=plain

APK="$HERE/app/build/outputs/apk/debug/app-debug.apk"
if [ -f "$APK" ]; then
  echo ""
  echo "构建完成：$APK"
  ls -lh "$APK"
else
  echo "构建结束但未找到 APK，请检查上面的日志。"
  exit 1
fi
