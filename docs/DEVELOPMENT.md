# 开发说明

## 环境

```powershell
python -m venv .venv
.\.venv\Scripts\pip.exe install -r requirements.txt
.\.venv\Scripts\pip.exe install -r requirements-dev.txt
```

桌面依赖单独安装：

```powershell
.\.venv\Scripts\pip.exe install -e ".[desktop]"
```

## 验证

```powershell
.\.venv\Scripts\python.exe -B -m compileall -q writing_agent
.\.venv\Scripts\python.exe -B -m pytest -q tests
npm --prefix writing_agent/web/frontend_svelte run build
cargo test --workspace --manifest-path engine/Cargo.toml
```

Node 只用于修改和构建前端。Rust 只用于构建、测试文档内核及 WASM Bridge，普通运行不得调用 Cargo；仓库不再包含 Node 后端、Tauri 或 Playwright。

架构规则：HTTP/桌面层只做输入输出适配；工作流通过显式依赖接收能力；模型调用统一经过 `writing_agent.llm.get_default_provider`；失败不得隐式切换 Provider；用户数据只写入统一数据根目录。Rust 内核不是第二套业务后端，不得实现 Provider、RAG 或持久化业务。
