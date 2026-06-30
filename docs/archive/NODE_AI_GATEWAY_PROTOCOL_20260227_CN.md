# Node AI Gateway 协议冻结（Phase 0）

日期：2026-02-27  
范围：`writing_agent`（Python） <-> `gateway/node_ai_gateway`（Node）

## 1. 协议目标

- 保持编排层（state / RAG / DOCX）不变。
- 在模型调用边界引入可切换双后端：
- Python native provider
- Node AI Gateway（Vercel AI SDK 官方 npm 包）
- 保证 stream/object/tool-call 三类语义一致。

## 2. 接口与请求响应协议

## 2.1 `POST /v1/stream-text`

请求：

```json
{
  "system": "string",
  "prompt": "string",
  "model": "string",
  "temperature": 0.2,
  "stream": true,
  "max_retries": 2,
  "timeout_ms": 60000
}
```

响应（非流）：

```json
{
  "ok": 1,
  "text": "string",
  "usage": {
    "prompt_tokens": 1,
    "completion_tokens": 2,
    "total_tokens": 3
  },
  "finish_reason": "stop",
  "trace_id": "uuid",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "latency_ms": 120
}
```

响应（流，SSE）：
- `data: {"type":"text-delta","delta":"...","trace_id":"..."}`
- `data: {"type":"done","text":"...","usage":{...},"trace_id":"...","latency_ms":123}`
- `data: {"type":"error","ok":0,"error":{...},"trace_id":"...","latency_ms":123}`

## 2.2 `POST /v1/generate-object`

请求：

```json
{
  "system": "string",
  "prompt": "string",
  "schema": {
    "type": "object",
    "properties": {}
  },
  "model": "string",
  "temperature": 0.1,
  "max_retries": 2,
  "timeout_ms": 60000
}
```

响应：

```json
{
  "ok": 1,
  "object": {},
  "usage": {
    "prompt_tokens": 1,
    "completion_tokens": 2,
    "total_tokens": 3
  },
  "finish_reason": "stop",
  "trace_id": "uuid",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "latency_ms": 120
}
```

## 2.3 `POST /v1/tool-call`

请求：

```json
{
  "tool_name": "echo",
  "arguments": {
    "k": "v"
  },
  "model": "string"
}
```

响应：

```json
{
  "ok": 1,
  "tool_name": "echo",
  "result": {},
  "trace_id": "uuid",
  "provider": "gateway-tool-runtime",
  "model": "gpt-4o-mini",
  "latency_ms": 10
}
```

## 3. 错误码映射（统一语义）

| 网关错误码 | HTTP | Python 侧分类 |
|---|---:|---|
| `RATE_LIMIT` | 429 | `RateLimitError` |
| `TIMEOUT` | 504 | `TimeoutError` |
| `CONTEXT_OVERFLOW` | 400 | `ContextOverflowError` |
| `SCHEMA_FAIL` | 422 | `SchemaValidationError` |
| `BAD_REQUEST` | 400 | `AISDKError` |
| `PROVIDER_ERROR` | 5xx | `AISDKError` |
| `INTERNAL_ERROR` | 500 | `AISDKError` |

统一错误响应：

```json
{
  "ok": 0,
  "error": {
    "code": "TIMEOUT",
    "message": "upstream timeout",
    "retryable": true
  },
  "trace_id": "uuid",
  "provider": "openai",
  "model": "gpt-4o-mini",
  "latency_ms": 60012
}
```

## 4. 可观测字段（统一约定）

- 请求头透传：
- `x-trace-id`
- `x-correlation-id`
- `x-idempotency-key`
- 响应字段：
- `trace_id`
- `provider`
- `model`
- `latency_ms`
- `usage.prompt_tokens`
- `usage.completion_tokens`
- `usage.total_tokens`
- 网关结构化日志：
- 事件名：`stream-text` / `generate-object` / `tool-call`
- 结果：`ok`（1/0）
- 错误：`error.code`（如失败）
- 审计文件：`.data/metrics/node_gateway_events.jsonl`

## 5. Python/Node 语义对齐结论

- Python `AISDKAdapter.stream_text` <-> Node `/v1/stream-text` 一致。
- Python `AISDKAdapter.generate_object` <-> Node `/v1/generate-object` 一致。
- Python `AISDKAdapter.tool_call` 优先走 Node，失败回退本地 registry。
- 当 Node 路径异常且启用回退时，自动切回 Python provider。
