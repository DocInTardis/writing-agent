# Writing Agent

一个面向个人使用的轻量桌面写作工具，提供文档编辑、AI 生成与局部修订、资料检索、引用管理、版本记录和 DOCX 导出。

## 当前架构

- 桌面壳：PySide6 + 系统内本地 FastAPI 服务。
- 界面：预构建的 Svelte 工作台；普通使用不需要 Node。
- 核心：单一 Python 实现，不再包含 Tauri、Rust 编辑引擎或 Node AI 网关。
- 模型：统一走用户选择的 Provider。默认支持 OpenAI-compatible API，DeepSeek 可直接使用；Ollama 仅在明确选择时启用。调用失败会原样报告，不会偷偷切换服务或下载模型。
- 数据：默认保存在项目 `.data/`；可用 `WRITING_AGENT_DATA_DIR` 指定其他目录。

## 启动

Windows 下运行：

```powershell
.\scripts\start_desktop.ps1
```

首次安装或依赖变化时：

```powershell
.\scripts\start_desktop.ps1 -InstallDependencies
```

开发者如只需本地 HTTP 服务：

```powershell
.\.venv\Scripts\python.exe -B -m writing_agent.launch --web
```

## 模型配置

复制 `.env.example` 为 `.env`，或在应用设置中填写 Provider、Base URL、模型和 API key。DeepSeek 示例：

```dotenv
WRITING_AGENT_LLM_PROVIDER=openai
WRITING_AGENT_OPENAI_BASE_URL=https://api.deepseek.com
WRITING_AGENT_OPENAI_API_KEY=your-key
WRITING_AGENT_OPENAI_MODEL=deepseek-v4-flash
```

向量检索默认不调用嵌入模型。只有设置 `WRITING_AGENT_EMBED_MODEL` 后才会请求所选 Provider 的 embeddings 接口。

## 空间检查

```powershell
.\.venv\Scripts\python.exe -B -m writing_agent.storage_report
```

该命令只盘点，不删除。`.data` 包含用户文档和配置，不应整体清理。更多说明见 [本地运行与空间](docs/LOCAL_RUNTIME.md)。

## 文档

- [功能与实现](docs/FEATURES_AND_IMPLEMENTATION.md)
- [开发说明](docs/DEVELOPMENT.md)
- [本地运行与空间](docs/LOCAL_RUNTIME.md)
- [重构执行清单](docs/REFACTOR_CHECKLIST.md)

历史设计与企业化方案已从工作树移除，仍可从 Git 历史恢复。
