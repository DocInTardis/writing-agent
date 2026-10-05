<script lang="ts">
  import Modal from './Modal.svelte'
  import { docId, pushToast } from '../stores'

  let open = $state(false)
  let loading = $state(false)
  let saving = $state(false)
  let purpose = $state('')
  let audience = $state('')
  let voice = $state('')
  let targetMode = $state<'chars' | 'pages'>('chars')
  let targetValue: number | '' = $state('')
  let expandOutline = $state(false)
  let citationsRequired = $state(false)
  let minReferenceCount = $state(0)
  let includeToc = $state(true)
  let extraRequirements = $state('')
  let loadedFormatting = $state<Record<string, unknown>>({})
  let loadedPrefs = $state<Record<string, unknown>>({})

  async function loadSettings() {
    const id = $docId
    if (!id) return
    loading = true
    try {
      const resp = await fetch(`/api/doc/${id}`)
      if (!resp.ok) throw new Error(await resp.text() || '设置读取失败')
      const data = await resp.json()
      loadedFormatting = { ...(data.formatting || {}) }
      loadedPrefs = { ...(data.generation_prefs || {}) }
      purpose = String(loadedPrefs.purpose || '')
      audience = String(loadedPrefs.audience || '')
      voice = String(loadedPrefs.voice || loadedFormatting.style || '')
      targetMode = loadedPrefs.target_length_mode === 'pages' ? 'pages' : 'chars'
      const value = Number(loadedPrefs.target_length_value || loadedPrefs.target_char_count || 0)
      targetValue = value > 0 ? value : ''
      expandOutline = Boolean(loadedPrefs.expand_outline)
      citationsRequired = Boolean(loadedPrefs.citations_required)
      minReferenceCount = Math.max(0, Number(loadedPrefs.min_reference_count || 0))
      includeToc = loadedPrefs.include_toc !== false
      extraRequirements = String(loadedPrefs.extra_requirements || '')
    } catch (error) {
      pushToast(error instanceof Error ? error.message : '设置读取失败', 'bad')
    } finally {
      loading = false
    }
  }

  async function saveSettings() {
    const id = $docId
    if (!id || saving) return
    const numericTarget = Number(targetValue || 0)
    if (numericTarget < 0 || (targetMode === 'pages' && numericTarget > 1000) || (targetMode === 'chars' && numericTarget > 1_000_000)) {
      pushToast('目标篇幅超出合理范围。', 'bad')
      return
    }
    saving = true
    try {
      const generationPrefs: Record<string, unknown> = {
        ...loadedPrefs,
        purpose: purpose.trim(),
        audience: audience.trim(),
        voice: voice.trim(),
        target_length_mode: numericTarget > 0 ? targetMode : '',
        target_length_value: numericTarget,
        target_char_count: targetMode === 'chars' ? numericTarget : 0,
        target_page_count: targetMode === 'pages' ? numericTarget : 0,
        target_length_confirmed: numericTarget > 0,
        expand_outline: expandOutline,
        citations_required: citationsRequired,
        min_reference_count: Math.max(0, Math.round(minReferenceCount)),
        include_toc: includeToc,
        extra_requirements: extraRequirements.trim()
      }
      const resp = await fetch(`/api/doc/${id}/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ generation_prefs: generationPrefs, formatting: loadedFormatting })
      })
      if (!resp.ok) throw new Error(await resp.text() || '设置保存失败')
      loadedPrefs = generationPrefs
      pushToast('写作偏好已保存。', 'ok')
      open = false
    } catch (error) {
      pushToast(error instanceof Error ? error.message : '设置保存失败', 'bad')
    } finally {
      saving = false
    }
  }

  function handleOpen() {
    open = true
    void loadSettings()
  }
</script>

<button class="btn ghost" onclick={handleOpen}>偏好</button>

<Modal {open} title="写作偏好" onClose={() => (open = false)}>
  {#if loading}
    <div class="loading">正在读取设置…</div>
  {:else}
    <div class="settings-grid">
      <label><span>文档用途</span><input bind:value={purpose} placeholder="例如：毕业论文、项目报告" /></label>
      <label><span>目标读者</span><input bind:value={audience} placeholder="例如：评审教师、普通读者" /></label>
      <label><span>语言风格</span><input bind:value={voice} placeholder="例如：正式、简洁、客观" /></label>
      <div class="target-row">
        <label><span>目标篇幅</span><input type="number" min="0" bind:value={targetValue} placeholder="不限制" /></label>
        <label class="unit"><span>单位</span><select bind:value={targetMode}><option value="chars">字</option><option value="pages">页</option></select></label>
      </div>
      <label class="check"><input type="checkbox" bind:checked={expandOutline} /><span>生成时扩展已有大纲</span></label>
      <label class="check"><input type="checkbox" bind:checked={includeToc} /><span>长文包含目录</span></label>
      <div class="citation-row">
        <label class="check"><input type="checkbox" bind:checked={citationsRequired} /><span>要求引用资料来源</span></label>
        {#if citationsRequired}<label class="count"><span>最少</span><input type="number" min="0" max="200" bind:value={minReferenceCount} /><span>条</span></label>{/if}
      </div>
      <label><span>其他要求</span><textarea rows="3" bind:value={extraRequirements} placeholder="只填写长期适用于本文档的要求"></textarea></label>
    </div>

    <details class="shortcut-settings">
      <summary>编辑快捷键</summary>
      <dl>
        <dt>Ctrl / ⌘ + Alt + 0–3</dt><dd>正文或标题 1–3</dd>
        <dt>Alt + Shift + ↑ / ↓</dt><dd>移动当前块</dd>
        <dt>Ctrl / ⌘ + Shift + Space</dt><dd>选择当前块</dd>
        <dt>Esc / Enter</dt><dd>退出块选择</dd>
      </dl>
      <p>输入法组合输入期间不会接管这些快捷键。</p>
    </details>

    <div class="settings-actions">
      <button class="btn ghost" onclick={() => (open = false)}>取消</button>
      <button class="btn primary" disabled={saving} onclick={saveSettings}>{saving ? '保存中…' : '保存'}</button>
    </div>
  {/if}
</Modal>

<style>
  .loading { padding: 30px; color: var(--wa-text-muted); text-align: center; }
  .settings-grid { display: grid; gap: 13px; }
  .settings-grid > label, .target-row label { display: grid; gap: 5px; color: var(--wa-text-secondary); font-size: 12px; }
  .settings-grid input, .settings-grid select, .settings-grid textarea { width: 100%; min-height: 34px; padding: 7px 9px; border: 1px solid var(--wa-border-strong); border-radius: var(--wa-radius); background: var(--wa-surface); color: var(--wa-text); outline: none; }
  .settings-grid input:focus, .settings-grid select:focus, .settings-grid textarea:focus { border-color: var(--wa-accent); }
  .target-row { display: grid; grid-template-columns: 1fr 100px; gap: 10px; }
  .check { display: flex !important; align-items: center; gap: 8px !important; }
  .check input { width: 15px; min-height: 15px; }
  .citation-row { display: flex; min-height: 34px; align-items: center; justify-content: space-between; }
  .count { display: flex; align-items: center; gap: 5px; color: var(--wa-text-muted); font-size: 12px; }
  .count input { width: 64px; }
  .shortcut-settings { margin-top: 16px; padding: 10px; border: 1px solid var(--wa-border); border-radius: var(--wa-radius); background: var(--wa-surface-subtle); color: var(--wa-text-secondary); font-size: 12px; }
  .shortcut-settings summary { cursor: pointer; }
  .shortcut-settings dl { display: grid; grid-template-columns: 1.4fr 1fr; gap: 6px 12px; }
  .shortcut-settings dt { font-family: ui-monospace, Consolas, monospace; }
  .shortcut-settings dd { margin: 0; }
  .settings-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 18px; }
</style>
