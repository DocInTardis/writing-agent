<script lang="ts">
  import { docId, pushToast } from '../stores'
  import type { Citation, VerifyItem, VerifySummary } from '../citations/citationTypes'
  import { formatCitation, normalizeItems, normalizeResolveItem, statusClass, statusLabel } from '../citations/citationUtils'

  let { visible = $bindable(false) }: { visible?: boolean } = $props()
  let citations = $state<Citation[]>([])
  let loading = $state(false)
  let saving = $state(false)
  let verifying = $state(false)
  let resolving = $state(false)
  let lastLoadedId = $state('')
  let verifyMap = $state<Record<string, VerifyItem>>({})
  let verifySummary = $state<VerifySummary | null>(null)
  let resolveUrl = $state('')
  let draft = $state<Citation>({ id: '', author: '', title: '', year: '', source: '' })

  function citationId(citation: Citation) {
    const existing = citation.id.trim()
    if (existing) return existing
    const author = citation.author.toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff]+/g, '').slice(0, 12) || 'ref'
    const year = citation.year.replace(/\D/g, '').slice(0, 4)
    let candidate = `${author}${year}`
    let suffix = 2
    while (citations.some((item) => item.id === candidate)) candidate = `${author}${year}_${suffix++}`
    return candidate
  }

  async function loadCitations() {
    const id = $docId
    if (!id) return
    loading = true
    try {
      const resp = await fetch(`/api/doc/${id}/citations`)
      if (!resp.ok) throw new Error(await resp.text() || '引用读取失败')
      citations = normalizeItems((await resp.json())?.items)
      verifyMap = {}
      verifySummary = null
    } catch (error) {
      pushToast(error instanceof Error ? error.message : '引用读取失败', 'bad')
    } finally {
      loading = false
    }
  }

  async function persist(next: Citation[], successMessage = '') {
    const id = $docId
    if (!id || saving) return false
    saving = true
    try {
      const resp = await fetch(`/api/doc/${id}/citations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items: next })
      })
      if (!resp.ok) throw new Error(await resp.text() || '引用保存失败')
      citations = next
      if (successMessage) pushToast(successMessage, 'ok')
      return true
    } catch (error) {
      pushToast(error instanceof Error ? error.message : '引用保存失败', 'bad')
      return false
    } finally {
      saving = false
    }
  }

  async function resolveFromUrl() {
    const id = $docId
    const url = resolveUrl.trim()
    if (!id || !url || resolving) return
    resolving = true
    try {
      const resp = await fetch(`/api/doc/${id}/citations/resolve-url`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url })
      })
      if (!resp.ok) throw new Error(await resp.text() || '链接识别失败')
      const payload = await resp.json()
      const item = normalizeResolveItem(payload?.item)
      if (!item) throw new Error('没有识别到可用的文献信息')
      draft = { ...item, id: item.id || draft.id }
      const warnings = Array.isArray(payload?.warnings) ? payload.warnings.filter(Boolean) : []
      pushToast(warnings.length ? '已填写可识别字段，请检查后保存。' : '文献信息已识别，请检查后保存。', warnings.length ? 'info' : 'ok')
    } catch (error) {
      pushToast(error instanceof Error ? error.message : '链接识别失败', 'bad')
    } finally {
      resolving = false
    }
  }

  async function addCitation() {
    const author = draft.author.trim()
    const title = draft.title.trim()
    if (!author || !title) {
      pushToast('请填写作者和标题。', 'bad')
      return
    }
    const item = { ...draft, id: citationId(draft), author, title, year: draft.year.trim(), source: draft.source.trim() }
    if (citations.some((citation) => citation.id === item.id)) {
      pushToast('引用标记已存在，请修改标记。', 'bad')
      return
    }
    if (await persist([...citations, item], '引用已添加。')) {
      draft = { id: '', author: '', title: '', year: '', source: '' }
      resolveUrl = ''
    }
  }

  async function removeCitation(id: string) {
    if (!window.confirm('从本文档删除这条引用？')) return
    if (await persist(citations.filter((citation) => citation.id !== id), '引用已删除。')) {
      const next = { ...verifyMap }
      delete next[id]
      verifyMap = next
    }
  }

  async function verifyCitations() {
    const id = $docId
    if (!id || !citations.length || verifying) return
    verifying = true
    try {
      const resp = await fetch(`/api/doc/${id}/citations/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items: citations, persist: true, debug: false })
      })
      if (!resp.ok) throw new Error(await resp.text() || '引用核验失败')
      const payload = await resp.json()
      const map: Record<string, VerifyItem> = {}
      for (const raw of Array.isArray(payload?.items) ? payload.items : []) {
        if (!raw?.id) continue
        map[String(raw.id)] = {
          id: String(raw.id), status: String(raw.status || 'not_found') as VerifyItem['status'],
          provider: String(raw.provider || ''), score: Number(raw.score || 0),
          matched_title: String(raw.matched_title || ''), matched_year: String(raw.matched_year || ''),
          matched_source: String(raw.matched_source || ''), reason: String(raw.reason || '')
        }
      }
      verifyMap = map
      const summary = payload?.summary || {}
      verifySummary = {
        total: Number(summary.total || 0), verified: Number(summary.verified || 0),
        possible: Number(summary.possible || 0), not_found: Number(summary.not_found || 0), error: Number(summary.error || 0)
      }
      const updated = normalizeItems(payload?.updated_items)
      if (updated.length) citations = updated
      pushToast('引用核验完成。未命中不等于虚假，仍需人工检查。', 'ok')
    } catch (error) {
      pushToast(error instanceof Error ? error.message : '引用核验失败', 'bad')
    } finally {
      verifying = false
    }
  }

  async function copyMarker(id: string) {
    try { await navigator.clipboard.writeText(`[@${id}]`); pushToast('引用标记已复制。', 'ok') }
    catch { pushToast('无法访问系统剪贴板。', 'bad') }
  }

  function exportBibliography(style: 'apa' | 'mla' | 'gb') {
    const blob = new Blob([citations.map((item) => formatCitation(item, style)).join('\n\n')], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `references_${style}.txt`
    link.click()
    URL.revokeObjectURL(url)
  }

  $effect(() => {
    if (!visible) return
    const id = $docId
    if (id && id !== lastLoadedId) {
      lastLoadedId = id
      void loadCitations()
    }
  })
</script>

{#if visible}
  <button class="backdrop" aria-label="关闭引用管理" onclick={() => (visible = false)}></button>
  <dialog class="citation-dialog" open aria-label="引用管理">
    <header><div><h2>引用管理</h2><p>保存来源、插入引用标记，并在导出前核验。</p></div><button onclick={() => (visible = false)}>关闭</button></header>
    <div class="citation-body">
      <section class="add-panel">
        <h3>添加来源</h3>
        <div class="url-row"><input bind:value={resolveUrl} placeholder="DOI、arXiv 或论文页面链接" onkeydown={(event) => { if (event.key === 'Enter') { event.preventDefault(); void resolveFromUrl() } }} /><button disabled={!resolveUrl.trim() || resolving} onclick={resolveFromUrl}>{resolving ? '识别中…' : '识别链接'}</button></div>
        <div class="form-grid">
          <label><span>作者 *</span><input bind:value={draft.author} /></label>
          <label><span>年份</span><input bind:value={draft.year} /></label>
          <label class="wide"><span>标题 *</span><input bind:value={draft.title} /></label>
          <label class="wide"><span>期刊、会议或网址</span><input bind:value={draft.source} /></label>
          <label class="wide"><span>引用标记（留空自动生成）</span><input bind:value={draft.id} placeholder="例如 zhang2024" /></label>
        </div>
        <button class="primary" disabled={saving} onclick={addCitation}>保存引用</button>
      </section>

      <section class="list-panel">
        <div class="list-head"><div><h3>本文档引用</h3><p>{citations.length} 条</p></div><button disabled={verifying || !citations.length} onclick={verifyCitations}>{verifying ? '核验中…' : '核验全部'}</button></div>
        {#if verifySummary}<div class="summary">已核验 {verifySummary.verified} · 可能匹配 {verifySummary.possible} · 未命中 {verifySummary.not_found} · 错误 {verifySummary.error}</div>{/if}
        {#if loading}<div class="empty">正在读取…</div>
        {:else if !citations.length}<div class="empty">还没有引用。可粘贴链接自动填写，也可手动添加。</div>
        {:else}<div class="citation-list">
          {#each citations as citation (citation.id)}
            {@const verify = verifyMap[citation.id]}
            <article>
              <div class="citation-main"><strong>{citation.title}</strong><p>{citation.author}{citation.year ? ` · ${citation.year}` : ''}{citation.source ? ` · ${citation.source}` : ''}</p><code>[@{citation.id}]</code>
                {#if verify}<div class={`verify ${statusClass(verify.status)}`}><span>{statusLabel(verify.status)}</span>{#if verify.matched_title}<small>匹配：{verify.matched_title}</small>{:else if verify.reason}<small>{verify.reason}</small>{/if}</div>{/if}
              </div>
              <div class="item-actions"><button onclick={() => copyMarker(citation.id)}>复制标记</button><button class="danger" onclick={() => removeCitation(citation.id)}>删除</button></div>
            </article>
          {/each}
        </div>{/if}
        <footer><span>导出参考文献</span><button onclick={() => exportBibliography('gb')}>GB/T 7714</button><button onclick={() => exportBibliography('apa')}>APA</button><button onclick={() => exportBibliography('mla')}>MLA</button></footer>
      </section>
    </div>
  </dialog>
{/if}

<style>
  .backdrop { position: fixed; z-index: 60; inset: 0; border: 0; background: rgba(20,29,43,.28); }.citation-dialog { position: fixed; z-index: 61; top: 6vh; left: 50%; box-sizing: border-box; width: min(920px, 94vw); max-height: 88vh; overflow: hidden; transform: translateX(-50%); border: 1px solid #dfe3e8; border-radius: 10px; background: #fff; color: #273142; box-shadow: 0 24px 70px rgba(20,29,43,.2); }.citation-dialog > header, .list-head, .url-row, .item-actions, .list-panel footer { display: flex; align-items: center; }.citation-dialog > header { justify-content: space-between; padding: 17px 20px; border-bottom: 1px solid #e6e9ee; }.citation-dialog h2, .citation-dialog h3, .citation-dialog p { margin: 0; }.citation-dialog h2 { font-size: 18px; }.citation-dialog h3 { font-size: 14px; }.citation-dialog header p, .list-head p { margin-top: 4px; color: #7b8491; font-size: 11px; }.citation-dialog button { min-height: 31px; padding: 0 10px; border: 1px solid #d7dce4; border-radius: 6px; background: #fff; color: #465164; cursor: pointer; font: inherit; font-size: 12px; }.citation-dialog button:disabled { opacity: .45; cursor: default; }.citation-dialog button.primary { border-color: #2468c8; background: #2468c8; color: #fff; }.citation-dialog button.danger { border-color: transparent; color: #b42318; }
  .citation-body { display: grid; grid-template-columns: 330px minmax(0,1fr); min-height: 560px; max-height: calc(88vh - 72px); overflow: hidden; }.add-panel, .list-panel { padding: 18px; }.add-panel { border-right: 1px solid #e6e9ee; background: #fafbfc; }.url-row { gap: 7px; margin: 14px 0; }.url-row input { min-width: 0; flex: 1; }.form-grid { display: grid; grid-template-columns: 1fr 90px; gap: 10px; margin-bottom: 14px; }.form-grid label { display: grid; gap: 4px; color: #697386; font-size: 11px; }.form-grid .wide { grid-column: 1 / -1; }.citation-dialog input { box-sizing: border-box; width: 100%; min-height: 33px; padding: 6px 8px; border: 1px solid #d7dce4; border-radius: 6px; background: #fff; outline: none; }.citation-dialog input:focus { border-color: #7ba8df; }
  .list-panel { display: flex; min-width: 0; flex-direction: column; overflow: hidden; }.list-head { justify-content: space-between; }.summary { margin-top: 10px; padding: 7px 9px; border-radius: 6px; background: #eef4fb; color: #41658f; font-size: 11px; }.citation-list { display: grid; gap: 8px; margin-top: 12px; overflow: auto; }.citation-list article { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; padding: 11px; border: 1px solid #e2e6eb; border-radius: 7px; }.citation-main { min-width: 0; }.citation-main strong { display: block; font-size: 13px; }.citation-main p { margin-top: 4px; overflow: hidden; color: #727c8b; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }.citation-main code { display: inline-block; margin-top: 7px; color: #2468c8; font-size: 11px; }.item-actions { flex: none; gap: 4px; }.verify { display: flex; gap: 7px; margin-top: 7px; font-size: 11px; }.verify.ok { color: #177245; }.verify.warn { color: #a15c00; }.verify.err { color: #b42318; }.verify.miss { color: #697386; }.verify small { overflow: hidden; max-width: 260px; text-overflow: ellipsis; white-space: nowrap; }.empty { display: grid; flex: 1; place-items: center; color: #8a93a1; font-size: 12px; text-align: center; }.list-panel footer { gap: 6px; margin-top: 12px; padding-top: 10px; border-top: 1px solid #e6e9ee; }.list-panel footer span { margin-right: auto; color: #7a8493; font-size: 11px; }
  @media (max-width: 760px) { .citation-body { grid-template-columns: 1fr; overflow: auto; }.add-panel { border-right: 0; border-bottom: 1px solid #e6e9ee; }.citation-dialog { top: 3vh; max-height: 94vh; } }
</style>
