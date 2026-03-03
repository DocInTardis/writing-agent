export type ComposeMode = 'auto' | 'continue' | 'overwrite'

export type SelectionPayload = {
  start?: number
  end?: number
  text: string
}

export type ContextPolicyPayload = {
  version: string
  short_selection_threshold_chars: number
  short_selection_threshold_tokens: number
  window_formula: string
  window_min_chars: number
  window_max_chars: number
  prompt_budget_ratio: number
}

type SanitizeTextOptions = {
  trim?: boolean
  collapseWhitespace?: boolean
  maxChars?: number
}

type SanitizeListOptions = {
  maxItems?: number
  maxItemChars?: number
}

type BuildGeneratePayloadInput = {
  instruction: unknown
  text: unknown
  composeMode?: unknown
  selection?: unknown
  contextPolicy?: unknown
  resumeSections?: unknown
  cursorAnchor?: unknown
}

const CONTROL_CHAR_RE = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g

const DEFAULT_MAX_CHARS = 12000
const DEFAULT_INSTRUCTION_MAX_CHARS = 12000
const DEFAULT_DOC_TEXT_MAX_CHARS = 2_000_000
const DEFAULT_SELECTION_TEXT_MAX_CHARS = 16000
const DEFAULT_RESUME_SECTIONS_MAX_ITEMS = 64
const DEFAULT_RESUME_SECTION_MAX_CHARS = 120
const DEFAULT_CURSOR_ANCHOR_MAX_CHARS = 260

export const DIAGRAM_PROMPT_MAX_CHARS = 2400

export const DEFAULT_CONTEXT_POLICY: ContextPolicyPayload = {
  version: 'dynamic_v1',
  short_selection_threshold_chars: 30,
  short_selection_threshold_tokens: 8,
  window_formula: '220 + 0.8 * L + short_boost',
  window_min_chars: 240,
  window_max_chars: 1200,
  prompt_budget_ratio: 0.3
}

function asBoundedInt(raw: unknown, bounds: { min: number; max: number }): number | null {
  const min = Number(bounds.min)
  const max = Number(bounds.max)
  const value = Number(raw)
  if (!Number.isFinite(value)) return null
  const rounded = Math.trunc(value)
  if (rounded < min || rounded > max) return null
  return rounded
}

function clampNumber(raw: unknown, fallback: number, min: number, max: number): number {
  const value = Number(raw)
  if (!Number.isFinite(value)) return fallback
  if (value < min) return min
  if (value > max) return max
  return value
}

function normalizeComposeMode(raw: unknown): ComposeMode {
  const mode = String(raw || '').trim().toLowerCase()
  if (mode === 'continue' || mode === 'overwrite' || mode === 'auto') {
    return mode
  }
  return 'auto'
}

export function sanitizeAiInputText(raw: unknown, opts: SanitizeTextOptions = {}): string {
  const trim = opts.trim !== false
  const collapseWhitespace = opts.collapseWhitespace === true
  const maxChars = Math.max(0, Math.trunc(Number(opts.maxChars || DEFAULT_MAX_CHARS)))
  let text = String(raw ?? '')
  text = text.replace(/\r\n?/g, '\n')
  text = text.replace(CONTROL_CHAR_RE, '')
  if (collapseWhitespace) {
    text = text.replace(/\s+/g, ' ')
  }
  if (trim) {
    text = text.trim()
  }
  if (maxChars > 0 && text.length > maxChars) {
    text = text.slice(0, maxChars)
    if (trim) {
      text = text.trim()
    }
  }
  return text
}

export function sanitizeAiDocumentText(raw: unknown, maxChars: number = DEFAULT_DOC_TEXT_MAX_CHARS): string {
  const text = String(raw ?? "")
  const cap = Math.max(0, Math.trunc(Number(maxChars || 0)))
  if (cap > 0 && text.length > cap) {
    return text.slice(0, cap)
  }
  return text
}

export function sanitizeAiStringList(raw: unknown, opts: SanitizeListOptions = {}): string[] {
  if (!Array.isArray(raw)) return []
  const maxItems = Math.max(1, Math.trunc(Number(opts.maxItems || DEFAULT_RESUME_SECTIONS_MAX_ITEMS)))
  const maxItemChars = Math.max(8, Math.trunc(Number(opts.maxItemChars || DEFAULT_RESUME_SECTION_MAX_CHARS)))
  const out: string[] = []
  const seen = new Set<string>()
  for (const item of raw) {
    const value = sanitizeAiInputText(item, { trim: true, maxChars: maxItemChars })
    if (!value || seen.has(value)) continue
    seen.add(value)
    out.push(value)
    if (out.length >= maxItems) break
  }
  return out
}

export function sanitizeAiSelectionPayload(
  raw: unknown,
  opts: { maxTextChars?: number } = {}
): SelectionPayload | null {
  const maxTextChars = Math.max(16, Math.trunc(Number(opts.maxTextChars || DEFAULT_SELECTION_TEXT_MAX_CHARS)))
  if (raw == null) return null

  if (typeof raw === 'string') {
    const text = sanitizeAiInputText(raw, { trim: true, maxChars: maxTextChars })
    return text ? { text } : null
  }

  if (typeof raw !== 'object' || Array.isArray(raw)) {
    return null
  }

  const row = raw as Record<string, unknown>
  const text = sanitizeAiInputText(row.text, { trim: true, maxChars: maxTextChars })
  if (!text) return null
  const start = asBoundedInt(row.start, { min: 0, max: 5_000_000 })
  const end = asBoundedInt(row.end, { min: 0, max: 5_000_000 })
  if (start !== null && end !== null && end >= start) {
    return { start, end, text }
  }
  return { text }
}

export function normalizeContextPolicy(raw: unknown): ContextPolicyPayload {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) {
    return { ...DEFAULT_CONTEXT_POLICY }
  }
  const row = raw as Record<string, unknown>
  const version = sanitizeAiInputText(row.version, { trim: true, maxChars: 32 }) || DEFAULT_CONTEXT_POLICY.version
  const minChars = clampNumber(row.window_min_chars, DEFAULT_CONTEXT_POLICY.window_min_chars, 120, 2400)
  const maxChars = clampNumber(row.window_max_chars, DEFAULT_CONTEXT_POLICY.window_max_chars, minChars, 6000)
  return {
    version,
    short_selection_threshold_chars: clampNumber(
      row.short_selection_threshold_chars,
      DEFAULT_CONTEXT_POLICY.short_selection_threshold_chars,
      5,
      400
    ),
    short_selection_threshold_tokens: clampNumber(
      row.short_selection_threshold_tokens,
      DEFAULT_CONTEXT_POLICY.short_selection_threshold_tokens,
      1,
      256
    ),
    window_formula:
      sanitizeAiInputText(row.window_formula, { trim: true, maxChars: 120 }) || DEFAULT_CONTEXT_POLICY.window_formula,
    window_min_chars: minChars,
    window_max_chars: maxChars,
    prompt_budget_ratio: clampNumber(
      row.prompt_budget_ratio,
      DEFAULT_CONTEXT_POLICY.prompt_budget_ratio,
      0.1,
      0.8
    )
  }
}

export function sanitizeDiagramPrompt(raw: unknown, maxChars: number = DIAGRAM_PROMPT_MAX_CHARS): string {
  return sanitizeAiInputText(raw, { trim: true, maxChars: Math.max(200, Math.trunc(Number(maxChars || 0))) })
}

export function buildGenerateRequestPayload(input: BuildGeneratePayloadInput): Record<string, unknown> {
  const instruction = sanitizeAiInputText(input.instruction, {
    trim: true,
    maxChars: DEFAULT_INSTRUCTION_MAX_CHARS
  })
  const text = sanitizeAiDocumentText(input.text, DEFAULT_DOC_TEXT_MAX_CHARS)
  const composeMode = normalizeComposeMode(input.composeMode)

  const payload: Record<string, unknown> = {
    instruction,
    text,
    compose_mode: composeMode
  }

  const selection = sanitizeAiSelectionPayload(input.selection)
  if (selection) {
    payload.selection = selection
    payload.context_policy = normalizeContextPolicy(input.contextPolicy)
  }

  const resumeSections = sanitizeAiStringList(input.resumeSections, {
    maxItems: DEFAULT_RESUME_SECTIONS_MAX_ITEMS,
    maxItemChars: DEFAULT_RESUME_SECTION_MAX_CHARS
  })
  if (resumeSections.length > 0) {
    payload.resume_sections = resumeSections
  }

  const cursorAnchor = sanitizeAiInputText(input.cursorAnchor, {
    trim: true,
    maxChars: DEFAULT_CURSOR_ANCHOR_MAX_CHARS
  })
  if (cursorAnchor) {
    payload.cursor_anchor = cursorAnchor
  }

  return payload
}
