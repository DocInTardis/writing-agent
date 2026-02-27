function usageFromText(text) {
  return {
    prompt_tokens: 32,
    completion_tokens: Math.max(1, Math.floor(String(text || '').length / 4)),
    total_tokens: 32 + Math.max(1, Math.floor(String(text || '').length / 4)),
  };
}

function buildMockText({ system, prompt }) {
  const sys = String(system || '').trim();
  const usr = String(prompt || '').trim();
  return `MOCK_RESPONSE::${sys ? `[S:${sys.slice(0, 24)}]` : ''}${usr ? `[U:${usr.slice(0, 96)}]` : ''}`;
}

export function createMockEngine() {
  return {
    async generateText({ system, prompt }) {
      const text = buildMockText({ system, prompt });
      return { text, usage: usageFromText(text), finish_reason: 'stop' };
    },

    async *streamText({ system, prompt }) {
      const text = buildMockText({ system, prompt });
      for (const ch of text) {
        yield { type: 'text-delta', delta: ch };
      }
      yield { type: 'done', text, usage: usageFromText(text), finish_reason: 'stop' };
    },

    async generateObject({ prompt }) {
      const text = String(prompt || '');
      const object = {
        ok: 1,
        source: 'mock',
        summary: text.slice(0, 48),
      };
      return { object, usage: usageFromText(text), finish_reason: 'stop' };
    },
  };
}
