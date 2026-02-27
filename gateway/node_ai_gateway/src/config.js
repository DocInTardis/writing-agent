import { randomUUID } from 'node:crypto';

function asBool(value, fallback = false) {
  const raw = String(value ?? '').trim().toLowerCase();
  if (!raw) return Boolean(fallback);
  return ['1', 'true', 'yes', 'on'].includes(raw);
}

function asInt(value, fallback) {
  const parsed = Number.parseInt(String(value ?? ''), 10);
  if (Number.isNaN(parsed)) return fallback;
  return parsed;
}

export function loadConfig(env = process.env) {
  return {
    host: String(env.WA_NODE_GATEWAY_HOST || '127.0.0.1'),
    port: asInt(env.WA_NODE_GATEWAY_PORT, 8787),
    provider: String(env.WA_NODE_GATEWAY_PROVIDER || 'openai'),
    defaultModel: String(env.WA_NODE_GATEWAY_MODEL || env.WRITING_AGENT_OPENAI_MODEL || 'gpt-4o-mini'),
    timeoutMs: asInt(env.WA_NODE_GATEWAY_TIMEOUT_MS, 60000),
    maxRetries: asInt(env.WA_NODE_GATEWAY_MAX_RETRIES, 2),
    mockMode: asBool(env.WA_NODE_GATEWAY_MOCK, false),
    logPath: String(env.WA_NODE_GATEWAY_LOG_PATH || '.data/metrics/node_gateway_events.jsonl'),
    startupTraceId: randomUUID(),
  };
}
