#!/usr/bin/env bash
# =============================================================
# AgentTeams Desktop 完整构建脚本
#
# 用法:
#   ./build-desktop.sh [--target TARGET] [--skip-runtime]
#
# 执行流程:
#   1. 构建 Client Runtime（PyInstaller → sidecar）
#   2. 构建 Tauri 桌面应用
# =============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CLIENT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DESKTOP_DIR="$CLIENT_DIR/desktop"

SKIP_RUNTIME=false
TARGET="auto"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --target)    TARGET="$2"; shift 2 ;;
        --skip-runtime) SKIP_RUNTIME=true; shift ;;
        *) echo "未知参数: $1"; exit 1 ;;
    esac
done

echo "============================================"
echo " AgentTeams Desktop 完整构建"
echo " 目标: $TARGET"
echo "============================================"

# Step 1: 构建 Runtime
if [ "$SKIP_RUNTIME" = false ]; then
    echo ""
    echo ">>> Step 1: 构建 Client Runtime..."
    bash "$SCRIPT_DIR/build-runtime.sh" "$TARGET"
else
    echo ""
    echo ">>> Step 1: 跳过 Runtime 构建"
fi

# Step 2: 构建 Tauri 桌面应用
echo ""
echo ">>> Step 2: 构建 Tauri 桌面应用..."
cd "$DESKTOP_DIR"

if [ ! -d "node_modules" ]; then
    echo "[INFO] 安装前端依赖..."
    npm install
fi

echo "[INFO] 执行 Tauri 构建..."
npm run tauri:build

echo ""
echo "============================================"
echo " 构建完成！"
echo " 产物目录: $DESKTOP_DIR/src-tauri/target/release/bundle/"
echo "============================================"
