<script lang="ts">
  export let templateText = ''
  $: warnings = lintTemplate(templateText)

  function lintTemplate(text: string): string[] {
    const t = String(text || '')
    const out: string[] = []
    if (!t.includes('{{title}}')) out.push('missing variable: {{title}}')
    if (!t.includes('{{body}}')) out.push('missing variable: {{body}}')
    if (t.length > 10000) out.push('template too long (>10k chars)')
    return out
  }
</script>

<div class="template-lint">
  <h3>Template Lint</h3>
  {#if warnings.length === 0}
    <p class="ok">No issues detected.</p>
  {:else}
    <ul>
      {#each warnings as row}
        <li>{row}</li>
      {/each}
    </ul>
    <p class="hint">Auto-fix suggestion: add missing placeholders and keep template concise.</p>
  {/if}
</div>

<style>
  .template-lint { border: 1px solid #d7d7d7; border-radius: 8px; padding: 10px; }
  .ok { color: #1f7a3d; margin: 0; }
  .hint { color: #666; font-size: 12px; }
</style>
