# Node AI Gateway 上线证据清单（Phase 4）

## A. Phase 0 协议冻结

- [x] `docs/NODE_AI_GATEWAY_PROTOCOL_20260227_CN.md`
- [x] stream/object/tool-call 协议定义
- [x] 错误码映射定义
- [x] 可观测字段定义

## B. Phase 1 网关最小实现

- [x] Node 20+ 网关项目：`gateway/node_ai_gateway/`
- [x] `POST /v1/stream-text`
- [x] `POST /v1/generate-object`
- [x] `POST /v1/tool-call`
- [x] 幂等键透传（`x-idempotency-key`）
- [x] 统一错误分类输出
- [x] 结构化日志与 trace 透传

## C. Phase 2 Python 双路径接入

- [x] 新增配置：`WRITING_AGENT_LLM_BACKEND=python|node`
- [x] 新增配置：`WRITING_AGENT_NODE_GATEWAY_URL`
- [x] Factory 双路径路由：`writing_agent/llm/factory.py`
- [x] Node 路径失败自动回退（可配置）

## D. Phase 3 灰度与回归

- [x] 灰度策略文档：5% -> 20% -> 50% -> 100%
- [x] 关键指标汇总脚本：`scripts/node_gateway_rollout_monitor.py`
- [x] 单元测试、契约测试、集成测试覆盖 Node 路径

## E. Phase 4 稳定收口

- [x] runbook + rollback：`docs/NODE_AI_GATEWAY_RUNBOOK_20260227_CN.md`
- [x] 回归基线更新（测试与门禁）
- [x] 审计证据文档（本文档）
