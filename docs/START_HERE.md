# 快速开始

## 1. 准备环境

需要 Python 3.10+。桌面启动脚本会自动创建 `.venv` 并安装桌面依赖：

```powershell
.\scripts\start_desktop.ps1
```

也可以双击 `start.bat` 打开桌面窗口。启动不下载模型；当前桌面仍内嵌本地界面。

已有虚拟环境时默认复用，不会每次启动都运行 pip。依赖有变更或需要修复时显式执行：

```powershell
.\scripts\start_desktop.ps1 -InstallDependencies
```

## 2. 配置模型

可以在应用的模型设置中配置，也可以设置环境变量：

```powershell
$env:WRITING_AGENT_LLM_PROVIDER = "openai"
$env:WRITING_AGENT_OPENAI_API_KEY = "<API key>"
$env:WRITING_AGENT_OPENAI_MODEL = "<model name>"
```

兼容接口可另外设置 `WRITING_AGENT_OPENAI_BASE_URL`。本地 Ollama 使用 `WRITING_AGENT_LLM_PROVIDER=ollama`。

## 3. 开发环境

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt -r requirements-dev.txt
npm --prefix writing_agent/web/frontend_svelte ci
```

CI uses `requirements-pinned.txt` for reproducible dependency versions.

日常使用只需要默认 `.venv` 和已构建的 Web 文件，不需要 Node 网关、Rust、Tauri 或测试浏览器。
只有修改对应组件时才安装它的开发依赖；不要为每次检查另建一套虚拟环境。
详见 `LOCAL_RUNTIME.md`。

运行维护中的检查：

```powershell
.\.venv\Scripts\python -m pytest -q tests
npm --prefix writing_agent/web/frontend_svelte run build
npm --prefix gateway/node_ai_gateway test
cargo test --workspace --manifest-path engine/Cargo.toml
```

## 4. 桌面端

当前默认桌面入口使用 PySide6，交互验收仍在进行：

```powershell
.\scripts\start_desktop.ps1
```

`desktop-tauri/` 是实验实现，不作为日常启动入口。

## 5. 继续阅读

- 功能和实现位置：`FEATURES_AND_IMPLEMENTATION.md`
- 项目结构：`PROJECT_STRUCTURE.md`
- 阅读顺序：`READING_GUIDE.md`
- 常见问题：`TROUBLESHOOTING_DECISION_TREE.md`

旧归档计划已删除，可从 Git 历史查阅；仍保留的旧发布工程文档不是当前操作说明。
