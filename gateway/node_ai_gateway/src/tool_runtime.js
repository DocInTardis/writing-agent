function asObject(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  return value;
}

export function runTool(toolName, argumentsPayload) {
  const args = asObject(argumentsPayload);
  const name = String(toolName || '').trim();
  if (!name) throw new Error('tool_name required');

  if (name === 'echo') {
    return { ok: 1, echoed: args };
  }
  if (name === 'health_check') {
    return { ok: 1, status: 'ok' };
  }
  if (name === 'word_count') {
    const text = String(args.text || '');
    const words = text.trim() ? text.trim().split(/\s+/).length : 0;
    return { ok: 1, words };
  }

  // Keep explicit failure for unknown tools; Python can still execute tools locally.
  throw new Error(`tool_not_found:${name}`);
}
