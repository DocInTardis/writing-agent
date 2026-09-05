# 功能与实现

| 能力 | 主要实现 |
|---|---|
| 桌面启动与本地服务 | `writing_agent/desktop_app.py`、`writing_agent/launch.py` |
| 工作区与持久化 | `writing_agent/storage.py`、`writing_agent/web/api/workspace_flow.py` |
| AI 生成 | `writing_agent/workflows/`、`writing_agent/v2/graph_runner.py` |
| 全文与局部修订 | `writing_agent/workflows/revision_request_workflow.py`、`writing_agent/web/domains/revision_*` |
| 模型接入 | `writing_agent/llm/factory.py`、`writing_agent/llm/providers/` |
| 资料库、RAG、引用 | `writing_agent/v2/rag/`、`writing_agent/web/api/rag_flow.py` |
| 编辑器与 DocIR | `writing_agent/web/frontend_svelte/`、`writing_agent/v2/doc_ir.py` |
| 版本与检查点 | `writing_agent/state_engine/`、`writing_agent/web/api/version_flow.py` |
| 图表 | `writing_agent/capabilities/diagramming.py`、`writing_agent/diagrams/` |
| DOCX/HTML/PDF 导出 | `writing_agent/document/`、`writing_agent/web/api/export_flow.py` |
| 质量提示 | `writing_agent/quality/`、`writing_agent/capabilities/generation_quality.py` |

当前只有一套 Python 业务实现。Svelte 是桌面窗口内的界面资源，不是独立部署的 Web 产品。OpenAI、DeepSeek、其他 OpenAI-compatible API 和明确选择的 Ollama 共用 Provider 协议；不存在跨服务自动 fallback。

已知边界：AI 文本率和相似度是本地启发式提示，不等同于正式检测服务；PDF 质量受本机转换能力影响；真实桌面排版与 Word 仍需人工样本文档验收。
