<script lang="ts">
  export let errorType = ''
  export let message = ''

  $: display = formatError(errorType, message)

  function formatError(kind: string, msg: string): string {
    const k = String(kind || '').toLowerCase()
    if (k.includes('timeout')) return 'Request timed out. You can retry with shorter sections.'
    if (k.includes('quota')) return 'Quota exceeded. Please retry later or switch model.'
    if (k.includes('citation')) return 'Citation verification failed. Open citation review panel to repair references.'
    if (k.includes('network')) return 'Network jitter detected. Session recovery is available.'
    return msg || 'Unexpected error.'
  }
</script>

<div class="error-path-panel">
  <h3>Error Path</h3>
  <p>{display}</p>
</div>

<style>
  .error-path-panel { border: 1px solid #e4b4b4; background: #fff6f6; border-radius: 8px; padding: 10px; }
  p { margin: 0; color: #7c2f2f; }
</style>
