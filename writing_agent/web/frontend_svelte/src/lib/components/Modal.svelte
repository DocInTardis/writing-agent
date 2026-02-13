<script lang="ts">
  export let open = false
  export let title = ''
  export let onClose: () => void
</script>

{#if open}
  <button type="button" class="modal-backdrop" aria-label="关闭" on:click={onClose}></button>
  <div class="modal" role="dialog" aria-modal="true">
    <div class="modal-header">
      <div class="modal-title">{title}</div>
      <button class="btn ghost" on:click={onClose}>关闭</button>
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
    background: rgba(15, 23, 42, 0.4);
    z-index: 60;
  }

  .modal {
    position: fixed;
    top: 10%;
    left: 50%;
    transform: translateX(-50%);
    width: min(560px, 92vw);
    background: rgba(255, 255, 255, 0.96);
    border-radius: 16px;
    box-shadow: 0 24px 70px rgba(15, 23, 42, 0.28);
    z-index: 61;
    padding: 16px;
  }

  .modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
  }

  .modal-title {
    font-size: 16px;
    font-weight: 600;
  }
</style>
