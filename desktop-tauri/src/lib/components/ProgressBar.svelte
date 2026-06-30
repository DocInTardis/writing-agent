<script lang="ts">
  export let progress: number = 0 // 0-100
  export let indeterminate: boolean = false
</script>

<div class="progress-container">
  {#if indeterminate}
    <div class="progress-bar indeterminate"></div>
  {:else}
    <div class="progress-bar" style="width: {Math.min(100, Math.max(0, progress))}%"></div>
  {/if}
</div>

<style>
  .progress-container {
    width: 100%;
    height: 4px;
    background: rgba(200, 180, 150, 0.2);
    border-radius: 2px;
    overflow: hidden;
    position: relative;
  }

  .progress-bar {
    height: 100%;
    background: linear-gradient(90deg, #a5722a 0%, #8b7355 50%, #a5722a 100%);
    background-size: 200% 100%;
    transition: width 0.3s ease;
    border-radius: 2px;
  }

  .progress-bar.indeterminate {
    width: 40%;
    animation: indeterminate 1.5s infinite;
  }

  @keyframes indeterminate {
    0% {
      transform: translateX(-100%);
    }
    100% {
      transform: translateX(350%);
    }
  }
</style>
