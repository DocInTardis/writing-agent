export interface CacheMetrics {
  size: number
  ttl_s: number
  max_entries: number
  hit: number
  miss: number
  set: number
  expired: number
  evicted: number
}

export interface ObserveCacheDelta {
  hit: number
  miss: number
  set: number
  expired: number
  evicted: number
  hit_rate: number
}

export interface ObserveRecentRun {
  ts: number
  elapsed_ms: number
  item_count: number
  worker_count: number
  error_count: number
  cache_delta: ObserveCacheDelta
}

export interface ObserveWindow {
  window_s: number
  max_runs: number
  runs: number
  elapsed_ms: { avg: number; p50: number; p95: number; max: number }
  items: { total: number; avg: number; p50: number; p95: number; max: number }
  workers: { avg: number; max: number }
  errors: { total: number; rate_per_run: number }
  cache_delta: ObserveCacheDelta
  recent: ObserveRecentRun[]
}

export type AlertLevel = 'warn' | 'critical'
export type AlertSeverity = 'ok' | 'warn' | 'critical'

export interface MetricsAlertRule {
  id: string
  level: AlertLevel
  triggered: boolean
  value: number
  threshold: number
  op: string
  message: string
}

export interface MetricsNotifyEvent {
  id: string
  ts: number
  severity: AlertSeverity
  event_type: string
  status: string
  sent: boolean
  dedupe_hit: boolean
  triggered_rules: string[]
  channels: string[]
}

export interface MetricsTrendPoint {
  id: string
  ts: number
  severity: AlertSeverity
  degraded: boolean
  runs: number
  p95_ms: number
  error_rate_per_run: number
  cache_delta_hit_rate: number
  triggered_alerts: number
  notification_status: string
}

export interface MetricsTrend {
  enabled: boolean
  total: number
  limit: number
  points: MetricsTrendPoint[]
}

export interface MetricsEventContext {
  event_id: string
  total: number
  before: number
  after: number
  points: MetricsTrendPoint[]
}

export interface MetricsAlerts {
  enabled: boolean
  severity: AlertSeverity
  triggered: number
  runs: number
  min_runs: number
  warmup: boolean
  thresholds: {
    p95_ms: number
    error_rate_per_run: number
    cache_delta_hit_rate: number
  }
  rules: MetricsAlertRule[]
  triggered_rules: string[]
  notification: {
    enabled: boolean
    webhook_configured: boolean
    sent: boolean
    channels: string[]
    signature: string
    dedupe_hit: boolean
    event_type: string
    status: string
    cooldown_s: number
    last_sent_at: number
    suppressed: number
    last_error: string
    event_id: string
    events_total: number
    events_recent: MetricsNotifyEvent[]
  }
}

export interface MetricsView {
  cache: CacheMetrics
  observe: ObserveWindow
  degraded: boolean
  errors: string[]
  alerts: MetricsAlerts
  trend: MetricsTrend
}

export interface AlertConfigForm {
  enabled: boolean
  min_runs: number
  p95_ms: number
  error_rate_per_run: number
  cache_delta_hit_rate: number
}

type UnknownRecord = Record<string, unknown>

export const POLL_MS = 5000

export function toSafeInt(value: unknown): number {
  const n = Number(value)
  if (!Number.isFinite(n)) return 0
  return Math.max(0, Math.round(n))
}

export function toSafeFloat(value: unknown): number {
  const n = Number(value)
  if (!Number.isFinite(n)) return 0
  return Math.max(0, n)
}

export function toSafeRate(value: unknown): number {
  return Math.max(0, Math.min(1, toSafeFloat(value)))
}

export function formatRate(rate: number): string {
  return `${(Math.max(0, Math.min(1, rate)) * 100).toFixed(1)}%`
}

export function cacheHitRate(cache: CacheMetrics): number {
  const lookups = toSafeInt(cache.hit) + toSafeInt(cache.miss)
  if (lookups <= 0) return 0
  return toSafeInt(cache.hit) / lookups
}

export function formatTime(ts: number): string {
  const raw = Number(ts || 0)
  if (!Number.isFinite(raw) || raw <= 0) return '--:--:--'
  const ms = raw > 10_000_000_000 ? raw : raw * 1000
  return new Date(ms).toLocaleTimeString('zh-CN', { hour12: false })
}

export function formatAlertMetric(value: number): string {
  const n = Number(value || 0)
  if (!Number.isFinite(n)) return '0'
  if (Math.abs(n) < 1) return n.toFixed(3)
  if (Math.abs(n) < 100) return n.toFixed(2)
  return n.toFixed(1)
}

export function clampAlertConfig(input: {
  enabled: unknown
  min_runs: unknown
  p95_ms: unknown
  error_rate_per_run: unknown
  cache_delta_hit_rate: unknown
}): AlertConfigForm {
  return {
    enabled: Boolean(input.enabled),
    min_runs: Math.max(1, Math.min(500, toSafeInt(input.min_runs) || 8)),
    p95_ms: Math.max(100, Math.min(60000, toSafeInt(input.p95_ms) || 4500)),
    error_rate_per_run: Math.max(0, Math.min(1, toSafeFloat(input.error_rate_per_run) || 0)),
    cache_delta_hit_rate: Math.max(0, Math.min(1, toSafeFloat(input.cache_delta_hit_rate) || 0))
  }
}

function normalizeObserveCacheDelta(raw: unknown): ObserveCacheDelta {
  const row = raw && typeof raw === 'object' ? (raw as UnknownRecord) : {}
  return {
    hit: toSafeInt(row.hit),
    miss: toSafeInt(row.miss),
    set: toSafeInt(row.set),
    expired: toSafeInt(row.expired),
    evicted: toSafeInt(row.evicted),
    hit_rate: toSafeRate(row.hit_rate)
  }
}

function normalizeErrorList(raw: unknown): string[] {
  if (!Array.isArray(raw)) return []
  return raw
    .map((row) => String(row || '').trim())
    .filter((row) => row.length > 0)
    .slice(0, 12)
}

function normalizeAlertLevel(raw: unknown): AlertLevel {
  return String(raw || '').trim().toLowerCase() === 'critical' ? 'critical' : 'warn'
}

function normalizeAlertSeverity(raw: unknown): AlertSeverity {
  const v = String(raw || '').trim().toLowerCase()
  if (v === 'critical') return 'critical'
  if (v === 'warn') return 'warn'
  return 'ok'
}

export function normalizeTrendPoint(raw: unknown): MetricsTrendPoint {
  const item = raw && typeof raw === 'object' ? (raw as UnknownRecord) : {}
  return {
    id: String(item.id || '').trim(),
    ts: toSafeFloat(item.ts),
    severity: normalizeAlertSeverity(item.severity),
    degraded: Boolean(item.degraded),
    runs: toSafeInt(item.runs),
    p95_ms: toSafeFloat(item.p95_ms),
    error_rate_per_run: toSafeRate(item.error_rate_per_run),
    cache_delta_hit_rate: toSafeRate(item.cache_delta_hit_rate),
    triggered_alerts: toSafeInt(item.triggered_alerts),
    notification_status: String(item.notification_status || '').trim()
  }
}

export function normalizeEventContextPayload(data: unknown, eventId: string): MetricsEventContext {
  const payload = data && typeof data === 'object' ? (data as UnknownRecord) : {}
  const ctxRaw =
    payload.trend_context && typeof payload.trend_context === 'object' ? (payload.trend_context as UnknownRecord) : {}
  const pointsRaw = Array.isArray(ctxRaw.points) ? ctxRaw.points : []
  return {
    event_id: eventId,
    total: toSafeInt(ctxRaw.total),
    before: toSafeInt(ctxRaw.before),
    after: toSafeInt(ctxRaw.after),
    points: pointsRaw.map((row) => normalizeTrendPoint(row)).filter((row) => row.id.length > 0)
  }
}

export function normalizeMetricsPayload(data: unknown): MetricsView {
  const payload = data && typeof data === 'object' ? (data as UnknownRecord) : {}
  const cacheRaw = payload.cache && typeof payload.cache === 'object' ? (payload.cache as UnknownRecord) : {}
  const observeRaw = payload.observe && typeof payload.observe === 'object' ? (payload.observe as UnknownRecord) : {}
  const elapsedRaw = observeRaw.elapsed_ms && typeof observeRaw.elapsed_ms === 'object' ? (observeRaw.elapsed_ms as UnknownRecord) : {}
  const itemsRaw = observeRaw.items && typeof observeRaw.items === 'object' ? (observeRaw.items as UnknownRecord) : {}
  const workersRaw = observeRaw.workers && typeof observeRaw.workers === 'object' ? (observeRaw.workers as UnknownRecord) : {}
  const errorsRaw = observeRaw.errors && typeof observeRaw.errors === 'object' ? (observeRaw.errors as UnknownRecord) : {}
  const recentRaw = Array.isArray(observeRaw.recent) ? observeRaw.recent : []
  const degraded = Boolean(payload.degraded)
  const errorList = normalizeErrorList(payload.errors)

  const alertsRaw = payload.alerts && typeof payload.alerts === 'object' ? (payload.alerts as UnknownRecord) : {}
  const alertRulesRaw = Array.isArray(alertsRaw.rules) ? alertsRaw.rules : []
  const alertTriggeredRaw = Array.isArray(alertsRaw.triggered_rules) ? alertsRaw.triggered_rules : []
  const alertThresholdsRaw =
    alertsRaw.thresholds && typeof alertsRaw.thresholds === 'object' ? (alertsRaw.thresholds as UnknownRecord) : {}
  const alertNotificationRaw =
    alertsRaw.notification && typeof alertsRaw.notification === 'object'
      ? (alertsRaw.notification as UnknownRecord)
      : {}

  const trendRaw = payload.trend && typeof payload.trend === 'object' ? (payload.trend as UnknownRecord) : {}
  const trendPointsRaw = Array.isArray(trendRaw.points) ? trendRaw.points : []

  return {
    cache: {
      size: toSafeInt(cacheRaw.size),
      ttl_s: toSafeFloat(cacheRaw.ttl_s),
      max_entries: toSafeInt(cacheRaw.max_entries),
      hit: toSafeInt(cacheRaw.hit),
      miss: toSafeInt(cacheRaw.miss),
      set: toSafeInt(cacheRaw.set),
      expired: toSafeInt(cacheRaw.expired),
      evicted: toSafeInt(cacheRaw.evicted)
    },
    observe: {
      window_s: toSafeFloat(observeRaw.window_s),
      max_runs: toSafeInt(observeRaw.max_runs),
      runs: toSafeInt(observeRaw.runs),
      elapsed_ms: {
        avg: toSafeFloat(elapsedRaw.avg),
        p50: toSafeFloat(elapsedRaw.p50),
        p95: toSafeFloat(elapsedRaw.p95),
        max: toSafeFloat(elapsedRaw.max)
      },
      items: {
        total: toSafeInt(itemsRaw.total),
        avg: toSafeFloat(itemsRaw.avg),
        p50: toSafeFloat(itemsRaw.p50),
        p95: toSafeFloat(itemsRaw.p95),
        max: toSafeFloat(itemsRaw.max)
      },
      workers: {
        avg: toSafeFloat(workersRaw.avg),
        max: toSafeFloat(workersRaw.max)
      },
      errors: {
        total: toSafeInt(errorsRaw.total),
        rate_per_run: toSafeRate(errorsRaw.rate_per_run)
      },
      cache_delta: normalizeObserveCacheDelta(observeRaw.cache_delta),
      recent: recentRaw
        .filter((row) => row && typeof row === 'object')
        .map((row) => {
          const entry = row as UnknownRecord
          return {
            ts: toSafeFloat(entry.ts),
            elapsed_ms: toSafeFloat(entry.elapsed_ms),
            item_count: toSafeInt(entry.item_count),
            worker_count: toSafeInt(entry.worker_count),
            error_count: toSafeInt(entry.error_count),
            cache_delta: normalizeObserveCacheDelta(entry.cache_delta)
          }
        })
    },
    degraded,
    errors: errorList,
    alerts: {
      enabled: Boolean(alertsRaw.enabled),
      severity: normalizeAlertSeverity(alertsRaw.severity),
      triggered: toSafeInt(alertsRaw.triggered),
      runs: toSafeInt(alertsRaw.runs),
      min_runs: toSafeInt(alertsRaw.min_runs),
      warmup: Boolean(alertsRaw.warmup),
      thresholds: {
        p95_ms: Math.max(100, Math.min(60000, toSafeFloat(alertThresholdsRaw.p95_ms) || 4500)),
        error_rate_per_run: Math.max(0, Math.min(1, toSafeRate(alertThresholdsRaw.error_rate_per_run))),
        cache_delta_hit_rate: Math.max(0, Math.min(1, toSafeRate(alertThresholdsRaw.cache_delta_hit_rate)))
      },
      rules: alertRulesRaw
        .filter((row) => row && typeof row === 'object')
        .map((row) => {
          const x = row as UnknownRecord
          return {
            id: String(x.id || '').trim(),
            level: normalizeAlertLevel(x.level),
            triggered: Boolean(x.triggered),
            value: toSafeFloat(x.value),
            threshold: toSafeFloat(x.threshold),
            op: String(x.op || '').trim(),
            message: String(x.message || '').trim()
          }
        })
        .filter((row) => row.id.length > 0),
      triggered_rules: alertTriggeredRaw.map((row) => String(row || '').trim()).filter((row) => row.length > 0),
      notification: {
        enabled: Boolean(alertNotificationRaw.enabled),
        webhook_configured: Boolean(alertNotificationRaw.webhook_configured),
        sent: Boolean(alertNotificationRaw.sent),
        channels: Array.isArray(alertNotificationRaw.channels)
          ? alertNotificationRaw.channels.map((row) => String(row || '').trim()).filter((row) => row.length > 0)
          : [],
        signature: String(alertNotificationRaw.signature || '').trim(),
        dedupe_hit: Boolean(alertNotificationRaw.dedupe_hit),
        event_type: String(alertNotificationRaw.event_type || '').trim() || 'none',
        status: String(alertNotificationRaw.status || '').trim() || 'unknown',
        cooldown_s: toSafeFloat(alertNotificationRaw.cooldown_s),
        last_sent_at: toSafeFloat(alertNotificationRaw.last_sent_at),
        suppressed: toSafeInt(alertNotificationRaw.suppressed),
        last_error: String(alertNotificationRaw.last_error || '').trim(),
        event_id: String(alertNotificationRaw.event_id || '').trim(),
        events_total: toSafeInt(alertNotificationRaw.events_total),
        events_recent: Array.isArray(alertNotificationRaw.events_recent)
          ? alertNotificationRaw.events_recent
              .filter((row) => row && typeof row === 'object')
              .map((row) => {
                const item = row as UnknownRecord
                return {
                  id: String(item.id || '').trim(),
                  ts: toSafeFloat(item.ts),
                  severity: normalizeAlertSeverity(item.severity),
                  event_type: String(item.event_type || '').trim() || 'none',
                  status: String(item.status || '').trim() || 'unknown',
                  sent: Boolean(item.sent),
                  dedupe_hit: Boolean(item.dedupe_hit),
                  triggered_rules: Array.isArray(item.triggered_rules)
                    ? item.triggered_rules.map((x) => String(x || '').trim()).filter((x) => x.length > 0)
                    : [],
                  channels: Array.isArray(item.channels)
                    ? item.channels.map((x) => String(x || '').trim()).filter((x) => x.length > 0)
                    : []
                }
              })
              .filter((row) => row.id.length > 0)
          : []
      }
    },
    trend: {
      enabled: Boolean(trendRaw.enabled),
      total: toSafeInt(trendRaw.total),
      limit: toSafeInt(trendRaw.limit),
      points: trendPointsRaw
        .filter((row) => row && typeof row === 'object')
        .map((row) => normalizeTrendPoint(row))
        .filter((row) => row.id.length > 0)
    }
  }
}
