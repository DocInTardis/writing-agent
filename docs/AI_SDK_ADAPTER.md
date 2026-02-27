# AI SDK Adapter

Backend adapter:

- `writing_agent/llm/ai_sdk_adapter.py`
- `writing_agent/llm/tool_registry.py`
- `writing_agent/llm/tool_manifest.json`
- `writing_agent/web/idempotency.py`

Frontend stream bridge:

- `writing_agent/web/frontend_svelte/src/lib/flows/aiSdkClient.ts`

Provides unified semantics for:

- `stream_text`
- `generate_object`
- `tool_call`

Error classification:

- rate limit / timeout / context overflow / schema failure

Request dedupe:

- idempotency key support in generation service (`x-idempotency-key`)
