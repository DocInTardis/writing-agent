<script lang="ts">
  import type { OriginalitySummary, ResumeState } from './types'
  import { summarizeOriginalitySummary } from './metadata'

  let {
    generating,
    progress,
    resumeState,
    sectionFailures,
    sectionOriginalitySummary,
    retrySection,
    reviseRiskSection
  }: {
    generating: boolean
    progress: { current: number; total: number; percent: number; etaS: number; section: string }
    resumeState: ResumeState | null
    sectionFailures: { section: string; reason: string }[]
    sectionOriginalitySummary: OriginalitySummary | null
    retrySection: (section: string) => void
    reviseRiskSection: (section: string) => void
  } = $props()
</script>

{#if generating && progress.total > 0}
  <div class="generation-banner">
    生成中 {progress.current}/{progress.total} · {progress.percent}% · 预计剩余 {Math.ceil(progress.etaS / 60)} 分 {progress.etaS % 60} 秒
  </div>
{/if}

{#if resumeState && !generating && resumeState.status === 'interrupted'}
  <div class="generation-banner">
    检测到未完成任务（已缓存约 {resumeState.partial_chars} 字）
    {#if resumeState.pending_sections && resumeState.pending_sections.length > 0}
      ，待续写章节：{resumeState.pending_sections.join(' / ')}
    {/if}
    。可点击“续跑”继续生成。
  </div>
{/if}

{#if sectionFailures.length > 0}
  <section class="section-failures">
    <div class="panel-title">失败章节</div>
    {#each sectionFailures as f}
      <div class="failure-row">
        <span>{f.section}</span>
        <button class="btn ghost" onclick={() => retrySection(f.section)}>重试</button>
      </div>
    {/each}
  </section>
{/if}

{#if sectionOriginalitySummary && (sectionOriginalitySummary.checkedSectionCount > 0 || sectionOriginalitySummary.rows.length > 0)}
  <section class="section-failures originality-panel">
    <div class="panel-title">原创性风险热区</div>
    <div class="panel-sub">{summarizeOriginalitySummary(sectionOriginalitySummary)}</div>
    {#each sectionOriginalitySummary.rows as row}
      <div class="risk-row">
        <div>
          <div class="risk-title">{row.title || row.section}</div>
          <div class="risk-metrics">
            <span>失败 {row.failed_event_count}</span>
            <span>重写 {row.rewrite_count}</span>
            <span>重试 {row.retry_count}</span>
            <span>套话率 {Math.round(row.max_formulaic_opening_ratio * 100)}%</span>
          </div>
        </div>
        <div class="risk-actions">
          <span class:ok={row.latest_passed} class:bad={!row.latest_passed} class="risk-badge">
            {row.latest_passed ? '已通过' : '待处理'}
          </span>
          <button class="btn ghost" onclick={() => reviseRiskSection(row.title || row.section)}>定向修订</button>
        </div>
      </div>
    {/each}
  </section>
{/if}
