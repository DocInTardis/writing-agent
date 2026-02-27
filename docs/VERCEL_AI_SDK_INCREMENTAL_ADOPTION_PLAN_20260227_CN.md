# Vercel AI SDK 增量接入方案（不做全量重构）

日期：2026-02-27  
适用项目：`writing-agent`

## 1. 结论（先说结果）

不建议为了“写上 Vercel AI SDK”而对现有 Python/FastAPI 主干做全量重构。  
建议采用**增量接入**：保持现有编排、RAG、导出链路不动，仅在模型调用层引入 Node 网关，使用 Vercel AI SDK 官方 npm 包承接 `streamText / generateObject / tool calls`，Python 侧通过 HTTP 调用。

这条路径的收益是：
- 技术风险可控：不动核心业务主链路。
- 改造成本可控：1-2 周可落地可回滚版本。
- 简历收益真实：可以明确写“接入 Vercel AI SDK 官方包并上线”。

## 2. 当前现状判断

目前项目已具备：
- 后端 `AISDKAdapter`（语义适配层），支持 `stream_text / generate_object / tool_call`。
- Provider 抽象、模型路由、错误分类、重试机制。

目前项目尚未具备：
- 在生产调用链里直接使用 `Vercel AI SDK` 官方 npm 包（`ai` / `@ai-sdk/*`）作为真实执行引擎。

因此，最合理路线不是推翻现有实现，而是把现有 Adapter 升级为“可切换双后端”：
- `python-native provider`（现状）
- `node-ai-sdk gateway`（新增）

## 3. 目标架构（增量）

```text
Client/UI
   |
FastAPI (Python, existing)
   |      \
   |       \  (feature flag / model route)
   |        \
   |         -> Python Provider Path (existing)
   |
   -> Node AI Gateway (new, Vercel AI SDK official npm package)
         - streamText
         - generateObject
         - tool calls
```

关键原则：
- 编排层（LangGraph / state / RAG / DOCX）保持不变。
- 调用层通过接口协议解耦，支持随时切回 Python provider。
- 先小流量灰度，再逐步扩大。

## 4. 分阶段实施（推荐）

## Phase 0：设计冻结（0.5 天）

输出文档：
- `request/response` 协议（stream + object + tool-call）。
- 错误码映射（rate limit / timeout / context overflow / schema fail）。
- 可观测字段（trace_id / provider / model / latency_ms / token usage）。

验收：
- 协议评审通过，确保 Python 与 Node 两侧语义一致。

## Phase 1：最小 Node Gateway（1-2 天）

建议技术栈：
- Node 20+
- `ai`（Vercel AI SDK）
- `@ai-sdk/openai`（或目标 provider）
- `fastify`/`express` 二选一

最小接口：
- `POST /v1/stream-text`
- `POST /v1/generate-object`
- `POST /v1/tool-call`（可选；也可先由 Python 侧执行）

必做：
- 请求幂等键透传（`x-idempotency-key`）。
- 超时、重试、错误分类统一输出。
- 结构化日志与 trace 透传。

验收：
- 单元测试 + contract test 通过。
- 能替换一个真实写作流程的 LLM 调用并跑通。

## Phase 2：Python 侧对接与双路径开关（1 天）

新增配置：
- `WRITING_AGENT_LLM_BACKEND=python|node`
- `WRITING_AGENT_NODE_GATEWAY_URL`

实现：
- 在 `writing_agent/llm/factory.py` 或上层 service 增加 backend 选择。
- 保留现有 provider 作为默认回退路径。

验收：
- 同一请求在两条路径输出格式一致。
- Node 路径失败时可自动降级到 Python 路径（可配置）。

## Phase 3：灰度与回归（1-2 天）

灰度策略：
- 先 5%，再 20%，再 50%，最后 100%（按稳定性推进）。

关键监控：
- 错误率（4xx/5xx 分类）
- p95/p99 延迟
- schema 失败率
- 导出失败率
- 回退触发率

验收：
- 连续 24-48 小时指标无劣化，回归套件通过。

## Phase 4：稳定收口（0.5 天）

收口动作：
- 固化 runbook + rollback 流程。
- 更新文档与测试基线。
- 形成“可审计的上线证据”。

## 5. 风险与回滚

主要风险：
- Node/Python 双栈行为差异（尤其结构化输出与工具调用）。
- 流式协议边界差异导致前端兼容问题。
- Provider 配额与限流策略变化。

回滚策略：
- 任意阶段可通过 `WRITING_AGENT_LLM_BACKEND=python` 一键切回。
- 灰度期间不删除 Python 路径。
- 所有变更以 feature flag 控制，不做破坏性替换。

## 6. 最小验收清单（必须满足）

- 功能一致：`streamText`、`generateObject`、工具调用语义一致。
- 错误一致：统一错误分类，不把 provider 原始异常直接暴露前端。
- 观测一致：trace_id、latency、usage、error_code 全链路可追踪。
- 质量一致：回归集通过，导出链路无回归。
- 可回滚：5 分钟内可切回 Python 路径。

## 7. 简历可写口径（完成后再写）

推荐写法（上线后可用）：
- “通过引入 Node AI Gateway 并接入 Vercel AI SDK 官方 npm 包，实现 `streamText/generateObject/tool calls` 统一语义层，并通过双路径开关完成灰度发布与快速回滚，保障生成链路稳定性。”

未上线前不建议写“已全面基于 Vercel AI SDK 重构”。

## 8. 为什么不建议全量重构

全量重构会同时触发：
- 技术栈迁移风险（Python -> Node）
- 业务语义回归风险（RAG、导出、状态编排）
- 交付延迟风险（难以快速验证）

而增量接入把风险收敛在“LLM 调用边界”，收益/风险比更高。

