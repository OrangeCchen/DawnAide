#!/usr/bin/env bash
# =============================================================
# AgentTeams 开发模式启动脚本
# 同时启动：后端服务 + Client Runtime + Tauri 开发窗口
# =============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
RUNTIME_DIR="$SCRIPT_DIR/../runtime"
DESKTOP_DIR="$SCRIPT_DIR/../desktop"

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
echo "[1/3] 启动后端服务 (port 8000)..."
cd "$ROOT_DIR"
python -m uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload &
BACKEND_PID=$!

# 启动 Client Runtime
echo "[2/3] 启动 Client Runtime (port 19800)..."
cd "$RUNTIME_DIR"
python main.py &
RUNTIME_PID=$!

# 等待服务就绪
echo "[INFO] 等待服务启动..."
sleep 3

# 启动 Tauri 开发窗口（可选）
if [ -d "$DESKTOP_DIR/node_modules" ]; then
    echo "[3/3] 启动 Tauri 开发窗口..."
    cd "$DESKTOP_DIR"
    npm run tauri:dev &
else
    echo "[3/3] 跳过 Tauri（未安装依赖）。仅启动 Web 模式。"
    echo "      后端: http://127.0.0.1:8000"
    echo "      Runtime: http://127.0.0.1:19800"
fi

echo ""
echo "============================================"
echo " 所有服务已启动"
echo " 后端:    http://127.0.0.1:8000"
echo " Runtime: http://127.0.0.1:19800/health"
echo " 按 Ctrl+C 停止所有服务"
echo "============================================"

wait
