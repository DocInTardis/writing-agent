import assert from 'node:assert/strict';
import test from 'node:test';

import { createMockEngine } from '../src/mock_engine.js';
import { createServer } from '../src/server.js';

async function withServer(fn) {
  const app = createServer({
    config: {
      host: '127.0.0.1',
      port: 0,
      provider: 'openai',
      defaultModel: 'gpt-4o-mini',
      timeoutMs: 10000,
      maxRetries: 1,
      mockMode: true,
      logPath: '.data/metrics/node_gateway_test_events.jsonl',
      startupTraceId: 'test-trace',
    },
    engine: createMockEngine(),
  });
  await app.listen({ host: '127.0.0.1', port: 0 });
  const address = app.server.address();
  const baseUrl = `http://127.0.0.1:${address.port}`;
  try {
    await fn(baseUrl);
  } finally {
    await app.close();
  }
}

test('POST /v1/stream-text (non-stream) contract', async () => {
  await withServer(async (baseUrl) => {
    const response = await fetch(`${baseUrl}/v1/stream-text`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-trace-id': 'trace-a',
        'x-idempotency-key': 'idem-a',
      },
      body: JSON.stringify({
        stream: false,
        system: 'system prompt',
        prompt: 'hello',
      }),
    });
    assert.equal(response.status, 200);
    assert.equal(response.headers.get('x-trace-id'), 'trace-a');
    assert.equal(response.headers.get('x-idempotency-key'), 'idem-a');
    const data = await response.json();
    assert.equal(data.ok, 1);
    assert.equal(typeof data.text, 'string');
    assert.equal(typeof data.latency_ms, 'number');
    assert.equal(data.trace_id, 'trace-a');
  });
});

test('POST /v1/stream-text (stream) emits SSE done payload', async () => {
  await withServer(async (baseUrl) => {
    const response = await fetch(`${baseUrl}/v1/stream-text`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-trace-id': 'trace-b',
      },
      body: JSON.stringify({
        stream: true,
        system: 'system prompt',
        prompt: 'hello',
      }),
    });
    assert.equal(response.status, 200);
    const text = await response.text();
    assert.match(text, /"type":"text-delta"/);
    assert.match(text, /"type":"done"/);
    assert.match(text, /"trace_id":"trace-b"/);
  });
});

test('POST /v1/generate-object contract', async () => {
  await withServer(async (baseUrl) => {
    const response = await fetch(`${baseUrl}/v1/generate-object`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-trace-id': 'trace-c',
      },
      body: JSON.stringify({
        system: 'system prompt',
        prompt: 'object please',
        schema: {
          type: 'object',
          properties: {
            ok: { type: 'number' },
            summary: { type: 'string' },
          },
        },
      }),
    });
    assert.equal(response.status, 200);
    const data = await response.json();
    assert.equal(data.ok, 1);
    assert.equal(typeof data.object, 'object');
    assert.equal(data.trace_id, 'trace-c');
  });
});

test('POST /v1/tool-call contract', async () => {
  await withServer(async (baseUrl) => {
    const response = await fetch(`${baseUrl}/v1/tool-call`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
      },
      body: JSON.stringify({
        tool_name: 'echo',
        arguments: { hello: 'world' },
      }),
    });
    assert.equal(response.status, 200);
    const data = await response.json();
    assert.equal(data.ok, 1);
    assert.equal(data.tool_name, 'echo');
    assert.deepEqual(data.result.echoed, { hello: 'world' });
  });
});
