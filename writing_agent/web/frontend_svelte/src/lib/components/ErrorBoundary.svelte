<script lang="ts">
  import { onMount } from 'svelte'

  export let fallback: string = '出现错误，请刷新页面重试'
  
  let hasError = false
  let errorMessage = ''

  onMount(() => {
    const handleError = (event: ErrorEvent) => {
      hasError = true
      errorMessage = event.error?.message || event.message || '未知错误'
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
    <div class="error-icon">⚠️</div>
    <h2>抱歉，出现了一些问题</h2>
    <p class="error-message">{errorMessage}</p>
    <div class="error-suggestion">
      建议：
      <ul>
        <li>刷新页面重试</li>
        <li>检查网络连接</li>
        <li>清除浏览器缓存</li>
        <li>如问题持续，请联系技术支持</li>
      </ul>
    </div>
    <button class="btn-retry" on:click={() => window.location.reload()}>
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
    background: rgba(255, 243, 224, 0.6);
    border-radius: 16px;
    border: 2px solid rgba(200, 100, 100, 0.3);
  }

  .error-icon {
    font-size: 64px;
    margin-bottom: 20px;
    animation: shake 0.5s ease;
  }

  @keyframes shake {
    0%, 100% { transform: translateX(0); }
    25% { transform: translateX(-10px); }
    75% { transform: translateX(10px); }
  }

  h2 {
    color: #8b4513;
    margin: 0 0 16px;
    font-size: 24px;
  }

  .error-message {
    color: #d32f2f;
    font-size: 14px;
    font-family: 'Courier New', monospace;
    background: rgba(211, 47, 47, 0.1);
    padding: 12px 20px;
    border-radius: 8px;
    margin: 16px 0;
    max-width: 600px;
  }

  .error-suggestion {
    text-align: left;
    max-width: 500px;
    color: #6b5d45;
    line-height: 1.6;
  }

  .error-suggestion ul {
    margin-top: 8px;
  }

  .btn-retry {
    margin-top: 24px;
    padding: 12px 32px;
    background: linear-gradient(135deg, #8b7355 0%, #6b5d45 100%);
    color: #fff;
    border: none;
    border-radius: 12px;
    font-size: 16px;
    cursor: pointer;
    transition: transform 0.2s, box-shadow 0.2s;
  }

  .btn-retry:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 16px rgba(139, 115, 85, 0.3);
  }
</style>
