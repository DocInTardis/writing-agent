<script lang="ts">
  export let open = false
  export let title = ''
  export let onClose: () => void
</script>

{#if open}
  <button type="button" class="modal-backdrop" aria-label="关闭" onclick={onClose}></button>
  <div class="modal" role="dialog" aria-modal="true">
    <div class="modal-header">
      <div class="modal-title">{title}</div>
      <button class="btn ghost" onclick={onClose}>关闭</button>
    </div>
    <div class="modal-body">
      <slot></slot>
    </div>
  </div>
{/if}

<style>
  .modal-backdrop {
    position: fixed;
    inset: 0;
    border: 0;
    background: rgba(21, 31, 46, 0.28);
    z-index: 60;
  }

  .modal {
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: min(560px, 92vw);
    max-height: min(760px, 88vh);
    overflow: auto;
    border: 1px solid var(--wa-border, #dde2e8);
    background: var(--wa-surface, #fff);
    color: var(--wa-text, #20242c);
    border-radius: var(--wa-radius-lg, 10px);
    box-shadow: var(--wa-shadow-float, 0 18px 48px rgba(21,31,46,.16));
    z-index: 61;
    padding: 0;
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    min-height: 52px;
    padding: 0 18px;
    border-bottom: 1px solid var(--wa-border, #dde2e8);
  }

  .modal-title {
    font-size: 16px;
    font-weight: 600;
  }
  .modal-body { padding: 18px; }
</style>
