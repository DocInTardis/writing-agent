<script lang="ts">
  import { onDestroy } from 'svelte'
  import './PerformanceMetrics.css'
  import {
    POLL_MS,
    cacheHitRate,
    clampAlertConfig,
    formatAlertMetric,
    formatRate,
    formatTime,
    normalizeEventContextPayload,
    normalizeMetricsPayload,
    type AlertConfigForm,
    type MetricsEventContext,
    type MetricsView
  } from './performanceMetricsUtils'

  export let visible = false

  let metrics: MetricsView | null = null
  let loading = false
  let refreshing = false
  let errorMsg = ''
  let updatedAt = ''
  let pollTimer: ReturnType<typeof setInterval> | null = null
  let wasVisible = false

  let savingAlertConfig = false
  let alertConfigDirty = false
  let alertConfigMsg = ''
  let alertConfigMsgKind: 'ok' | 'bad' | '' = ''
  let alertAdminKey = ''

  let eventContextLoading = false
  let eventContextError = ''
  let eventContextTargetId = ''
  let selectedEventContext: MetricsEventContext | null = null

  let alertConfigForm: AlertConfigForm = {
    enabled: true,
    min_runs: 8,
    p95_ms: 4500,
    error_rate_per_run: 0.3,
    cache_delta_hit_rate: 0.35
  }

  if (typeof window !== 'undefined') {
    alertAdminKey = String(window.localStorage.getItem('wa_alert_admin_key') || '')
  }

  function buildAdminHeaders(contentTypeJson = false): Record<string, string> {
    const headers: Record<string, string> = {}
    if (contentTypeJson) headers['Content-Type'] = 'application/json'
    const key = String(alertAdminKey || '').trim()
    if (key) headers['X-Admin-Key'] = key
    return headers
  }

  function saveAdminKeyLocal(): void {
    if (typeof window === 'undefined') return
    const key = String(alertAdminKey || '')
    if (key.trim()) window.localStorage.setItem('wa_alert_admin_key', key)
    else window.localStorage.removeItem('wa_alert_admin_key')
  }

  function applyAlertConfigFromMetrics(next: MetricsView): void {
    if (alertConfigDirty || savingAlertConfig) return
    alertConfigForm = clampAlertConfig({
      enabled: next.alerts.enabled,
      min_runs: next.alerts.min_runs,
      p95_ms: next.alerts.thresholds.p95_ms,
      error_rate_per_run: next.alerts.thresholds.error_rate_per_run,
      cache_delta_hit_rate: next.alerts.thresholds.cache_delta_hit_rate
    })
  }

  async function saveAlertConfig(): Promise<void> {
    if (!metrics) return
    savingAlertConfig = true
    alertConfigMsg = ''
    alertConfigMsgKind = ''
    try {
      const payload = clampAlertConfig(alertConfigForm)
      alertConfigForm = payload
      const resp = await fetch('/api/metrics/citation_verify/alerts/config', {
        method: 'POST',
        headers: buildAdminHeaders(true),
        body: JSON.stringify({ config: payload })
      })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      if (Number(data?.ok || 0) !== 1) throw new Error('Failed to save alert config')
      const saved = data?.config && typeof data.config === 'object' ? (data.config as Record<string, unknown>) : {}
      alertConfigForm = clampAlertConfig({
        enabled: saved.enabled,
        min_runs: saved.min_runs,
        p95_ms: saved.p95_ms,
        error_rate_per_run: saved.error_rate_per_run,
        cache_delta_hit_rate: saved.cache_delta_hit_rate
      })
      alertConfigDirty = false
      alertConfigMsg = 'Alert config saved'
      alertConfigMsgKind = 'ok'
      await loadMetrics(true)
    } catch (err) {
      alertConfigMsg = err instanceof Error ? err.message : 'Failed to save alert config'
      alertConfigMsgKind = 'bad'
    } finally {
      savingAlertConfig = false
    }
  }

  async function resetAlertConfig(): Promise<void> {
    savingAlertConfig = true
    alertConfigMsg = ''
    alertConfigMsgKind = ''
    try {
      const resp = await fetch('/api/metrics/citation_verify/alerts/config', {
        method: 'POST',
        headers: buildAdminHeaders(true),
        body: JSON.stringify({ reset: true })
      })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      if (Number(data?.ok || 0) !== 1) throw new Error('Failed to reset alert config')
      const saved = data?.config && typeof data.config === 'object' ? (data.config as Record<string, unknown>) : {}
      alertConfigForm = clampAlertConfig({
        enabled: saved.enabled,
        min_runs: saved.min_runs,
        p95_ms: saved.p95_ms,
        error_rate_per_run: saved.error_rate_per_run,
        cache_delta_hit_rate: saved.cache_delta_hit_rate
      })
      alertConfigDirty = false
      alertConfigMsg = 'Alert config reset to defaults'
      alertConfigMsgKind = 'ok'
      await loadMetrics(true)
    } catch (err) {
      alertConfigMsg = err instanceof Error ? err.message : 'Failed to reset alert config'
      alertConfigMsgKind = 'bad'
    } finally {
      savingAlertConfig = false
    }
  }

  async function loadEventContext(eventId: string): Promise<void> {
    const id = String(eventId || '').trim()
    if (!id) return
    eventContextLoading = true
    eventContextTargetId = id
    eventContextError = ''
    try {
      const resp = await fetch(`/api/metrics/citation_verify/alerts/event/${encodeURIComponent(id)}?context=12`, {
        headers: buildAdminHeaders(false)
      })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      if (Number(data?.ok || 0) !== 1) throw new Error('Failed to load event context')
      selectedEventContext = normalizeEventContextPayload(data, id)
    } catch (err) {
      eventContextError = err instanceof Error ? err.message : 'Failed to load event context'
      selectedEventContext = null
    } finally {
      eventContextLoading = false
    }
  }

  async function loadMetrics(manual = false): Promise<void> {
    if (manual) {
      refreshing = true
    } else if (!metrics) {
      loading = true
    }

    errorMsg = ''
    try {
      const resp = await fetch('/api/metrics/citation_verify')
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      metrics = normalizeMetricsPayload(data)
      if (metrics) applyAlertConfigFromMetrics(metrics)
      updatedAt = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    } catch (err) {
      errorMsg = err instanceof Error ? err.message : 'Failed to load performance metrics'
    } finally {
      loading = false
      refreshing = false
    }
  }

  function stopPolling(): void {
    if (!pollTimer) return
    clearInterval(pollTimer)
    pollTimer = null
  }

  function startPolling(): void {
    if (pollTimer) return
    pollTimer = setInterval(() => {
      if (!visible) return
      void loadMetrics(false)
    }, POLL_MS)
  }

  $: {
    if (visible && !wasVisible) {
      wasVisible = true
      void loadMetrics(false)
      startPolling()
    } else if (!visible && wasVisible) {
      wasVisible = false
      stopPolling()
    }
  }

  onDestroy(() => {
    stopPolling()
  })
</script>

{#if visible}
  <div
    class="perf-backdrop"
    role="button"
    tabindex="0"
    aria-label="鍏抽棴鎬ц兘瑙傛祴"
    on:click={() => (visible = false)}
    on:keydown={(e) => {
      if (e.key === 'Enter' || e.key === ' ' || e.key === 'Escape') {
        e.preventDefault()
        visible = false
      }
    }}
  >
    <div class="perf-modal" role="dialog" aria-modal="true" tabindex="-1" on:click|stopPropagation on:keydown|stopPropagation>
      <div class="perf-header">
        <div>
          <h2>鏍搁獙鎬ц兘瑙傛祴</h2>
          <div class="perf-sub">绐楀彛缁熻 + 鏈€杩戣姹傛槑缁�</div>
        </div>
        <div class="perf-actions">
          <button class="btn-refresh" on:click={() => loadMetrics(true)} disabled={loading || refreshing}>
            {#if refreshing}鍒锋柊涓?..{:else}鍒锋柊{/if}
          </button>
          <button class="btn-close" on:click={() => (visible = false)} aria-label="鍏抽棴">脳</button>
        </div>
      </div>

      <div class="perf-body">
        {#if loading && !metrics}
          <div class="perf-empty">鍔犺浇涓?..</div>
        {:else if errorMsg}
          <div class="perf-error">{errorMsg}</div>
        {:else if metrics}
          <div class="perf-updated">鏈€杩戝埛鏂? {updatedAt || '--:--:--'} | 鑷姩杞 {Math.floor(POLL_MS / 1000)}s</div>
          <div class={"perf-health " + (metrics.degraded ? 'warn' : 'ok')}>
            <span class="health-tag">{metrics.degraded ? 'DEGRADED' : 'HEALTHY'}</span>
            {#if metrics.degraded}
              <span>鎸囨爣鎺ュ彛宸查檷绾ц繑鍥烇紝褰撳墠鏁版嵁鏉ヨ嚜鍏滃簳蹇収銆�</span>
            {:else}
              <span>鎸囨爣鎺ュ彛姝ｅ父銆�</span>
            {/if}
          </div>
          {#if metrics.degraded && metrics.errors.length > 0}
            <div class="perf-degraded-errors">
              <div class="title">Degraded Causes</div>
              <div class="error-list">
                {#each metrics.errors as err}
                  <span class="error-item">{err}</span>
                {/each}
              </div>
            </div>
          {/if}
          <div class={"perf-alert-summary " + (metrics.alerts.enabled ? metrics.alerts.severity : 'ok')}>
            <span class="alerts-tag">Alerts</span>
            {#if metrics.alerts.enabled}
              <span>
                severity {metrics.alerts.severity.toUpperCase()} | triggered {metrics.alerts.triggered} | runs {metrics.alerts.runs}/{metrics.alerts.min_runs}
              </span>
            {:else}
              <span>alerts disabled</span>
            {/if}
            {#if metrics.alerts.warmup && metrics.alerts.enabled}
              <span class="alerts-warmup">warmup: alerts suppressed until enough runs</span>
            {/if}
          </div>
          <div class={"perf-notify-summary " + (metrics.alerts.notification.sent ? 'sent' : 'idle')}>
            <span class="notify-tag">Notify</span>
            <span>
              status {metrics.alerts.notification.status} | event {metrics.alerts.notification.event_type} | channels
              {#if metrics.alerts.notification.channels.length > 0}
                {metrics.alerts.notification.channels.join(',')}
              {:else}
                none
              {/if}
            </span>
            {#if metrics.alerts.notification.suppressed > 0}
              <span>suppressed {metrics.alerts.notification.suppressed}</span>
            {/if}
            {#if metrics.alerts.notification.dedupe_hit}
              <span>dedupe-hit</span>
            {/if}
            {#if metrics.alerts.notification.event_id}
              <span>event {metrics.alerts.notification.event_id.slice(0, 8)}</span>
            {/if}
            {#if metrics.alerts.notification.signature}
              <span class="notify-signature">{metrics.alerts.notification.signature}</span>
            {/if}
            {#if metrics.alerts.notification.last_error}
              <span class="notify-error">{metrics.alerts.notification.last_error}</span>
            {/if}
          </div>
          {#if metrics.alerts.notification.events_recent.length > 0}
            <div class="perf-alert-events">
              <div class="title">
                Alert Events ({metrics.alerts.notification.events_recent.length}/{metrics.alerts.notification.events_total})
              </div>
              <div class="alert-event-list">
                {#each metrics.alerts.notification.events_recent.slice().reverse() as ev}
                  <div class={"alert-event-item " + ev.severity}>
                    <span class="event-time">{formatTime(ev.ts)}</span>
                    <span class="event-type">{ev.event_type}</span>
                    <span class="event-status">{ev.status}</span>
                    <span>sent {ev.sent ? 'yes' : 'no'}</span>
                    {#if ev.dedupe_hit}
                      <span>dedupe</span>
                    {/if}
                    {#if ev.triggered_rules.length > 0}
                      <span>rules {ev.triggered_rules.join(',')}</span>
                    {/if}
                    {#if ev.channels.length > 0}
                      <span>via {ev.channels.join(',')}</span>
                    {/if}
                    {#if ev.id}
                      <button class="event-link" on:click={() => loadEventContext(ev.id)} disabled={eventContextLoading}>
                        {#if eventContextLoading && eventContextTargetId === ev.id}loading...{:else}locate{/if}
                      </button>
                    {/if}
                  </div>
                {/each}
              </div>
            </div>
          {/if}
          {#if eventContextError}
            <div class="perf-error">{eventContextError}</div>
          {/if}
          {#if selectedEventContext}
            <div class="perf-event-context">
              <div class="title">Event Context ({selectedEventContext.event_id.slice(0, 8)})</div>
              <div class="line">
                points {selectedEventContext.points.length}/{selectedEventContext.total} | before {selectedEventContext.before}
                | after {selectedEventContext.after}
              </div>
              {#if selectedEventContext.points.length > 0}
                <div class="trend-list">
                  {#each selectedEventContext.points as point, idx (`ctx-${point.id}-${idx}`)}
                    <div class={"trend-item " + point.severity}>
                      <span class="time">{formatTime(point.ts)}</span>
                      <span>p95 {point.p95_ms.toFixed(1)}ms</span>
                      <span>err {formatRate(point.error_rate_per_run)}</span>
                      <span>hit {formatRate(point.cache_delta_hit_rate)}</span>
                      <span>alerts {point.triggered_alerts}</span>
                      <span>notify {point.notification_status || 'none'}</span>
                      {#if point.degraded}
                        <span>degraded</span>
                      {/if}
                    </div>
                  {/each}
                </div>
              {/if}
            </div>
          {/if}
          <div class="perf-alert-config">
            <div class="title">Alert Config</div>
            <div class="alert-admin-key">
              <label for="alert-admin-key">admin key (optional)</label>
              <input
                id="alert-admin-key"
                type="password"
                bind:value={alertAdminKey}
                placeholder="X-Admin-Key"
                on:change={saveAdminKeyLocal}
              />
            </div>
            <div class="alert-config-grid">
              <label class="alert-field checkbox">
                <input
                  type="checkbox"
                  bind:checked={alertConfigForm.enabled}
                  on:change={() => {
                    alertConfigDirty = true
                    alertConfigMsg = ''
                    alertConfigMsgKind = ''
                  }}
                />
                <span>enabled</span>
              </label>
              <label class="alert-field">
                <span>min runs</span>
                <input
                  type="number"
                  min="1"
                  max="500"
                  bind:value={alertConfigForm.min_runs}
                  on:input={() => {
                    alertConfigDirty = true
                    alertConfigMsg = ''
                    alertConfigMsgKind = ''
                  }}
                />
              </label>
              <label class="alert-field">
                <span>p95 ms >=</span>
                <input
                  type="number"
                  min="100"
                  max="60000"
                  bind:value={alertConfigForm.p95_ms}
                  on:input={() => {
                    alertConfigDirty = true
                    alertConfigMsg = ''
                    alertConfigMsgKind = ''
                  }}
                />
              </label>
              <label class="alert-field">
                <span>error rate >=</span>
                <input
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  bind:value={alertConfigForm.error_rate_per_run}
                  on:input={() => {
                    alertConfigDirty = true
                    alertConfigMsg = ''
                    alertConfigMsgKind = ''
                  }}
                />
              </label>
              <label class="alert-field">
                <span>hit rate &lt;=</span>
                <input
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  bind:value={alertConfigForm.cache_delta_hit_rate}
                  on:input={() => {
                    alertConfigDirty = true
                    alertConfigMsg = ''
                    alertConfigMsgKind = ''
                  }}
                />
              </label>
            </div>
            <div class="alert-config-actions">
              <button class="btn-alert-save" on:click={saveAlertConfig} disabled={savingAlertConfig || !alertConfigDirty}>
                {#if savingAlertConfig}淇濆瓨涓?..{:else}淇濆瓨鍛婅閰嶇疆{/if}
              </button>
              <button class="btn-alert-reset" on:click={resetAlertConfig} disabled={savingAlertConfig}>
                鎭㈠榛樿
              </button>
              {#if alertConfigMsg}
                <span class={"alert-config-msg " + (alertConfigMsgKind || 'ok')}>{alertConfigMsg}</span>
              {/if}
            </div>
          </div>
          {#if metrics.alerts.enabled && metrics.alerts.triggered > 0}
            <div class="perf-alert-rules">
              <div class="title">Triggered Rules</div>
              <div class="alert-rule-list">
                {#each metrics.alerts.rules.filter((row) => row.triggered) as row}
                  <div class={"alert-rule-item " + row.level}>
                    <span class="rule-id">{row.id}</span>
                    <span>{row.message}</span>
                    <span>value {formatAlertMetric(row.value)} {row.op} {formatAlertMetric(row.threshold)}</span>
                  </div>
                {/each}
              </div>
            </div>
          {/if}

          <div class="perf-cards">
            <div class="perf-card">
              <div class="label">绐楀彛</div>
              <div class="value">{metrics.observe.runs}/{metrics.observe.max_runs}</div>
              <div class="meta">window {metrics.observe.window_s.toFixed(0)}s</div>
            </div>
            <div class="perf-card">
              <div class="label">寤惰繜</div>
              <div class="value">{metrics.observe.elapsed_ms.p50.toFixed(1)} / {metrics.observe.elapsed_ms.p95.toFixed(1)} ms</div>
              <div class="meta">max {metrics.observe.elapsed_ms.max.toFixed(1)} ms</div>
            </div>
            <div class="perf-card">
              <div class="label">璐熻浇</div>
              <div class="value">{metrics.observe.items.avg.toFixed(1)} items/run</div>
              <div class="meta">workers avg {metrics.observe.workers.avg.toFixed(1)} | max {metrics.observe.workers.max.toFixed(0)}</div>
            </div>
            <div class="perf-card">
              <div class="label">閿欒/鍛戒腑</div>
              <div class="value">{formatRate(metrics.observe.errors.rate_per_run)} / {formatRate(metrics.observe.cache_delta.hit_rate)}</div>
              <div class="meta">errors {metrics.observe.errors.total} | hit_delta</div>
            </div>
          </div>

          <div class="perf-cache">
            <div class="title">缂撳瓨蹇収</div>
            <div class="line">
              size {metrics.cache.size}/{metrics.cache.max_entries} | ttl {metrics.cache.ttl_s.toFixed(0)}s | hit {metrics.cache.hit}/
              {metrics.cache.hit + metrics.cache.miss} ({formatRate(cacheHitRate(metrics.cache))})
            </div>
            <div class="line">
              set {metrics.cache.set} | evicted {metrics.cache.evicted} | expired {metrics.cache.expired}
            </div>
          </div>

          <div class="perf-recent">
            <div class="title">Recent Runs ({metrics.observe.recent.length})</div>
            {#if metrics.observe.recent.length === 0}
              <div class="perf-empty">鏆傛棤鏁版嵁</div>
            {:else}
              <div class="recent-list">
                {#each metrics.observe.recent.slice().reverse() as run, idx (`${run.ts}-${idx}`)}
                  <div class="recent-item">
                    <span class="time">{formatTime(run.ts)}</span>
                    <span>{run.elapsed_ms.toFixed(1)}ms</span>
                    <span>items {run.item_count}</span>
                    <span>w{run.worker_count}</span>
                    <span>err {run.error_count}</span>
                    <span>hit_delta {formatRate(run.cache_delta.hit_rate)}</span>
                  </div>
                {/each}
              </div>
            {/if}
          </div>

          <div class="perf-trend">
            <div class="title">Trend ({metrics.trend.points.length}/{metrics.trend.total})</div>
            {#if !metrics.trend.enabled}
              <div class="line">trend storage disabled</div>
            {:else if metrics.trend.points.length === 0}
              <div class="perf-empty">鏆傛棤瓒嬪娍鏁版嵁</div>
            {:else}
              <div class="trend-list">
                {#each metrics.trend.points.slice().reverse() as point, idx (`${point.id}-${idx}`)}
                  <div class={"trend-item " + point.severity}>
                    <span class="time">{formatTime(point.ts)}</span>
                    <span>p95 {point.p95_ms.toFixed(1)}ms</span>
                    <span>err {formatRate(point.error_rate_per_run)}</span>
                    <span>hit {formatRate(point.cache_delta_hit_rate)}</span>
                    <span>alerts {point.triggered_alerts}</span>
                    <span>notify {point.notification_status || 'none'}</span>
                    {#if point.degraded}
                      <span>degraded</span>
                    {/if}
                  </div>
                {/each}
              </div>
            {/if}
          </div>
        {:else}
          <div class="perf-empty">鏆傛棤瑙傛祴鏁版嵁</div>
        {/if}
      </div>
    </div>
  </div>
{/if}

