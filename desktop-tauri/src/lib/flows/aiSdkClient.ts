export interface StreamEvent {
  event: string
  data: unknown
}

export async function* streamText(
  url: string,
  payload: Record<string, unknown>,
  signal?: AbortSignal
): AsyncGenerator<StreamEvent, void, unknown> {
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload || {}),
    signal
  })
  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status}`)
  }
  const reader = resp.body?.getReader()
  if (!reader) return
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let idx = buffer.indexOf('\n')
    while (idx >= 0) {
      const line = buffer.slice(0, idx).trim()
      buffer = buffer.slice(idx + 1)
      if (line) {
        try {
          const parsed = JSON.parse(line)
          yield { event: String(parsed.event || 'delta'), data: parsed }
        } catch {
          yield { event: 'delta', data: { delta: line } }
        }
      }
      idx = buffer.indexOf('\n')
    }
  }
}

export function makeResumePayload(
  base: Record<string, unknown>,
  opts: { composeMode?: string; resumeSections?: string[]; formatOnly?: boolean }
): Record<string, unknown> {
  const out: Record<string, unknown> = { ...(base || {}) }
  if (opts.composeMode) out.compose_mode = opts.composeMode
  if (opts.resumeSections && opts.resumeSections.length) out.resume_sections = opts.resumeSections
  if (typeof opts.formatOnly === 'boolean') out.format_only = opts.formatOnly
  return out
}
