<script lang="ts">
  import Modal from './Modal.svelte'
  import { docId, pushToast } from '../stores'

  let open = false
  let expandOutline = false
  let targetChars: number | '' = ''
  let styleTone = ''
  let citationsRequired = false
  let outputFormat = 'markdown'
  let formattingJson = ''
  let prefsJson = ''

  async function loadSettings() {
    const id = $docId
    if (!id) return
    const resp = await fetch(`/api/doc/${id}`)
    if (!resp.ok) return
    const data = await resp.json()
    const prefs = data.generation_prefs || {}
    const formatting = data.formatting || {}
    expandOutline = Boolean(prefs.expand_outline)
    targetChars = prefs.target_chars ? Number(prefs.target_chars) : ''
    styleTone = String(formatting.style || '')
    citationsRequired = Boolean(prefs.citations_required)
    outputFormat = String(prefs.output_format || 'markdown')
    formattingJson = JSON.stringify(formatting, null, 2)
    prefsJson = JSON.stringify(prefs, null, 2)
  }

  async function saveSettings() {
    const id = $docId
    if (!id) return
    let formatting = {}
    let generation = {}
    try {
      formatting = formattingJson.trim() ? JSON.parse(formattingJson) : {}
      generation = prefsJson.trim() ? JSON.parse(prefsJson) : {}
    } catch {
      pushToast('高级设置 JSON 解析失败，请检查格式。', 'bad')
      return
    }

    const payload: any = {
      generation_prefs: {
        ...generation,
        expand_outline: expandOutline,
        citations_required: citationsRequired,
        output_format: outputFormat
      },
      formatting: {
        ...formatting,
        style: styleTone
      }
    }
    if (targetChars) payload.generation_prefs.target_chars = Number(targetChars)

    await fetch(`/api/doc/${id}/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    pushToast('设置已保存', 'ok')
    open = false
  }

  function handleOpen() {
    open = true
    loadSettings().catch(() => {})
  }
</script>

<button class="btn ghost" onclick={handleOpen}>设置</button>

<Modal {open} title="生成设置" onClose={() => (open = false)}>
  <div class="settings-row">
    <label>
      <input type="checkbox" bind:checked={expandOutline} />
      扩展大纲
    </label>
  </div>
  <div class="settings-row">
    <label>
      <input type="checkbox" bind:checked={citationsRequired} />
      需要引用
    </label>
  </div>
  <div class="settings-row">
    <label for="targetChars">目标字数</label>
    <input id="targetChars" type="number" min="100" max="10000" bind:value={targetChars} placeholder="例如 1000" />
  </div>
  <div class="settings-row">
    <label for="styleTone">风格/语气</label>
    <input id="styleTone" type="text" bind:value={styleTone} placeholder="例如：正式、简洁、适度营销" />
  </div>
  <div class="settings-row">
    <label for="outputFormat">输出格式</label>
    <select id="outputFormat" bind:value={outputFormat}>
      <option value="markdown">Markdown 文档</option>
      <option value="plain">纯文本</option>
    </select>
  </div>

  <div class="settings-section">
    <div class="section-title">高级设置（可改所有默认值）</div>
    <label for="formattingJson">格式配置（formatting）</label>
    <textarea id="formattingJson" rows="6" bind:value={formattingJson}></textarea>
    <label for="prefsJson">生成偏好（generation_prefs）</label>
    <textarea id="prefsJson" rows="6" bind:value={prefsJson}></textarea>
  </div>

  <details class="shortcut-settings">
    <summary>编辑快捷键</summary>
    <dl>
      <dt>Ctrl / ⌘ + Alt + 0</dt><dd>正文</dd>
      <dt>Ctrl / ⌘ + Alt + 1–3</dt><dd>标题 1–3</dd>
      <dt>Alt + Shift + ↑ / ↓</dt><dd>移动段落或所选块</dd>
      <dt>Ctrl / ⌘ + Shift + Space</dt><dd>选择当前块</dd>
      <dt>↑ / ↓（块选择）</dt><dd>选择相邻块</dd>
      <dt>Esc / Enter（块选择）</dt><dd>回到文字编辑</dd>
    </dl>
    <p>输入法组合输入期间不会接管这些按键。</p>
  </details>

  <div class="settings-actions">
    <button class="btn primary" onclick={saveSettings}>保存</button>
    <button class="btn ghost" onclick={() => (open = false)}>取消</button>
  </div>
</Modal>

<style>
  .settings-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 12px;
    font-size: 13px;
  }

  .settings-row input[type='number'] {
    width: 120px;
    padding: 6px 8px;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
  }

  .settings-row input[type='text'],
  .settings-row select {
    width: 220px;
    padding: 6px 8px;
    border: 1px solid rgba(90, 70, 45, 0.18);
    border-radius: 10px;
    background: rgba(255, 255, 255, 0.9);
  }

  .settings-section {
    margin-top: 16px;
    display: grid;
    gap: 8px;
    font-size: 12px;
  }

  .settings-section textarea {
    width: 100%;
    border: 1px solid rgba(90, 70, 45, 0.18);
    border-radius: 10px;
    padding: 8px 10px;
    background: rgba(255, 255, 255, 0.85);
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace;
    font-size: 12px;
  }

  .section-title {
    font-weight: 600;
    color: #5b4a33;
  }

  .settings-actions {
    display: flex;
    gap: 10px;
    justify-content: flex-end;
    margin-top: 12px;
  }
  .shortcut-settings { margin-top: 14px; color: #4f5d70; font-size: 12px; }
  .shortcut-settings summary { cursor: pointer; font-weight: 600; }
  .shortcut-settings dl { display: grid; grid-template-columns: 1.6fr 1fr; gap: 6px 10px; margin: 10px 0; }
  .shortcut-settings dt { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
  .shortcut-settings dd { margin: 0; }
  .shortcut-settings p { margin: 0; color: #7a8594; }
</style>
