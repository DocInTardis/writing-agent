<script lang="ts">
  import { createEventDispatcher } from 'svelte'

  export let open = false
  export let docId = ''
  const dispatch = createEventDispatcher()

  let prompt = ''
  let kind: 'flow' | 'er' | 'sequence' = 'flow'
  let loading = false
  let error = ''
  let svg = ''
  let spec: Record<string, unknown> | null = null

  async function generateDiagram() {
    if (!docId || !prompt.trim()) return
    loading = true
    error = ''
    svg = ''
    spec = null
    try {
      const resp = await fetch(`/api/doc/${docId}/diagram/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, kind })
      })
      if (!resp.ok) throw new Error(await resp.text())
      const data = await resp.json()
      spec = data.spec as Record<string, unknown>
      const render = await fetch('/api/figure/render', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ spec })
      })
      if (!render.ok) throw new Error(await render.text())
      const fig = await render.json()
      svg = String(fig.svg || '')
    } catch (err) {
      error = err instanceof Error ? err.message : '生成失败'
    } finally {
      loading = false
    }
  }

  function handleInsert() {
    if (!spec) return
    dispatch('insert', { spec })
  }
</script>

{#if open}
  <div class="canvas-backdrop" on:click={() => dispatch('close')}>
    <div class="canvas-panel" on:click|stopPropagation>
      <header>
        <div>
          <h3>AI 画布</h3>
          <p>输入描述即可生成流程图 / ER 图 / 时序图</p>
        </div>
        <button class="close-btn" on:click={() => dispatch('close')}>×</button>
      </header>
      <div class="canvas-controls">
        <select bind:value={kind}>
          <option value="flow">流程图</option>
          <option value="er">ER 图</option>
          <option value="sequence">时序图</option>
        </select>
        <textarea
          rows="3"
          bind:value={prompt}
          placeholder="例如：用户登录 -> 权限校验 -> 查询数据 -> 返回结果"
        ></textarea>
        <div class="canvas-actions">
          <button class="btn primary" on:click={generateDiagram} disabled={loading || !prompt.trim()}>
            {loading ? '生成中…' : '生成画布'}
          </button>
          <button class="btn ghost" on:click={handleInsert} disabled={!spec}>插入文档</button>
        </div>
        {#if error}
          <div class="error">{error}</div>
        {/if}
      </div>
      <div class="canvas-preview">
        {#if svg}
          <div class="svg-box">{@html svg}</div>
        {:else}
          <div class="placeholder">画布预览区</div>
        {/if}
      </div>
    </div>
  </div>
{/if}

<style>
  .canvas-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(15, 23, 42, 0.4);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 20;
  }

  .canvas-panel {
    width: min(920px, 92vw);
    max-height: 90vh;
    background: rgba(255, 255, 255, 0.98);
    border-radius: 24px;
    padding: 20px;
    display: grid;
    grid-template-columns: 280px 1fr;
    gap: 18px;
    box-shadow: 0 30px 80px rgba(15, 23, 42, 0.35);
  }

  header {
    grid-column: 1 / -1;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  header h3 {
    margin: 0 0 6px 0;
    font-size: 18px;
  }

  header p {
    margin: 0;
    font-size: 12px;
    color: rgba(51, 65, 85, 0.7);
  }

  .close-btn {
    border: none;
    background: rgba(15, 23, 42, 0.08);
    width: 32px;
    height: 32px;
    border-radius: 10px;
    cursor: pointer;
  }

  .canvas-controls {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  select,
  textarea {
    border: 1px solid rgba(148, 163, 184, 0.35);
    border-radius: 12px;
    padding: 8px 10px;
    font-size: 12px;
    background: #fff;
  }

  .canvas-actions {
    display: flex;
    gap: 8px;
  }

  .btn {
    border: none;
    padding: 8px 12px;
    border-radius: 10px;
    cursor: pointer;
    font-size: 12px;
  }

  .btn.primary {
    background: linear-gradient(135deg, #2563eb, #0ea5e9);
    color: #fff;
  }

  .btn.ghost {
    background: rgba(15, 23, 42, 0.08);
  }

  .canvas-preview {
    border-radius: 18px;
    background: rgba(15, 23, 42, 0.04);
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: auto;
    padding: 16px;
    min-height: 360px;
  }

  .svg-box {
    width: 100%;
  }

  .placeholder {
    color: rgba(51, 65, 85, 0.6);
    font-size: 14px;
  }

  .error {
    color: #ef4444;
    font-size: 12px;
  }

  @media (max-width: 900px) {
    .canvas-panel {
      grid-template-columns: 1fr;
    }
  }
</style>
