#!/usr/bin/env bash
# =============================================================
# AgentTeams Client Runtime 构建脚本
# 将 Python Runtime 打包为单文件可执行程序（跨平台）
#
# 用法:
#   ./build-runtime.sh [--target TARGET]
#
# TARGET:
#   macos-x64     macOS Intel
#   macos-arm64   macOS Apple Silicon
#   windows-x64   Windows 64位
#   linux-x64     Linux x86_64（含麒麟、统信）
#   linux-arm64   Linux ARM64（麒麟 ARM 版）
# =============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUNTIME_DIR="$(cd "$SCRIPT_DIR/../runtime" && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/../desktop/src-tauri/sidecar"

TARGET="${1:-auto}"

detect_platform() {
    local os arch
    os="$(uname -s)"
    arch="$(uname -m)"

    case "$os" in
        Darwin)
            case "$arch" in
                arm64) echo "macos-arm64" ;;
                *)     echo "macos-x64" ;;
            esac ;;
        Linux)
            case "$arch" in
                aarch64) echo "linux-arm64" ;;
                *)       echo "linux-x64" ;;
            esac ;;
        MINGW*|MSYS*|CYGWIN*)
            echo "windows-x64" ;;
        *)
            echo "unknown" ;;
    esac
}

if [ "$TARGET" = "auto" ]; then
    TARGET="$(detect_platform)"
    echo "[INFO] 自动检测平台: $TARGET"
fi

# PyInstaller 目标三元组映射（对应 Tauri sidecar 命名）
case "$TARGET" in
    macos-x64)    SUFFIX="x86_64-apple-darwin" ;;
    macos-arm64)  SUFFIX="aarch64-apple-darwin" ;;
    windows-x64)  SUFFIX="x86_64-pc-windows-msvc.exe" ;;
    linux-x64)    SUFFIX="x86_64-unknown-linux-gnu" ;;
    linux-arm64)  SUFFIX="aarch64-unknown-linux-gnu" ;;
    *)
        echo "[ERROR] 不支持的平台: $TARGET"
        exit 1 ;;
esac

echo "========================================"
echo " AgentTeams Runtime 构建"
echo " 目标: $TARGET ($SUFFIX)"
echo " 源码: $RUNTIME_DIR"
echo " 输出: $OUTPUT_DIR"
echo "========================================"

# 确保依赖已安装
echo "[1/3] 安装 Runtime 依赖..."
pip install -r "$RUNTIME_DIR/requirements.txt" -q
pip install pyinstaller -q

# 打包
echo "[2/3] 使用 PyInstaller 打包..."
cd "$RUNTIME_DIR"
pyinstaller \
    --onefile \
    --name "agentteams-runtime-$SUFFIX" \
    --add-data "services:services" \
    --add-data "store:store" \
    --add-data "config.py:." \
    --hidden-import "uvicorn.logging" \
    --hidden-import "uvicorn.lifespan" \
    --hidden-import "uvicorn.lifespan.on" \
    --hidden-import "uvicorn.protocols" \
    --hidden-import "uvicorn.protocols.http" \
    --hidden-import "uvicorn.protocols.http.auto" \
    --hidden-import "uvicorn.protocols.websockets" \
    --hidden-import "uvicorn.protocols.websockets.auto" \
    --hidden-import "chromadb" \
    --hidden-import "pdfplumber" \
    --clean \
    --noconfirm \
    main.py

# 移动到 sidecar 目录
echo "[3/3] 部署到 sidecar 目录..."
mkdir -p "$OUTPUT_DIR"
cp "$RUNTIME_DIR/dist/agentteams-runtime-$SUFFIX" "$OUTPUT_DIR/"

echo ""
echo "[完成] 构建产物: $OUTPUT_DIR/agentteams-runtime-$SUFFIX"
echo ""
