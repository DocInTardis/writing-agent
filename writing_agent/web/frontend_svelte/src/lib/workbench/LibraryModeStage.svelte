<script lang="ts">
  import Icon from '../components/Icon.svelte'
  import type { LibraryCard } from './types'
  import { formatLibraryCardTime } from './libraryCards'

  let {
    libraryViewMode = $bindable<'grid' | 'list'>('grid'),
    statusFilter = $bindable<'active' | 'pending' | 'approved' | 'trashed'>('active'),
    cards,
    loading,
    error,
    selectedId,
    previewText,
    onUpload,
    onOpenCard,
    onDrop,
    onApprove,
    onTrash,
    onRestore,
    onDelete,
    onCopyExcerpt
  }: {
    libraryViewMode: 'grid' | 'list'
    statusFilter: 'active' | 'pending' | 'approved' | 'trashed'
    cards: LibraryCard[]
    loading: boolean
    error: string
    selectedId: string
    previewText: string
    onUpload: () => void
    onOpenCard: (card: LibraryCard) => void
    onDrop: (event: DragEvent) => void
    onApprove: (id: string) => void | Promise<void>
    onTrash: (id: string) => void | Promise<void>
    onRestore: (id: string) => void | Promise<void>
    onDelete: (id: string) => void | Promise<void>
    onCopyExcerpt: () => void | Promise<void>
  } = $props()

  let selected = $derived(cards.find((card) => card.id === selectedId) || null)
</script>

<section class="library-stage" aria-label="资料库" ondragover={(event) => event.preventDefault()} ondrop={onDrop}>
  <header class="library-head">
    <div>
      <h1>资料库</h1>
      <p>只有“已用于 AI”的资料会参与检索。上传不会改动当前正文。</p>
    </div>
    <div class="head-actions">
      <button class="primary" onclick={onUpload}><Icon name="upload" size={14} />添加资料</button>
    </div>
  </header>

  <div class="library-toolbar">
    <div class="filters" role="tablist" aria-label="资料状态">
      {#each [
        ['active', '全部'],
        ['pending', '待启用'],
        ['approved', '已用于 AI'],
        ['trashed', '回收站']
      ] as option}
        <button class:active={statusFilter === option[0]} onclick={() => (statusFilter = option[0] as typeof statusFilter)}>{option[1]}</button>
      {/each}
    </div>
    <span>{cards.length} 项</span>
    <div class="view-switch">
      <button class:active={libraryViewMode === 'grid'} onclick={() => (libraryViewMode = 'grid')} title="网格"><Icon name="grid" size={14} /></button>
      <button class:active={libraryViewMode === 'list'} onclick={() => (libraryViewMode = 'list')} title="列表"><Icon name="list" size={14} /></button>
    </div>
  </div>

  <div class="library-body" class:with-preview={Boolean(selected)}>
    <div class="library-content">
      {#if loading}
        <div class="empty">正在读取资料…</div>
      {:else if error}
        <div class="empty error">{error}</div>
      {:else if cards.length === 0}
        <button class="empty drop-target" onclick={onUpload}>
          <Icon name="upload" size={22} />
          <strong>拖入文件，或点击选择</strong>
          <span>支持 PDF、DOCX、Markdown、文本、表格和常见图片</span>
        </button>
      {:else}
        <div class={`card-board ${libraryViewMode}`}>
          {#each cards as card (card.id)}
            <button class:selected={selectedId === card.id} class="material-card" onclick={() => onOpenCard(card)}>
              <div class="card-top">
                <span class={`status ${card.status}`}>{card.status_label}</span>
                <span class="kind">{card.kind_label}</span>
              </div>
              <strong>{card.title}</strong>
              <p>{card.summary}</p>
              <footer><span>{card.size_label}</span><span>{formatLibraryCardTime(card.updated_at)}</span></footer>
            </button>
          {/each}
        </div>
      {/if}
    </div>

    {#if selected}
      <aside class="preview" aria-label="资料详情">
        <div class="preview-head">
          <div><span>{selected.kind_label}</span><h2>{selected.title}</h2></div>
          <button aria-label="关闭详情" onclick={() => onOpenCard(selected)}>×</button>
        </div>
        <dl>
          <dt>状态</dt><dd>{selected.status_label}</dd>
          <dt>来源</dt><dd>{selected.source_name || '内部文本'}</dd>
          <dt>内容</dt><dd>{selected.size_label}</dd>
        </dl>
        <div class="preview-text">{previewText || '没有提取到可预览的文字。原文件仍保存在本地资料库。'}</div>
        <div class="preview-actions">
          {#if selected.status === 'pending'}
            <button class="primary" onclick={() => onApprove(selected.id)}>启用给 AI</button>
            <button class="quiet" onclick={() => onTrash(selected.id)}>移到回收站</button>
          {:else if selected.status === 'approved'}
            <button class="quiet" onclick={onCopyExcerpt}>复制摘录</button>
            <button class="quiet" onclick={() => onTrash(selected.id)}>停用并移除</button>
          {:else}
            <button class="primary" onclick={() => onRestore(selected.id)}>恢复</button>
            <button class="danger" onclick={() => onDelete(selected.id)}>永久删除</button>
          {/if}
        </div>
      </aside>
    {/if}
  </div>
</section>

<style>
  .library-stage { height: 100%; overflow: auto; padding: 28px 32px 40px; background: #f5f6f8; color: #202936; }
  .library-head, .library-toolbar, .card-top, .material-card footer, .preview-head, .head-actions, .view-switch, .filters, .preview-actions { display: flex; align-items: center; }
  .library-head { justify-content: space-between; gap: 20px; margin-bottom: 22px; }
  h1, h2, p { margin: 0; } h1 { font-size: 24px; } h2 { margin-top: 3px; font-size: 17px; }
  .library-head p { margin-top: 6px; color: #6b7280; font-size: 13px; }
  button { font: inherit; cursor: pointer; }
  .head-actions, .preview-actions { gap: 8px; }
  .primary, .quiet, .danger { min-height: 34px; padding: 0 13px; border-radius: 7px; }
  .primary { display: inline-flex; gap: 7px; align-items: center; border: 1px solid #2468c8; background: #2468c8; color: #fff; }
  .quiet { border: 1px solid #d6dbe3; background: #fff; color: #354052; }
  .danger { border: 1px solid #efc3c3; background: #fff7f7; color: #b42318; }
  .library-toolbar { min-height: 42px; justify-content: space-between; gap: 12px; border-bottom: 1px solid #dfe3e8; }
  .filters { gap: 4px; align-self: stretch; }
  .filters button { padding: 0 11px; border: 0; border-bottom: 2px solid transparent; background: transparent; color: #697386; }
  .filters button.active { border-bottom-color: #2468c8; color: #1e5eb7; font-weight: 600; }
  .library-toolbar > span { margin-left: auto; color: #7a8493; font-size: 12px; }
  .view-switch { gap: 3px; }.view-switch button { display: grid; width: 30px; height: 28px; place-items: center; border: 1px solid transparent; border-radius: 5px; background: transparent; color: #667085; }
  .view-switch button.active { border-color: #d7dce4; background: #fff; color: #2468c8; }
  .library-body { display: grid; min-height: 420px; }.library-body.with-preview { grid-template-columns: minmax(0, 1fr) 340px; gap: 18px; }
  .library-content { padding-top: 18px; }
  .card-board { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 12px; }
  .card-board.list { grid-template-columns: 1fr; }.card-board.list .material-card { min-height: 96px; }
  .material-card { min-height: 150px; padding: 15px; border: 1px solid #dfe3e8; border-radius: 9px; background: #fff; color: inherit; text-align: left; box-shadow: 0 1px 2px rgba(16,24,40,.03); }
  .material-card:hover, .material-card.selected { border-color: #8bb3e7; }.material-card.selected { box-shadow: 0 0 0 2px rgba(36,104,200,.1); }
  .card-top { justify-content: space-between; margin-bottom: 13px; }.status, .kind { font-size: 11px; }.kind { color: #7a8493; }
  .status { padding: 3px 7px; border-radius: 999px; background: #f0f2f5; color: #596579; }.status.approved { background: #e7f6ed; color: #177245; }.status.trashed { background: #f4f4f5; color: #777; }
  .material-card strong { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 14px; }
  .material-card p { margin-top: 8px; overflow: hidden; color: #6b7280; font-size: 12px; line-height: 1.55; text-overflow: ellipsis; white-space: nowrap; }
  .material-card footer { justify-content: space-between; margin-top: 22px; color: #8a93a1; font-size: 11px; }
  .empty { display: grid; min-height: 320px; place-items: center; align-content: center; gap: 9px; border: 1px dashed #cfd5de; border-radius: 10px; background: #fafbfc; color: #737d8c; text-align: center; }.empty.drop-target { width: 100%; }.empty span { font-size: 12px; }.empty.error { color: #b42318; }
  .preview { align-self: start; margin-top: 18px; padding: 18px; border: 1px solid #dfe3e8; border-radius: 9px; background: #fff; }
  .preview-head { justify-content: space-between; align-items: flex-start; }.preview-head span { color: #7b8491; font-size: 11px; }.preview-head button { border: 0; background: transparent; color: #737d8c; font-size: 20px; }
  dl { display: grid; grid-template-columns: 54px 1fr; gap: 6px 8px; margin: 18px 0 12px; font-size: 12px; } dt { color: #8a93a1; } dd { overflow: hidden; margin: 0; text-overflow: ellipsis; white-space: nowrap; }
  .preview-text { max-height: 360px; overflow: auto; padding: 12px; border: 1px solid #eceff3; border-radius: 6px; background: #fafbfc; color: #465164; font-size: 12px; line-height: 1.65; white-space: pre-wrap; }
  .preview-actions { flex-wrap: wrap; margin-top: 14px; }
  @media (max-width: 1050px) { .library-body.with-preview { grid-template-columns: 1fr; }.preview { order: -1; }.library-stage { padding: 20px; } }
</style>
