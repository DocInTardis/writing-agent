<script lang="ts">
  import Modal from './Modal.svelte'
  import { pushToast } from '../stores'

  let open = false
  let presets: Record<string, any> = {}
  let config: any = { active_provider_id: '', providers: [] }
  let editing: any = null
  let testing = false
  let loading = false
  let loadError = ''

  async function load() {
    loading = true
    loadError = ''
    try {
      const [presetsResp, configResp] = await Promise.all([
        fetch('/api/llm/presets'),
        fetch('/api/llm/config')
      ])
      if (!presetsResp.ok || !configResp.ok) throw new Error('无法读取模型配置')
      const [presetData, configData] = await Promise.all([presetsResp.json(), configResp.json()])
      presets = presetData.presets || {}
      config = configData.config || { active_provider_id: '', providers: [] }
    } catch (error) {
      loadError = error instanceof Error ? error.message : '无法读取模型配置'
    } finally {
      loading = false
    }
  }

  function startEdit(provider?: any) {
    if (provider) {
      editing = {
        provider_id: provider.provider_id,
        api_key: '',
        base_url: provider.base_url || '',
        model: provider.model || '',
        timeout_s: provider.timeout_s || 120,
        label: provider.label || '',
        enabled: provider.enabled !== false,
        _existing: true
      }
    } else {
      editing = {
        provider_id: '',
        api_key: '',
        base_url: '',
        model: '',
        timeout_s: 120,
        label: '',
        enabled: true,
        _existing: false
      }
    }
  }

  function cancelEdit() {
    editing = null
  }

  async function saveEdit() {
    if (!editing.provider_id) {
      pushToast('请选择提供商', 'bad')
      return
    }
    const payload = { ...editing }
    delete payload._existing
    const resp = await fetch('/api/llm/config/provider', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}))
      pushToast(err.detail || '保存失败', 'bad')
      return
    }
    const d = await resp.json()
    config = d.config
    editing = null
    pushToast('模型配置已保存', 'ok')
  }

  async function removeProvider(providerId: string) {
    if (!confirm('确定删除此模型配置？')) return
    const resp = await fetch('/api/llm/config/provider/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider_id: providerId })
    })
    if (resp.ok) {
      const d = await resp.json()
      config = d.config
      pushToast('已删除', 'ok')
    }
  }

  async function setActive(providerId: string) {
    const resp = await fetch('/api/llm/config/active', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider_id: providerId })
    })
    if (resp.ok) {
      const d = await resp.json()
      config = d.config
      pushToast('已切换模型', 'ok')
    } else {
      pushToast('切换失败，请检查该配置是否可用', 'bad')
    }
  }

  async function testConnection() {
    if (!editing) return
    testing = true
    const payload = { ...editing }
    delete payload._existing
    try {
      const resp = await fetch('/api/llm/config/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      const d = await resp.json().catch(() => ({}))
      if (resp.ok && d.ok) {
        pushToast('连接成功', 'ok')
      } else {
        pushToast('连接失败: ' + (d.error || d.detail || `HTTP ${resp.status}`), 'bad')
      }
    } catch (error) {
      pushToast(`连接失败: ${error instanceof Error ? error.message : '网络错误'}`, 'bad')
    } finally {
      testing = false
    }
  }

  function activeLabel() {
    const active = config.providers.find((p: any) => p.provider_id === config.active_provider_id)
    return active?.label || active?.provider_id || '配置模型'
  }

  function presetModels(pid: string) {
    return presets[pid]?.models || []
  }

  function presetBaseUrl(pid: string) {
    return presets[pid]?.base_url || ''
  }

  function handlePresetChange() {
    if (!editing) return
    const pid = editing.provider_id
    const preset = presets[pid]
    if (preset) {
      if (!editing.base_url) editing.base_url = preset.base_url || ''
      if (!editing.model) editing.model = preset.default_model || ''
      if (!editing.label) editing.label = preset.name || pid
    }
  }

  function handleOpen() {
    open = true
    load().catch(() => {})
  }
</script>

<button class="btn ghost icon-btn-text" onclick={handleOpen} title={`模型配置：${activeLabel()}`}>
  <span>模型</span>
</button>

<Modal {open} title="AI 模型配置" onClose={() => { open = false; editing = null; }}>
  {#if !editing}
    {#if loading}<div class="llm-empty">正在读取配置…</div>{/if}
    {#if loadError}<div class="llm-error">{loadError}<button class="btn small ghost" onclick={load}>重试</button></div>{/if}
    <div class="llm-list">
      {#each config.providers as p}
        <div class="llm-item" class:active={p.provider_id === config.active_provider_id}>
          <div class="llm-info">
            <strong>{p.label || p.provider_id}</strong>
            <span class="llm-meta">{p.model || '—'} · {p.base_url || '—'}</span>
          </div>
          <div class="llm-actions">
            {#if p.provider_id === config.active_provider_id}
              <span class="badge active">使用中</span>
            {:else}
              <button class="btn small" onclick={() => setActive(p.provider_id)}>切换</button>
            {/if}
            <button class="btn small ghost" onclick={() => startEdit(p)}>编辑</button>
            <button class="btn small danger" onclick={() => removeProvider(p.provider_id)}>删除</button>
          </div>
        </div>
      {/each}
      {#if config.providers.length === 0}
        <div class="llm-empty">尚未配置模型。编辑功能不受影响；需要 AI 时再添加自己的 API。</div>
      {/if}
    </div>
    <div class="llm-footer">
      <button class="btn primary" onclick={() => startEdit()}>+ 添加模型</button>
    </div>
  {:else}
    <div class="llm-form">
      <label>
        提供商
        <select bind:value={editing.provider_id} onchange={handlePresetChange}>
          <option value="">请选择</option>
          {#each Object.entries(presets) as [key, preset]}
            <option value={key}>{preset.name}</option>
          {/each}
        </select>
      </label>

      <label>
        API Key
        <input type="password" bind:value={editing.api_key} placeholder="sk-..." />
        {#if editing._existing}
          <small>留空则保留已保存的密钥</small>
        {/if}
        <small>密钥仅保存在本机当前用户的加密存储中。</small>
      </label>

      <label>
        Base URL
        <input type="text" bind:value={editing.base_url} placeholder="https://api.example.com/v1" />
      </label>

      <label>
        模型
        {#if presetModels(editing.provider_id).length > 0}
          <select bind:value={editing.model}>
            <option value="">请选择</option>
            {#each presetModels(editing.provider_id) as m}
              <option value={m}>{m}</option>
            {/each}
          </select>
        {:else}
          <input type="text" bind:value={editing.model} placeholder="例如 gpt-4o" />
        {/if}
      </label>

      <label>
        超时 (秒)
        <input type="number" bind:value={editing.timeout_s} min="10" max="600" />
      </label>

      <label>
        显示名称
        <input type="text" bind:value={editing.label} placeholder="自定义名称" />
      </label>

      <label class="inline">
        <input type="checkbox" bind:checked={editing.enabled} />
        启用
      </label>
    </div>
    <div class="llm-footer">
      <button class="btn primary" onclick={saveEdit}>保存</button>
      <button class="btn ghost" onclick={testConnection} disabled={testing}>
        {testing ? '测试中...' : '测试连接'}
      </button>
      <button class="btn ghost" onclick={cancelEdit}>取消</button>
    </div>
  {/if}
</Modal>

<style>
  .llm-list {
    display: grid;
    gap: 8px;
    max-height: 360px;
    overflow-y: auto;
    padding-right: 4px;
  }
  .llm-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 12px;
    border: 1px solid var(--wa-border);
    border-radius: var(--wa-radius);
    background: var(--wa-surface);
  }
  .llm-item.active {
    border-color: #82ba9c;
    background: var(--wa-success-soft);
  }
  .llm-info {
    display: grid;
    gap: 2px;
  }
  .llm-meta {
    font-size: 11px;
    color: var(--wa-text-muted);
  }
  .llm-actions {
    display: flex;
    gap: 6px;
    align-items: center;
  }
  .badge.active {
    background: var(--wa-success);
    color: #fff;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 11px;
  }
  .llm-empty {
    text-align: center;
    color: var(--wa-text-muted);
    font-size: 13px;
    padding: 20px;
  }
  .llm-error {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
    margin-bottom: 10px;
    padding: 10px 12px;
    border-radius: var(--wa-radius);
    color: var(--wa-danger);
    background: var(--wa-danger-soft);
  }
  .llm-footer {
    display: flex;
    gap: 10px;
    justify-content: flex-end;
    margin-top: 12px;
    padding-top: 10px;
    border-top: 1px solid var(--wa-border);
  }
  .llm-form {
    display: grid;
    gap: 10px;
    max-height: 420px;
    overflow-y: auto;
    padding-right: 4px;
  }
  .llm-form label {
    display: grid;
    gap: 4px;
    font-size: 13px;
  }
  .llm-form label.inline {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .llm-form input,
  .llm-form select {
    padding: 6px 8px;
    border: 1px solid var(--wa-border-strong);
    border-radius: var(--wa-radius);
    background: var(--wa-surface);
    color: var(--wa-text);
    font-size: 13px;
  }
  .llm-form small {
    color: var(--wa-text-muted);
    font-size: 11px;
  }
  .btn.small {
    padding: 4px 10px;
    font-size: 12px;
    border-radius: 6px;
  }
  .btn.danger {
    color: var(--wa-danger);
    border-color: #efc3c3;
  }
</style>
