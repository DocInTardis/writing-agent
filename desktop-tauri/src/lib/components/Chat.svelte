<script lang="ts">
  import Icon from './Icon.svelte'
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
        <span class="assistant-dot"><Icon name="spark" size={12} /></span>
        智能助手
      </div>
      <button class="assistant-toggle" onclick={toggleThoughts}>
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
    <button class="attach-btn" onclick={triggerUpload}>
      <Icon name="upload" size={13} className="btn-icon" />
      <span>上传内容</span>
    </button>
    <span class="composer-tip">支持图片与文档</span>
  </div>
  <div class="composer">
    <textarea
      rows="3"
      bind:value={$instruction}
      onkeydown={handleKeydown}
      placeholder="输入需求或修改指令"
    ></textarea>
    <button class="send-btn" onclick={handleSend}>
      <Icon name="play" size={14} className="btn-icon" />
      <span>发送</span>
    </button>
  </div>
  <input
    class="hidden-input"
    type="file"
    accept="image/*,.doc,.docx,.pdf,.txt,.md,.html,.htm,.ppt,.pptx,.xls,.xlsx,.csv,.json"
    bind:this={uploadInput}
    onchange={handleUploadChange}
  />
</div>

<style>
  .chat-shell {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .chat-shell.assistant {
    width: 360px;
    height: 560px;
    padding: 14px;
    border-radius: 22px;
    background:
      none, transparent 72%),
      #faf9f7;
    border: 1px solid rgba(231, 229, 228, 1);
    box-shadow:
      0 24px 54px rgba(0, 0, 0, 0.01),
      none;
    
  }

  .assistant-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 2px 2px 4px;
  }

  .assistant-title {
    font-size: 13px;
    letter-spacing: 0.03em;
    color: rgba(168, 162, 158, 0.94);
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .assistant-dot {
    width: 16px;
    height: 16px;
    border-radius: 50%;
    color: #86efac;
    background: rgba(22, 163, 74, 0.18);
    box-shadow: 0 0 0 4px rgba(22, 163, 74, 0.14);
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  .assistant-toggle {
    border: 1px solid rgba(231, 229, 228, 1);
    background: rgba(245, 243, 240, 0.74);
    color: rgba(210, 225, 248, 0.88);
    padding: 5px 9px;
    border-radius: 999px;
    font-size: 11px;
    cursor: pointer;
  }

  .assistant-toggle:hover {
    border-color: rgba(217, 119, 6, 0.3);
    background: rgba(245, 243, 240, 0.84);
  }

  .panel-title {
    font-weight: 600;
  }

  .thoughts {
    padding: 10px;
    border-radius: 14px;
    border: 1px dashed rgba(231, 229, 228, 1);
    background: rgba(245, 243, 240, 0.74);
  }

  .thoughts-title {
    font-size: 12px;
    color: rgba(168, 162, 158, 0.76);
    margin-bottom: 6px;
  }

  .thought-list {
    max-height: 132px;
    overflow: auto;
    display: grid;
    gap: 8px;
  }

  .thought-item {
    background: rgba(245, 243, 240, 0.84);
    border-radius: 10px;
    border: 1px solid rgba(149, 175, 214, 0.24);
    padding: 8px 10px;
    font-size: 12px;
    box-shadow: none;
  }

  .thought-meta {
    display: flex;
    justify-content: space-between;
    color: rgba(168, 162, 158, 0.75);
    margin-bottom: 4px;
  }

  .detail {
    color: #1c1917;
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
    max-width: 86%;
    padding: 9px 12px;
    border-radius: 13px;
    border: 1px solid rgba(149, 176, 216, 0.24);
    background: rgba(19, 33, 59, 0.84);
    color: rgba(168, 162, 158, 0.92);
    font-size: 12px;
    line-height: 1.45;
    box-shadow: 0 10px 16px rgba(0, 0, 0, 0.01);
  }

  .chat-msg.user .chat-bubble {
    border-color: rgba(172, 208, 255, 0.6);
    background: linear-gradient(132deg, rgba(217, 119, 6, 0.94), rgba(217, 119, 6, 0.9));
    color: #fff;
    box-shadow: 0 12px 18px rgba(217, 119, 6, 0.3);
  }

  .composer {
    display: flex;
    gap: 8px;
    align-items: stretch;
  }

  .composer-tools {
    display: flex;
    align-items: center;
    gap: 8px;
  }

  .attach-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border: 1px solid rgba(231, 229, 228, 1);
    background: rgba(23, 36, 63, 0.82);
    color: rgba(168, 162, 158, 0.9);
    border-radius: 10px;
    padding: 7px 10px;
    font-size: 12px;
    cursor: pointer;
  }

  .attach-btn:hover {
    border-color: rgba(160, 205, 255, 0.62);
    background: rgba(36, 53, 89, 0.88);
  }

  .composer-tip {
    font-size: 11px;
    color: rgba(182, 200, 230, 0.72);
  }

  .composer textarea {
    flex: 1;
    border: 1px solid rgba(151, 179, 218, 0.28);
    border-radius: 12px;
    padding: 10px;
    font-size: 12px;
    line-height: 1.45;
    background: rgba(14, 24, 45, 0.86);
    color: #1c1917;
    outline: none;
  }

  .composer textarea::placeholder {
    color: rgba(168, 162, 158, 0.72);
  }

  .composer textarea:focus {
    border-color: rgba(217, 119, 6, 0.2);
    box-shadow: 0 0 0 3px rgba(217, 119, 6, 0.2);
  }

  .send-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border: 1px solid rgba(177, 208, 255, 0.54);
    background: linear-gradient(132deg, rgba(217, 119, 6, 0.96), rgba(217, 119, 6, 0.92));
    color: #fff;
    border-radius: 12px;
    padding: 0 15px;
    min-width: 56px;
    font-weight: 600;
    cursor: pointer;
    box-shadow: 0 12px 20px rgba(217, 119, 6, 0.28);
  }

  .send-btn:hover {
    transform: translateY(-1px);
    box-shadow: 0 14px 24px rgba(217, 119, 6, 0.34);
  }

  .btn-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    line-height: 1;
  }

  .hidden-input {
    display: none;
  }

  @media (max-width: 900px) {
    .chat-shell.assistant {
      width: min(360px, calc(100vw - 24px));
      height: min(560px, calc(100vh - 110px));
      border-radius: 18px;
    }
  }
</style>
