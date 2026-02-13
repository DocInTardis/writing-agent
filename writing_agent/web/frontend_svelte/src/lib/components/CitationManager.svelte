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

  let citations: Citation[] = []
  let loading = false
  let lastLoadedId = ''
  let saveTimer: ReturnType<typeof setTimeout> | null = null
  let newCitation: Citation = {
    id: '',
    author: '',
    title: '',
    year: '',
    source: ''
  }

  async function loadCitations() {
    const id = $docId
    if (!id) return
    loading = true
    try {
      const resp = await fetch(`/api/doc/${id}/citations`)
      if (!resp.ok) throw new Error(await resp.text())
      const data = await resp.json()
      citations = Array.isArray(data.items) ? data.items : []
    } catch (e) {
      console.error('Failed to load citations:', e)
      pushToast('加载引用失败', 'error')
    } finally {
      loading = false
    }
  }

  async function saveCitations() {
    const id = $docId
    if (!id) return
    await fetch(`/api/doc/${id}/citations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ items: citations })
    })
  }

  function queueSave() {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveCitations().catch(() => {
        pushToast('保存引用失败', 'error')
      })
    }, 300)
  }

  function addCitation() {
    if (!newCitation.id || !newCitation.author || !newCitation.title) {
      pushToast('请填写必填字段（ID、作者、标题）', 'bad')
      return
    }
    if (citations.some(c => c.id === newCitation.id)) {
      pushToast('引用ID已存在', 'bad')
      return
    }
    citations = [...citations, { ...newCitation }]
    queueSave()
    newCitation = { id: '', author: '', title: '', year: '', source: '' }
    pushToast('已添加引用', 'ok')
  }

  function deleteCitation(id: string) {
    citations = citations.filter(c => c.id !== id)
    queueSave()
    pushToast('已删除引用', 'ok')
  }

  function copyCiteKey(id: string) {
    navigator.clipboard.writeText(`[@${id}]`)
    pushToast('已复制引用标记', 'ok')
  }

  function formatCitation(cite: Citation, style: 'apa' | 'mla' | 'gb'): string {
    if (style === 'apa') {
      return `${cite.author} (${cite.year}). ${cite.title}. ${cite.source}.`
    } else if (style === 'mla') {
      return `${cite.author}. "${cite.title}." ${cite.source}, ${cite.year}.`
    } else { // GB/T 7714
      return `${cite.author}. ${cite.title}[J]. ${cite.source}, ${cite.year}.`
    }
  }

  function exportBibliography(style: 'apa' | 'mla' | 'gb') {
    const bib = citations.map(c => formatCitation(c, style)).join('\n\n')
    const blob = new Blob([bib], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `references_${style}.txt`
    a.click()
    URL.revokeObjectURL(url)
    pushToast(`已导出 ${style.toUpperCase()} 格式参考文献`, 'ok')
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
  <div class="modal-backdrop" on:click={() => (visible = false)}>
    <div class="modal" on:click|stopPropagation>
      <div class="modal-header">
        <h2>引用管理</h2>
        <button class="close-btn" on:click={() => (visible = false)}>×</button>
      </div>
      
      <div class="modal-body">
        <div class="add-section">
          <h3>添加引用</h3>
          <div class="form-grid">
            <input type="text" placeholder="引用ID (如: smith2023)*" bind:value={newCitation.id} />
            <input type="text" placeholder="作者*" bind:value={newCitation.author} />
            <input type="text" placeholder="标题*" bind:value={newCitation.title} />
            <input type="text" placeholder="年份" bind:value={newCitation.year} />
            <input type="text" placeholder="来源（期刊/会议/出版社）" bind:value={newCitation.source} class="full-width" />
          </div>
          <button class="btn-add" on:click={addCitation}>添加引用</button>
        </div>

        <div class="export-section">
          <h3>导出参考文献</h3>
          <div class="export-btns">
            <button class="btn-export" on:click={() => exportBibliography('apa')}>APA格式</button>
            <button class="btn-export" on:click={() => exportBibliography('mla')}>MLA格式</button>
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
                <div class="citation-item">
                  <div class="citation-info">
                    <strong>[@{cite.id}]</strong>
                    <span>{cite.author} ({cite.year}). {cite.title}</span>
                    {#if cite.source}
                      <span class="source">{cite.source}</span>
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
    animation: fadeIn 0.2s ease;
  }

  @keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
  }

  .modal {
    background: #fffdf8;
    border-radius: 16px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
    max-width: 800px;
    width: 90%;
    max-height: 80vh;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    animation: slideUp 0.3s ease;
  }

  @keyframes slideUp {
    from { transform: translateY(20px); opacity: 0; }
    to { transform: translateY(0); opacity: 1; }
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 20px 24px;
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
    font-size: 32px;
    color: #6b5d45;
    cursor: pointer;
    line-height: 1;
    transition: color 0.2s;
  }

  .close-btn:hover {
    color: #2b2416;
  }

  .modal-body {
    padding: 24px;
    overflow-y: auto;
  }

  .add-section, .export-section, .list-section {
    margin-bottom: 32px;
  }

  h3 {
    margin: 0 0 12px;
    color: #2b2416;
    font-size: 16px;
  }

  .form-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    margin-bottom: 12px;
  }

  .form-grid input {
    padding: 10px 14px;
    border: 1px solid rgba(90, 70, 45, 0.2);
    border-radius: 8px;
    font-size: 14px;
    background: rgba(255, 255, 255, 0.8);
  }

  .form-grid input.full-width {
    grid-column: 1 / -1;
  }

  .btn-add {
    width: 100%;
    padding: 10px;
    background: linear-gradient(135deg, #a5722a 0%, #8b7355 100%);
    color: #fff;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
    transition: transform 0.2s;
  }

  .btn-add:hover {
    transform: translateY(-1px);
  }

  .export-btns {
    display: flex;
    gap: 12px;
  }

  .btn-export {
    flex: 1;
    padding: 10px;
    background: rgba(165, 114, 42, 0.1);
    color: #8b7355;
    border: 1px solid rgba(165, 114, 42, 0.3);
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
    transition: background 0.2s;
  }

  .btn-export:hover {
    background: rgba(165, 114, 42, 0.2);
  }

  .citation-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .citation-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    background: rgba(255, 255, 255, 0.6);
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
  }

  .citation-info .source {
    font-style: italic;
    color: #8b7355;
  }

  .citation-actions {
    display: flex;
    gap: 8px;
  }

  .btn-copy, .btn-delete {
    padding: 6px 12px;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    font-size: 12px;
    transition: transform 0.15s;
  }

  .btn-copy {
    background: rgba(42, 165, 114, 0.1);
    color: #2aa572;
  }

  .btn-copy:hover {
    transform: scale(1.05);
    background: rgba(42, 165, 114, 0.2);
  }

  .btn-delete {
    background: rgba(211, 47, 47, 0.1);
    color: #d32f2f;
  }

  .btn-delete:hover {
    transform: scale(1.05);
    background: rgba(211, 47, 47, 0.2);
  }

  .empty {
    text-align: center;
    color: #8b7355;
    padding: 40px 20px;
    font-size: 14px;
  }
</style>
