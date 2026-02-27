# `writing_agent` Package Guide

## Subpackages

- `agents/`：任务代理能力（写作、改写、图表等）
- `v2/`：核心写作流程与运行时
- `web/`：FastAPI 接口与前端工作台
- `document/`：DOCX/HTML 导出
- `llm/`：模型提供商与适配层
- `state_engine/`：图执行引擎与状态管理
- `observability/`：监控与 tracing 适配
- `quality/`：质量检测算法

## Entry Points

- `python -m writing_agent.launch`
- `python -m writing_agent`
