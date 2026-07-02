import type { OriginalitySummary, PlagiarismResult, QualityAdviceItem, QualityOverview } from './types'

export type QualitySignals = {
  aiRateResult: Record<string, any> | null
  sectionOriginalitySummary: OriginalitySummary | null
  plagiarismLatestReport: Record<string, any> | null
  plagiarismResults: PlagiarismResult[]
  plagiarismMaxScore: number
  plagiarismFlaggedCount: number
}

export function normalizeScore(value: any): number {
  const n = Number(value || 0)
  if (!Number.isFinite(n)) return 0
  return Math.max(0, Math.min(1, n))
}

export function plagiarismRiskLabel(score: number): string {
  const s = normalizeScore(score)
  if (s >= 0.7) return '高风险'
  if (s >= 0.45) return '中风险'
  if (s >= 0.2) return '低风险'
  return '很低'
}

export function aiRateScore(aiRateResult: Record<string, any> | null): number {
  if (!aiRateResult || typeof aiRateResult !== 'object') return 0
  const direct = Number(aiRateResult.ai_rate)
  if (Number.isFinite(direct) && direct > 0) {
    return normalizeScore(direct)
  }
  const percent = Number(aiRateResult.ai_rate_percent)
  if (Number.isFinite(percent) && percent > 0) {
    return normalizeScore(percent / 100)
  }
  return 0
}

export function buildQualityOverview(signals: QualitySignals): QualityOverview {
  const aiScore = aiRateScore(signals.aiRateResult)
  const originalityRisk = normalizeScore(signals.sectionOriginalitySummary?.failedSectionRatio || 0)
  const plagiarismScore = normalizeScore(signals.plagiarismMaxScore)
  const worst = Math.max(aiScore, originalityRisk, plagiarismScore)
  if (!signals.aiRateResult && !signals.plagiarismLatestReport && !signals.sectionOriginalitySummary) {
    return {
      tone: 'good',
      label: '待检测',
      note: '运行检测后这里会汇总原创性与重合度风险'
    }
  }
  if (worst >= 0.55) {
    return {
      tone: 'alert',
      label: '需优先修订',
      note: '当前存在明显模板化或重合风险，建议先处理再导出'
    }
  }
  if (worst >= 0.25) {
    return {
      tone: 'warn',
      label: '建议复核',
      note: '结构可用，但仍有原创性或重合度信号需要人工确认'
    }
  }
  return {
    tone: 'good',
    label: '整体稳定',
    note: '当前结构、原创性和重合度信号没有明显异常'
  }
}

export function buildQualityAdviceItems(signals: QualitySignals): QualityAdviceItem[] {
  const items: QualityAdviceItem[] = []
  const aiScore = aiRateScore(signals.aiRateResult)
  const repeated3gramRatio = normalizeScore(signals.aiRateResult?.signals?.repeated_3gram_ratio)
  const lexicalDiversity = normalizeScore(signals.aiRateResult?.signals?.lexical_diversity)
  const burstiness = normalizeScore(signals.aiRateResult?.signals?.sentence_burstiness_cv)
  const failedRows = (signals.sectionOriginalitySummary?.rows || []).filter((row) => !row.latest_passed)
  const overlapRows = signals.plagiarismResults.filter((row) => row.suspected || row.score >= row.threshold)

  if (failedRows.length > 0) {
    const first = failedRows[0]
    items.push({
      id: 'hotspot-revise',
      tone: 'alert',
      title: `优先修订章节：${first.title || first.section}`,
      detail: `该章节触发了原创性热采样风险，先补充具体对象、时间、机制和结果，再重新检测。`,
      action: 'revise-first-risk',
      actionLabel: '定向修订'
    })
  }

  if (signals.aiRateResult && (Boolean(signals.aiRateResult.suspected_ai) || aiScore >= 0.45 || repeated3gramRatio >= 0.1)) {
    items.push({
      id: 'ai-style',
      tone: aiScore >= 0.6 || repeated3gramRatio >= 0.16 ? 'alert' : 'warn',
      title: '压缩模板化表达',
      detail: '优先改写连续重复的开头句、总分总套话和泛化过渡句，把段落改成“对象-动作-证据-结论”的具体表达。',
      action: 'open-ai-panel',
      actionLabel: '查看 AI 面板'
    })
  }

  if (signals.aiRateResult && ((lexicalDiversity > 0 && lexicalDiversity <= 0.42) || burstiness <= 0.18)) {
    items.push({
      id: 'ai-diversity',
      tone: 'warn',
      title: '提高词汇与句式多样性',
      detail: '不要只替换同义词。优先拆开长句、改变论证顺序，并引入具体案例、变量、时间窗和限制条件。',
      action: 'run-ai-check',
      actionLabel: '复测 AI 率'
    })
  }

  if (overlapRows.length > 0 || signals.plagiarismMaxScore >= 0.35) {
    items.push({
      id: 'plagiarism-overlap',
      tone: signals.plagiarismMaxScore >= 0.55 ? 'alert' : 'warn',
      title: '处理高重合片段',
      detail: `当前有 ${Math.max(overlapRows.length, signals.plagiarismFlaggedCount)} 个来源超过或接近阈值。优先重写证据后的分析句群，而不是仅删除引用。`,
      action: 'open-plagiarism-panel',
      actionLabel: '查看查重面板'
    })
  }

  if (!signals.aiRateResult) {
    items.push({
      id: 'run-ai',
      tone: 'good',
      title: '运行 AI 风险检测',
      detail: '先做一次检测，确认重复 3-gram、词汇多样性和句长波动是否已经回到正常范围。',
      action: 'run-ai-check',
      actionLabel: '开始检测'
    })
  }

  if (!signals.plagiarismLatestReport && signals.plagiarismResults.length === 0) {
    items.push({
      id: 'run-plag',
      tone: 'good',
      title: '运行查重或全库扫描',
      detail: '导出前至少对历史稿、参考文本或资料库做一次交叉比对，先发现高重合来源，再决定重写范围。',
      action: 'run-plagiarism-check',
      actionLabel: '开始查重'
    })
  }

  if (items.length === 0) {
    items.push({
      id: 'quality-stable',
      tone: 'good',
      title: '当前质量信号稳定',
      detail: '下一步建议做人工复核，重点看论证是否具体、引用是否准确、结论是否真正回应研究问题。'
    })
  }

  return items.slice(0, 4)
}
