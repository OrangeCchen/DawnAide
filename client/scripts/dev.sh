#!/usr/bin/env bash
# =============================================================
# AgentTeams 开发模式启动脚本
# 同时启动：后端服务 + 前端开发服务器 + Client Runtime + Tauri 开发窗口
# =============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
RUNTIME_DIR="$SCRIPT_DIR/../runtime"
DESKTOP_DIR="$SCRIPT_DIR/../desktop"
FRONTEND_DIR="$ROOT_DIR/frontend"

cleanup() {
    echo ""
    echo "[INFO] 正在关闭所有服务..."
    kill $(jobs -p) 2>/dev/null || true
    exit 0
}

trap cleanup SIGINT SIGTERM

echo "============================================"
echo " AgentTeams 开发模式（C/S 架构）"
echo "============================================"

# 启动后端服务
echo "[1/4] 启动后端服务 (port 8000)..."
cd "$ROOT_DIR"
python -m uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload &
BACKEND_PID=$!

# 启动前端开发服务器（Vite HMR，实时反映代码变更）
echo "[2/4] 启动前端开发服务器 (port 3000)..."
cd "$FRONTEND_DIR"
if [ ! -d "node_modules" ]; then
    echo "[INFO] 安装前端依赖..."
    npm install
fi
npm run dev &
FRONTEND_PID=$!

# 启动 Client Runtime
echo "[3/4] 启动 Client Runtime (port 19800)..."
cd "$RUNTIME_DIR"
python main.py &
RUNTIME_PID=$!

# 等待服务就绪
echo "[INFO] 等待服务启动..."
sleep 3

# 启动 Tauri 开发窗口（可选）
if [ -d "$DESKTOP_DIR/node_modules" ]; then
    echo "[4/4] 启动 Tauri 开发窗口..."
    cd "$DESKTOP_DIR"
    # Dev 模式：后端和 Runtime 已单独启动，无需打包 sidecar 二进制
    # 用 TAURI_CONFIG 临时覆盖 externalBin 为空，跳过 sidecar 路径校验
    TAURI_CONFIG='{"bundle":{"externalBin":[]}}' npm run tauri:dev &
else
    echo "[4/4] 跳过 Tauri（未安装依赖）。仅启动 Web 模式。"
fi

echo ""
echo "============================================"
echo " 所有服务已启动"
echo " 前端:    http://127.0.0.1:3000  ← 开发时请访问此地址"
echo " 后端:    http://127.0.0.1:8000"
echo " Runtime: http://127.0.0.1:19800/health"
echo " 按 Ctrl+C 停止所有服务"
echo "============================================"

wait
