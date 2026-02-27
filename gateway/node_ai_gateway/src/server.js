import { randomUUID } from 'node:crypto';

import Fastify from 'fastify';

import { createAiEngine } from './ai_engine.js';
import { loadConfig } from './config.js';
import { buildErrorPayload, classifyError, ErrorCode } from './errors.js';
import { writeAuditLog } from './logger.js';
import { createMockEngine } from './mock_engine.js';
import { runTool } from './tool_runtime.js';

function nowMs() {
  return Date.now();
}

function buildRuntimeMeta(request, config) {
  const traceId = String(request.headers['x-trace-id'] || request.headers['x-correlation-id'] || randomUUID());
  const idempotencyKey = String(request.headers['x-idempotency-key'] || '');
  return {
    traceId,
    idempotencyKey,
    provider: config.provider,
    model: '',
    startedAtMs: nowMs(),
  };
}

function setResponseHeaders(reply, meta) {
  reply.header('x-trace-id', meta.traceId);
  if (meta.idempotencyKey) {
    reply.header('x-idempotency-key', meta.idempotencyKey);
  }
}

function writeSse(reply, payload) {
  reply.raw.write(`data: ${JSON.stringify(payload)}\n\n`);
}

function audit(app, config, payload) {
  app.log.info(payload);
  writeAuditLog(config.logPath, payload);
}

export function createServer({ config: explicitConfig, engine: explicitEngine } = {}) {
  const config = explicitConfig || loadConfig(process.env);
  const app = Fastify({ logger: true });
  const engine = explicitEngine || (config.mockMode ? createMockEngine() : createAiEngine(config));

  app.get('/health', async () => ({ ok: 1, service: 'node-ai-gateway', provider: config.provider }));

  app.post('/v1/stream-text', async (request, reply) => {
    const meta = buildRuntimeMeta(request, config);
    const body = request.body || {};
    meta.model = String(body.model || config.defaultModel);
    const streamMode = Boolean(body.stream !== false);

    try {
      if (!streamMode) {
        const result = await engine.generateText(body);
        const latencyMs = nowMs() - meta.startedAtMs;
        const response = {
          ok: 1,
          text: String(result.text || ''),
          usage: result.usage || {},
          finish_reason: String(result.finish_reason || 'stop'),
          trace_id: meta.traceId,
          provider: meta.provider,
          model: meta.model,
          latency_ms: latencyMs,
        };
        setResponseHeaders(reply, meta);
        audit(app, config, { event: 'stream-text', mode: 'non-stream', ok: 1, ...response });
        return response;
      }

      setResponseHeaders(reply, meta);
      reply.raw.writeHead(200, {
        'content-type': 'text/event-stream; charset=utf-8',
        'cache-control': 'no-cache, no-transform',
        connection: 'keep-alive',
      });

      for await (const event of engine.streamText(body)) {
        if (event.type === 'text-delta') {
          writeSse(reply, {
            type: 'text-delta',
            delta: String(event.delta || ''),
            trace_id: meta.traceId,
          });
          continue;
        }

        if (event.type === 'done') {
          const latencyMs = nowMs() - meta.startedAtMs;
          writeSse(reply, {
            type: 'done',
            text: String(event.text || ''),
            usage: event.usage || {},
            finish_reason: String(event.finish_reason || 'stop'),
            trace_id: meta.traceId,
            provider: meta.provider,
            model: meta.model,
            latency_ms: latencyMs,
          });
          audit(app, config, {
            event: 'stream-text',
            mode: 'stream',
            ok: 1,
            trace_id: meta.traceId,
            provider: meta.provider,
            model: meta.model,
            latency_ms: latencyMs,
          });
        }
      }
      reply.raw.end();
      return reply;
    } catch (error) {
      const latencyMs = nowMs() - meta.startedAtMs;
      const classified = classifyError(error);
      const payload = buildErrorPayload(classified, {
        traceId: meta.traceId,
        provider: meta.provider,
        model: meta.model,
        latencyMs,
      });
      if (streamMode) {
        writeSse(reply, { type: 'error', ...payload });
        reply.raw.end();
      } else {
        setResponseHeaders(reply, meta);
        reply.code(classified.httpStatus).send(payload);
      }
      audit(app, config, { event: 'stream-text', mode: streamMode ? 'stream' : 'non-stream', ok: 0, ...payload });
      return reply;
    }
  });

  app.post('/v1/generate-object', async (request, reply) => {
    const meta = buildRuntimeMeta(request, config);
    const body = request.body || {};
    meta.model = String(body.model || config.defaultModel);
    try {
      const result = await engine.generateObject(body);
      const latencyMs = nowMs() - meta.startedAtMs;
      const response = {
        ok: 1,
        object: result.object || {},
        usage: result.usage || {},
        finish_reason: String(result.finish_reason || 'stop'),
        trace_id: meta.traceId,
        provider: meta.provider,
        model: meta.model,
        latency_ms: latencyMs,
      };
      setResponseHeaders(reply, meta);
      audit(app, config, { event: 'generate-object', ok: 1, ...response });
      return response;
    } catch (error) {
      const latencyMs = nowMs() - meta.startedAtMs;
      const classified = classifyError(error);
      const payload = buildErrorPayload(classified, {
        traceId: meta.traceId,
        provider: meta.provider,
        model: meta.model,
        latencyMs,
      });
      setResponseHeaders(reply, meta);
      audit(app, config, { event: 'generate-object', ok: 0, ...payload });
      return reply.code(classified.httpStatus).send(payload);
    }
  });

  app.post('/v1/tool-call', async (request, reply) => {
    const meta = buildRuntimeMeta(request, config);
    const body = request.body || {};
    meta.model = String(body.model || config.defaultModel);
    try {
      const toolName = String(body.tool_name || '');
      const result = runTool(toolName, body.arguments || {});
      const latencyMs = nowMs() - meta.startedAtMs;
      const response = {
        ok: 1,
        tool_name: toolName,
        result,
        trace_id: meta.traceId,
        provider: 'gateway-tool-runtime',
        model: meta.model,
        latency_ms: latencyMs,
      };
      setResponseHeaders(reply, meta);
      audit(app, config, { event: 'tool-call', ok: 1, ...response });
      return response;
    } catch (error) {
      const latencyMs = nowMs() - meta.startedAtMs;
      const classified = classifyError(error?.message?.startsWith('tool_not_found:') ? { message: ErrorCode.BAD_REQUEST } : error);
      const payload = buildErrorPayload(classified, {
        traceId: meta.traceId,
        provider: 'gateway-tool-runtime',
        model: meta.model,
        latencyMs,
      });
      setResponseHeaders(reply, meta);
      audit(app, config, { event: 'tool-call', ok: 0, ...payload });
      return reply.code(classified.httpStatus).send(payload);
    }
  });

  return app;
}

async function main() {
  const config = loadConfig(process.env);
  const app = createServer({ config });
  await app.listen({ host: config.host, port: config.port });
  app.log.info({
    event: 'node-ai-gateway-started',
    host: config.host,
    port: config.port,
    provider: config.provider,
    model: config.defaultModel,
    trace_id: config.startupTraceId,
  });
}

if (process.argv[1] && process.argv[1].endsWith('server.js')) {
  main().catch((error) => {
    // eslint-disable-next-line no-console
    console.error(error);
    process.exit(1);
  });
}
