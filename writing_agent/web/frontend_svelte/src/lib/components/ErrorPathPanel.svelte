<script lang="ts">
  let { errorType = '', message = '' } = $props()

  let display = $derived(formatError(errorType, message))

  function formatError(kind: string, msg: string): string {
    const k = String(kind || '').toLowerCase()
    if (k.includes('timeout')) return '请求超时。建议缩短单次处理内容后重试。'
    if (k.includes('quota')) return '配额已用尽，请稍后重试或切换模型。'
    if (k.includes('citation')) return '引用核验失败。请打开引用审查面板修复参考文献。'
    if (k.includes('network')) return '检测到网络波动，可尝试使用会话恢复功能。'
    return msg || '发生未预期错误。'
  }
</script>

<div class="error-path-panel">
  <h3>错误路径</h3>
  <p>{display}</p>
</div>

<style>
  .error-path-panel { border: 1px solid #e4b4b4; background: #fff6f6; border-radius: 8px; padding: 10px; }
  p { margin: 0; color: #7c2f2f; }
</style>
