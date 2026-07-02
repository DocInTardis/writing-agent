<script lang="ts">
  import Chat from '../components/Chat.svelte'

  let {
    badgeCount,
    onClose,
    onKeydown,
    onSend,
    onUpload
  }: {
    badgeCount: number
    onClose: () => void
    onKeydown: (event: KeyboardEvent) => void
    onSend: (text: string) => void
    onUpload: (event: any) => void
  } = $props()
</script>

<div class="assistant-sheet-backdrop" role="presentation">
  <button type="button" class="sheet-backdrop-hit" onclick={onClose} aria-label="关闭智能助手"></button>
  <div class="assistant-sheet" role="dialog" aria-modal="true" aria-label="智能助手" tabindex="-1" onkeydown={onKeydown}>
    <div class="assistant-sheet-head">
      <div>
        <div class="panel-title">智能助手</div>
        <div class="panel-sub">快捷键：Ctrl/Cmd + K</div>
      </div>
      {#if badgeCount > 0}
        <span class="assistant-queue-badge">{badgeCount}</span>
      {/if}
      <button class="btn ghost btn-sm" onclick={onClose}>关闭</button>
    </div>
    <Chat variant="assistant" onsend={onSend} onupload={onUpload} />
  </div>
</div>
