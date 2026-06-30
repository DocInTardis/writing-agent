<script lang="ts">
  import KnowledgeGraphView from './KnowledgeGraphView.svelte'

  export interface CitationReviewItem {
    id: string
    source: string
    confidence: number
    reachable: boolean
    suggestion?: string
  }

  export interface KnowledgeUnitItem {
    ku_id: string
    claim: string
    evidence: string
    source_doc: string
    source_page?: number | null
    source_para?: number | null
    confidence: number
    entities: string[]
    status?: '审核中' | '已通过' | '已驳回'
  }

  export interface KGPreviewNode {
    id: string
    name: string
    type: 'method' | 'dataset' | 'concept' | 'claim' | 'author' | 'metric'
    distance?: number
  }

  export interface KGPreviewEdge {
    from: string
    to: string
    relation: string
  }

  let {
    items = [] as CitationReviewItem[],
    kuItems = [] as KnowledgeUnitItem[],
    kgNodes = [] as KGPreviewNode[],
    kgEdges = [] as KGPreviewEdge[],
    onKuStatusChange,
    onKuJumpToSource,
  }: {
    items?: CitationReviewItem[]
    kuItems?: KnowledgeUnitItem[]
    kgNodes?: KGPreviewNode[]
    kgEdges?: KGPreviewEdge[]
    onKuStatusChange?: (ku_id: string, status: KnowledgeUnitItem['status']) => void
    onKuJumpToSource?: (ku_id: string) => void
  } = $props()

  let selectedKuId = $state<string | null>(null)

  function statusBadgeClass(status?: string) {
    if (status === '已通过') return 'pass'
    if (status === '已驳回') return 'reject'
    return 'pending'
  }
</script>

<div class="citation-review">
  <h3>引用审查</h3>
  {#if !items.length && !kuItems.length}
    <p class="empty">未发现引用问题。</p>
  {:else}
    {#if items.length}
      <ul class="ref-list">
        {#each items as item}
          <li>
            <strong>{item.id}</strong>
            <span class="source">{item.source}</span>
            <span class="badge {item.reachable ? 'ok' : 'bad'}">{item.reachable ? '可访问' : '异常'}</span>
            <span class="conf">置信度 {item.confidence.toFixed(2)}</span>
            {#if item.suggestion}<div class="suggestion">{item.suggestion}</div>{/if}
          </li>
        {/each}
      </ul>
    {/if}

    {#if kuItems.length}
      <div class="ku-section">
        <h4>知识点级溯源 ({kuItems.length})</h4>
        {#if kgNodes.length}
          <div class="kg-preview">
            <KnowledgeGraphView
              nodes={kgNodes}
              edges={kgEdges}
              width={440}
              height={280}
              onNodeClick={(n) => { selectedKuId = n.id }}
            />
          </div>
        {/if}
        <ul class="ku-list">
          {#each kuItems as ku}
            <li class={selectedKuId === ku.ku_id ? 'selected' : ''}>
              <div class="ku-claim">
                <span class="ku-badge {statusBadgeClass(ku.status)}">{ku.status || '审核中'}</span>
                <strong>{ku.claim}</strong>
                <span class="ku-conf">置信度 {ku.confidence.toFixed(0)}%</span>
              </div>
              <div class="ku-evidence">
                <blockquote>{ku.evidence}</blockquote>
              </div>
              <div class="ku-meta">
                {#if ku.source_doc}
                  <span class="ku-source">来源: {ku.source_doc}</span>
                {/if}
                {#if ku.source_page}
                  <span class="ku-page">第 {ku.source_page} 页</span>
                {/if}
                {#if ku.source_para}
                  <span class="ku-para">段落 {ku.source_para}</span>
                {/if}
                {#if ku.entities.length}
                  <span class="ku-entities">实体: {ku.entities.join(', ')}</span>
                {/if}
              </div>
              <div class="ku-actions">
                <button class="btn-pass" onclick={() => onKuStatusChange?.(ku.ku_id, '已通过')}>通过</button>
                <button class="btn-reject" onclick={() => onKuStatusChange?.(ku.ku_id, '已驳回')}>驳回</button>
                <button class="btn-jump" onclick={() => onKuJumpToSource?.(ku.ku_id)}>跳转原文</button>
              </div>
            </li>
          {/each}
        </ul>
      </div>
    {/if}
  {/if}
</div>

<style>
  .citation-review { border: 1px solid #d7d7d7; border-radius: 8px; padding: 10px; }
  .empty { color: #666; margin: 0; }
  .ref-list { margin: 0; padding-left: 18px; }
  .ref-list li { margin: 6px 0; }
  .source { margin-left: 6px; color: #444; }
  .badge { margin-left: 6px; padding: 2px 6px; border-radius: 999px; font-size: 11px; }
  .badge.ok { background: #e8f6ec; color: #1f7a3d; }
  .badge.bad { background: #fde8e8; color: #b33838; }
  .conf { margin-left: 6px; color: #555; font-size: 12px; }
  .suggestion { color: #333; font-size: 12px; margin-top: 2px; }

  .ku-section { margin-top: 12px; border-top: 1px solid #e0e0e0; padding-top: 10px; }
  .ku-section h4 { margin: 0 0 8px; font-size: 14px; color: #2b2416; }
  .kg-preview { margin-bottom: 10px; }
  .ku-list { margin: 0; padding: 0; list-style: none; }
  .ku-list li { margin: 8px 0; padding: 8px; border-radius: 6px; background: #faf8f3; border: 1px solid rgba(90,70,45,0.08); }
  .ku-list li.selected { border-color: #4a90d9; background: #f0f6fc; }
  .ku-claim { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
  .ku-claim strong { color: #2b2416; font-size: 13px; }
  .ku-conf { font-size: 11px; color: #666; margin-left: auto; }
  .ku-badge { font-size: 10px; padding: 1px 6px; border-radius: 999px; }
  .ku-badge.pass { background: #e8f6ec; color: #1f7a3d; }
  .ku-badge.reject { background: #fde8e8; color: #b33838; }
  .ku-badge.pending { background: #fff3cd; color: #856404; }
  .ku-evidence blockquote { margin: 4px 0 0; padding-left: 10px; border-left: 3px solid #d7d7d7; color: #444; font-size: 12px; }
  .ku-meta { margin-top: 4px; font-size: 11px; color: #666; display: flex; gap: 8px; flex-wrap: wrap; }
  .ku-actions { margin-top: 6px; display: flex; gap: 6px; }
  .ku-actions button { font-size: 11px; padding: 3px 10px; border-radius: 4px; border: 1px solid #ccc; background: #fff; cursor: pointer; }
  .ku-actions .btn-pass { border-color: #1f7a3d; color: #1f7a3d; }
  .ku-actions .btn-reject { border-color: #b33838; color: #b33838; }
  .ku-actions .btn-jump { border-color: #4a90d9; color: #4a90d9; }
</style>
