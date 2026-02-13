<script lang="ts">
  import { toasts } from '../stores'
</script>

<div class="toast-root">
  {#each $toasts as t (t.id)}
    <div class="toast {t.type}">{t.message}</div>
  {/each}
</div>

<style>
  .toast-root {
    position: fixed;
    top: 16px;
    right: 16px;
    display: grid;
    gap: 8px;
    z-index: 50;
  }

  .toast {
    padding: 10px 14px;
    border-radius: 10px;
    color: #fff;
    font-size: 12px;
    box-shadow: 0 16px 30px rgba(15, 23, 42, 0.18);
  }

  .toast.info {
    background: #2563eb;
  }

  .toast.ok {
    background: #16a34a;
  }

  .toast.bad {
    background: #dc2626;
  }
</style>
