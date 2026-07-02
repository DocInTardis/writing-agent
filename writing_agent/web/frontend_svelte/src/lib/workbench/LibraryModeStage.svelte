<script lang="ts">
  import Icon from '../components/Icon.svelte'
  import type { LibraryCard } from './types'
  import { formatLibraryCardTime } from './libraryCards'

  let {
    libraryViewMode = $bindable<'grid' | 'masonry' | 'list'>('grid'),
    librarySearch,
    filteredLibraryCards,
    librarySelectAll,
    selectedLibraryCardId,
    onUpload,
    onOpenCitations,
    onOpenVersions,
    onOpenCard,
    onDrop,
    onBack
  }: {
    libraryViewMode: 'grid' | 'masonry' | 'list'
    librarySearch: string
    filteredLibraryCards: LibraryCard[]
    librarySelectAll: boolean
    selectedLibraryCardId: string
    onUpload: () => void
    onOpenCitations: () => void
    onOpenVersions: () => void
    onOpenCard: (card: LibraryCard) => void
    onDrop: (event: DragEvent) => void
    onBack: () => void
  } = $props()
</script>

<div class="library-command-bar">
  <div class="library-view-switch">
    <button class={`view-btn ${libraryViewMode === 'grid' ? 'active' : ''}`} onclick={() => (libraryViewMode = 'grid')} title="网格视图">
      <Icon name="grid" className="ui-icon" />
    </button>
    <button class={`view-btn ${libraryViewMode === 'masonry' ? 'active' : ''}`} onclick={() => (libraryViewMode = 'masonry')} title="瀑布视图">
      <Icon name="masonry" className="ui-icon" />
    </button>
    <button class={`view-btn ${libraryViewMode === 'list' ? 'active' : ''}`} onclick={() => (libraryViewMode = 'list')} title="列表视图">
      <Icon name="list" className="ui-icon" />
    </button>
  </div>
  <div class="library-counter">{librarySearch ? `搜索：${librarySearch}` : '资料模式：拖拽素材、整理证据、批量管理'}</div>
  <div class="library-actions">
    <button class="btn ghost icon-btn-text" onclick={onUpload}>
      <Icon name="upload" className="ui-icon" />
      <span>上传素材</span>
    </button>
    <button class="btn ghost icon-btn-text" onclick={onBack}>
      <Icon name="open" className="ui-icon" />
      <span>返回编辑</span>
    </button>
  </div>
</div>
<section class="library-mode-stage" aria-label="资料模式拖拽工作区" ondragover={(e) => e.preventDefault()} ondrop={onDrop}>
  <div class="library-mode-dropzone">
    <div class="panel-title">资料工作区</div>
    <div class="panel-sub">拖拽图片/文档到此处，或点击上传素材。资料模式默认不展示正文编辑器。</div>
    <div class="library-mode-actions">
      <button class="btn ghost icon-btn-text" onclick={onUpload}>
        <Icon name="upload" className="ui-icon" />
        <span>上传文件</span>
      </button>
      <button class="btn ghost icon-btn-text" onclick={onOpenCitations}>
        <Icon name="cite" className="ui-icon" />
        <span>引用管理</span>
      </button>
      <button class="btn ghost icon-btn-text" onclick={onOpenVersions}>
        <Icon name="clock" className="ui-icon" />
        <span>版本记录</span>
      </button>
    </div>
  </div>
  <div class={`library-mode-board ${libraryViewMode}`}>
    {#if filteredLibraryCards.length === 0}
      <div class="panel-empty">暂无匹配资料，请调整筛选条件或上传新素材。</div>
    {:else}
      {#each filteredLibraryCards as card}
        <button
          class={`library-mode-card tone-${card.tone} ${librarySelectAll || selectedLibraryCardId === card.id ? 'selected' : ''}`}
          onclick={() => onOpenCard(card)}
          title={card.summary}
        >
          <div class="library-mode-card-head">
            <span class={`library-status status-${card.status}`}>{card.status_label}</span>
            <span class="library-kind">{card.kind_label}</span>
          </div>
          <div class="library-mode-card-title">{card.title}</div>
          <div class="library-mode-card-summary">{card.summary}</div>
          <div class="library-mode-card-foot">
            <span>{formatLibraryCardTime(card.updated_at)}</span>
            <span>{card.size_label}</span>
          </div>
        </button>
      {/each}
    {/if}
  </div>
</section>
