<script lang="ts">
  export let original = ''
  export let revised = ''

  function lines(text: string): string[] {
    return String(text || '').split(/\r?\n/)
  }

  $: left = lines(original)
  $: right = lines(revised)
  $: total = Math.max(left.length, right.length)
</script>

<div class="diff-panel">
  <h3>Paragraph Diff/Patch</h3>
  <div class="grid">
    {#each Array(total) as _, i}
      <div class="row {left[i] === right[i] ? 'same' : 'changed'}">
        <div class="cell left">{left[i] || ''}</div>
        <div class="cell right">{right[i] || ''}</div>
      </div>
    {/each}
  </div>
</div>

<style>
  .diff-panel { border: 1px solid #d7d7d7; border-radius: 8px; padding: 10px; }
  .grid { display: grid; gap: 6px; }
  .row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .row.changed .cell { background: #fff4dd; }
  .cell { border: 1px solid #ececec; border-radius: 6px; padding: 6px; font-size: 12px; white-space: pre-wrap; }
</style>
