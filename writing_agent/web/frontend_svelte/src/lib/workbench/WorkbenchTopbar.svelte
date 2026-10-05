<script lang="ts">
  import Icon from '../components/Icon.svelte'
  import LLMConfig from '../components/LLMConfig.svelte'
  import Settings from '../components/Settings.svelte'
  import type { WorkspaceMode } from './types'

  let {
    workspaceMode,
    topStatusLine,
    onSwitchMode,
    onSave,
    onExportDocx,
    onExportPdf,
    onToggleInfo,
    onOpenVersions,
    onOpenAssistant
  }: {
    workspaceMode: WorkspaceMode
    topStatusLine: string
    onSwitchMode: (mode: WorkspaceMode) => void
    onSave: () => void
    onExportDocx: () => void
    onExportPdf: () => void
    onToggleInfo: () => void
    onOpenVersions: () => void
    onOpenAssistant: () => void
  } = $props()
</script>

<header class="topbar">
  <div class="brand">
    <a class="home-link" href="/" aria-label="返回文档列表">
      <div class="logo">W</div>
    </a>
    <div class="brand-text">
      <div class="brand-title">写作助手</div>
      <div class="brand-sub">{topStatusLine}</div>
    </div>
  </div>
  <div class="workspace-hub">
    <nav class="menu" aria-label="工作区模式">
      <button class={`menu-item ${workspaceMode === 'editor' ? 'active' : ''}`} onclick={() => onSwitchMode('editor')}>
        <span>文档</span>
      </button>
      <button class={`menu-item ${workspaceMode === 'library' ? 'active' : ''}`} onclick={() => onSwitchMode('library')}>
        <span>资料</span>
      </button>
      <button class="menu-item" onclick={onOpenAssistant}>
        <span>助手</span>
      </button>
    </nav>
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
      <span>PDF</span>
    </button>
    <button class="btn ghost icon-btn-text" onclick={onOpenVersions} title="版本记录">
      <span>版本</span>
    </button>
    <LLMConfig />
    <Settings />
    <button class="btn ghost topbar-more" onclick={onToggleInfo} title="文档信息" aria-label="文档信息">···</button>
  </div>
</header>
