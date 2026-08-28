# 快速开始

## 1. 准备环境

需要 Python 3.10+。Web 启动脚本会自动创建 `.venv` 并安装运行依赖：

```powershell
.\scripts\start.ps1
```

打开 `http://127.0.0.1:8000`。

如果已有虚拟环境并且已经安装依赖：

```powershell
.\scripts\start.ps1 -SkipInstall
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
npm --prefix gateway/node_ai_gateway ci
```

CI uses `requirements-pinned.txt` for reproducible dependency versions.

运行维护中的检查：

```powershell
.\.venv\Scripts\python -m pytest -q tests --ignore=tests/ui
npm --prefix writing_agent/web/frontend_svelte run build
npm --prefix gateway/node_ai_gateway test
cargo test --workspace --manifest-path engine/Cargo.toml
```

## 4. 桌面端

当前稳定桌面入口使用 PySide6：

```powershell
.\scripts\start_desktop.ps1
```

`desktop-tauri/` 是实验实现，不作为日常启动入口。

## 5. 继续阅读

- 功能和实现位置：`FEATURES_AND_IMPLEMENTATION.md`
- 项目结构：`PROJECT_STRUCTURE.md`
- 阅读顺序：`READING_GUIDE.md`
- 常见问题：`TROUBLESHOOTING_DECISION_TREE.md`

`docs/archive/` 和旧发布工程文档只记录历史方案，不是当前操作说明。
