# Node AI Gateway (Vercel AI SDK)

This service is the incremental bridge for adopting the official Vercel AI SDK npm packages while keeping Python orchestration unchanged.

## Endpoints

- `POST /v1/stream-text`
- `POST /v1/generate-object`
- `POST /v1/tool-call`
- `GET /health`

## Environment Variables

- `WA_NODE_GATEWAY_HOST` (default: `127.0.0.1`)
- `WA_NODE_GATEWAY_PORT` (default: `8787`)
- `WA_NODE_GATEWAY_PROVIDER` (default: `openai`)
- `WA_NODE_GATEWAY_MODEL` (default: `gpt-4o-mini`)
- `WA_NODE_GATEWAY_TIMEOUT_MS` (default: `60000`)
- `WA_NODE_GATEWAY_MAX_RETRIES` (default: `2`)
- `WA_NODE_GATEWAY_MOCK` (default: `0`)
- `WA_NODE_GATEWAY_LOG_PATH` (default: `.data/metrics/node_gateway_events.jsonl`)
- `WRITING_AGENT_OPENAI_API_KEY` (required when mock mode is disabled)

## Local Development

```bash
npm install
npm test
npm run dev
```

## Production

```bash
npm install --omit=dev
npm start
```
