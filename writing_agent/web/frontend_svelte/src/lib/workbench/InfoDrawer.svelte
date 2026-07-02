<script lang="ts">
  import Icon from '../components/Icon.svelte'

  let {
    preview,
    title,
    sizeKb,
    wordCount,
    selectedCount,
    routeId,
    onClose,
    onSwitchToEditor,
    onClearSelection
  }: {
    preview: string
    title: string
    sizeKb: number
    wordCount: number
    selectedCount: number
    routeId: string
    onClose: () => void
    onSwitchToEditor: () => void
    onClearSelection: () => void
  } = $props()
</script>

<div class="info-drawer-backdrop" role="presentation">
  <button type="button" class="sheet-backdrop-hit" onclick={onClose} aria-label="关闭文档信息"></button>
  <div class="info-drawer panel-card media-meta-panel" role="dialog" aria-modal="true" aria-label="文档信息">
    <div class="panel-header">
      <div>
        <div class="panel-title">文档信息</div>
        <div class="panel-sub">当前工作区摘要</div>
      </div>
      <button class="btn ghost btn-sm" onclick={onClose}>关闭</button>
    </div>
    <div class="meta-hero">
      <div class="meta-hero-glow"></div>
      <div class="meta-hero-text">{preview || '暂无内容预览'}</div>
    </div>
    <div class="meta-list">
      <div><span>名称</span><strong>{title}</strong></div>
      <div><span>类型</span><strong>text/markdown</strong></div>
      <div><span>大小</span><strong>{sizeKb} KB</strong></div>
      <div><span>词数</span><strong>{wordCount}</strong></div>
      <div><span>选区</span><strong>{selectedCount || 0}</strong></div>
      <div><span>路由</span><strong>{routeId || '默认'}</strong></div>
    </div>
    <div class="meta-actions">
      <button class="btn ghost icon-btn-text" onclick={onSwitchToEditor}>
        <Icon name="open" className="ui-icon" />
        <span>定位到编辑区</span>
      </button>
      <button class="btn ghost danger icon-btn-text" onclick={onClearSelection}>
        <Icon name="clearSelection" className="ui-icon" />
        <span>清空选区</span>
      </button>
    </div>
  </div>
</div>
