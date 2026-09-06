<script lang="ts">
  import { onMount } from 'svelte'
  import { docId, pushToast } from '../stores'
  import type {
    Citation,
    VerifyDebugHistoryEntry,
    VerifyDebugLevel,
    VerifyDebugPayload,
    VerifyItem,
    VerifySummary
  } from '../citations/citationTypes'
  import { parseVerifyDebugPayload } from '../citations/citationDebug'
  import {
    averageNumber,
    cacheEvictRate,
    cacheHitRate,
    cacheLookupCount,
    formatCitation,
    formatRate,
    normalizeItems,
    normalizeResolveItem,
    statusClass,
    statusLabel,
    toSafeInt
  } from '../citations/citationUtils'

  let { visible = $bindable(false) }: { visible?: boolean } = $props()

  const VERIFY_DEBUG_ENABLED = Boolean(import.meta.env.DEV)
  const VERIFY_DEBUG_HISTORY_LIMIT = 8
  const CACHE_HIT_RATE_WARN_THRESHOLD = 0.55
  const CACHE_EVICT_RATE_WARN_THRESHOLD = 0.08

  let citations = $state<Citation[]>([])
  let loading = $state(false)
  let verifying = $state(false)
  let verifyMap = $state<Record<string, VerifyItem>>({})
  let verifySummary = $state<VerifySummary | null>(null)
  let verifyDebug = $state<VerifyDebugPayload | null>(null)
  let verifyDebugHistory = $state<VerifyDebugHistoryEntry[]>([])
  let verifyDebugHistorySeq = $state(0)
  let verifyDebugLevel = $state<VerifyDebugLevel>('safe')
  let lastLoadedId = $state('')
  let saveTimer = $state<ReturnType<typeof setTimeout> | null>(null)
  let resolveUrl = $state('')
  let resolvingUrl = $state(false)

  let newCitation = $state<Citation>({
    id: '',
    author: '',
    title: '',
    year: '',
    source: ''
  })

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

  async function resolveCitationFromUrl() {
    const id = $docId
    if (!id) return
    const target = String(resolveUrl || '').trim()
    if (!target) {
      pushToast('请先输入链接', 'bad')
      return
    }
    resolvingUrl = true
    try {
      const resp = await fetch(`/api/doc/${id}/citations/resolve-url`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: target })
      })
      if (!resp.ok) throw new Error(await resp.text())
      const data = await resp.json()
      const item = normalizeResolveItem(data?.item)
      if (!item) throw new Error('invalid resolve item')
      newCitation = {
        id: item.id || newCitation.id,
        author: item.author || newCitation.author,
        title: item.title || newCitation.title,
        year: item.year || newCitation.year,
        source: item.source || newCitation.source
      }
      const warnings = Array.isArray(data?.warnings)
        ? data.warnings.map((x: unknown) => String(x || '').trim()).filter((x: string) => x)
        : []
      const confidence = Number(data?.confidence || 0)
      if (warnings.length > 0) {
        pushToast(`自动补全完成，请核对：${warnings.join(', ')}`, 'info')
      } else {
        pushToast(`自动补全完成（置信度 ${(Math.max(0, Math.min(1, confidence)) * 100).toFixed(0)}%）`, 'ok')
      }
    } catch (err) {
      console.error('Failed to resolve citation from url', err)
      pushToast('链接自动补全失败', 'bad')
    } finally {
      resolvingUrl = false
    }
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
    resolveUrl = ''
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
        const nextDebug = parseVerifyDebugPayload(data.debug)
        verifyDebug = nextDebug
        if (nextDebug) appendVerifyDebugHistory(nextDebug)
        if (nextDebug?.requested_level === 'full' && nextDebug.level !== 'full') {
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

  $effect(() => {
    if (visible) {
      const id = $docId
      if (id && id !== lastLoadedId) {
        lastLoadedId = id
        loadCitations()
      }
    }
  })
</script>

{#if visible}
  <div
    class="modal-backdrop"
    role="button"
    tabindex="0"
    aria-label="关闭引用管理"
    onclick={() => (visible = false)}
    onkeydown={(e) => {
      if (e.key === 'Enter' || e.key === ' ' || e.key === 'Escape') {
        e.preventDefault()
        visible = false
      }
    }}
  >
    <div class="modal" role="dialog" aria-modal="true" tabindex="-1" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()}>
      <div class="modal-header">
        <h2>引用管理</h2>
        <button class="close-btn" onclick={() => (visible = false)}>×</button>
      </div>

      <div class="modal-body">
        <div class="add-section">
          <h3>添加引用</h3>
          <div class="resolve-row">
            <input
              type="text"
              class="resolve-input"
              placeholder="粘贴论文链接（DOI/arXiv/期刊页面）"
              bind:value={resolveUrl}
              disabled={resolvingUrl}
              onkeydown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault()
                  resolveCitationFromUrl()
                }
              }}
            />
            <button class="btn-resolve" disabled={resolvingUrl} onclick={resolveCitationFromUrl}>
              {#if resolvingUrl}自动补全中...{:else}链接自动补全{/if}
            </button>
          </div>
          <div class="form-grid">
            <input type="text" placeholder="引用 ID（如 smith2023）" bind:value={newCitation.id} />
            <input type="text" placeholder="作者*" bind:value={newCitation.author} />
            <input type="text" placeholder="标题*" bind:value={newCitation.title} />
            <input type="text" placeholder="年份" bind:value={newCitation.year} />
            <input type="text" placeholder="来源（期刊/会议/URL）" bind:value={newCitation.source} class="full-width" />
          </div>
          <button class="btn-add" onclick={addCitation}>添加引用</button>
        </div>

        <div class="verify-section">
          <h3>核验真实性</h3>
          <div class="verify-row">
            <button class="btn-verify" disabled={verifying || loading || citations.length === 0} onclick={verifyCitations}>
              {#if verifying}核验中...{:else}核验引用{/if}
            </button>
            {#if VERIFY_DEBUG_ENABLED}
              <div class="verify-debug-controls">
                <label for="verify-debug-level">调试级别</label>
                <select id="verify-debug-level" bind:value={verifyDebugLevel} disabled={verifying}>
                  <option value="safe">安全（脱敏）</option>
                  <option value="strict">严格（仅指标）</option>
                  <option value="full">完整（原始数据，限频）</option>
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
                  调试 · 请求 {verifyDebug.requested_level} · 生效 {verifyDebug.level} · 工作线程 {verifyDebug.request.workers} · 采样 {verifyDebug.sampling.output_items}/{verifyDebug.sampling.input_items} · 耗时 {verifyDebug.elapsed_ms.toFixed(1)}ms
                </span>
                <span class="verify-debug-metrics">
                  缓存 {verifyDebug.cache.size}/{verifyDebug.cache.max_entries || '-'} · TTL {verifyDebug.cache.ttl_s.toFixed(0)}s · 命中 {verifyDebug.cache.hit}/{cacheLookupCount(verifyDebug.cache)} ({formatRate(cacheHitRate(verifyDebug.cache))}) · 淘汰 {verifyDebug.cache.evicted}/{verifyDebug.cache.set} ({formatRate(cacheEvictRate(verifyDebug.cache))}) · 过期 {verifyDebug.cache.expired}
                </span>
                {#if verifyDebug.observe}
                  <span class="verify-debug-observe">
                    窗口 {verifyDebug.observe.window.runs}/{verifyDebug.observe.window.max_runs || '-'} · P50/P95 {verifyDebug.observe.window.elapsed_ms.p50.toFixed(1)}/{verifyDebug.observe.window.elapsed_ms.p95.toFixed(1)}ms · 平均条目 {verifyDebug.observe.window.items.avg.toFixed(1)} · 平均线程 {verifyDebug.observe.window.workers.avg.toFixed(1)} · 命中变化 {formatRate(verifyDebug.observe.window.cache_delta.hit_rate)}
                  </span>
                {/if}
                <span class="verify-debug-health">
                  <span class={"verify-debug-chip " + (cacheHitRate(verifyDebug.cache) < CACHE_HIT_RATE_WARN_THRESHOLD ? 'warn' : 'ok')}>
                    命中率 {formatRate(cacheHitRate(verifyDebug.cache))}
                  </span>
                  <span class={"verify-debug-chip " + (cacheEvictRate(verifyDebug.cache) > CACHE_EVICT_RATE_WARN_THRESHOLD ? 'warn' : 'ok')}>
                    淘汰率 {formatRate(cacheEvictRate(verifyDebug.cache))}
                  </span>
                </span>
                {#if verifyDebug.rate_limited_full}
                  <span class="verify-debug-flag">完整 -> 安全（已限流）</span>
                {/if}
                {#if verifyDebugHistory.length > 0}
                  <span class="verify-debug-trend">
                    近 5 次平均 命中率 {formatRate(historyAverageHitRate(5))} · 淘汰率 {formatRate(historyAverageEvictRate(5))} · 耗时 {historyAverageElapsedMs(5).toFixed(1)}ms
                  </span>
                {/if}
                <button
                  class="btn-debug-clear"
                  onclick={clearVerifyDebugHistory}
                  disabled={verifyDebugHistory.length === 0}
                >
                  清空历史
                </button>
                <button class="btn-debug-copy" onclick={copyVerifyDebugJson}>复制诊断 JSON</button>
              </div>
              {#if verifyDebugHistory.length > 0}
                <div class="verify-debug-history">
                  <div class="verify-debug-history-title">最近核验记录 ({verifyDebugHistory.length}/{VERIFY_DEBUG_HISTORY_LIMIT})</div>
                  <div class="verify-debug-history-list">
                    {#each verifyDebugHistory.slice().reverse() as run (run.id)}
                      <div class="verify-debug-history-item">
                        <span class="history-time">{run.at_label}</span>
                        <span class={"history-chip " + (run.hit_rate < CACHE_HIT_RATE_WARN_THRESHOLD ? 'warn' : 'ok')}>命中率 {formatRate(run.hit_rate)}</span>
                        <span class={"history-chip " + (run.evict_rate > CACHE_EVICT_RATE_WARN_THRESHOLD ? 'warn' : 'ok')}>淘汰率 {formatRate(run.evict_rate)}</span>
                        <span class="history-meta">线程 {run.workers}</span>
                        <span class="history-meta">缓存 {run.cache_size}/{run.cache_max || '-'}</span>
                        <span class="history-meta">采样 {run.sampled_output}/{run.sampled_input}</span>
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
            <button class="btn-export" onclick={() => exportBibliography('apa')}>APA</button>
            <button class="btn-export" onclick={() => exportBibliography('mla')}>MLA</button>
            <button class="btn-export" onclick={() => exportBibliography('gb')}>GB/T 7714</button>
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
                            <summary>调试详情</summary>
                            <div class="debug-line">缓存命中：{vdbg.cache_hit ? '是' : '否'}</div>
                            {#if vdbg.query}<div class="debug-line">检索查询：{vdbg.query}</div>{/if}
                            {#if vdbg.picked_provider}
                              <div class="debug-line">
                                选中来源：{vdbg.picked_provider}（总分 {vdbg.picked_total_score.toFixed(3)}，标题 {vdbg.picked_title_score.toFixed(3)}，年份 {vdbg.picked_year_score.toFixed(3)}）
                              </div>
                            {/if}
                            <div class="debug-line">候选来源：{JSON.stringify(vdbg.providers)}</div>
                            {#if vdbg.errors.length > 0}
                              <div class="debug-line">错误：{vdbg.errors.join(' | ')}</div>
                            {/if}
                            <div class="debug-line">耗时：{vdbg.elapsed_ms.toFixed(2)}ms</div>
                          </details>
                        {/if}
                      </div>
                    {/if}
                  </div>
                  <div class="citation-actions">
                    <button class="btn-copy" onclick={() => copyCiteKey(cite.id)}>复制</button>
                    <button class="btn-delete" onclick={() => deleteCitation(cite.id)}>删除</button>
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
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.01);
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

  .resolve-row {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 10px;
    margin-bottom: 10px;
  }

  .resolve-input {
    padding: 9px 12px;
    border: 1px solid rgba(90, 70, 45, 0.2);
    border-radius: 8px;
    font-size: 14px;
    background: rgba(255, 255, 255, 0.8);
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
  .btn-resolve,
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

  .btn-resolve {
    width: 152px;
    white-space: nowrap;
  }

  .btn-resolve[disabled],
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
    background: rgba(217, 119, 6, 0.16);
    border-color: rgba(217, 119, 6, 0.35);
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
    background: rgba(217, 119, 6, 0.14);
    border-color: rgba(217, 119, 6, 0.32);
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
    background: rgba(217, 119, 6, 0.16);
    border: 1px solid rgba(217, 119, 6, 0.35);
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
