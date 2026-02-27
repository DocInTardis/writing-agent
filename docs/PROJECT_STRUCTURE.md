# Project Structure Guide

本文档用于帮助新开发者快速定位代码职责，避免在超大文件中迷失。

## 1. Core Runtime

- `writing_agent/v2/`
- 职责：写作编排主流程、文档解析/格式化、RAG 调用链路。
- 关键入口：
- `writing_agent/v2/graph_runner.py`
- `writing_agent/v2/doc_format.py`
- `writing_agent/v2/rag/retrieve.py`

## 2. State Engine

- `writing_agent/state_engine/`
- 职责：图执行定义、双引擎调度、checkpoint 与 replay。
- 关键入口：
- `writing_agent/state_engine/graph_contracts.py`
- `writing_agent/state_engine/dual_engine.py`

## 3. Web/API Layer

- `writing_agent/web/`
- 职责：FastAPI 路由、服务边界、领域逻辑、前端资源。
- 分层约定：
- `web/api/*_flow.py`：仅编排请求流程与响应组装
- `web/services/*_service.py`：业务服务接口层
- `web/domains/*_domain.py`：纯领域逻辑
- `web/frontend_svelte/`：前端工作台

## 4. LLM Adapter Layer

- `writing_agent/llm/`
- 职责：provider 抽象、模型路由、AI SDK 语义适配、工具调用协议。
- 关键入口：
- `writing_agent/llm/factory.py`
- `writing_agent/llm/model_router.py`
- `writing_agent/llm/ai_sdk_adapter.py`

## 5. Document Export Layer

- `writing_agent/document/`
- 职责：导出构建、样式/目录/字段写入、HTML 到 DOCX 转换。
- 关键入口：
- `writing_agent/document/v2_report_docx.py`
- `writing_agent/document/docx_builder.py`

## 6. Quality & Governance

- `scripts/`：检查与发布流程
- `security/`：门禁配置
- `tests/`：测试体系（unit/integration/e2e）

## 7. Node Gateway

- `gateway/node_ai_gateway/`：Node 侧 AI Gateway（Vercel AI SDK 官方 npm 包）
- 职责：提供 `stream-text` / `generate-object` / `tool-call` HTTP 边界能力

## 8. Legacy Scripts

- `scripts/dev/`：历史调试脚本
- `tests/legacy/`：历史脚本化测试（默认不参与 CI 主测试）

## 9. Reading Order (Recommended)

1. `writing_agent/launch.py`
2. `writing_agent/web/app_v2.py`
3. `writing_agent/web/api/generation_flow.py`
4. `writing_agent/web/services/generation_service.py`
5. `writing_agent/v2/graph_runner.py`
6. `writing_agent/v2/rag/retrieve.py`
7. `writing_agent/document/v2_report_docx.py`
