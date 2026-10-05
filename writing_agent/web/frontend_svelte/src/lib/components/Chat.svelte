<script lang="ts">
  import Icon from './Icon.svelte'
  import { instruction, chat, thoughtLog } from '../stores'

  let {
    variant = 'panel' as 'panel' | 'assistant',
    onsend,
    onupload
  }: {
    variant?: 'panel' | 'assistant'
    onsend?: (text: string) => void
    onupload?: (payload: { file: File }) => void
  } = $props()

  let showActivity = $state(false)
  let uploadInput: HTMLInputElement | null = null

  function handleSend() {
    const text = $instruction.trim()
    if (!text) return
    onsend?.(text)
    instruction.set('')
    queueMicrotask(() => document.querySelector('.chat-history')?.scrollTo({ top: 999999 }))
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
      event.preventDefault()
      handleSend()
    }
  }

  function handleUploadChange(event: Event) {
    const input = event.currentTarget as HTMLInputElement
    const file = input.files?.[0]
    if (file) onupload?.({ file })
    input.value = ''
  }
</script>

<div class={`chat-shell ${variant}`}>
  <div class="chat-tools">
    <span>针对当前文档提出修改要求；发送前不会改动正文。</span>
    {#if $thoughtLog.length > 0}
      <button onclick={() => (showActivity = !showActivity)}>{showActivity ? '收起记录' : `运行记录 ${$thoughtLog.length}`}</button>
    {/if}
  </div>

  {#if showActivity}
    <div class="activity" aria-label="运行记录">
      {#each $thoughtLog as item}
        <div><strong>{item.label}</strong><span>{item.time}</span><p>{item.detail}</p></div>
      {/each}
    </div>
  {/if}

  <div class="chat-history">
    {#if $chat.length === 0}
      <div class="chat-empty">
        <strong>可以直接说你想改什么</strong>
        <span>例如：压缩这段、检查论证、根据资料补充引用。</span>
      </div>
    {:else}
      {#each $chat as message}
        <div class={`chat-msg ${message.role}`}><div class="chat-bubble">{message.text}</div></div>
      {/each}
    {/if}
  </div>

  <div class="composer-shell">
    <textarea rows="4" bind:value={$instruction} onkeydown={handleKeydown} placeholder="描述修改要求；Shift+Enter 换行"></textarea>
    <div class="composer-actions">
      <button class="attach" onclick={() => uploadInput?.click()} title="添加到资料库">
        <Icon name="upload" size={14} /><span>添加资料</span>
      </button>
      <span>Enter 发送</span>
      <button class="send" onclick={handleSend} disabled={!$instruction.trim()}><Icon name="play" size={14} /><span>发送</span></button>
    </div>
  </div>
  <input class="hidden-input" type="file" accept="image/*,.doc,.docx,.pdf,.txt,.md,.html,.htm,.ppt,.pptx,.xls,.xlsx,.csv,.json" bind:this={uploadInput} onchange={handleUploadChange} />
</div>

<style>
  .chat-shell { display: flex; min-height: 0; flex: 1; flex-direction: column; gap: 12px; color: var(--wa-text); }
  .chat-shell.assistant { width: 100%; height: 100%; padding: 0; background: var(--wa-surface); }
  .chat-tools { display: flex; align-items: center; justify-content: space-between; gap: 10px; color: var(--wa-text-muted); font-size: 11px; }
  .chat-tools button { flex: none; padding: 4px 7px; border: 1px solid transparent; border-radius: var(--wa-radius); background: var(--wa-surface-subtle); color: var(--wa-text-secondary); cursor: pointer; }
  .activity { max-height: 150px; overflow: auto; padding: 9px; border: 1px solid var(--wa-border); border-radius: var(--wa-radius); background: var(--wa-surface-subtle); }
  .activity > div { display: grid; grid-template-columns: 1fr auto; gap: 2px 8px; padding: 5px; font-size: 11px; }
  .activity strong { color: var(--wa-text-secondary); }.activity span { color: var(--wa-text-muted); }.activity p { grid-column: 1 / -1; margin: 0; color: var(--wa-text-muted); line-height: 1.45; white-space: pre-wrap; }
  .chat-history { display: flex; min-height: 180px; flex: 1; flex-direction: column; gap: 8px; overflow: auto; padding: 4px 2px; }
  .chat-empty { display: grid; flex: 1; place-content: center; gap: 6px; color: var(--wa-text-muted); text-align: center; }.chat-empty strong { color: var(--wa-text-secondary); font-size: 13px; }.chat-empty span { font-size: 11px; }
  .chat-msg { display: flex; }.chat-msg.user { justify-content: flex-end; }
  .chat-bubble { max-width: 86%; padding: 9px 11px; border: 1px solid var(--wa-border); border-radius: var(--wa-radius-lg); background: var(--wa-surface-subtle); color: var(--wa-text-secondary); font-size: 12px; line-height: 1.55; white-space: pre-wrap; }
  .chat-msg.user .chat-bubble { border-color: var(--wa-accent); background: var(--wa-accent); color: #fff; }
  .composer-shell { padding: 8px; border: 1px solid var(--wa-border-strong); border-radius: var(--wa-radius-lg); background: var(--wa-surface); }
  .composer-shell:focus-within { border-color: var(--wa-accent); box-shadow: 0 0 0 2px rgba(37,99,235,.09); }
  .composer-shell textarea { width: 100%; resize: none; border: 0; background: transparent; color: var(--wa-text); outline: none; font-size: 13px; line-height: 1.5; }.composer-shell textarea::placeholder { color: var(--wa-text-muted); }
  .composer-actions { display: flex; align-items: center; gap: 8px; margin-top: 5px; }.composer-actions > span { margin-left: auto; color: var(--wa-text-muted); font-size: 10px; }.composer-actions button { display: inline-flex; min-height: 29px; align-items: center; gap: 6px; padding: 0 9px; border-radius: var(--wa-radius); cursor: pointer; font-size: 11px; }.attach { border: 0; background: var(--wa-surface-subtle); color: var(--wa-text-secondary); }.send { border: 1px solid var(--wa-accent); background: var(--wa-accent); color: #fff; }.send:disabled { opacity: .45; cursor: default; }
  .hidden-input { display: none; }
  @media (max-width: 900px) { .chat-shell.assistant { width: min(390px, calc(100vw - 24px)); } }
</style>
