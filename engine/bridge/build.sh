#!/bin/bash
# Rust WASM构建脚本

set -e

echo "🔨 开始构建Rust引擎WASM模块..."

cd "$(dirname "$0")"

# 安装wasm-pack（如果未安装）
if ! command -v wasm-pack &> /dev/null; then
    echo "📦 安装wasm-pack..."
    cargo install wasm-pack
fi

# 构建WASM
echo "🏗️  编译WASM..."
wasm-pack build --target web --out-dir pkg --release

# 复制到前端目录
FRONTEND_DIR="../../writing_agent/web/frontend_svelte/public/wasm"
echo "📋 复制到前端目录: $FRONTEND_DIR"
mkdir -p "$FRONTEND_DIR"
cp pkg/* "$FRONTEND_DIR/"

echo "✅ WASM构建完成！"
echo "📊 文件大小:"
ls -lh pkg/wa_bridge_bg.wasm

echo ""
echo "🎯 下一步:"
echo "1. cd ../../writing_agent/web/frontend_svelte"
echo "2. npm run dev"
echo "3. 打开浏览器，点击🚀图标切换到Rust引擎"
