<script lang="ts">
  import Icon from '../components/Icon.svelte'
  import LLMConfig from '../components/LLMConfig.svelte'
  import Settings from '../components/Settings.svelte'
  import type { QualityOverview, WorkspaceMode } from './types'

  let {
    workspaceMode,
    qualityOverview,
    wordCount,
    routeId,
    topStatusLine,
    onSwitchMode,
    onSave,
    onExportDocx,
    onExportPdf,
    onToggleInfo
  }: {
    workspaceMode: WorkspaceMode
    qualityOverview: QualityOverview
    wordCount: number
    routeId: string
    topStatusLine: string
    onSwitchMode: (mode: WorkspaceMode) => void
    onSave: () => void
    onExportDocx: () => void
    onExportPdf: () => void
    onToggleInfo: () => void
  } = $props()
</script>

<header class="topbar">
  <div class="brand">
    <div class="logo">IR</div>
    <div class="brand-text">
      <div class="brand-title">Astra 写作工作台</div>
      <div class="brand-sub">图路由引擎 · 结构化编辑</div>
    </div>
  </div>
  <div class="workspace-hub">
    <div class="workspace-status-line" title={topStatusLine}>
      <span class="dot"></span>
      <span>{topStatusLine}</span>
    </div>
    <nav class="menu" aria-label="工作区模式">
      <button class={`menu-item ${workspaceMode === 'editor' ? 'active' : ''}`} onclick={() => onSwitchMode('editor')}>
        <span>编辑</span>
      </button>
      <button class={`menu-item ${workspaceMode === 'library' ? 'active' : ''}`} onclick={() => onSwitchMode('library')}>
        <span>资料</span>
      </button>
      <button class={`menu-item ${workspaceMode === 'collab' ? 'active' : ''}`} onclick={() => onSwitchMode('collab')}>
        <span>协作</span>
      </button>
    </nav>
    <div class="workspace-metrics" aria-label="工作台概览">
      <div class={`metric-pill tone-${qualityOverview.tone}`}>
        <span class="metric-label">质量</span>
        <strong>{qualityOverview.label}</strong>
      </div>
      <div class="metric-pill">
        <span class="metric-label">字数</span>
        <strong>{Math.max(0, Number(wordCount || 0))}</strong>
      </div>
      <div class="metric-pill">
        <span class="metric-label">路由</span>
        <strong>{routeId || '默认'}</strong>
      </div>
    </div>
  </div>
  <div class="top-actions">
    <button class="btn ghost icon-btn-text" onclick={onSave}>
      <Icon name="save" className="ui-icon" />
      <span>保存</span>
    </button>
    <button class="btn ghost icon-btn-text" onclick={onExportDocx}>
      <Icon name="doc" className="ui-icon" />
      <span>导出 Word</span>
    </button>
    <button class="btn ghost icon-btn-text" onclick={onExportPdf}>
      <Icon name="pdf" className="ui-icon" />
      <span>导出 PDF</span>
    </button>
    <button class="btn ghost icon-btn-text" onclick={onToggleInfo}>
      <Icon name="doc" className="ui-icon" />
      <span>文档信息</span>
    </button>
    <LLMConfig />
    <Settings />
  </div>
</header>
