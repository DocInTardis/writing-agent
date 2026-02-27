<script lang="ts">
  import { instruction, chat, thoughtLog } from '../stores'
  import { createEventDispatcher } from 'svelte'

  const dispatch = createEventDispatcher<{
    send: string
    upload: { file: File }
  }>()
  export let variant: 'panel' | 'assistant' = 'panel'
  let showThoughts = true
  let uploadInput: HTMLInputElement | null = null

  function handleSend() {
    const text = $instruction.trim()
    if (!text) return
    dispatch('send', text)
    instruction.set('')
    tickScroll()
  }

  function handleKeydown(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  function toggleThoughts() {
    showThoughts = !showThoughts
    tickScroll()
  }

  function tickScroll() {
    queueMicrotask(() => {
      const el = document.querySelector('.chat-history')
      if (el) el.scrollTop = el.scrollHeight
      const thoughts = document.querySelector('.thought-list')
      if (thoughts) thoughts.scrollTop = thoughts.scrollHeight
    })
  }

  function triggerUpload() {
    uploadInput?.click()
  }

  function handleUploadChange(event: Event) {
    const input = event.currentTarget as HTMLInputElement | null
    const file = input?.files?.[0]
    if (!file) return
    dispatch('upload', { file })
    if (input) input.value = ''
  }
</script>

<div class={`chat-shell ${variant}`}>
  {#if variant === 'assistant'}
    <div class="assistant-header">
      <div class="assistant-title">
        <span class="assistant-dot"></span>
        智能助手
      </div>
      <button class="assistant-toggle" on:click={toggleThoughts}>
        {showThoughts ? '隐藏思考' : '思考链'}
      </button>
    </div>
  {:else}
    <div class="panel-title">对话写作</div>
  {/if}

  {#if showThoughts}
    <div class="thoughts">
      <div class="thoughts-title">思考链</div>
      <div class="thought-list">
        {#each $thoughtLog as t}
          <div class="thought-item">
            <div class="thought-meta">
              <span class="label">{t.label}</span>
              <span class="time">{t.time}</span>
            </div>
            <div class="detail">{t.detail}</div>
          </div>
        {/each}
      </div>
    </div>
  {/if}

  <div class="chat-history">
    {#each $chat as m}
      <div class="chat-msg {m.role}">
        <div class="chat-bubble">{m.text}</div>
      </div>
    {/each}
  </div>
  <div class="composer-tools">
    <button class="attach-btn" on:click={triggerUpload}>上传内容</button>
    <span class="composer-tip">支持图片与文档</span>
  </div>
  <div class="composer">
    <textarea
      rows="3"
      bind:value={$instruction}
      on:keydown={handleKeydown}
      placeholder="输入需求或修改指令"
    ></textarea>
    <button class="send-btn" on:click={handleSend}>发送</button>
  </div>
  <input
    class="hidden-input"
    type="file"
    accept="image/*,.doc,.docx,.pdf,.txt,.md,.html,.htm,.ppt,.pptx,.xls,.xlsx,.csv,.json"
    bind:this={uploadInput}
    on:change={handleUploadChange}
  />
</div>

<style>
  .chat-shell {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .chat-shell.assistant {
    width: 320px;
    height: 520px;
    padding: 14px;
    border-radius: 28px;
    background: linear-gradient(160deg, rgba(255, 255, 255, 0.98), rgba(241, 246, 255, 0.95));
    border: 1px solid rgba(148, 163, 184, 0.25);
    box-shadow: 0 24px 60px rgba(15, 23, 42, 0.2);
  }

  .assistant-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .assistant-title {
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .assistant-dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: #22c55e;
    box-shadow: 0 0 0 4px rgba(34, 197, 94, 0.18);
  }

  .assistant-toggle {
    border: none;
    background: rgba(15, 23, 42, 0.08);
    padding: 4px 8px;
    border-radius: 999px;
    font-size: 11px;
    cursor: pointer;
  }

  .panel-title {
    font-weight: 600;
  }

  .thoughts {
    padding: 10px;
    border-radius: 16px;
    border: 1px dashed rgba(148, 163, 184, 0.4);
    background: rgba(255, 255, 255, 0.7);
  }

  .thoughts-title {
    font-size: 12px;
    color: rgba(51, 65, 85, 0.7);
    margin-bottom: 6px;
  }

  .thought-list {
    max-height: 120px;
    overflow: auto;
    display: grid;
    gap: 8px;
  }

  .thought-item {
    background: rgba(255, 255, 255, 0.9);
    border-radius: 12px;
    padding: 8px 10px;
    font-size: 12px;
    box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.18);
  }

  .thought-meta {
    display: flex;
    justify-content: space-between;
    color: rgba(51, 65, 85, 0.7);
    margin-bottom: 4px;
  }

  .detail {
    color: #0f172a;
    white-space: pre-wrap;
  }

  .chat-history {
    flex: 1;
    overflow: auto;
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding-right: 4px;
  }

  .chat-msg {
    display: flex;
  }

  .chat-msg.user {
    justify-content: flex-end;
  }

  .chat-bubble {
    max-width: 80%;
    padding: 8px 12px;
    border-radius: 14px;
    background: rgba(255, 255, 255, 0.9);
    font-size: 12px;
    box-shadow: 0 8px 16px rgba(15, 23, 42, 0.12);
  }

  .chat-msg.user .chat-bubble {
    background: linear-gradient(135deg, rgba(37, 99, 235, 0.9), rgba(14, 165, 233, 0.9));
    color: #fff;
  }

  .composer {
    display: flex;
    gap: 8px;
  }

  .composer-tools {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .attach-btn {
    border: 1px solid rgba(148, 163, 184, 0.35);
    background: rgba(255, 255, 255, 0.88);
    color: #0f172a;
    border-radius: 10px;
    padding: 6px 10px;
    font-size: 12px;
    cursor: pointer;
  }

  .composer-tip {
    font-size: 11px;
    color: rgba(71, 85, 105, 0.9);
  }

  .composer textarea {
    flex: 1;
    border: 1px solid rgba(148, 163, 184, 0.3);
    border-radius: 12px;
    padding: 10px;
    font-size: 12px;
    background: rgba(255, 255, 255, 0.85);
  }

  .send-btn {
    border: none;
    background: linear-gradient(135deg, #2563eb, #38bdf8);
    color: #fff;
    border-radius: 12px;
    padding: 0 14px;
    cursor: pointer;
  }

  .hidden-input {
    display: none;
  }
</style>
