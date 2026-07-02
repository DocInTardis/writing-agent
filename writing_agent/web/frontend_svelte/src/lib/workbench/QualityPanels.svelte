<script lang="ts">
  import type { FeedbackItem, PlagiarismResult, QualityAdviceItem, QualityOverview } from './types'

  let {
    qualityAdviceItems,
    qualityOverview,
    runQualityAdviceAction,
    showAiRatePanel,
    aiRateThreshold = $bindable(0.65),
    aiRateLoading,
    aiRateResult,
    runAiRateCheck,
    showPlagiarismPanel,
    plagiarismThreshold = $bindable(0.35),
    plagiarismReferenceDocIds = $bindable(''),
    plagiarismReferenceText = $bindable(''),
    plagiarismLoading,
    plagiarismLibraryLoading,
    plagiarismResults,
    plagiarismMaxScore,
    plagiarismFlaggedCount,
    plagiarismLatestReport,
    runPlagiarismCheck,
    runPlagiarismLibraryScan,
    downloadPlagiarismReport,
    plagiarismRiskLabel,
    showFeedbackPanel,
    satisfactionRating = $bindable(0),
    satisfactionStage = $bindable('general'),
    satisfactionNote = $bindable(''),
    satisfactionSaving,
    lastLowFeedbackRecorded,
    feedbackItems,
    submitSatisfaction,
    formatFeedbackTime
  }: {
    qualityAdviceItems: QualityAdviceItem[]
    qualityOverview: QualityOverview
    runQualityAdviceAction: (action?: any) => void
    showAiRatePanel: boolean
    aiRateThreshold: number
    aiRateLoading: boolean
    aiRateResult: Record<string, any> | null
    runAiRateCheck: () => void
    showPlagiarismPanel: boolean
    plagiarismThreshold: number
    plagiarismReferenceDocIds: string
    plagiarismReferenceText: string
    plagiarismLoading: boolean
    plagiarismLibraryLoading: boolean
    plagiarismResults: PlagiarismResult[]
    plagiarismMaxScore: number
    plagiarismFlaggedCount: number
    plagiarismLatestReport: Record<string, any> | null
    runPlagiarismCheck: () => void
    runPlagiarismLibraryScan: () => void
    downloadPlagiarismReport: (format: 'json' | 'md' | 'csv') => void
    plagiarismRiskLabel: (score: number) => string
    showFeedbackPanel: boolean
    satisfactionRating: number
    satisfactionStage: string
    satisfactionNote: string
    satisfactionSaving: boolean
    lastLowFeedbackRecorded: number
    feedbackItems: FeedbackItem[]
    submitSatisfaction: () => void
    formatFeedbackTime: (ts: number) => string
  } = $props()
</script>
{#if qualityAdviceItems.length > 0}
        <section class="feedback-panel quality-advice-panel">
          <div class="feedback-panel-head">
            <div>
              <div class="panel-title">原创性修订建议</div>
              <div class="panel-sub">这里汇总的是质量改进建议，不是检测规避指令。</div>
            </div>
            <span class={`quality-overview-badge tone-${qualityOverview.tone}`}>{qualityOverview.label}</span>
          </div>
          <div class="quality-advice-note">{qualityOverview.note}</div>
          <div class="quality-advice-grid">
            {#each qualityAdviceItems as item}
              <article class={`quality-advice-card tone-${item.tone}`}>
                <div class="quality-advice-title-row">
                  <div class="quality-advice-title">{item.title}</div>
                  <span class={`quality-tone-chip tone-${item.tone}`}>
                    {item.tone === 'good' ? '稳定' : item.tone === 'warn' ? '关注' : '优先'}
                  </span>
                </div>
                <div class="quality-advice-detail">{item.detail}</div>
                {#if item.action && item.actionLabel}
                  <div class="quality-advice-actions">
                    <button class="btn ghost btn-sm" onclick={() => runQualityAdviceAction(item.action)}>
                      {item.actionLabel}
                    </button>
                  </div>
                {/if}
              </article>
            {/each}
          </div>
        </section>
      {/if}

      {#if showAiRatePanel}
        <section class="feedback-panel ai-rate-panel">
          <div class="feedback-panel-head">
            <div>
              <div class="panel-title">AI 率检测</div>
              <div class="panel-sub">基于 burstiness、重复率、词汇熵、连接词密度等信号估计。</div>
            </div>
          </div>
          <div class="feedback-form">
            <div class="plagiarism-grid">
              <label class="feedback-label" for="ai-rate-threshold">判定阈值</label>
              <input
                id="ai-rate-threshold"
                type="number"
                min="0.05"
                max="0.95"
                step="0.01"
                bind:value={aiRateThreshold}
                data-testid="ai-rate-threshold"
              />
              <span class="panel-sub">建议 0.65，结果仅作为风险提示</span>
            </div>
            <div class="feedback-actions">
              <button
                class="btn primary"
                onclick={runAiRateCheck}
                disabled={aiRateLoading}
                data-testid="ai-rate-run"
              >
                {aiRateLoading ? '检测中...' : '开始 AI 率检测'}
              </button>
              {#if aiRateResult}
                <span class="feedback-tip">
                  估计 AI 率 {Math.round(Number(aiRateResult.ai_rate || 0) * 100)}%，
                  风险 {String(aiRateResult.risk_level || '未知')}，
                  置信度 {Math.round(Number(aiRateResult.confidence || 0) * 100)}%
                </span>
              {/if}
            </div>
            {#if aiRateResult}
              <div class="plagiarism-item">
                <div class="plagiarism-item-head">
                  <span>阈值 {Math.round(Number(aiRateResult.threshold || 0.65) * 100)}%</span>
                  <span class:danger={Boolean(aiRateResult.suspected_ai)}>
                    判定 {Boolean(aiRateResult.suspected_ai) ? '疑似AI生成' : '未超阈值'}
                  </span>
                </div>
                <div class="plagiarism-item-metrics">
                  <span>重复率 {Math.round(Number(aiRateResult.signals?.repeated_3gram_ratio || 0) * 100)}%</span>
                  <span>词汇多样性 {Math.round(Number(aiRateResult.signals?.lexical_diversity || 0) * 100)}%</span>
                  <span>熵 {Math.round(Number(aiRateResult.signals?.token_entropy_norm || 0) * 100)}%</span>
                  <span>句长波动 {Math.round(Number(aiRateResult.signals?.sentence_burstiness_cv || 0) * 100)}%</span>
                </div>
                {#if Array.isArray(aiRateResult.evidence) && aiRateResult.evidence.length > 0}
                  <div class="plagiarism-evidence">
                    依据：{String(aiRateResult.evidence[0] || '')}
                  </div>
                {/if}
                <div class="panel-sub">{String(aiRateResult.note || '')}</div>
              </div>
            {/if}
          </div>
        </section>
      {/if}

      {#if showPlagiarismPanel}
        <section class="feedback-panel plagiarism-panel">
          <div class="feedback-panel-head">
            <div>
              <div class="panel-title">内容查重检测</div>
              <div class="panel-sub">算法：n-gram + Winnowing + SimHash 混合评分，建议阈值 0.35。</div>
            </div>
          </div>
          <div class="feedback-form">
            <div class="plagiarism-grid">
              <label class="feedback-label" for="plag-threshold">判定阈值</label>
              <input
                id="plag-threshold"
                type="number"
                min="0.05"
                max="0.95"
                step="0.01"
                bind:value={plagiarismThreshold}
                data-testid="plagiarism-threshold"
              />
              <label class="feedback-label" for="plag-docids">参考文档ID</label>
              <input
                id="plag-docids"
                type="text"
                bind:value={plagiarismReferenceDocIds}
                placeholder="多个ID用逗号或空格分隔"
                data-testid="plagiarism-docids"
              />
            </div>
            <div class="feedback-row">
              <span class="feedback-label">参考文本</span>
              <textarea
                bind:value={plagiarismReferenceText}
                rows="4"
                maxlength="30000"
                placeholder="可粘贴外部资料、历史稿件或样本文本用于查重"
                data-testid="plagiarism-text"
              ></textarea>
            </div>
            <div class="feedback-actions">
              <button
                class="btn primary"
                onclick={runPlagiarismCheck}
                disabled={plagiarismLoading}
                data-testid="plagiarism-run"
              >
                {plagiarismLoading ? '检测中...' : '开始查重'}
              </button>
              <button
                class="btn ghost"
                onclick={runPlagiarismLibraryScan}
                disabled={plagiarismLibraryLoading}
                data-testid="plagiarism-library-run"
              >
                {plagiarismLibraryLoading ? '全库扫描中...' : '全库查重'}
              </button>
              {#if plagiarismResults.length > 0}
                <span class="feedback-tip">
                  最高重复分数 {Math.round(plagiarismMaxScore * 100)}%，
                  风险等级 {plagiarismRiskLabel(plagiarismMaxScore)}，
                  超阈值来源 {plagiarismFlaggedCount} 个
                </span>
              {/if}
            </div>

            {#if plagiarismLatestReport}
              <div class="plagiarism-report-actions">
                <span class="panel-sub">
                  报告ID {plagiarismLatestReport.report_id} · 来源 {plagiarismLatestReport.total_references} · 超阈值 {plagiarismLatestReport.flagged_count}
                </span>
                <button class="btn ghost" onclick={() => downloadPlagiarismReport('json')}>下载 JSON</button>
                <button class="btn ghost" onclick={() => downloadPlagiarismReport('md')}>下载 MD</button>
                <button class="btn ghost" onclick={() => downloadPlagiarismReport('csv')}>下载 CSV</button>
              </div>
            {/if}

            {#if plagiarismResults.length > 0}
              <div class="plagiarism-results">
                {#each plagiarismResults as row}
                  <div class="plagiarism-item">
                    <div class="plagiarism-item-head">
                      <span>
                        {row.reference_title || row.reference_id}
                        {#if row.reference_id}
                          <em>({row.reference_id})</em>
                        {/if}
                      </span>
                      <span class:danger={row.suspected}>
                        分数 {Math.round(row.score * 100)}% / 阈值 {Math.round(row.threshold * 100)}%
                      </span>
                    </div>
                    <div class="plagiarism-item-metrics">
                      <span>Containment {Math.round((Number(row.metrics?.containment || 0)) * 100)}%</span>
                      <span>Jaccard {Math.round((Number(row.metrics?.jaccard_resemblance || 0)) * 100)}%</span>
                      <span>Winnowing {Math.round((Number(row.metrics?.winnowing_overlap || 0)) * 100)}%</span>
                      <span>Longest {Number(row.metrics?.longest_match_chars || 0)} chars</span>
                    </div>
                    {#if row.evidence && row.evidence.length > 0}
                      <div class="plagiarism-evidence">
                        证据片段：{String(row.evidence[0]?.snippet || '').slice(0, 120)}
                      </div>
                    {/if}
                  </div>
                {/each}
              </div>
            {/if}
          </div>
        </section>
      {/if}

      {#if showFeedbackPanel}
        <section class="feedback-panel">
          <div class="feedback-panel-head">
            <div>
              <div class="panel-title">用户满意度</div>
              <div class="panel-sub">1 分最低，5 分最高；低分样本会进入学习池。</div>
            </div>
          </div>
          <div class="feedback-form">
            <div class="feedback-row">
              <span class="feedback-label">评分</span>
              <div class="rating-group">
                {#each [1, 2, 3, 4, 5] as score}
                  <button
                    class={`rating-btn ${satisfactionRating === score ? 'active' : ''}`}
                    data-testid={`rating-${score}`}
                    onclick={() => (satisfactionRating = score)}
                    type="button"
                  >
                    {score}
                  </button>
                {/each}
              </div>
              <span class="feedback-label">阶段</span>
              <select data-testid="feedback-stage" bind:value={satisfactionStage}>
                <option value="general">通用反馈</option>
                <option value="stage1">阶段1 生成</option>
                <option value="stage2">阶段2 修改</option>
                <option value="final">最终版本</option>
              </select>
            </div>
            <div class="feedback-row">
              <span class="feedback-label">备注</span>
              <textarea
                data-testid="feedback-note"
                bind:value={satisfactionNote}
                rows="2"
                maxlength="600"
                placeholder="可选：不满意点、缺失点、改进建议"
              ></textarea>
            </div>
            <div class="feedback-actions">
              <button
                class="btn primary"
                data-testid="feedback-submit"
                onclick={submitSatisfaction}
                disabled={satisfactionSaving}
              >
                {satisfactionSaving ? '提交中...' : '提交评分'}
              </button>
              {#if lastLowFeedbackRecorded > 0}
                <span class="feedback-tip">已记录低满意度样本 {lastLowFeedbackRecorded} 条</span>
              {/if}
            </div>
            {#if feedbackItems.length > 0}
              <div class="feedback-history">
                <div class="panel-sub">最近反馈</div>
                {#each feedbackItems.slice(0, 5) as item}
                  <div class="feedback-item">
                    <div class="feedback-item-head">
                      <span>{item.rating}/5 · {item.stage}</span>
                      <span>{formatFeedbackTime(item.created_at)}</span>
                    </div>
                    {#if item.note}
                      <div class="feedback-item-note">{item.note}</div>
                    {/if}
                  </div>
                {/each}
              </div>
            {/if}
          </div>
        </section>
      {/if}

