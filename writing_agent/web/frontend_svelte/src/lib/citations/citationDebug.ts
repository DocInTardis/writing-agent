import type {
  VerifyDebugCache,
  VerifyDebugItem,
  VerifyDebugObserve,
  VerifyDebugPayload
} from './citationTypes'
import { normalizeVerifyDebugLevel, toSafeFloat, toSafeInt } from './citationUtils'

export function parseVerifyDebugPayload(raw: unknown): VerifyDebugPayload | null {
  if (!raw || typeof raw !== 'object') return null
  const dbg = raw as Record<string, unknown>
  const rawRequest = dbg.request
  const requestInfo = rawRequest && typeof rawRequest === 'object' ? (rawRequest as Record<string, unknown>) : {}
  const requestedLevel = normalizeVerifyDebugLevel(dbg.requested_level)
  const effectiveLevel = normalizeVerifyDebugLevel(dbg.level)
  const rawCache = dbg.cache
  const cache = rawCache && typeof rawCache === 'object' ? (rawCache as Record<string, unknown>) : {}
  const cacheInfo: VerifyDebugCache = {
    size: toSafeInt(cache.size),
    ttl_s: Number(cache.ttl_s || 0),
    max_entries: toSafeInt(cache.max_entries),
    hit: toSafeInt(cache.hit),
    miss: toSafeInt(cache.miss),
    set: toSafeInt(cache.set),
    expired: toSafeInt(cache.expired),
    evicted: toSafeInt(cache.evicted)
  }
  const rawSampling = dbg.sampling
  const sampling = rawSampling && typeof rawSampling === 'object' ? (rawSampling as Record<string, unknown>) : {}
  const rawItems = Array.isArray(dbg.items) ? dbg.items : []
  const observeInfo = parseObservePayload(dbg.observe)
  const rows: Record<string, VerifyDebugItem> = {}
  for (const rawItem of rawItems) {
    if (!rawItem || typeof rawItem !== 'object') continue
    const row = rawItem as Record<string, unknown>
    const idVal = String(row.id || '').trim()
    if (!idVal) continue
    const providersRaw = row.providers
    const providersObj =
      providersRaw && typeof providersRaw === 'object' ? (providersRaw as Record<string, unknown>) : {}
    const providerMap: Record<string, number> = {}
    for (const [k, v] of Object.entries(providersObj)) {
      providerMap[String(k)] = Number(v || 0)
    }
    rows[idVal] = {
      id: idVal,
      cache_hit: Boolean(row.cache_hit),
      query: String(row.query || '').trim(),
      providers: providerMap,
      errors: Array.isArray(row.errors) ? row.errors.map((x) => String(x || '').trim()).filter(Boolean) : [],
      picked_provider: String(row.picked_provider || '').trim(),
      picked_title_score: Number(row.picked_title_score || 0),
      picked_year_score: Number(row.picked_year_score || 0),
      picked_total_score: Number(row.picked_total_score || 0),
      elapsed_ms: Number(row.elapsed_ms || 0)
    }
  }
  return {
    request: {
      persist: Boolean(requestInfo.persist),
      debug: Boolean(requestInfo.debug),
      input_count: toSafeInt(requestInfo.input_count),
      workers: toSafeInt(requestInfo.workers)
    },
    requested_level: requestedLevel,
    level: effectiveLevel,
    sanitized: typeof dbg.sanitized === 'boolean' ? dbg.sanitized : effectiveLevel !== 'full',
    rate_limited_full: Boolean(dbg.rate_limited_full),
    cache: cacheInfo,
    observe: observeInfo,
    sampling: {
      input_items: Number(sampling.input_items || rawItems.length),
      output_items: Number(sampling.output_items || rawItems.length),
      limit: Number(sampling.limit || 0),
      truncated: Boolean(sampling.truncated)
    },
    elapsed_ms: Number(dbg.elapsed_ms || 0),
    items: rows
  }
}

function parseObservePayload(raw: unknown): VerifyDebugObserve | null {
  const observeObj = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : null
  if (!observeObj) return null
  const observeReqRaw = observeObj.request
  const observeReq =
    observeReqRaw && typeof observeReqRaw === 'object' ? (observeReqRaw as Record<string, unknown>) : {}
  const observeWinRaw = observeObj.window
  const observeWin =
    observeWinRaw && typeof observeWinRaw === 'object' ? (observeWinRaw as Record<string, unknown>) : {}
  const observeElapsedRaw = observeWin.elapsed_ms
  const observeElapsed =
    observeElapsedRaw && typeof observeElapsedRaw === 'object' ? (observeElapsedRaw as Record<string, unknown>) : {}
  const observeItemsRaw = observeWin.items
  const observeItems =
    observeItemsRaw && typeof observeItemsRaw === 'object' ? (observeItemsRaw as Record<string, unknown>) : {}
  const observeWorkersRaw = observeWin.workers
  const observeWorkers =
    observeWorkersRaw && typeof observeWorkersRaw === 'object' ? (observeWorkersRaw as Record<string, unknown>) : {}
  const observeErrorsRaw = observeWin.errors
  const observeErrors =
    observeErrorsRaw && typeof observeErrorsRaw === 'object' ? (observeErrorsRaw as Record<string, unknown>) : {}
  const observeCacheDeltaRaw = observeWin.cache_delta
  const observeCacheDelta =
    observeCacheDeltaRaw && typeof observeCacheDeltaRaw === 'object'
      ? (observeCacheDeltaRaw as Record<string, unknown>)
      : {}
  const observeReqCacheDeltaRaw = observeReq.cache_delta
  const observeReqCacheDelta =
    observeReqCacheDeltaRaw && typeof observeReqCacheDeltaRaw === 'object'
      ? (observeReqCacheDeltaRaw as Record<string, unknown>)
      : {}
  return {
    request: {
      elapsed_ms: toSafeFloat(observeReq.elapsed_ms),
      item_count: toSafeInt(observeReq.item_count),
      worker_count: toSafeInt(observeReq.worker_count),
      error_count: toSafeInt(observeReq.error_count),
      cache_delta: {
        hit: toSafeInt(observeReqCacheDelta.hit),
        miss: toSafeInt(observeReqCacheDelta.miss),
        set: toSafeInt(observeReqCacheDelta.set),
        expired: toSafeInt(observeReqCacheDelta.expired),
        evicted: toSafeInt(observeReqCacheDelta.evicted),
        hit_rate: toSafeFloat(observeReqCacheDelta.hit_rate)
      }
    },
    window: {
      window_s: toSafeFloat(observeWin.window_s),
      max_runs: toSafeInt(observeWin.max_runs),
      runs: toSafeInt(observeWin.runs),
      elapsed_ms: {
        avg: toSafeFloat(observeElapsed.avg),
        p50: toSafeFloat(observeElapsed.p50),
        p95: toSafeFloat(observeElapsed.p95),
        max: toSafeFloat(observeElapsed.max)
      },
      items: {
        total: toSafeInt(observeItems.total),
        avg: toSafeFloat(observeItems.avg),
        p50: toSafeFloat(observeItems.p50),
        p95: toSafeFloat(observeItems.p95),
        max: toSafeFloat(observeItems.max)
      },
      workers: {
        avg: toSafeFloat(observeWorkers.avg),
        max: toSafeFloat(observeWorkers.max)
      },
      errors: {
        total: toSafeInt(observeErrors.total),
        rate_per_run: toSafeFloat(observeErrors.rate_per_run)
      },
      cache_delta: {
        hit: toSafeInt(observeCacheDelta.hit),
        miss: toSafeInt(observeCacheDelta.miss),
        set: toSafeInt(observeCacheDelta.set),
        expired: toSafeInt(observeCacheDelta.expired),
        evicted: toSafeInt(observeCacheDelta.evicted),
        hit_rate: toSafeFloat(observeCacheDelta.hit_rate)
      }
    }
  }
}
