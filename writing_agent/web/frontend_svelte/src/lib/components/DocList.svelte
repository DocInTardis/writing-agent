<script lang="ts">
  import { onMount } from 'svelte'
  import { pushToast } from '../stores'

  export let visible = false
  export let onSelect: (docId: string) => void = () => {}

  interface Doc {
    doc_id: string
    title: string
    text: string
    updated_at: string
    char_count: number
  }

  let docs: Doc[] = []
  let loading = false

  async function loadDocs() {
    loading = true
    try {
      const resp = await fetch('/api/docs/list')
      if (!resp.ok) throw new Error('加载失败')
      const data = await resp.json()
      docs = data.docs || []
    } catch (e) {
      pushToast('加载文档列表失败', 'error')
    } finally {
      loading = false
    }
  }

  function formatDate(ts: string) {
    try {
      return new Date(ts).toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
      })
    } catch {
      return ts
    }
  }

  function truncate(text: string, len: number) {
    return (text || '').length > len ? text.slice(0, len) + '...' : text
  }

  async function deleteDoc(docId: string) {
    if (!confirm('确定删除此文档？')) return
    try {
      await fetch(`/api/doc/${docId}/delete`, { method: 'POST' })
      pushToast('已删除', 'ok')
      await loadDocs()
    } catch {
      pushToast('删除失败', 'error')
    }
  }

  onMount(() => {
    if (visible) loadDocs()
  })

  $: if (visible) loadDocs()
</script>

{#if visible}
  <div
    class="modal-backdrop"
    role="button"
    tabindex="0"
    aria-label="关闭文档列表"
    on:click={() => (visible = false)}
    on:keydown={(e) => {
      if (e.key === 'Enter' || e.key === ' ' || e.key === 'Escape') {
        e.preventDefault()
        visible = false
      }
    }}
  >
    <div class="modal-panel" role="dialog" aria-modal="true" tabindex="-1" on:click|stopPropagation on:keydown|stopPropagation>
      <div class="modal-header">
        <h2>文档列表</h2>
        <button class="close-btn" on:click={() => (visible = false)}>✕</button>
      </div>
      <div class="modal-body">
        {#if loading}
          <div class="loading">加载中...</div>
        {:else if docs.length === 0}
          <div class="empty">暂无文档</div>
        {:else}
          <div class="doc-list">
            {#each docs as doc}
              <div class="doc-item">
                <button class="doc-info" type="button" on:click={() => onSelect(doc.doc_id)}>
                  <div class="doc-title">{doc.title || '自动生成文档'}</div>
                  <div class="doc-meta">
                    <span>{formatDate(doc.updated_at)}</span>
                    <span>{doc.char_count || 0} 字</span>
                  </div>
                  <div class="doc-preview">{truncate(doc.text, 80)}</div>
                </button>
                <button class="delete-btn" on:click={() => deleteDoc(doc.doc_id)}>删除</button>
              </div>
            {/each}
          </div>
        {/if}
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.5);
    display: grid;
    place-items: center;
    z-index: 1000;
    backdrop-filter: blur(4px);
  }

  .modal-panel {
    background: #fffdf8;
    border-radius: 20px;
    width: 90%;
    max-width: 720px;
    max-height: 80vh;
    display: flex;
    flex-direction: column;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 20px 24px;
    border-bottom: 1px solid rgba(90, 70, 45, 0.15);
  }

  .modal-header h2 {
    margin: 0;
    font-size: 18px;
    font-weight: 700;
    color: #2b2416;
  }

  .close-btn {
    border: none;
    background: rgba(200, 180, 150, 0.2);
    color: #5b4a33;
    width: 32px;
    height: 32px;
    border-radius: 50%;
    cursor: pointer;
    font-size: 18px;
    transition: background 0.2s;
  }

  .close-btn:hover {
    background: rgba(200, 180, 150, 0.35);
  }

  .modal-body {
    padding: 16px;
    overflow-y: auto;
  }

  .loading,
  .empty {
    text-align: center;
    padding: 40px;
    color: #8b7d65;
  }

  .doc-list {
    display: grid;
    gap: 12px;
  }

  .doc-item {
    display: flex;
    gap: 12px;
    padding: 16px;
    background: rgba(255, 255, 255, 0.7);
    border: 1px solid rgba(90, 70, 45, 0.12);
    border-radius: 14px;
    transition: border-color 0.2s, box-shadow 0.2s;
  }

  .doc-item:hover {
    border-color: rgba(140, 100, 50, 0.3);
    box-shadow: 0 4px 12px rgba(70, 50, 20, 0.1);
  }

  .doc-info {
    flex: 1;
    cursor: pointer;
    border: none;
    background: transparent;
    text-align: left;
    padding: 0;
    font: inherit;
  }

  .doc-title {
    font-size: 15px;
    font-weight: 600;
    margin-bottom: 6px;
    color: #2b2416;
  }

  .doc-meta {
    display: flex;
    gap: 12px;
    font-size: 12px;
    color: #8b7d65;
    margin-bottom: 8px;
  }

  .doc-preview {
    font-size: 13px;
    color: #6b5d45;
    line-height: 1.5;
  }

  .delete-btn {
    border: 1px solid rgba(200, 100, 80, 0.3);
    background: rgba(255, 220, 210, 0.5);
    color: #a04030;
    padding: 6px 12px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 12px;
    transition: background 0.2s;
    align-self: flex-start;
  }

  .delete-btn:hover {
    background: rgba(255, 200, 190, 0.7);
  }
</style>
