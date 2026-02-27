<script lang="ts">
  import { onMount } from 'svelte'
  import { docId, pushToast } from '../stores'

  export let visible = false

  interface Citation {
    id: string
    author: string
    title: string
    year: string
    source: string
  }

  interface VerifyItem {
    id: string
    status: 'verified' | 'possible' | 'not_found' | 'error'
    provider?: string
    score?: number
    matched_title?: string
    matched_year?: string
    matched_source?: string
    reason?: string
  }

  interface VerifySummary {
    total: number
    verified: number
    possible: number
    not_found: number
    error: number
  }

  type VerifyDebugLevel = 'safe' | 'strict' | 'full'

  interface VerifyDebugItem {
    id: string
    cache_hit: boolean
    query: string
    providers: Record<string, number>
    errors: string[]
    picked_provider: string
    picked_title_score: number
    picked_year_score: number
    picked_total_score: number
    elapsed_ms: number
  }

  interface VerifyDebugSampling {
    input_items: number
    output_items: number
    limit: number
    truncated: boolean
  }

  interface VerifyDebugRequest {
    persist: boolean
    debug: boolean
    input_count: number
    workers: number
  }

  interface VerifyDebugCache {
    size: number
    ttl_s: number
    max_entries: number
    hit: number
    miss: number
    set: number
    expired: number
    evicted: number
  }

  interface VerifyObserveCacheDelta {
    hit: number
    miss: number
    set: number
    expired: number
    evicted: number
    hit_rate: number
  }

  interface VerifyObserveRequest {
    elapsed_ms: number
    item_count: number
    worker_count: number
    error_count: number
    cache_delta: VerifyObserveCacheDelta
  }

  interface VerifyObserveWindow {
    window_s: number
    max_runs: number
    runs: number
    elapsed_ms: { avg: number; p50: number; p95: number; max: number }
    items: { total: number; avg: number; p50: number; p95: number; max: number }
    workers: { avg: number; max: number }
    errors: { total: number; rate_per_run: number }
    cache_delta: VerifyObserveCacheDelta
  }

  interface VerifyDebugObserve {
    request: VerifyObserveRequest
    window: VerifyObserveWindow
  }

  interface VerifyDebugPayload {
    request: VerifyDebugRequest
    requested_level: VerifyDebugLevel
    level: VerifyDebugLevel
    sanitized: boolean
    rate_limited_full: boolean
    cache: VerifyDebugCache
    observe: VerifyDebugObserve | null
    sampling: VerifyDebugSampling
    elapsed_ms: number
    items: Record<string, VerifyDebugItem>
  }

  interface VerifyDebugHistoryEntry {
    id: string
    at_label: string
    level: VerifyDebugLevel
    workers: number
    elapsed_ms: number
    cache_size: number
    cache_max: number
    hit_rate: number
    evict_rate: number
    sampled_output: number
    sampled_input: number
  }

  const VERIFY_DEBUG_ENABLED = Boolean(import.meta.env.DEV)
  const VERIFY_DEBUG_HISTORY_LIMIT = 8
  const CACHE_HIT_RATE_WARN_THRESHOLD = 0.55
  const CACHE_EVICT_RATE_WARN_THRESHOLD = 0.08

  let citations: Citation[] = []
  let loading = false
  let verifying = false
  let verifyMap: Record<string, VerifyItem> = {}
  let verifySummary: VerifySummary | null = null
  let verifyDebug: VerifyDebugPayload | null = null
  let verifyDebugHistory: VerifyDebugHistoryEntry[] = []
  let verifyDebugHistorySeq = 0
  let verifyDebugLevel: VerifyDebugLevel = 'safe'
  let lastLoadedId = ''
  let saveTimer: ReturnType<typeof setTimeout> | null = null

  let newCitation: Citation = {
    id: '',
    author: '',
    title: '',
    year: '',
    source: ''
  }

  function normalizeItems(items: unknown): Citation[] {
    if (!Array.isArray(items)) return []
    return items
      .filter((raw) => raw && typeof raw === 'object')
      .map((raw) => {
        const row = raw as Record<string, unknown>
        return {
          id: String(row.id || '').trim(),
          author: String(row.author || '').trim(),
          title: String(row.title || '').trim(),
          year: String(row.year || '').trim(),
          source: String(row.source || '').trim()
        }
      })
      .filter((c) => c.id && c.title)
  }

  function normalizeVerifyDebugLevel(value: unknown): VerifyDebugLevel {
    const raw = String(value || '').trim().toLowerCase()
    if (raw === 'full') return 'full'
    if (raw === 'strict') return 'strict'
    return 'safe'
  }

  function toSafeInt(value: unknown): number {
    const n = Number(value)
    if (!Number.isFinite(n)) return 0
    return Math.max(0, Math.round(n))
  }

  function toSafeFloat(value: unknown): number {
    const n = Number(value)
    if (!Number.isFinite(n)) return 0
    return Math.max(0, n)
  }

  function cacheLookupCount(cache: VerifyDebugCache): number {
    return toSafeInt(cache.hit) + toSafeInt(cache.miss)
  }

  function cacheHitRate(cache: VerifyDebugCache): number {
    const total = cacheLookupCount(cache)
    if (total <= 0) return 0
    return toSafeInt(cache.hit) / total
  }

  function cacheEvictRate(cache: VerifyDebugCache): number {
    const sets = toSafeInt(cache.set)
    if (sets <= 0) return 0
    return toSafeInt(cache.evicted) / sets
  }

  function formatRate(value: number): string {
    const clamped = Math.max(0, Math.min(1, Number(value) || 0))
    return `${(clamped * 100).toFixed(1)}%`
  }

  function debugTimeLabel(): string {
    return new Date().toLocaleTimeString('zh-CN', { hour12: false })
  }

  function appendVerifyDebugHistory(payload: VerifyDebugPayload): void {
    const entry: VerifyDebugHistoryEntry = {
      id: `${Date.now()}-${verifyDebugHistorySeq++}`,
      at_label: debugTimeLabel(),
      level: payload.level,
      workers: toSafeInt(payload.request.workers),
      elapsed_ms: Number(payload.elapsed_ms || 0),
      cache_size: toSafeInt(payload.cache.size),
      cache_max: toSafeInt(payload.cache.max_entries),
      hit_rate: cacheHitRate(payload.cache),
      evict_rate: cacheEvictRate(payload.cache),
      sampled_output: toSafeInt(payload.sampling.output_items),
      sampled_input: toSafeInt(payload.sampling.input_items)
    }
    verifyDebugHistory = [...verifyDebugHistory, entry].slice(-VERIFY_DEBUG_HISTORY_LIMIT)
  }

  function averageNumber(values: number[]): number {
    if (!values.length) return 0
    return values.reduce((sum, n) => sum + (Number.isFinite(n) ? n : 0), 0) / values.length
  }

  function historyRecent(limit = 5): VerifyDebugHistoryEntry[] {
    const size = Math.max(1, toSafeInt(limit))
    return verifyDebugHistory.slice(-size)
  }

  function historyAverageHitRate(limit = 5): number {
    return averageNumber(historyRecent(limit).map((x) => Number(x.hit_rate || 0)))
  }

  function historyAverageEvictRate(limit = 5): number {
    return averageNumber(historyRecent(limit).map((x) => Number(x.evict_rate || 0)))
  }

  function historyAverageElapsedMs(limit = 5): number {
    return averageNumber(historyRecent(limit).map((x) => Number(x.elapsed_ms || 0)))
  }

  function clearVerifyDebugHistory(): void {
    if (!verifyDebugHistory.length) return
    verifyDebugHistory = []
    pushToast('已清空调试历史', 'ok')
  }

  async function loadCitations() {
    const id = $docId
    if (!id) return
    loading = true
    try {
      const resp = await fetch(`/api/doc/${id}/citations`)
      if (!resp.ok) throw new Error(await resp.text())
      const data = await resp.json()
      citations = normalizeItems(data?.items)
      verifyMap = {}
      verifySummary = null
      verifyDebug = null
      verifyDebugHistory = []
    } catch (err) {
      console.error('Failed to load citations', err)
      pushToast('加载引用失败', 'bad')
    } finally {
      loading = false
    }
  }

  async function saveCitations() {
    const id = $docId
    if (!id) return
    const resp = await fetch(`/api/doc/${id}/citations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items: citations })
    })
    if (!resp.ok) {
      throw new Error(await resp.text())
    }
  }

  function queueSave() {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveCitations().catch((err) => {
        console.error('Failed to save citations', err)
        pushToast('保存引用失败', 'bad')
      })
    }, 300)
  }

  function addCitation() {
    if (!newCitation.id || !newCitation.author || !newCitation.title) {
      pushToast('请填写必填项：ID、作者、标题', 'bad')
      return
    }
    if (citations.some((c) => c.id === newCitation.id)) {
      pushToast('引用 ID 已存在', 'bad')
      return
    }
    citations = [...citations, { ...newCitation }]
    queueSave()
    newCitation = { id: '', author: '', title: '', year: '', source: '' }
    pushToast('已添加引用', 'ok')
  }

  function deleteCitation(id: string) {
    citations = citations.filter((c) => c.id !== id)
    const next = { ...verifyMap }
    delete next[id]
    verifyMap = next
    if (verifyDebug && verifyDebug.items[id]) {
      const nextDebugItems = { ...verifyDebug.items }
      delete nextDebugItems[id]
      verifyDebug = { ...verifyDebug, items: nextDebugItems }
    }
    queueSave()
    pushToast('已删除引用', 'ok')
  }

  async function copyCiteKey(id: string) {
    try {
      await navigator.clipboard.writeText(`[@${id}]`)
      pushToast('已复制引用标记', 'ok')
    } catch {
      pushToast('复制失败，请手动复制', 'bad')
    }
  }

  function formatCitation(cite: Citation, style: 'apa' | 'mla' | 'gb'): string {
    if (style === 'apa') {
      return `${cite.author} (${cite.year}). ${cite.title}. ${cite.source}.`
    }
    if (style === 'mla') {
      return `${cite.author}. "${cite.title}." ${cite.source}, ${cite.year}.`
    }
    return `${cite.author}. ${cite.title}[J]. ${cite.source}, ${cite.year}.`
  }

  function exportBibliography(style: 'apa' | 'mla' | 'gb') {
    const lines = citations.map((c) => formatCitation(c, style))
    const blob = new Blob([lines.join('\n\n')], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `references_${style}.txt`
    a.click()
    URL.revokeObjectURL(url)
    pushToast(`已导出 ${style.toUpperCase()} 参考文献`, 'ok')
  }

  function buildVerifyDebugSnapshot(): Record<string, unknown> | null {
    if (!verifyDebug) return null
    const rows = citations.map((cite) => ({
      id: cite.id,
      verify: verifyMap[cite.id] || null,
      debug: verifyDebug?.items?.[cite.id] || null
    }))
    const historyNewestFirst = verifyDebugHistory.slice().reverse()
    return {
      generated_at: new Date().toISOString(),
      doc_id: $docId,
      debug_level_selected: verifyDebugLevel,
      summary: verifySummary || null,
      debug: verifyDebug,
      debug_history_limit: VERIFY_DEBUG_HISTORY_LIMIT,
      debug_history: historyNewestFirst,
      debug_history_stats: {
        sample_size: historyRecent(5).length,
        avg_hit_rate: historyAverageHitRate(5),
        avg_evict_rate: historyAverageEvictRate(5),
        avg_elapsed_ms: historyAverageElapsedMs(5)
      },
      rows
    }
  }

  async function copyVerifyDebugJson() {
    if (!VERIFY_DEBUG_ENABLED || !verifyDebug) return
    const payload = buildVerifyDebugSnapshot()
    if (!payload) return
    try {
      await navigator.clipboard.writeText(JSON.stringify(payload, null, 2))
      pushToast('已复制核验诊断 JSON', 'ok')
    } catch {
      pushToast('复制诊断 JSON 失败', 'bad')
    }
  }

  function statusClass(status: string): string {
    if (status === 'verified') return 'ok'
    if (status === 'possible') return 'warn'
    if (status === 'error') return 'err'
    return 'miss'
  }

  function statusLabel(status: string): string {
    if (status === 'verified') return '已核验'
    if (status === 'possible') return '疑似匹配'
    if (status === 'error') return '核验失败'
    return '未命中'
  }

  async function verifyCitations() {
    const id = $docId
    if (!id) return
    if (!citations.length) {
      pushToast('暂无可核验的引用', 'info')
      return
    }
    verifying = true
    try {
      const verifyRequestBody: Record<string, unknown> = { items: citations, persist: true, debug: VERIFY_DEBUG_ENABLED }
      if (VERIFY_DEBUG_ENABLED) {
        verifyRequestBody.debug_level = verifyDebugLevel
      }
      const resp = await fetch(`/api/doc/${id}/citations/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(verifyRequestBody)
      })
      if (!resp.ok) throw new Error(await resp.text())
      const data = await resp.json()
      const items = Array.isArray(data?.items) ? data.items : []
      const map: Record<string, VerifyItem> = {}
      for (const raw of items) {
        if (!raw || typeof raw !== 'object') continue
        const row = raw as Record<string, unknown>
        const idVal = String(row.id || '').trim()
        if (!idVal) continue
        map[idVal] = {
          id: idVal,
          status: (String(row.status || 'not_found') as VerifyItem['status']) || 'not_found',
          provider: String(row.provider || '').trim(),
          score: Number(row.score || 0),
          matched_title: String(row.matched_title || '').trim(),
          matched_year: String(row.matched_year || '').trim(),
          matched_source: String(row.matched_source || '').trim(),
          reason: String(row.reason || '').trim()
        }
      }
      verifyMap = map
      const summary = data?.summary || {}
      verifySummary = {
        total: Number(summary.total || 0),
        verified: Number(summary.verified || 0),
        possible: Number(summary.possible || 0),
        not_found: Number(summary.not_found || 0),
        error: Number(summary.error || 0)
      }
      if (VERIFY_DEBUG_ENABLED && data && typeof data === 'object' && data.debug && typeof data.debug === 'object') {
        const dbg = data.debug as Record<string, unknown>
        const rawRequest = dbg.request
        const requestInfo =
          rawRequest && typeof rawRequest === 'object' ? (rawRequest as Record<string, unknown>) : {}
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
        const sampling =
          rawSampling && typeof rawSampling === 'object' ? (rawSampling as Record<string, unknown>) : {}
        const rawSanitized = dbg.sanitized
        const rawObserve = dbg.observe
        const observeObj =
          rawObserve && typeof rawObserve === 'object' ? (rawObserve as Record<string, unknown>) : null
        let observeInfo: VerifyDebugObserve | null = null
        if (observeObj) {
          const observeReqRaw = observeObj.request
          const observeReq =
            observeReqRaw && typeof observeReqRaw === 'object'
              ? (observeReqRaw as Record<string, unknown>)
              : {}
          const observeWinRaw = observeObj.window
          const observeWin =
            observeWinRaw && typeof observeWinRaw === 'object'
              ? (observeWinRaw as Record<string, unknown>)
              : {}
          const observeElapsedRaw = observeWin.elapsed_ms
          const observeElapsed =
            observeElapsedRaw && typeof observeElapsedRaw === 'object'
              ? (observeElapsedRaw as Record<string, unknown>)
              : {}
          const observeItemsRaw = observeWin.items
          const observeItems =
            observeItemsRaw && typeof observeItemsRaw === 'object'
              ? (observeItemsRaw as Record<string, unknown>)
              : {}
          const observeWorkersRaw = observeWin.workers
          const observeWorkers =
            observeWorkersRaw && typeof observeWorkersRaw === 'object'
              ? (observeWorkersRaw as Record<string, unknown>)
              : {}
          const observeErrorsRaw = observeWin.errors
          const observeErrors =
            observeErrorsRaw && typeof observeErrorsRaw === 'object'
              ? (observeErrorsRaw as Record<string, unknown>)
              : {}
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
          observeInfo = {
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
        const rows: Record<string, VerifyDebugItem> = {}
        const rawItems = Array.isArray(dbg.items) ? dbg.items : []
        for (const raw of rawItems) {
          if (!raw || typeof raw !== 'object') continue
          const row = raw as Record<string, unknown>
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
        const nextDebug: VerifyDebugPayload = {
          request: {
            persist: Boolean(requestInfo.persist),
            debug: Boolean(requestInfo.debug),
            input_count: toSafeInt(requestInfo.input_count),
            workers: toSafeInt(requestInfo.workers)
          },
          requested_level: requestedLevel,
          level: effectiveLevel,
          sanitized: typeof rawSanitized === 'boolean' ? rawSanitized : effectiveLevel !== 'full',
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
        verifyDebug = nextDebug
        appendVerifyDebugHistory(nextDebug)
        if (requestedLevel === 'full' && effectiveLevel !== 'full') {
          pushToast('debug full 已被限流降级为 safe', 'info')
        }
      } else {
        verifyDebug = null
      }
      const updatedItems = normalizeItems(data?.updated_items)
      if (updatedItems.length) {
        citations = updatedItems
      }
      pushToast('引用核验完成', 'ok')
    } catch (err) {
      console.error('Failed to verify citations', err)
      pushToast('引用核验失败', 'bad')
    } finally {
      verifying = false
    }
  }

  onMount(() => {
    if (visible) loadCitations()
  })

  $: if (visible) {
    const id = $docId
    if (id && id !== lastLoadedId) {
      lastLoadedId = id
      loadCitations()
    }
  }
</script>

{#if visible}
  <div
    class="modal-backdrop"
    role="button"
    tabindex="0"
    aria-label="关闭引用管理"
    on:click={() => (visible = false)}
    on:keydown={(e) => {
      if (e.key === 'Enter' || e.key === ' ' || e.key === 'Escape') {
        e.preventDefault()
        visible = false
      }
    }}
  >
    <div class="modal" role="dialog" aria-modal="true" tabindex="-1" on:click|stopPropagation on:keydown|stopPropagation>
      <div class="modal-header">
        <h2>引用管理</h2>
        <button class="close-btn" on:click={() => (visible = false)}>×</button>
      </div>

      <div class="modal-body">
        <div class="add-section">
          <h3>添加引用</h3>
          <div class="form-grid">
            <input type="text" placeholder="引用 ID（如 smith2023）" bind:value={newCitation.id} />
            <input type="text" placeholder="作者*" bind:value={newCitation.author} />
            <input type="text" placeholder="标题*" bind:value={newCitation.title} />
            <input type="text" placeholder="年份" bind:value={newCitation.year} />
            <input type="text" placeholder="来源（期刊/会议/URL）" bind:value={newCitation.source} class="full-width" />
          </div>
          <button class="btn-add" on:click={addCitation}>添加引用</button>
        </div>

        <div class="verify-section">
          <h3>核验真实性</h3>
          <div class="verify-row">
            <button class="btn-verify" disabled={verifying || loading || citations.length === 0} on:click={verifyCitations}>
              {#if verifying}核验中...{:else}核验引用{/if}
            </button>
            {#if VERIFY_DEBUG_ENABLED}
              <div class="verify-debug-controls">
                <label for="verify-debug-level">debug level</label>
                <select id="verify-debug-level" bind:value={verifyDebugLevel} disabled={verifying}>
                  <option value="safe">safe (masked)</option>
                  <option value="strict">strict (metrics only)</option>
                  <option value="full">full (raw, rate limited)</option>
                </select>
              </div>
            {/if}
            {#if verifySummary}
              <div class="verify-summary">
                总计 {verifySummary.total} · 已核验 {verifySummary.verified} · 疑似 {verifySummary.possible} · 未命中 {verifySummary.not_found} · 异常 {verifySummary.error}
              </div>
            {/if}
            {#if VERIFY_DEBUG_ENABLED && verifyDebug}
              <div class="verify-debug-summary">
                <span>
                  Debug · req {verifyDebug.requested_level} · active {verifyDebug.level} · workers {verifyDebug.request.workers} · sampled {verifyDebug.sampling.output_items}/{verifyDebug.sampling.input_items} · elapsed {verifyDebug.elapsed_ms.toFixed(1)}ms
                </span>
                <span class="verify-debug-metrics">
                  cache {verifyDebug.cache.size}/{verifyDebug.cache.max_entries || '-'} · ttl {verifyDebug.cache.ttl_s.toFixed(0)}s · hit {verifyDebug.cache.hit}/{cacheLookupCount(verifyDebug.cache)} ({formatRate(cacheHitRate(verifyDebug.cache))}) · evict {verifyDebug.cache.evicted}/{verifyDebug.cache.set} ({formatRate(cacheEvictRate(verifyDebug.cache))}) · expired {verifyDebug.cache.expired}
                </span>
                {#if verifyDebug.observe}
                  <span class="verify-debug-observe">
                    window {verifyDebug.observe.window.runs}/{verifyDebug.observe.window.max_runs || '-'} · p50/p95 {verifyDebug.observe.window.elapsed_ms.p50.toFixed(1)}/{verifyDebug.observe.window.elapsed_ms.p95.toFixed(1)}ms · avg items {verifyDebug.observe.window.items.avg.toFixed(1)} · avg workers {verifyDebug.observe.window.workers.avg.toFixed(1)} · hitΔ {formatRate(verifyDebug.observe.window.cache_delta.hit_rate)}
                  </span>
                {/if}
                <span class="verify-debug-health">
                  <span class={"verify-debug-chip " + (cacheHitRate(verifyDebug.cache) < CACHE_HIT_RATE_WARN_THRESHOLD ? 'warn' : 'ok')}>
                    hit {formatRate(cacheHitRate(verifyDebug.cache))}
                  </span>
                  <span class={"verify-debug-chip " + (cacheEvictRate(verifyDebug.cache) > CACHE_EVICT_RATE_WARN_THRESHOLD ? 'warn' : 'ok')}>
                    evict {formatRate(cacheEvictRate(verifyDebug.cache))}
                  </span>
                </span>
                {#if verifyDebug.rate_limited_full}
                  <span class="verify-debug-flag">full -> safe (rate limited)</span>
                {/if}
                {#if verifyDebugHistory.length > 0}
                  <span class="verify-debug-trend">
                    avg(5) hit {formatRate(historyAverageHitRate(5))} · evict {formatRate(historyAverageEvictRate(5))} · elapsed {historyAverageElapsedMs(5).toFixed(1)}ms
                  </span>
                {/if}
                <button
                  class="btn-debug-clear"
                  on:click={clearVerifyDebugHistory}
                  disabled={verifyDebugHistory.length === 0}
                >
                  清空历史
                </button>
                <button class="btn-debug-copy" on:click={copyVerifyDebugJson}>复制诊断 JSON</button>
              </div>
              {#if verifyDebugHistory.length > 0}
                <div class="verify-debug-history">
                  <div class="verify-debug-history-title">recent verify runs ({verifyDebugHistory.length}/{VERIFY_DEBUG_HISTORY_LIMIT})</div>
                  <div class="verify-debug-history-list">
                    {#each verifyDebugHistory.slice().reverse() as run (run.id)}
                      <div class="verify-debug-history-item">
                        <span class="history-time">{run.at_label}</span>
                        <span class={"history-chip " + (run.hit_rate < CACHE_HIT_RATE_WARN_THRESHOLD ? 'warn' : 'ok')}>hit {formatRate(run.hit_rate)}</span>
                        <span class={"history-chip " + (run.evict_rate > CACHE_EVICT_RATE_WARN_THRESHOLD ? 'warn' : 'ok')}>evict {formatRate(run.evict_rate)}</span>
                        <span class="history-meta">w{run.workers}</span>
                        <span class="history-meta">cache {run.cache_size}/{run.cache_max || '-'}</span>
                        <span class="history-meta">sample {run.sampled_output}/{run.sampled_input}</span>
                        <span class="history-meta">{run.elapsed_ms.toFixed(1)}ms</span>
                      </div>
                    {/each}
                  </div>
                </div>
              {/if}
            {/if}
          </div>
        </div>

        <div class="export-section">
          <h3>导出参考文献</h3>
          <div class="export-btns">
            <button class="btn-export" on:click={() => exportBibliography('apa')}>APA</button>
            <button class="btn-export" on:click={() => exportBibliography('mla')}>MLA</button>
            <button class="btn-export" on:click={() => exportBibliography('gb')}>GB/T 7714</button>
          </div>
        </div>

        <div class="list-section">
          <h3>已有引用 ({citations.length})</h3>
          {#if loading}
            <p class="empty">加载中...</p>
          {:else if citations.length === 0}
            <p class="empty">暂无引用</p>
          {:else}
            <div class="citation-list">
              {#each citations as cite}
                {@const verify = verifyMap[cite.id]}
                {@const vdbg = verifyDebug?.items?.[cite.id]}
                <div class="citation-item">
                  <div class="citation-info">
                    <strong>[@{cite.id}]</strong>
                    <span>{cite.author} ({cite.year}). {cite.title}</span>
                    {#if cite.source}
                      <span class="source">{cite.source}</span>
                    {/if}
                    {#if verify}
                      <div class="verify-info">
                        <span class={"status " + statusClass(verify.status)}>{statusLabel(verify.status)}</span>
                        {#if verify.provider}<span class="hint">来源：{verify.provider}</span>{/if}
                        {#if Number(verify.score || 0) > 0}
                          <span class="hint">相似度：{Number(verify.score || 0).toFixed(2)}</span>
                        {/if}
                        {#if verify.matched_title}
                          <span class="hint">匹配标题：{verify.matched_title}</span>
                        {/if}
                        {#if verify.matched_year}
                          <span class="hint">匹配年份：{verify.matched_year}</span>
                        {/if}
                        {#if VERIFY_DEBUG_ENABLED && vdbg}
                          <details class="verify-debug-item">
                            <summary>debug details</summary>
                            <div class="debug-line">cache_hit: {vdbg.cache_hit ? 'true' : 'false'}</div>
                            {#if vdbg.query}<div class="debug-line">query: {vdbg.query}</div>{/if}
                            {#if vdbg.picked_provider}
                              <div class="debug-line">
                                picked: {vdbg.picked_provider} (total {vdbg.picked_total_score.toFixed(3)}, title {vdbg.picked_title_score.toFixed(3)}, year {vdbg.picked_year_score.toFixed(3)})
                              </div>
                            {/if}
                            <div class="debug-line">providers: {JSON.stringify(vdbg.providers)}</div>
                            {#if vdbg.errors.length > 0}
                              <div class="debug-line">errors: {vdbg.errors.join(' | ')}</div>
                            {/if}
                            <div class="debug-line">elapsed: {vdbg.elapsed_ms.toFixed(2)}ms</div>
                          </details>
                        {/if}
                      </div>
                    {/if}
                  </div>
                  <div class="citation-actions">
                    <button class="btn-copy" on:click={() => copyCiteKey(cite.id)}>复制</button>
                    <button class="btn-delete" on:click={() => deleteCitation(cite.id)}>删除</button>
                  </div>
                </div>
              {/each}
            </div>
          {/if}
        </div>
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }

  .modal {
    background: #fffdf8;
    border-radius: 16px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
    max-width: 860px;
    width: 92%;
    max-height: 82vh;
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px 20px;
    border-bottom: 1px solid rgba(90, 70, 45, 0.12);
  }

  .modal-header h2 {
    margin: 0;
    color: #2b2416;
    font-size: 20px;
  }

  .close-btn {
    background: none;
    border: none;
    font-size: 28px;
    color: #6b5d45;
    cursor: pointer;
    line-height: 1;
  }

  .modal-body {
    padding: 20px;
    overflow-y: auto;
  }

  .add-section,
  .verify-section,
  .export-section,
  .list-section {
    margin-bottom: 22px;
  }

  h3 {
    margin: 0 0 10px;
    color: #2b2416;
    font-size: 16px;
  }

  .form-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    margin-bottom: 10px;
  }

  .form-grid input {
    padding: 9px 12px;
    border: 1px solid rgba(90, 70, 45, 0.2);
    border-radius: 8px;
    font-size: 14px;
    background: rgba(255, 255, 255, 0.8);
  }

  .form-grid input.full-width {
    grid-column: 1 / -1;
  }

  .btn-add,
  .btn-verify {
    width: 100%;
    padding: 10px;
    background: linear-gradient(135deg, #a5722a 0%, #8b7355 100%);
    color: #fff;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
  }

  .btn-verify[disabled] {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .verify-row {
    display: grid;
    gap: 8px;
  }

  .verify-debug-controls {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
    color: #4f6886;
  }

  .verify-debug-controls label {
    font-weight: 600;
    letter-spacing: 0.2px;
  }

  .verify-debug-controls select {
    border: 1px solid rgba(24, 119, 242, 0.35);
    background: rgba(255, 255, 255, 0.9);
    color: #1f4b77;
    border-radius: 6px;
    font-size: 12px;
    padding: 4px 8px;
  }

  .verify-summary {
    font-size: 13px;
    color: #5d513d;
    background: rgba(165, 114, 42, 0.08);
    border: 1px solid rgba(165, 114, 42, 0.2);
    border-radius: 8px;
    padding: 8px 10px;
  }

  .verify-debug-summary {
    font-size: 12px;
    color: #1f4b77;
    background: rgba(24, 119, 242, 0.08);
    border: 1px dashed rgba(24, 119, 242, 0.35);
    border-radius: 8px;
    padding: 6px 10px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .verify-debug-metrics {
    color: #355b85;
    font-size: 11px;
    line-height: 1.35;
  }

  .verify-debug-observe {
    color: #2e547d;
    font-size: 11px;
    line-height: 1.35;
  }

  .verify-debug-trend {
    color: #2b4f76;
    font-size: 11px;
    font-weight: 600;
  }

  .verify-debug-health {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }

  .verify-debug-chip {
    border-radius: 999px;
    border: 1px solid transparent;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
  }

  .verify-debug-chip.ok {
    color: #0e7f47;
    background: rgba(14, 127, 71, 0.12);
    border-color: rgba(14, 127, 71, 0.24);
  }

  .verify-debug-chip.warn {
    color: #8a3b12;
    background: rgba(245, 158, 11, 0.16);
    border-color: rgba(245, 158, 11, 0.35);
  }

  .verify-debug-history {
    border: 1px solid rgba(24, 119, 242, 0.22);
    background: rgba(24, 119, 242, 0.04);
    border-radius: 8px;
    padding: 8px 10px;
    display: grid;
    gap: 6px;
  }

  .verify-debug-history-title {
    font-size: 11px;
    font-weight: 600;
    color: #2b4f76;
    letter-spacing: 0.1px;
  }

  .verify-debug-history-list {
    display: grid;
    gap: 4px;
  }

  .verify-debug-history-item {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
    font-size: 11px;
  }

  .history-time {
    color: #355b85;
    font-weight: 600;
    min-width: 72px;
  }

  .history-chip {
    border-radius: 999px;
    border: 1px solid transparent;
    padding: 1px 7px;
    font-size: 11px;
    font-weight: 600;
  }

  .history-chip.ok {
    color: #0e7f47;
    background: rgba(14, 127, 71, 0.11);
    border-color: rgba(14, 127, 71, 0.24);
  }

  .history-chip.warn {
    color: #8a3b12;
    background: rgba(245, 158, 11, 0.14);
    border-color: rgba(245, 158, 11, 0.32);
  }

  .history-meta {
    color: #4e6a89;
  }

  .btn-debug-copy {
    border: 1px solid rgba(24, 119, 242, 0.5);
    background: rgba(255, 255, 255, 0.8);
    color: #1f4b77;
    font-size: 11px;
    border-radius: 6px;
    padding: 4px 8px;
    cursor: pointer;
  }

  .btn-debug-clear {
    border: 1px solid rgba(148, 163, 184, 0.55);
    background: rgba(255, 255, 255, 0.9);
    color: #475467;
    font-size: 11px;
    border-radius: 6px;
    padding: 4px 8px;
    cursor: pointer;
  }

  .btn-debug-clear[disabled] {
    opacity: 0.55;
    cursor: not-allowed;
  }

  .verify-debug-flag {
    font-size: 11px;
    font-weight: 600;
    color: #8a3b12;
    background: rgba(245, 158, 11, 0.16);
    border: 1px solid rgba(245, 158, 11, 0.35);
    border-radius: 999px;
    padding: 2px 8px;
  }

  .export-btns {
    display: flex;
    gap: 10px;
  }

  .btn-export {
    flex: 1;
    padding: 9px;
    background: rgba(165, 114, 42, 0.1);
    color: #8b7355;
    border: 1px solid rgba(165, 114, 42, 0.3);
    border-radius: 8px;
    cursor: pointer;
    font-size: 13px;
  }

  .citation-list {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .citation-item {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
    padding: 12px 14px;
    background: rgba(255, 255, 255, 0.7);
    border: 1px solid rgba(90, 70, 45, 0.12);
    border-radius: 8px;
  }

  .citation-info {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  .citation-info strong {
    color: #a5722a;
    font-size: 14px;
  }

  .citation-info span {
    color: #6b5d45;
    font-size: 13px;
    line-height: 1.4;
  }

  .source {
    font-style: italic;
    color: #8b7355;
  }

  .verify-info {
    display: flex;
    flex-direction: column;
    gap: 2px;
    margin-top: 2px;
  }

  .status {
    display: inline-block;
    width: fit-content;
    padding: 1px 8px;
    border-radius: 999px;
    font-size: 12px;
    font-weight: 600;
  }

  .status.ok {
    color: #0e7f47;
    background: rgba(14, 127, 71, 0.12);
  }

  .status.warn {
    color: #a86517;
    background: rgba(168, 101, 23, 0.14);
  }

  .status.err {
    color: #b42318;
    background: rgba(180, 35, 24, 0.12);
  }

  .status.miss {
    color: #475467;
    background: rgba(71, 84, 103, 0.1);
  }

  .hint {
    color: #667085;
    font-size: 12px;
  }

  .verify-debug-item {
    margin-top: 4px;
    border-left: 2px solid rgba(24, 119, 242, 0.35);
    padding-left: 8px;
  }

  .verify-debug-item summary {
    cursor: pointer;
    color: #1f4b77;
    font-size: 12px;
  }

  .debug-line {
    color: #44556f;
    font-size: 11px;
    line-height: 1.35;
    margin-top: 2px;
    word-break: break-word;
  }

  .citation-actions {
    display: flex;
    gap: 8px;
  }

  .btn-copy,
  .btn-delete {
    padding: 6px 12px;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 12px;
  }

  .btn-copy {
    background: rgba(42, 165, 114, 0.12);
    color: #198754;
  }

  .btn-delete {
    background: rgba(211, 47, 47, 0.12);
    color: #b42318;
  }

  .empty {
    text-align: center;
    color: #8b7355;
    padding: 22px 10px;
    font-size: 14px;
  }
</style>
