import type { GraphMeta, OriginalityRiskRow, OriginalitySummary, ResumeState } from './types'

export function normalizeStringArray(raw: unknown): string[] {
  if (!Array.isArray(raw)) return []
  const out: string[] = []
  const seen = new Set<string>()
  for (const item of raw) {
    const v = String(item || '').trim()
    if (!v || seen.has(v)) continue
    seen.add(v)
    out.push(v)
  }
  return out
}

export function normalizeResumeState(raw: any): ResumeState | null {
  if (!raw || typeof raw !== 'object') return null
  const status = String(raw.status || '').trim().toLowerCase()
  if (status !== 'running' && status !== 'interrupted') return null
  const composeModeRaw = String(raw.compose_mode || 'auto').trim().toLowerCase()
  const composeMode =
    composeModeRaw === 'continue' || composeModeRaw === 'overwrite' || composeModeRaw === 'auto'
      ? (composeModeRaw as ResumeState['compose_mode'])
      : 'auto'
  return {
    status: status as ResumeState['status'],
    updated_at: Number(raw.updated_at || 0),
    user_instruction: String(raw.user_instruction || '').trim(),
    request_instruction: String(raw.request_instruction || '').trim(),
    compose_mode: composeMode,
    partial_chars: Number(raw.partial_chars || 0),
    partial_preview: String(raw.partial_preview || '').trim(),
    plan_sections: normalizeStringArray(raw.plan_sections),
    completed_sections: normalizeStringArray(raw.completed_sections),
    pending_sections: normalizeStringArray(raw.pending_sections),
    cursor_anchor: String(raw.cursor_anchor || '').trim(),
    error: String(raw.error || '').trim()
  }
}

export function normalizeGraphMeta(raw: unknown): GraphMeta | null {
  if (!raw || typeof raw !== 'object') return null
  const obj = raw as Record<string, unknown>
  const path = String(obj.path || '').trim()
  if (path !== 'route_graph') return null
  return {
    path: 'route_graph',
    trace_id: String(obj.trace_id || '').trim(),
    engine: String(obj.engine || '').trim(),
    route_id: String(obj.route_id || '').trim(),
    route_entry: String(obj.route_entry || '').trim()
  }
}

export function summarizeGraphMeta(meta: GraphMeta) {
  const routeId = meta.route_id || 'default'
  const routeEntry = meta.route_entry || 'planner'
  const engine = meta.engine || 'legacy'
  const trace = meta.trace_id ? meta.trace_id.slice(0, 8) : '-'
  return `route=${routeId}; entry=${routeEntry}; engine=${engine}; trace=${trace}`
}

export function normalizeOriginalitySummary(raw: unknown): OriginalitySummary | null {
  if (!raw || typeof raw !== 'object') return null
  const obj = raw as Record<string, unknown>
  const rowsRaw = Array.isArray(obj.rows) ? obj.rows : []
  const rows: OriginalityRiskRow[] = rowsRaw
    .filter((row) => row && typeof row === 'object')
    .map((row) => {
      const item = row as Record<string, unknown>
      return {
        section: String(item.section || '').trim(),
        section_id: String(item.section_id || '').trim(),
        title: String(item.title || item.section || '').trim(),
        phases: Array.isArray(item.phases) ? item.phases.map((v) => String(v || '').trim()).filter(Boolean) : [],
        checked_event_count: Number(item.checked_event_count || 0),
        failed_event_count: Number(item.failed_event_count || 0),
        rewrite_count: Number(item.rewrite_count || 0),
        retry_count: Number(item.retry_count || 0),
        cache_rejected_count: Number(item.cache_rejected_count || 0),
        fast_draft_rejected_count: Number(item.fast_draft_rejected_count || 0),
        latest_passed: Boolean(item.latest_passed ?? true),
        max_repeat_sentence_ratio: Number(item.max_repeat_sentence_ratio || 0),
        max_formulaic_opening_ratio: Number(item.max_formulaic_opening_ratio || 0),
        max_source_overlap_ratio: Number(item.max_source_overlap_ratio || 0)
      }
    })
  return {
    enabled: Boolean(obj.enabled ?? false),
    eventCount: Number(obj.event_count || 0),
    checkedSectionCount: Number(obj.checked_section_count || 0),
    failedSectionCount: Number(obj.failed_section_count || 0),
    failedSectionRatio: Number(obj.failed_section_ratio || 0),
    rewriteCount: Number(obj.rewrite_count || 0),
    retryCount: Number(obj.retry_count || 0),
    cacheRejectedCount: Number(obj.cache_rejected_count || 0),
    fastDraftRejectedCount: Number(obj.fast_draft_rejected_count || 0),
    rows
  }
}

export function summarizeOriginalitySummary(summary: OriginalitySummary | null) {
  if (!summary) return '原创性热采样未启用'
  return `已检查 ${summary.checkedSectionCount} 节 · 风险 ${summary.failedSectionCount} 节 · 重写 ${summary.rewriteCount} 次 · 重试 ${summary.retryCount} 次`
}
