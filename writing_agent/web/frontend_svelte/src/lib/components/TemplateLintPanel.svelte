<script lang="ts">
  let { templateText = '' } = $props()
  let warnings = $derived(lintTemplate(templateText))

  function lintTemplate(text: string): string[] {
    const t = String(text || '')
    const out: string[] = []
    if (!t.includes('{{title}}')) out.push('缺少变量：{{title}}')
    if (!t.includes('{{body}}')) out.push('缺少变量：{{body}}')
    if (t.length > 10000) out.push('模板过长（超过 10000 字符）')
    return out
  }
</script>

<div class="template-lint">
  <h3>模板检查</h3>
  {#if warnings.length === 0}
    <p class="ok">未发现问题。</p>
  {:else}
    <ul>
      {#each warnings as row}
        <li>{row}</li>
      {/each}
    </ul>
    <p class="hint">建议补齐缺失占位符，并保持模板简洁。</p>
  {/if}
</div>

<style>
  .template-lint { border: 1px solid #d7d7d7; border-radius: 8px; padding: 10px; }
  .ok { color: #1f7a3d; margin: 0; }
  .hint { color: #666; font-size: 12px; }
</style>
