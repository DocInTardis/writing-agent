@echo off
REM Rust WASM构建脚本 (Windows)

echo 🔨 开始构建Rust引擎WASM模块...

cd /d "%~dp0"

REM 检查wasm-pack
where wasm-pack >nul 2>nul
if %errorlevel% neq 0 (
    echo 📦 安装wasm-pack...
    cargo install wasm-pack
)

REM 构建WASM
echo 🏗️  编译WASM...
wasm-pack build --target web --out-dir pkg --release

REM 复制到前端目录
set FRONTEND_DIR=..\..\writing_agent\web\frontend_svelte\public\wasm
echo 📋 复制到前端目录: %FRONTEND_DIR%
if not exist "%FRONTEND_DIR%" mkdir "%FRONTEND_DIR%"
copy /Y pkg\* "%FRONTEND_DIR%\"

echo ✅ WASM构建完成！
echo 📊 文件大小:
dir pkg\wa_bridge_bg.wasm

echo.
echo 🎯 下一步:
echo 1. cd ..\..\writing_agent\web\frontend_svelte
echo 2. npm run dev
echo 3. 打开浏览器，点击🚀图标切换到Rust引擎

pause
