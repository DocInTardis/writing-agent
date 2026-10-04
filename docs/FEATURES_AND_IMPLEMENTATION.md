# 功能与实现

| 能力 | 主要实现 |
|---|---|
| 桌面启动与本地服务 | `desktop-tauri/src-tauri/`、`writing_agent/sidecar.py`、`writing_agent/launch.py` |
| 工作区与持久化 | `writing_agent/storage.py`、`writing_agent/web/api/workspace_flow.py` |
| AI 生成 | `writing_agent/workflows/`、`writing_agent/v2/graph_runner.py` |
| 全文与局部修订 | `writing_agent/workflows/revision_request_workflow.py`、`writing_agent/web/domains/revision_*` |
| 模型接入 | `writing_agent/llm/factory.py`、`writing_agent/llm/providers/` |
| 资料库、RAG、引用 | `writing_agent/v2/rag/`、`writing_agent/web/api/rag_flow.py` |
| 编辑器与 Document V3 | `writing_agent/web/frontend_svelte/`、`writing_agent/v3/` |
| Rust 文档内核 | `engine/core/`、`engine/engine/`、`engine/bridge/`、`writing_agent/v2/rust_bridge.py` |
| 版本与检查点 | `writing_agent/state_engine/`、`writing_agent/web/api/version_flow.py` |
| 图表 | `writing_agent/capabilities/diagramming.py`、`writing_agent/diagrams/` |
| DOCX 结构化导入与 DOCX/HTML/PDF 导出 | `writing_agent/v3/docx_import.py`、`writing_agent/document/`、`writing_agent/web/api/export_flow.py` |
| 质量提示 | `writing_agent/quality/`、`writing_agent/capabilities/generation_quality.py` |

Python 是唯一业务实现，负责 Agent、模型调用、RAG 与持久化；Rust 是文档性能内核，负责 AST、编辑历史、布局、命中测试和渲染缓存，不复制业务逻辑。Svelte 通过 WASM Bridge 实际同步文档状态，并作为 Tauri 2 系统 WebView2 窗口内的界面资源，不是独立部署的 Web 产品。OpenAI、DeepSeek、其他 OpenAI-compatible API 和明确选择的 Ollama 共用 Provider 协议；不存在跨服务自动 fallback。

已知边界：AI 文本率和相似度是本地启发式提示，不等同于正式检测服务；轻量 PDF 后备渲染的字体度量受本机字体影响；应用内 Rust 预览与 Word 可有微小换行差异。已导入 DOCX 在未修改时按原包无损导出，修改后在原 OOXML 上回写，不用纯文本重建论文。

## 恢复与追溯

旧 Tauri 实验、Node 网关、容器配置和历史文档仍存在于 Git 提交 `0301db0` 及更早历史中。当前产品使用重新建立的最小 Tauri 2 壳；它只负责窗口、sidecar 生命周期、受控缓存目录和安装包，不承载业务逻辑。Rust 文档内核也已恢复并通过 WASM 接入工作台。

用户资料位于 `WRITING_AGENT_DATA_DIR`（默认 `.data`），不随源码回退自动迁移。执行任何 Git 回退前应先单独备份该目录；不要用源码清理命令处理用户数据。
