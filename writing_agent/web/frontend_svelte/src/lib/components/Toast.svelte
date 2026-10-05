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
    border-radius: var(--wa-radius, 7px);
    color: #fff;
    font-size: 12px;
    box-shadow: var(--wa-shadow-float, 0 18px 48px rgba(21,31,46,.16));
  }

  .toast.info {
    background: #315d98;
  }

  .toast.ok {
    background: var(--wa-success, #177245);
  }

  .toast.bad {
    background: var(--wa-danger, #b42318);
  }
</style>
