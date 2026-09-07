# 开发说明

## 环境

```powershell
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
.\.venv\Scripts\pip.exe install -r requirements-dev.txt
```

桌面开发还需要 Node.js、Rust、`wasm-pack` 和 Tauri 2 CLI；这些只参与构建，不进入普通用户的运行环境。

## 验证

```powershell
.\.venv\Scripts\python.exe -B -m compileall -q writing_agent
.\.venv\Scripts\python.exe -B -m pytest -q tests
npm --prefix writing_agent/web/frontend_svelte run check
npm --prefix writing_agent/web/frontend_svelte run build
cargo test --workspace --manifest-path engine/Cargo.toml
cargo check --offline --manifest-path desktop-tauri/src-tauri/Cargo.toml
```

`scripts/build_frontend.ps1` 生成 Rust/WASM 与 Svelte 静态资源；`scripts/build_sidecar.ps1` 生成不在每次启动时解压的 Python onedir sidecar；`scripts/build_desktop.ps1` 最终生成 NSIS 安装包。Node、Cargo、PyInstaller 都只用于构建，普通运行不会调用它们。仓库不包含 Node 后端、Playwright 或独立 Web 部署链路。

架构规则：HTTP/桌面层只做输入输出适配；工作流通过显式依赖接收能力；模型调用统一经过 `writing_agent.llm.get_default_provider`；失败不得隐式切换 Provider；用户数据只写入统一数据根目录。Rust 内核不是第二套业务后端，不得实现 Provider、RAG 或持久化业务。
