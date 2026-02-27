<script lang="ts">
  export interface CitationReviewItem {
    id: string
    source: string
    confidence: number
    reachable: boolean
    suggestion?: string
  }

  export let items: CitationReviewItem[] = []
</script>

<div class="citation-review">
  <h3>Citation Review</h3>
  {#if !items.length}
    <p class="empty">No citation issues.</p>
  {:else}
    <ul>
      {#each items as item}
        <li>
          <strong>{item.id}</strong>
          <span class="source">{item.source}</span>
          <span class="badge {item.reachable ? 'ok' : 'bad'}">{item.reachable ? 'reachable' : 'broken'}</span>
          <span class="conf">conf {item.confidence.toFixed(2)}</span>
          {#if item.suggestion}<div class="suggestion">{item.suggestion}</div>{/if}
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .citation-review { border: 1px solid #d7d7d7; border-radius: 8px; padding: 10px; }
  .empty { color: #666; margin: 0; }
  ul { margin: 0; padding-left: 18px; }
  li { margin: 6px 0; }
  .source { margin-left: 6px; color: #444; }
  .badge { margin-left: 6px; padding: 2px 6px; border-radius: 999px; font-size: 11px; }
  .badge.ok { background: #e8f6ec; color: #1f7a3d; }
  .badge.bad { background: #fde8e8; color: #b33838; }
  .conf { margin-left: 6px; color: #555; font-size: 12px; }
  .suggestion { color: #333; font-size: 12px; }
</style>
