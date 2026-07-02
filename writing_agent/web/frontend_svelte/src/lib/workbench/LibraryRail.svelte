<script lang="ts">
  import Icon from '../components/Icon.svelte'
  import type { LibraryCard, WorkspaceMode } from './types'
  import { formatLibraryCardTime } from './libraryCards'

  let {
    workspaceMode,
    librarySearch = $bindable(''),
    librarySelectAll = $bindable(false),
    selectedLibraryCardId = $bindable(''),
    libraryViewMode,
    filteredLibraryCards,
    onUpload,
    onOpenCard,
    onSwitchMode,
    onOpenCanvas,
    onOpenCitations,
    onOpenAssistant,
    onOpenMetrics
  }: {
    workspaceMode: WorkspaceMode
    librarySearch: string
    librarySelectAll: boolean
    selectedLibraryCardId: string
    libraryViewMode: 'grid' | 'masonry' | 'list'
    filteredLibraryCards: LibraryCard[]
    onUpload: () => void
    onOpenCard: (card: LibraryCard) => void
    onSwitchMode: (mode: WorkspaceMode) => void
    onOpenCanvas: () => void
    onOpenCitations: () => void
    onOpenAssistant: () => void
    onOpenMetrics: () => void
  } = $props()
</script>

<aside class="nav-rail">
  <div class="rail-search">
    <input type="text" placeholder="搜索资料卡片..." bind:value={librarySearch} />
  </div>
  <button class="rail-upload-btn icon-btn-text" onclick={onUpload}>
    <Icon name="upload" className="ui-icon" />
    <span>上传素材</span>
  </button>
  <div class="rail-tip">将图片、模板或参考文档拖入编辑区，可直接纳入当前工程。</div>

  <section class="rail-library">
    <div class="rail-group-head">
      <span>资料流</span>
      <em>{filteredLibraryCards.length}</em>
    </div>
    <div class={`library-card-stream ${libraryViewMode}`}>
      {#if filteredLibraryCards.length === 0}
        <div class="library-empty">没有匹配项，试试其他关键词。</div>
      {:else}
        {#each filteredLibraryCards as card}
          <button
            class={`library-card tone-${card.tone} ${librarySelectAll || selectedLibraryCardId === card.id ? 'selected' : ''}`}
            onclick={() => onOpenCard(card)}
            title={card.summary}
          >
            <div class="library-card-cover">
              <span class={`library-status status-${card.status}`}>{card.status_label}</span>
              <span class="library-kind">{card.kind_label}</span>
            </div>
            <div class="library-card-body">
              <div class="library-card-title-row">
                <span class="library-card-title">{card.title}</span>
                <span class="library-card-time">{formatLibraryCardTime(card.updated_at)}</span>
              </div>
              <div class="library-card-summary">{card.summary}</div>
              <div class="library-card-tags">
                {#each card.tags as tag}
                  <span>#{tag}</span>
                {/each}
              </div>
            </div>
          </button>
        {/each}
      {/if}
    </div>
  </section>

  <section class="rail-group workflow-group">
    <div class="rail-group-head">
      <span>快捷入口</span>
      <em>4</em>
    </div>
    <button class={`nav-btn ${workspaceMode === 'editor' ? 'active' : ''}`} onclick={() => onSwitchMode('editor')} title="编辑器">
      <Icon name="editor" className="ui-icon" />
      <span>正文编辑</span>
    </button>
    <button class="nav-btn" onclick={onOpenCanvas} title="画布">
      <Icon name="canvas" className="ui-icon" />
      <span>图形画布</span>
    </button>
    <button class="nav-btn" title="引用" onclick={onOpenCitations}>
      <Icon name="cite" className="ui-icon" />
      <span>引用管理</span>
    </button>
    <button class={`nav-btn ${workspaceMode === 'collab' ? 'active' : ''}`} title="协作助手" onclick={onOpenAssistant}>
      <Icon name="chat" className="ui-icon" />
      <span>协作助手</span>
    </button>
    <button class="nav-btn" title="性能" onclick={onOpenMetrics}>
      <Icon name="chart" className="ui-icon" />
      <span>性能指标</span>
    </button>
  </section>

  <button class="rail-reset icon-btn-text" onclick={() => { librarySearch = ''; librarySelectAll = false; selectedLibraryCardId = ''; }}>
    <Icon name="clearSelection" className="ui-icon" />
    <span>重置筛选</span>
  </button>
</aside>
