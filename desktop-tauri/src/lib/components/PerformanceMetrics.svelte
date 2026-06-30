<script lang="ts">
  import { onDestroy } from 'svelte'
  import './PerformanceMetrics.css'
  import {
    POLL_MS,
    cacheHitRate,
    clampAlertConfig,
    clampResolveAlertConfig,
    formatAlertMetric,
    formatRate,
    formatTime,
    normalizeEventContextPayload,
    normalizeMetricsPayload,
    normalizeResolveMetricsPayload,
    type AlertConfigForm,
    type MetricsEventContext,
    type MetricsView,
    type ResolveAlertConfigForm,
    type ResolveMetricsView
  } from './performanceMetricsUtils'

  export let visible = false

  let metrics: MetricsView | null = null
  let resolveMetrics: ResolveMetricsView | null = null
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
  let resolveSavingAlertConfig = false
  let resolveAlertConfigDirty = false
  let resolveAlertConfigMsg = ''
  let resolveAlertConfigMsgKind: 'ok' | 'bad' | '' = ''
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

  let resolveAlertConfigForm: ResolveAlertConfigForm = {
    enabled: true,
    min_runs: 8,
    failure_rate: 0.35,
    fallback_rate: 0.55,
    p95_ms: 4500,
    low_confidence_rate: 0.4,
    notify_enabled: true,
    notify_cooldown_s: 300,
    notify_timeout_s: 4
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

  function applyResolveAlertConfigFromMetrics(next: ResolveMetricsView): void {
    if (resolveAlertConfigDirty || resolveSavingAlertConfig) return
    resolveAlertConfigForm = clampResolveAlertConfig({
      enabled: next.alerts.enabled,
      min_runs: next.alerts.min_runs,
      failure_rate: next.alerts.thresholds.failure_rate,
      fallback_rate: next.alerts.thresholds.fallback_rate,
      p95_ms: next.alerts.thresholds.p95_ms,
      low_confidence_rate: next.alerts.thresholds.low_confidence_rate,
      notify_enabled: next.alerts.notification.enabled,
      notify_cooldown_s: next.alerts.notification.cooldown_s,
      notify_timeout_s: next.alerts.notification.timeout_s
    })
  }

  function topCountEntries(input: Record<string, number>, limit = 6): Array<{ key: string; count: number }> {
    return Object.entries(input || {})
      .map(([key, value]) => ({ key: String(key || '').trim() || '_unknown', count: Number(value || 0) }))
      .filter((row) => row.count > 0)
      .sort((a, b) => b.count - a.count || a.key.localeCompare(b.key))
      .slice(0, Math.max(1, Math.round(limit)))
  }

  function resolveRowStatus(row: ResolveMetricsView['recent'][number]): 'ok' | 'warn' | 'bad' {
    if (!row.ok) return 'bad'
    if (row.metadata_only || row.low_confidence) return 'warn'
    return 'ok'
  }

  function resolveRowLabel(row: ResolveMetricsView['recent'][number]): string {
    if (!row.ok) return 'failed'
    if (row.metadata_only) return 'metadata_only'
    if (row.low_confidence) return 'low_conf'
    return 'success'
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
      alertConfigMsg = '告警配置已保存'
      alertConfigMsgKind = 'ok'
      await loadMetrics(true)
    } catch (err) {
      alertConfigMsg = err instanceof Error ? err.message : '保存告警配置失败'
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
      alertConfigMsg = '告警配置已重置为默认值'
      alertConfigMsgKind = 'ok'
      await loadMetrics(true)
    } catch (err) {
      alertConfigMsg = err instanceof Error ? err.message : '重置告警配置失败'
      alertConfigMsgKind = 'bad'
    } finally {
      savingAlertConfig = false
    }
  }

  async function saveResolveAlertConfig(): Promise<void> {
    if (!resolveMetrics) return
    resolveSavingAlertConfig = true
    resolveAlertConfigMsg = ''
    resolveAlertConfigMsgKind = ''
    try {
      const payload = clampResolveAlertConfig(resolveAlertConfigForm)
      resolveAlertConfigForm = payload
      const resp = await fetch('/api/metrics/citation_resolve_url/alerts/config', {
        method: 'POST',
        headers: buildAdminHeaders(true),
        body: JSON.stringify({ config: payload })
      })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      if (Number(data?.ok || 0) !== 1) throw new Error('Failed to save resolve alert config')
      const saved = data?.config && typeof data.config === 'object' ? (data.config as Record<string, unknown>) : {}
      resolveAlertConfigForm = clampResolveAlertConfig({
        enabled: saved.enabled,
        min_runs: saved.min_runs,
        failure_rate: saved.failure_rate,
        fallback_rate: saved.fallback_rate,
        p95_ms: saved.p95_ms,
        low_confidence_rate: saved.low_confidence_rate,
        notify_enabled: saved.notify_enabled,
        notify_cooldown_s: saved.notify_cooldown_s,
        notify_timeout_s: saved.notify_timeout_s
      })
      resolveAlertConfigDirty = false
      resolveAlertConfigMsg = '解析告警配置已保存'
      resolveAlertConfigMsgKind = 'ok'
      await loadMetrics(true)
    } catch (err) {
      resolveAlertConfigMsg = err instanceof Error ? err.message : '保存解析告警配置失败'
      resolveAlertConfigMsgKind = 'bad'
    } finally {
      resolveSavingAlertConfig = false
    }
  }

  async function resetResolveAlertConfig(): Promise<void> {
    resolveSavingAlertConfig = true
    resolveAlertConfigMsg = ''
    resolveAlertConfigMsgKind = ''
    try {
      const resp = await fetch('/api/metrics/citation_resolve_url/alerts/config', {
        method: 'POST',
        headers: buildAdminHeaders(true),
        body: JSON.stringify({ reset: true })
      })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      if (Number(data?.ok || 0) !== 1) throw new Error('Failed to reset resolve alert config')
      const saved = data?.config && typeof data.config === 'object' ? (data.config as Record<string, unknown>) : {}
      resolveAlertConfigForm = clampResolveAlertConfig({
        enabled: saved.enabled,
        min_runs: saved.min_runs,
        failure_rate: saved.failure_rate,
        fallback_rate: saved.fallback_rate,
        p95_ms: saved.p95_ms,
        low_confidence_rate: saved.low_confidence_rate,
        notify_enabled: saved.notify_enabled,
        notify_cooldown_s: saved.notify_cooldown_s,
        notify_timeout_s: saved.notify_timeout_s
      })
      resolveAlertConfigDirty = false
      resolveAlertConfigMsg = '解析告警配置已重置为默认值'
      resolveAlertConfigMsgKind = 'ok'
      await loadMetrics(true)
    } catch (err) {
      resolveAlertConfigMsg = err instanceof Error ? err.message : '重置解析告警配置失败'
      resolveAlertConfigMsgKind = 'bad'
    } finally {
      resolveSavingAlertConfig = false
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
      if (Number(data?.ok || 0) !== 1) throw new Error('加载事件上下文失败')
      selectedEventContext = normalizeEventContextPayload(data, id)
    } catch (err) {
      eventContextError = err instanceof Error ? err.message : '加载事件上下文失败'
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
      const [verifyResult, resolveResult] = await Promise.allSettled([
        fetch('/api/metrics/citation_verify'),
        fetch('/api/metrics/citation_resolve_url?limit=60')
      ])
      if (verifyResult.status !== 'fulfilled') {
        throw (verifyResult.reason instanceof Error ? verifyResult.reason : new Error('加载验证指标失败'))
      }
      const verifyResp = verifyResult.value
      if (!verifyResp.ok) throw new Error(`HTTP ${verifyResp.status}`)
      const verifyData = await verifyResp.json()
      metrics = normalizeMetricsPayload(verifyData)
      if (metrics) applyAlertConfigFromMetrics(metrics)

      if (resolveResult.status === 'fulfilled' && resolveResult.value.ok) {
        const resolveData = await resolveResult.value.json()
        resolveMetrics = normalizeResolveMetricsPayload(resolveData)
        if (resolveMetrics) applyResolveAlertConfigFromMetrics(resolveMetrics)
      } else {
        resolveMetrics = normalizeResolveMetricsPayload({})
        if (resolveMetrics) applyResolveAlertConfigFromMetrics(resolveMetrics)
      }
      updatedAt = new Date().toLocaleTimeString('zh-CN', { hour12: false })
    } catch (err) {
      errorMsg = err instanceof Error ? err.message : '加载性能指标失败'
      resolveMetrics = null
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
    aria-label="关闭性能观测"
    onclick={() => (visible = false)}
    onkeydown={(e) => {
      if (e.key === 'Enter' || e.key === ' ' || e.key === 'Escape') {
        e.preventDefault()
        visible = false
      }
    }}
  >
    <div class="perf-modal" role="dialog" aria-modal="true" tabindex="-1" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()}>
      <div class="perf-header">
        <div>
          <h2>核验性能观测</h2>
          <div class="perf-sub">核验与 URL 解析指标，展示最近请求详情</div>
        </div>
        <div class="perf-actions">
          <button class="btn-refresh" onclick={() => loadMetrics(true)} disabled={loading || refreshing}>
            {#if refreshing}刷新中...{:else}刷新{/if}
          </button>
          <button class="btn-close" onclick={() => (visible = false)} aria-label="关闭">×</button>
        </div>
      </div>

      <div class="perf-body">
        {#if loading && !metrics}
          <div class="perf-empty">加载中...</div>
        {:else if errorMsg}
          <div class="perf-error">{errorMsg}</div>
        {:else if metrics}
          <div class="perf-updated">更新时间 {updatedAt || "--:--:--"} | 自动轮询 {Math.floor(POLL_MS / 1000)} 秒</div>
          <div class={"perf-health " + (metrics.degraded ? 'warn' : 'ok')}>
            <span class="health-tag">{metrics.degraded ? '降级' : '正常'}</span>
            {#if metrics.degraded}
              <span>指标接口当前已降级，正在展示回退快照数据。</span>
            {:else}
              <span>指标接口运行正常。</span>
            {/if}
          </div>
          {#if metrics.degraded && metrics.errors.length > 0}
            <div class="perf-degraded-errors">
              <div class="title">降级原因</div>
              <div class="error-list">
                {#each metrics.errors as err}
                  <span class="error-item">{err}</span>
                {/each}
              </div>
            </div>
          {/if}
          <div class={"perf-alert-summary " + (metrics.alerts.enabled ? metrics.alerts.severity : 'ok')}>
            <span class="alerts-tag">告警</span>
            {#if metrics.alerts.enabled}
              <span>
                级别 {metrics.alerts.severity.toUpperCase()} | 触发 {metrics.alerts.triggered} | 运行次数 {metrics.alerts.runs}/{metrics.alerts.min_runs}
              </span>
            {:else}
              <span>告警未启用</span>
            {/if}
            {#if metrics.alerts.warmup && metrics.alerts.enabled}
              <span class="alerts-warmup">预热中：达到足够运行次数前暂不触发告警</span>
            {/if}
          </div>
          <div class={"perf-notify-summary " + (metrics.alerts.notification.sent ? 'sent' : 'idle')}>
            <span class="notify-tag">通知</span>
            <span>
              状态 {metrics.alerts.notification.status} | 事件 {metrics.alerts.notification.event_type} | 通道
              {#if metrics.alerts.notification.channels.length > 0}
                {metrics.alerts.notification.channels.join(',')}
              {:else}
                无
              {/if}
            </span>
            {#if metrics.alerts.notification.suppressed > 0}
              <span>已抑制 {metrics.alerts.notification.suppressed}</span>
            {/if}
            {#if metrics.alerts.notification.dedupe_hit}
              <span>命中去重</span>
            {/if}
            {#if metrics.alerts.notification.event_id}
              <span>事件 {metrics.alerts.notification.event_id.slice(0, 8)}</span>
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
                告警事件（{metrics.alerts.notification.events_recent.length}/{metrics.alerts.notification.events_total}）
              </div>
              <div class="alert-event-list">
                {#each metrics.alerts.notification.events_recent.slice().reverse() as ev}
                  <div class={"alert-event-item " + ev.severity}>
                    <span class="event-time">{formatTime(ev.ts)}</span>
                    <span class="event-type">{ev.event_type}</span>
                    <span class="event-status">{ev.status}</span>
                    <span>已发送 {ev.sent ? '是' : '否'}</span>
                    {#if ev.dedupe_hit}
                      <span>去重</span>
                    {/if}
                    {#if ev.triggered_rules.length > 0}
                      <span>规则 {ev.triggered_rules.join(',')}</span>
                    {/if}
                    {#if ev.channels.length > 0}
                      <span>通道 {ev.channels.join(',')}</span>
                    {/if}
                    {#if ev.id}
                      <button class="event-link" onclick={() => loadEventContext(ev.id)} disabled={eventContextLoading}>
                        {#if eventContextLoading && eventContextTargetId === ev.id}加载中...{:else}定位{/if}
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
              <div class="title">事件上下文 ({selectedEventContext.event_id.slice(0, 8)})</div>
              <div class="line">
                数据点 {selectedEventContext.points.length}/{selectedEventContext.total} | 之前 {selectedEventContext.before}
                | 之后 {selectedEventContext.after}
              </div>
              {#if selectedEventContext.points.length > 0}
                <div class="trend-list">
                  {#each selectedEventContext.points as point, idx (`ctx-${point.id}-${idx}`)}
                    <div class={"trend-item " + point.severity}>
                      <span class="time">{formatTime(point.ts)}</span>
                      <span>P95 {point.p95_ms.toFixed(1)}ms</span>
                      <span>错误率 {formatRate(point.error_rate_per_run)}</span>
                      <span>命中率 {formatRate(point.cache_delta_hit_rate)}</span>
                      <span>告警 {point.triggered_alerts}</span>
                      <span>通知 {point.notification_status || '无'}</span>
                      {#if point.degraded}
                        <span>降级</span>
                      {/if}
                    </div>
                  {/each}
                </div>
              {/if}
            </div>
          {/if}
          <div class="perf-alert-config">
            <div class="title">告警配置</div>
            <div class="alert-admin-key">
              <label for="alert-admin-key">管理密钥（可选）</label>
              <input
                id="alert-admin-key"
                type="password"
                bind:value={alertAdminKey}
                placeholder="请输入 X-Admin-Key"
                onchange={saveAdminKeyLocal}
              />
            </div>
            <div class="alert-config-grid">
              <label class="alert-field checkbox">
                <input
                  type="checkbox"
                  bind:checked={alertConfigForm.enabled}
                  onchange={() => {
                    alertConfigDirty = true
                    alertConfigMsg = ''
                    alertConfigMsgKind = ''
                  }}
                />
                <span>启用</span>
              </label>
              <label class="alert-field">
                <span>最小运行次数</span>
                <input
                  type="number"
                  min="1"
                  max="500"
                  bind:value={alertConfigForm.min_runs}
                  oninput={() => {
                    alertConfigDirty = true
                    alertConfigMsg = ''
                    alertConfigMsgKind = ''
                  }}
                />
              </label>
              <label class="alert-field">
                <span>P95 毫秒 ≥</span>
                <input
                  type="number"
                  min="100"
                  max="60000"
                  bind:value={alertConfigForm.p95_ms}
                  oninput={() => {
                    alertConfigDirty = true
                    alertConfigMsg = ''
                    alertConfigMsgKind = ''
                  }}
                />
              </label>
              <label class="alert-field">
                <span>错误率 ≥</span>
                <input
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  bind:value={alertConfigForm.error_rate_per_run}
                  oninput={() => {
                    alertConfigDirty = true
                    alertConfigMsg = ''
                    alertConfigMsgKind = ''
                  }}
                />
              </label>
              <label class="alert-field">
                <span>命中率 ≤</span>
                <input
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  bind:value={alertConfigForm.cache_delta_hit_rate}
                  oninput={() => {
                    alertConfigDirty = true
                    alertConfigMsg = ''
                    alertConfigMsgKind = ''
                  }}
                />
              </label>
            </div>
            <div class="alert-config-actions">
              <button class="btn-alert-save" onclick={saveAlertConfig} disabled={savingAlertConfig || !alertConfigDirty}>
                {#if savingAlertConfig}保存中...{:else}保存告警配置{/if}
              </button>
              <button class="btn-alert-reset" onclick={resetAlertConfig} disabled={savingAlertConfig}>
                恢复默认值
              </button>
              {#if alertConfigMsg}
                <span class={"alert-config-msg " + (alertConfigMsgKind || 'ok')}>{alertConfigMsg}</span>
              {/if}
            </div>
          </div>
          {#if metrics.alerts.enabled && metrics.alerts.triggered > 0}
            <div class="perf-alert-rules">
              <div class="title">已触发规则</div>
              <div class="alert-rule-list">
                {#each metrics.alerts.rules.filter((row) => row.triggered) as row}
                  <div class={"alert-rule-item " + row.level}>
                    <span class="rule-id">{row.id}</span>
                    <span>{row.message}</span>
                    <span>数值 {formatAlertMetric(row.value)} {row.op} {formatAlertMetric(row.threshold)}</span>
                  </div>
                {/each}
              </div>
            </div>
          {/if}

          <div class="perf-cards">
            <div class="perf-card">
              <div class="label">窗口</div>
              <div class="value">{metrics.observe.runs}/{metrics.observe.max_runs}</div>
              <div class="meta">窗口 {metrics.observe.window_s.toFixed(0)} 秒</div>
            </div>
            <div class="perf-card">
              <div class="label">延迟</div>
              <div class="value">{metrics.observe.elapsed_ms.p50.toFixed(1)} / {metrics.observe.elapsed_ms.p95.toFixed(1)} ms</div>
              <div class="meta">最大 {metrics.observe.elapsed_ms.max.toFixed(1)} ms</div>
            </div>
            <div class="perf-card">
              <div class="label">负载</div>
              <div class="value">{metrics.observe.items.avg.toFixed(1)} 项/次</div>
              <div class="meta">平均线程 {metrics.observe.workers.avg.toFixed(1)} | 最大 {metrics.observe.workers.max.toFixed(0)}</div>
            </div>
            <div class="perf-card">
              <div class="label">错误率/命中率</div>
              <div class="value">{formatRate(metrics.observe.errors.rate_per_run)} / {formatRate(metrics.observe.cache_delta.hit_rate)}</div>
              <div class="meta">错误数 {metrics.observe.errors.total} | 命中变化</div>
            </div>
          </div>

          <div class="perf-cache">
            <div class="title">缓存快照</div>
            <div class="line">
              容量 {metrics.cache.size}/{metrics.cache.max_entries} | 过期 {metrics.cache.ttl_s.toFixed(0)} 秒 | 命中 {metrics.cache.hit}/
              {metrics.cache.hit + metrics.cache.miss} ({formatRate(cacheHitRate(metrics.cache))})
            </div>
            <div class="line">
              写入 {metrics.cache.set} | 淘汰 {metrics.cache.evicted} | 过期移除 {metrics.cache.expired}
            </div>
          </div>

          {#if resolveMetrics}
            <div class="perf-resolve">
              <div class="title">URL 解析 ({resolveMetrics.runs}/{resolveMetrics.max_runs})</div>
              <div class="resolve-cards">
                <div class="resolve-card">
                  <div class="label">成功率 / 回退率</div>
                  <div class="value">{formatRate(resolveMetrics.success_rate)} / {formatRate(resolveMetrics.fallback_rate)}</div>
                  <div class="meta">
                    请求 {resolveMetrics.totals.requests} · 成功 {resolveMetrics.totals.success} · 失败 {resolveMetrics.totals.failed}
                  </div>
                </div>
                <div class="resolve-card">
                  <div class="label">延迟</div>
                  <div class="value">{resolveMetrics.latency_ms.p50.toFixed(1)} / {resolveMetrics.latency_ms.p95.toFixed(1)} ms</div>
                  <div class="meta">平均 {resolveMetrics.latency_ms.avg.toFixed(1)} · 最大 {resolveMetrics.latency_ms.max.toFixed(1)}</div>
                </div>
                <div class="resolve-card">
                  <div class="label">置信度</div>
                  <div class="value">{formatRate(resolveMetrics.confidence.p50)} / {formatRate(resolveMetrics.confidence.p95)}</div>
                  <div class="meta">
                    平均 {formatRate(resolveMetrics.confidence.avg)} · 低置信 {resolveMetrics.totals.low_confidence}
                  </div>
                </div>
                <div class="resolve-card">
                  <div class="label">仅元数据</div>
                  <div class="value">{resolveMetrics.totals.metadata_only}</div>
                  <div class="meta">窗口 {resolveMetrics.window_s.toFixed(0)} 秒</div>
                </div>
              </div>
              <div class="resolve-map-row">
                <div class="resolve-map">
                  <span class="map-label">解析器</span>
                  {#if topCountEntries(resolveMetrics.resolvers, 6).length === 0}
                    <span class="map-empty">无</span>
                  {:else}
                    {#each topCountEntries(resolveMetrics.resolvers, 6) as row (`resolver-${row.key}`)}
                      <span class="map-chip">{row.key}:{row.count}</span>
                    {/each}
                  {/if}
                </div>
                <div class="resolve-map">
                  <span class="map-label">提供方</span>
                  {#if topCountEntries(resolveMetrics.providers, 6).length === 0}
                    <span class="map-empty">无</span>
                  {:else}
                    {#each topCountEntries(resolveMetrics.providers, 6) as row (`provider-${row.key}`)}
                      <span class="map-chip">{row.key}:{row.count}</span>
                    {/each}
                  {/if}
                </div>
              </div>
              <div class={"perf-alert-summary " + (resolveMetrics.alerts.enabled ? resolveMetrics.alerts.severity : 'ok')}>
                <span class="alerts-tag">解析告警</span>
                {#if resolveMetrics.alerts.enabled}
                  <span>
                    级别 {resolveMetrics.alerts.severity.toUpperCase()} | 已触发 {resolveMetrics.alerts.triggered} |
                    运行次数 {resolveMetrics.alerts.runs}/{resolveMetrics.alerts.min_runs}
                  </span>
                {:else}
                  <span>告警未启用</span>
                {/if}
                {#if resolveMetrics.alerts.warmup && resolveMetrics.alerts.enabled}
                  <span class="alerts-warmup">预热中：运行次数达到阈值前暂不触发告警</span>
                {/if}
              </div>
              <div class={"perf-notify-summary " + (resolveMetrics.alerts.notification.sent ? 'sent' : 'idle')}>
                <span class="notify-tag">解析通知</span>
                <span>
                  状态 {resolveMetrics.alerts.notification.status} | 事件 {resolveMetrics.alerts.notification.event_type} |
                  渠道
                  {#if resolveMetrics.alerts.notification.channels.length > 0}
                    {resolveMetrics.alerts.notification.channels.join(',')}
                  {:else}
                    无
                  {/if}
                </span>
                {#if resolveMetrics.alerts.notification.suppressed > 0}
                  <span>已抑制 {resolveMetrics.alerts.notification.suppressed}</span>
                {/if}
                {#if resolveMetrics.alerts.notification.dedupe_hit}
                  <span>命中去重</span>
                {/if}
                {#if resolveMetrics.alerts.notification.event_id}
                  <span>事件 {resolveMetrics.alerts.notification.event_id.slice(0, 8)}</span>
                {/if}
                {#if resolveMetrics.alerts.notification.signature}
                  <span class="notify-signature">{resolveMetrics.alerts.notification.signature}</span>
                {/if}
                {#if resolveMetrics.alerts.notification.last_error}
                  <span class="notify-error">{resolveMetrics.alerts.notification.last_error}</span>
                {/if}
              </div>
              <div class="perf-alert-config">
                <div class="title">解析告警配置</div>
                <div class="line">使用上方相同的管理密钥</div>
                <div class="alert-config-grid resolve">
                  <label class="alert-field checkbox">
                    <input
                      type="checkbox"
                      bind:checked={resolveAlertConfigForm.enabled}
                      onchange={() => {
                        resolveAlertConfigDirty = true
                        resolveAlertConfigMsg = ''
                        resolveAlertConfigMsgKind = ''
                      }}
                    />
                    <span>启用告警</span>
                  </label>
                  <label class="alert-field checkbox">
                    <input
                      type="checkbox"
                      bind:checked={resolveAlertConfigForm.notify_enabled}
                      onchange={() => {
                        resolveAlertConfigDirty = true
                        resolveAlertConfigMsg = ''
                        resolveAlertConfigMsgKind = ''
                      }}
                    />
                    <span>启用通知</span>
                  </label>
                  <label class="alert-field">
                    <span>最少运行次数</span>
                    <input
                      type="number"
                      min="1"
                      max="500"
                      bind:value={resolveAlertConfigForm.min_runs}
                      oninput={() => {
                        resolveAlertConfigDirty = true
                        resolveAlertConfigMsg = ''
                        resolveAlertConfigMsgKind = ''
                      }}
                    />
                  </label>
                  <label class="alert-field">
                    <span>失败率 &gt;=</span>
                    <input
                      type="number"
                      min="0"
                      max="1"
                      step="0.01"
                      bind:value={resolveAlertConfigForm.failure_rate}
                      oninput={() => {
                        resolveAlertConfigDirty = true
                        resolveAlertConfigMsg = ''
                        resolveAlertConfigMsgKind = ''
                      }}
                    />
                  </label>
                  <label class="alert-field">
                    <span>回退率 &gt;=</span>
                    <input
                      type="number"
                      min="0"
                      max="1"
                      step="0.01"
                      bind:value={resolveAlertConfigForm.fallback_rate}
                      oninput={() => {
                        resolveAlertConfigDirty = true
                        resolveAlertConfigMsg = ''
                        resolveAlertConfigMsgKind = ''
                      }}
                    />
                  </label>
                  <label class="alert-field">
                    <span>P95 延迟毫秒 &gt;=</span>
                    <input
                      type="number"
                      min="100"
                      max="60000"
                      bind:value={resolveAlertConfigForm.p95_ms}
                      oninput={() => {
                        resolveAlertConfigDirty = true
                        resolveAlertConfigMsg = ''
                        resolveAlertConfigMsgKind = ''
                      }}
                    />
                  </label>
                  <label class="alert-field">
                    <span>低置信率 &gt;=</span>
                    <input
                      type="number"
                      min="0"
                      max="1"
                      step="0.01"
                      bind:value={resolveAlertConfigForm.low_confidence_rate}
                      oninput={() => {
                        resolveAlertConfigDirty = true
                        resolveAlertConfigMsg = ''
                        resolveAlertConfigMsgKind = ''
                      }}
                    />
                  </label>
                  <label class="alert-field">
                    <span>通知冷却秒数</span>
                    <input
                      type="number"
                      min="10"
                      max="86400"
                      bind:value={resolveAlertConfigForm.notify_cooldown_s}
                      oninput={() => {
                        resolveAlertConfigDirty = true
                        resolveAlertConfigMsg = ''
                        resolveAlertConfigMsgKind = ''
                      }}
                    />
                  </label>
                  <label class="alert-field">
                    <span>通知超时秒数</span>
                    <input
                      type="number"
                      min="1"
                      max="30"
                      step="0.5"
                      bind:value={resolveAlertConfigForm.notify_timeout_s}
                      oninput={() => {
                        resolveAlertConfigDirty = true
                        resolveAlertConfigMsg = ''
                        resolveAlertConfigMsgKind = ''
                      }}
                    />
                  </label>
                </div>
                <div class="alert-config-actions">
                  <button
                    class="btn-alert-save"
                    onclick={saveResolveAlertConfig}
                    disabled={resolveSavingAlertConfig || !resolveAlertConfigDirty}
                  >
                    {#if resolveSavingAlertConfig}保存中...{:else}保存解析配置{/if}
                  </button>
                  <button class="btn-alert-reset" onclick={resetResolveAlertConfig} disabled={resolveSavingAlertConfig}>
                    恢复默认值
                  </button>
                  {#if resolveAlertConfigMsg}
                    <span class={"alert-config-msg " + (resolveAlertConfigMsgKind || 'ok')}>{resolveAlertConfigMsg}</span>
                  {/if}
                </div>
              </div>
              {#if resolveMetrics.alerts.notification.events_recent.length > 0}
                <div class="perf-alert-events">
                  <div class="title">
                    解析告警事件 ({resolveMetrics.alerts.notification.events_recent.length}/{resolveMetrics.alerts.notification.events_total})
                  </div>
                  <div class="alert-event-list">
                    {#each resolveMetrics.alerts.notification.events_recent.slice().reverse() as ev}
                      <div class={"alert-event-item " + ev.severity}>
                        <span class="event-time">{formatTime(ev.ts)}</span>
                        <span class="event-type">{ev.event_type}</span>
                        <span class="event-status">{ev.status}</span>
                        <span>已发送 {ev.sent ? '是' : '否'}</span>
                        {#if ev.dedupe_hit}
                          <span>去重</span>
                        {/if}
                        {#if ev.triggered_rules.length > 0}
                          <span>规则 {ev.triggered_rules.join(',')}</span>
                        {/if}
                        {#if ev.channels.length > 0}
                          <span>通道 {ev.channels.join(',')}</span>
                        {/if}
                      </div>
                    {/each}
                  </div>
                </div>
              {/if}
              {#if resolveMetrics.alerts.enabled && resolveMetrics.alerts.triggered > 0}
                <div class="perf-alert-rules">
                  <div class="title">已触发解析规则</div>
                  <div class="alert-rule-list">
                    {#each resolveMetrics.alerts.rules.filter((row) => row.triggered) as row}
                      <div class={"alert-rule-item " + row.level}>
                        <span class="rule-id">{row.id}</span>
                        <span>{row.message}</span>
                        <span>当前值 {formatAlertMetric(row.value)} {row.op} 阈值 {formatAlertMetric(row.threshold)}</span>
                      </div>
                    {/each}
                  </div>
                </div>
              {/if}
              <div class="resolve-recent">
                <div class="title">最近解析记录 ({resolveMetrics.recent.length})</div>
                {#if resolveMetrics.recent.length === 0}
                  <div class="perf-empty">暂无数据</div>
                {:else}
                  <div class="resolve-recent-list">
                    {#each resolveMetrics.recent.slice().reverse() as row, idx (`${row.ts}-${idx}`)}
                      <div class={"resolve-recent-item " + resolveRowStatus(row)}>
                        <span class="time">{formatTime(row.ts)}</span>
                        <span class={"resolve-chip " + resolveRowStatus(row)}>{resolveRowLabel(row)}</span>
                        <span>{row.elapsed_ms.toFixed(1)}ms</span>
                        <span>{row.resolver || '-'}</span>
                        <span>{row.provider || '-'}</span>
                        <span>置信度 {formatRate(row.confidence)}</span>
                        <span>警告 {row.warning_count}</span>
                        {#if row.error}
                          <span class="resolve-err">{row.error}</span>
                        {/if}
                      </div>
                    {/each}
                  </div>
                {/if}
              </div>
            </div>
          {/if}

          <div class="perf-recent">
            <div class="title">最近运行记录 ({metrics.observe.recent.length})</div>
            {#if metrics.observe.recent.length === 0}
              <div class="perf-empty">暂无数据</div>
            {:else}
              <div class="recent-list">
                {#each metrics.observe.recent.slice().reverse() as run, idx (`${run.ts}-${idx}`)}
                  <div class="recent-item">
                    <span class="time">{formatTime(run.ts)}</span>
                    <span>{run.elapsed_ms.toFixed(1)}ms</span>
                    <span>条目 {run.item_count}</span>
                    <span>线程 {run.worker_count}</span>
                    <span>错误 {run.error_count}</span>
                    <span>命中变化 {formatRate(run.cache_delta.hit_rate)}</span>
                  </div>
                {/each}
              </div>
            {/if}
          </div>

          <div class="perf-trend">
            <div class="title">趋势 ({metrics.trend.points.length}/{metrics.trend.total})</div>
            {#if !metrics.trend.enabled}
              <div class="line">趋势存储未启用</div>
            {:else if metrics.trend.points.length === 0}
              <div class="perf-empty">暂无趋势数据</div>
            {:else}
              <div class="trend-list">
                {#each metrics.trend.points.slice().reverse() as point, idx (`${point.id}-${idx}`)}
                  <div class={"trend-item " + point.severity}>
                    <span class="time">{formatTime(point.ts)}</span>
                    <span>P95 {point.p95_ms.toFixed(1)}ms</span>
                    <span>错误率 {formatRate(point.error_rate_per_run)}</span>
                    <span>命中率 {formatRate(point.cache_delta_hit_rate)}</span>
                    <span>告警 {point.triggered_alerts}</span>
                    <span>通知 {point.notification_status || '无'}</span>
                    {#if point.degraded}
                      <span>降级</span>
                    {/if}
                  </div>
                {/each}
              </div>
            {/if}
          </div>
        {:else}
          <div class="perf-empty">暂无观测数据</div>
        {/if}
      </div>
    </div>
  </div>
{/if}

