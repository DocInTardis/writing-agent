<script lang="ts">
  import type { PendingGenerateConfirmation } from './types'

  let {
    confirmation,
    busy,
    onCancel,
    onConfirm
  }: {
    confirmation: PendingGenerateConfirmation
    busy: boolean
    onCancel: () => void
    onConfirm: () => void
  } = $props()
</script>

<div class="confirm-overlay" role="dialog" aria-modal="true" aria-label="高风险编辑确认">
  <section class="confirm-dialog">
    <div class="panel-title">检测到高风险编辑</div>
    <div class="panel-sub">
      风险等级 {confirmation.riskLevel} · 计划来源 {confirmation.planSource}
      · 操作数 {confirmation.operationsCount}
    </div>
    <div class="confirm-note">
      {confirmation.note || '该请求会执行高风险文本改动，请确认是否继续。'}
    </div>
    <div class="confirm-actions">
      <button class="btn ghost" onclick={onCancel} disabled={busy}>取消</button>
      <button class="btn primary danger" onclick={onConfirm} disabled={busy}>
        {busy ? '执行中...' : '确认执行'}
      </button>
    </div>
  </section>
</div>
