<script lang="ts">
  import { onMount } from 'svelte'

  export let fallback: string = '出现错误，请刷新页面重试'
  
  let hasError = false
  let errorMessage = ''

  onMount(() => {
    const handleError = (event: ErrorEvent) => {
      hasError = true
      errorMessage = event.error?.message || event.message || fallback
      console.error('捕获到错误:', event.error)
    }

    window.addEventListener('error', handleError)
    
    return () => {
      window.removeEventListener('error', handleError)
    }
  })
</script>

{#if hasError}
  <div class="error-boundary">
    <h2>这个面板暂时无法显示</h2>
    <p>正文和已经保存的内容不会因此丢失。</p>
    <details><summary>错误详情</summary><p class="error-message">{errorMessage}</p></details>
    <button class="btn-retry" onclick={() => window.location.reload()}>
      重新加载
    </button>
  </div>
{:else}
  <slot />
{/if}

<style>
  .error-boundary {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    min-height: 400px;
    padding: 40px;
    text-align: center;
    background: var(--wa-surface-subtle, #f7f8fa);
    border-radius: var(--wa-radius-lg, 10px);
    border: 1px solid var(--wa-border, #dde2e8);
  }

  h2 {
    color: var(--wa-text, #20242c);
    margin: 0 0 16px;
    font-size: 24px;
  }

  .error-message {
    color: var(--wa-danger, #b42318);
    font-size: 12px;
    font-family: ui-monospace, Consolas, monospace;
    background: var(--wa-danger-soft, #fff1f0);
    padding: 12px 20px;
    border-radius: 8px;
    margin: 16px 0;
    max-width: 600px;
  }

  details { max-width: 600px; color: var(--wa-text-muted, #76808f); }

  .btn-retry {
    margin-top: 24px;
    padding: 12px 32px;
    background: var(--wa-accent, #2563eb);
    color: #fff;
    border: none;
    border-radius: var(--wa-radius, 7px);
    font-size: 13px;
    cursor: pointer;
  }
</style>
