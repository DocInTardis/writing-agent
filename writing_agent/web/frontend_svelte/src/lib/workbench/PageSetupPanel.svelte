<script lang="ts">
  import { docId, pageSettings, pushToast, type PageSettings } from '../stores'

  let open = $state(false)
  let loading = $state(false)
  let draft = $state<PageSettings>({ ...$pageSettings })

  function numberValue(value: unknown, fallback: number) {
    const parsed = Number(value)
    return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback
  }

  async function load() {
    if (!$docId) return
    loading = true
    try {
      const response = await fetch(`/api/doc/${$docId}`)
      if (!response.ok) throw new Error(await response.text())
      const data = await response.json()
      const prefs = data.generation_prefs || {}
      draft = {
        pageSize: ['A4', 'A5', 'LETTER'].includes(String(prefs.page_size || '').toUpperCase())
          ? String(prefs.page_size).toUpperCase() as PageSettings['pageSize']
          : 'A4',
        orientation: prefs.page_orientation === 'landscape' ? 'landscape' : 'portrait',
        marginTop: numberValue(prefs.page_margin_top_cm, 2.54),
        marginBottom: numberValue(prefs.page_margin_bottom_cm, 2.54),
        marginLeft: numberValue(prefs.page_margin_left_cm, 3.18),
        marginRight: numberValue(prefs.page_margin_right_cm, 3.18),
        showHeader: Boolean(prefs.include_header ?? true),
        headerText: String(prefs.header_text || ''),
        showFooter: Boolean(prefs.include_footer ?? true),
        footerText: String(prefs.footer_text || ''),
        pageNumbers: Boolean(prefs.page_numbers ?? true),
        pageNumberPosition: ['left', 'center', 'right'].includes(String(prefs.page_number_position || ''))
          ? prefs.page_number_position
          : 'center'
      }
      pageSettings.set({ ...draft })
    } catch {
      draft = { ...$pageSettings }
    } finally {
      loading = false
    }
  }

  function show() {
    open = true
    void load()
  }

  async function save() {
    if (!$docId) return
    loading = true
    try {
      const response = await fetch(`/api/doc/${$docId}/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          generation_prefs: {
            page_size: draft.pageSize,
            page_orientation: draft.orientation,
            page_margin_top_cm: draft.marginTop,
            page_margin_bottom_cm: draft.marginBottom,
            page_margin_left_cm: draft.marginLeft,
            page_margin_right_cm: draft.marginRight,
            include_header: draft.showHeader,
            header_text: draft.headerText,
            include_footer: draft.showFooter,
            footer_text: draft.footerText,
            page_numbers: draft.pageNumbers,
            page_number_position: draft.pageNumberPosition
          }
        })
      })
      if (!response.ok) throw new Error(await response.text())
      pageSettings.set({ ...draft })
      window.dispatchEvent(new CustomEvent('wa-page-settings-changed', { detail: { ...draft } }))
      pushToast('页面、页眉和页脚设置已保存', 'ok')
      open = false
    } catch (error) {
      pushToast(`页面设置保存失败：${error instanceof Error ? error.message : '未知错误'}`, 'bad')
    } finally {
      loading = false
    }
  }
</script>

<button class="ribbon-action" onclick={show}>页面设置</button>

{#if open}
  <div class="page-setup-backdrop" role="presentation" onclick={() => (open = false)}></div>
  <div class="page-setup-panel" role="dialog" aria-modal="true" aria-label="页面设置" tabindex="-1">
    <header><strong>页面设置</strong><button onclick={() => (open = false)} aria-label="关闭">×</button></header>
    <div class="page-setup-grid">
      <label>纸张<select bind:value={draft.pageSize}><option>A4</option><option>A5</option><option>LETTER</option></select></label>
      <label>方向<select bind:value={draft.orientation}><option value="portrait">纵向</option><option value="landscape">横向</option></select></label>
      <fieldset>
        <legend>页边距（厘米）</legend>
        <label>上<input type="number" min="0" max="10" step="0.1" bind:value={draft.marginTop} /></label>
        <label>下<input type="number" min="0" max="10" step="0.1" bind:value={draft.marginBottom} /></label>
        <label>左<input type="number" min="0" max="10" step="0.1" bind:value={draft.marginLeft} /></label>
        <label>右<input type="number" min="0" max="10" step="0.1" bind:value={draft.marginRight} /></label>
      </fieldset>
      <fieldset class="wide">
        <legend>页眉与页脚</legend>
        <label class="check"><input type="checkbox" bind:checked={draft.showHeader} />显示页眉</label>
        <input class="text" aria-label="页眉内容" placeholder="页眉内容" bind:value={draft.headerText} disabled={!draft.showHeader} />
        <label class="check"><input type="checkbox" bind:checked={draft.showFooter} />显示页脚</label>
        <input class="text" aria-label="页脚内容" placeholder="页脚内容" bind:value={draft.footerText} disabled={!draft.showFooter} />
        <label class="check"><input type="checkbox" bind:checked={draft.pageNumbers} />显示页码</label>
        <select aria-label="页码位置" bind:value={draft.pageNumberPosition} disabled={!draft.pageNumbers}>
          <option value="left">左侧</option><option value="center">居中</option><option value="right">右侧</option>
        </select>
      </fieldset>
    </div>
    <footer><button class="btn ghost" onclick={() => (open = false)}>取消</button><button class="btn primary" onclick={save} disabled={loading}>{loading ? '保存中…' : '应用'}</button></footer>
  </div>
{/if}

<style>
  .page-setup-backdrop { position: fixed; inset: 0; z-index: 490; background: rgba(15,23,42,.24); }
  .page-setup-panel { position: fixed; z-index: 491; top: 50%; left: 50%; width: min(560px, calc(100vw - 32px)); transform: translate(-50%,-50%); border: 1px solid #cfd5df; border-radius: 8px; background: #fff; color: #202124; box-shadow: 0 18px 50px rgba(15,23,42,.2); }
  header, footer { display: flex; align-items: center; justify-content: space-between; padding: 13px 16px; border-bottom: 1px solid #e3e6eb; }
  header button { border: 0; background: transparent; font-size: 22px; cursor: pointer; }
  footer { justify-content: flex-end; gap: 8px; border-top: 1px solid #e3e6eb; border-bottom: 0; }
  .page-setup-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; padding: 16px; }
  label { display: grid; gap: 5px; font-size: 12px; color: #535b66; }
  select, input { box-sizing: border-box; height: 32px; padding: 4px 8px; border: 1px solid #c9cfd8; border-radius: 4px; background: #fff; color: #202124; }
  fieldset { display: grid; grid-template-columns: repeat(2, 1fr); gap: 9px; padding: 10px; border: 1px solid #d7dce4; border-radius: 5px; }
  fieldset.wide { grid-column: 1 / -1; grid-template-columns: auto 1fr; align-items: center; }
  legend { padding: 0 5px; font-size: 12px; color: #535b66; }
  .check { display: flex; flex-direction: row; align-items: center; }
  .check input { width: 16px; height: 16px; }
  .text { width: 100%; }
</style>
