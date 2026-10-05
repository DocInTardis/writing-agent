<script lang="ts">
  import type { LibraryCard } from './types'

  let {
    librarySearch = $bindable(''),
    selectedLibraryCardId = $bindable(''),
    cards,
    onUpload,
    onOpenCard,
    onSwitchMode
  }: {
    librarySearch: string
    selectedLibraryCardId: string
    cards: LibraryCard[]
    onUpload: () => void
    onOpenCard: (card: LibraryCard) => void
    onSwitchMode: (mode: 'library') => void
  } = $props()
</script>

<aside class="nav-rail" aria-label="工作区导航">
  <section class="materials">
    <header><strong>资料</strong><button onclick={onUpload} title="添加资料">＋</button></header>
    <input type="search" placeholder="搜索资料" bind:value={librarySearch} />
    <div class="material-list">
      {#if cards.length === 0}
        <button class="empty" onclick={onUpload}>添加第一份资料</button>
      {:else}
        {#each cards.slice(0, 6) as card (card.id)}
          <button class:selected={selectedLibraryCardId === card.id} onclick={() => onOpenCard(card)} title={card.title}>
            <span class={`dot ${card.status}`}></span>
            <span class="material-name">{card.title}</span>
            <small>{card.kind_label}</small>
          </button>
        {/each}
      {/if}
    </div>
    {#if cards.length > 6}<button class="show-all" onclick={() => onSwitchMode('library')}>查看全部 {cards.length} 项</button>{/if}
  </section>
</aside>

<style>
  .nav-rail { box-sizing: border-box; display: flex; width: 226px; min-width: 226px; height: 100%; flex-direction: column; gap: 20px; padding: 16px 12px; border-right: 1px solid #e2e5ea; background: #fafafa; color: #303846; }
  button, input { font: inherit; }
  .materials { min-height: 0; }.materials header { display: flex; align-items: center; justify-content: space-between; padding: 0 6px 8px; color: #687386; font-size: 12px; }.materials header button { width: 25px; height: 25px; border: 0; border-radius: 5px; background: transparent; color: #596579; cursor: pointer; font-size: 18px; }.materials header button:hover { background: #eceff3; }
  input { box-sizing: border-box; width: 100%; height: 32px; padding: 0 9px; border: 1px solid #dfe3e8; border-radius: 6px; background: #fff; color: #303846; font-size: 12px; outline: none; } input:focus { border-color: #8bb3e7; }
  .material-list { display: grid; gap: 2px; margin-top: 8px; }.material-list > button { display: grid; grid-template-columns: 8px minmax(0, 1fr) auto; min-height: 34px; align-items: center; gap: 7px; padding: 0 7px; border: 0; border-radius: 6px; background: transparent; color: #4d5868; cursor: pointer; text-align: left; }.material-list > button:hover, .material-list > button.selected { background: #eef1f5; }.material-list > button.selected { color: #1e5eb7; }
  .dot { width: 6px; height: 6px; border-radius: 50%; background: #b8bec8; }.dot.approved { background: #27a463; }.dot.trashed { background: #c1c4ca; }.material-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }.material-list small { color: #939ba7; font-size: 9px; }.material-list .empty { display: block; padding: 10px; color: #7b8491; text-align: center; }
  .show-all { margin: 8px 6px 0; padding: 0; border: 0; background: transparent; color: #2468c8; cursor: pointer; font-size: 11px; }
  @media (max-width: 920px) { .nav-rail { width: 176px; min-width: 176px; } }
</style>
