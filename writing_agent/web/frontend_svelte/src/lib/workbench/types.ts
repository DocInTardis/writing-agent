export type PendingGenerateConfirmation = {
  requestPayload: Record<string, unknown>
  note: string
  reason: string
  riskLevel: string
  planSource: string
  operationsCount: number
}

export type ResumeState = {
  status: 'running' | 'interrupted'
  updated_at: number
  user_instruction: string
  request_instruction: string
  compose_mode: 'auto' | 'continue' | 'overwrite'
  partial_chars: number
  partial_preview: string
  plan_sections: string[]
  completed_sections: string[]
  pending_sections: string[]
  cursor_anchor: string
  error: string
}

export type GraphMeta = {
  path: 'route_graph'
  trace_id: string
  engine: string
  route_id: string
  route_entry: string
}

export type OriginalityRiskRow = {
  section: string
  section_id: string
  title: string
  phases: string[]
  checked_event_count: number
  failed_event_count: number
  rewrite_count: number
  retry_count: number
  cache_rejected_count: number
  fast_draft_rejected_count: number
  latest_passed: boolean
  max_repeat_sentence_ratio: number
  max_formulaic_opening_ratio: number
  max_source_overlap_ratio: number
}

export type OriginalitySummary = {
  enabled: boolean
  eventCount: number
  checkedSectionCount: number
  failedSectionCount: number
  failedSectionRatio: number
  rewriteCount: number
  retryCount: number
  cacheRejectedCount: number
  fastDraftRejectedCount: number
  rows: OriginalityRiskRow[]
}

export type WorkbenchSurface = 'chat' | 'library' | 'editor' | 'canvas'
export type WorkspaceMode = 'editor' | 'library' | 'collab'

export type LibraryCard = {
  id: string
  title: string
  summary: string
  status: 'synced' | 'draft' | 'review'
  status_label: string
  kind_label: string
  tone: 'azure' | 'gold' | 'violet' | 'teal'
  tags: string[]
  updated_at: number
  size_label: string
  action: 'editor' | 'citation' | 'metrics' | 'version' | 'assistant' | 'upload'
}

export type FeedbackItem = {
  id: string
  rating: number
  note: string
  stage: string
  tags?: string[]
  created_at: number
}

export type PlagiarismEvidence = {
  source_start: number
  reference_start: number
  match_chars: number
  snippet: string
}

export type PlagiarismResult = {
  reference_id: string
  reference_title: string
  score: number
  threshold: number
  suspected: boolean
  metrics: Record<string, any>
  evidence: PlagiarismEvidence[]
}

export type QualityAdviceAction =
  | 'open-ai-panel'
  | 'open-plagiarism-panel'
  | 'run-ai-check'
  | 'run-plagiarism-check'
  | 'revise-first-risk'

export type QualityAdviceItem = {
  id: string
  tone: 'good' | 'warn' | 'alert'
  title: string
  detail: string
  action?: QualityAdviceAction
  actionLabel?: string
}

export type QualityOverview = {
  tone: 'good' | 'warn' | 'alert'
  label: string
  note: string
}

export type InlinePanelTab = 'rewrite' | 'style' | 'assistant'

export type BlockSession = {
  tab: InlinePanelTab
  cmd: string
  styleFontSize: string
  styleLineHeight: string
  styleFontFamily: string
  styleColor: string
  styleBackground: string
  styleAlign: string
  styleFontWeight: string
  styleFontStyle: string
  candidates: Array<any>
  activeIndex: number
  originalText: string
  error: string
  dialogInput: string
}

export type QueuedInstruction = { id: number; text: string; createdAt: number }
