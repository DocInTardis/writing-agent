<script lang="ts">
  import { onMount } from 'svelte'
  import Chat from './lib/components/Chat.svelte'
  import Editor from './lib/components/Editor.svelte'
  import DiagramCanvas from './lib/components/DiagramCanvas.svelte'
  import Toast from './lib/components/Toast.svelte'
  import Settings from './lib/components/Settings.svelte'
  import LLMConfig from './lib/components/LLMConfig.svelte'
  import Icon from './lib/components/Icon.svelte'
  import DocList from './lib/components/DocList.svelte'
  import LoadingSkeleton from './lib/components/LoadingSkeleton.svelte'
  import ProgressBar from './lib/components/ProgressBar.svelte'
  import ErrorBoundary from './lib/components/ErrorBoundary.svelte'
  import CitationManager from './lib/components/CitationManager.svelte'
  import PerformanceMetrics from './lib/components/PerformanceMetrics.svelte'
  import { initWasmEngine, isWasmAvailable } from './lib/engine/wasmLoader'
  import { textToDocIr, docIrToMarkdown } from './lib/utils/markdown'
  import {
    buildGenerateRequestPayload,
    sanitizeAiDocumentText,
    sanitizeAiInputText,
    sanitizeAiSelectionPayload,
    sanitizeAiStringList
  } from './lib/utils/ai_payload'
  import {
    appendChat,
    docId,
    docStatus,
    flowStatus,
    generating,
    instruction,
    loadChat,
    loadThoughts,
    pushThought,
    pushToast,
    ribbonOpen,
    sourceText,
    docIr,
    docIrDirty,
    editorCommand,
    wordCount,
    thinkingSummary,
    thinkingSteps,
    thinkingMissing,
    darkMode,
    isLoading
  } from './lib/stores'
  import type { EditorCommand } from './lib/types'
  import type {
    BlockSession,
    FeedbackItem,
    GraphMeta,
    InlinePanelTab,
    LibraryCard,
    OriginalitySummary,
    PendingGenerateConfirmation,
    PlagiarismResult,
    QualityAdviceAction,
    QualityAdviceItem,
    QualityOverview,
    QueuedInstruction,
    ResumeState,
    WorkbenchSurface,
    WorkspaceMode
  } from './lib/workbench/types'

  let aborter = $state<AbortController | null>(null)
  let writeBuffer = $state('')
  let writeTimer = $state<ReturnType<typeof setTimeout> | null>(null)
  let docIrRefreshTimer = $state<ReturnType<typeof setTimeout> | null>(null)
  let streamingLive = $state(false)
  let typingActive = $state(false)
  let streamQueue = $state<Array<{ section: string; raw: boolean; text: string }>>([])
  let streamTimer = $state<ReturnType<typeof setTimeout> | null>(null)
  let streamToken = $state(0)
  let streamPendingChars = $state(0)
  let streamFastDrain = $state(false)
  let streamTypingActive = $state(false)
  let pendingFinalText = $state<string | null>(null)
  let pendingFinalDocIr = $state<Record<string, unknown> | null>(null)
  let genStartTs = $state(0)
  let lastEventName = $state('')
  let lastProgressMsg = $state('')
  let sawFinal = $state(false)
  let sawError = $state(false)
  let sawSectionDelta = $state(false)
  let lastEventAt = $state(0)
  let lastEventGap = $state(0)
  let maxEventGap = $state(0)
  let baseIdleMs = $state(90000)
  let stallTimer = $state<ReturnType<typeof setInterval> | null>(null)
  let fallbackTriggered = $state(false)
  let progress = $state({ current: 0, total: 0, percent: 0, etaS: 0, section: "" })
  let progressStart = $state(0)
  let progressEvents = $state<number[]>([])
  let sectionFailures = $state<{ section: string; reason: string }[]>([])
  let sectionOriginalitySummary = $state<OriginalitySummary | null>(null)
  let pendingGenerateConfirmation = $state<PendingGenerateConfirmation | null>(null)
  let confirmDialogBusy = $state(false)
  let planConfirmDecision = $state<'approved' | 'interrupted'>('approved')
  let planConfirmScore = $state(5)
  let planConfirmNote = $state('')
  let leftWidth = $state(46)
  let resizing = $state(false)
  let autoSaveTimer: ReturnType<typeof setTimeout> | null = null
  let partialSaveTimer = $state<ReturnType<typeof setTimeout> | null>(null)
  let partialSaveInFlight = $state(false)
  let partialSavedSnapshot = $state('')
  let lastSavedText = $state('')
  let lastSavedDocIr = $state<Record<string, unknown> | null>(null)
  let resumeState = $state<ResumeState | null>(null)
  let lastGraphMeta = $state<GraphMeta | null>(null)
  let surfaceTab = $state<WorkbenchSurface>('editor')
  let workspaceMode = $state<WorkspaceMode>('editor')
  let libraryViewMode = $state<'grid' | 'masonry' | 'list'>('grid')
  let librarySearch = $state('')
  let librarySelectAll = $state(false)
  let selectedLibraryCardId = $state('')
  let filteredLibraryCards = $state<LibraryCard[]>([])

  let hideLibraryInfo = $state(false)
  let infoDrawerOpen = $state(false)
  let showDocList = $state(false)
  let showCitations = $state(false)
  let showPerformanceMetrics = $state(false)
  let showVersions = $state(false)
  let showFeedbackPanel = $state(false)
  let feedbackItems = $state<FeedbackItem[]>([])
  let satisfactionRating = $state(0)
  let satisfactionStage = $state('general')
  let satisfactionNote = $state('')
  let satisfactionSaving = $state(false)
  let lastLowFeedbackRecorded = $state(0)
  let showPlagiarismPanel = $state(false)
  let plagiarismLoading = $state(false)
  let plagiarismLibraryLoading = $state(false)
  let plagiarismThreshold = $state(0.35)
  let plagiarismReferenceDocIds = $state('')
  let plagiarismReferenceText = $state('')
  let showAiRatePanel = $state(false)
  let aiRateLoading = $state(false)
  let aiRateThreshold = $state(0.65)
  let aiRateResult = $state<Record<string, any> | null>(null)
  let plagiarismResults = $state<PlagiarismResult[]>([])
  let plagiarismFlaggedCount = $state(0)
  let plagiarismMaxScore = $state(0)
  let plagiarismLatestReport = $state<Record<string, any> | null>(null)
  let versionLoading = $state(false)
  let versionList = $state<Array<any>>([])
  let versionGroups = $state<Array<any>>([])
  let versionDiff = $state('')
  let versionDiffFrom = $state('')
  let versionDiffTo = $state('')
  let versionTree = $state('')
  let versionMessage = $state('')
  let versionError = $state('')
  let assistantOpen = $state(false)
  let showAdvancedToolbar = $state(false)
  let canvasOpen = $state(false)
  let selectedBlockId = $state('')
  let selectedBlockIds = $state<string[]>([])
  let selectedBlocks = $state<Array<{
    id: string
    text: string
    style: Record<string, string>
    kind?: 'block' | 'section' | 'title'
    sectionId?: string
    sectionTitle?: string
  }>>([])
  let selectedBlockText = $state('')
  let blockStyleFontSize = $state('')
  let blockStyleLineHeight = $state('')
  let blockStyleFontFamily = $state('')
  let blockStyleColor = $state('')
  let blockStyleBackground = $state('')
  let blockStyleAlign = $state('')
  let blockStyleFontWeight = $state('')
  let blockStyleFontStyle = $state('')
  let blockEditCmd = $state('')
  let inlinePanelTab = $state<'rewrite' | 'style' | 'assistant'>('rewrite')
  let blockPreviewBusy = $state(false)
  let blockEditError = $state('')
  let blockOriginalText = $state('')
  let blockCandidates = $state<Array<any>>([])
  let activeCandidateIndex = $state(0)

  let blockDialogInput = $state('')
  const blockSessionStore = new Map<string, BlockSession>()
  let activeBlockSessionKey = $state('')
  let inlineBarVisible = $state(false)
  let inlineBarLeft = $state(0)
  let inlineBarTop = $state(0)
  let inlinePopoverOpen = $state(false)
  let inlinePopoverPlacement = $state<'up' | 'down'>('down')
  let inlinePopoverLeft = $state(0)
  let inlinePopoverTop = $state(0)
  let activeStreamingSections = $state<string[]>([])
  let completedStreamingSections = $state<string[]>([])
  let inlineEditLocked = $state(false)
  let inlineEditLockReason = $state('')
  let uploadImageInput = $state<HTMLInputElement | null>(null)
  let libraryUploadInput = $state<HTMLInputElement | null>(null)
  let pendingInlineImageTargets = $state<string[]>([])
  let renderActivityAt = $state(Date.now())
  let editorToolbarState = $state({
    focused: false,
    readonly: false,
    bold: false,
    italic: false,
    underline: false,
    hasSelection: false,
    canUndo: false,
    canRedo: false,
    canCopy: false,
    canCut: false,
    canPaste: false
  })
  let queuedInstructionSeed = $state(0)
  let queuedGlobalInstructions = $state<QueuedInstruction[]>([])
  let drainingQueuedGlobalInstructions = $state(false)
  let recentQueuedBadgeCount = $state(0)
  let recentQueuedBadgeTimer = $state<ReturnType<typeof setTimeout> | null>(null)
  let lastGenerateStartedAt = $state(0)
  let assistantBadgeCount = $derived(
    queuedGlobalInstructions.length || recentQueuedBadgeCount || ($generating || typingActive || streamTypingActive ? 1 : 0)
  )
  let rustEngineReadyLocal = $state(false)
  let wasmInitPromise = $state<Promise<boolean> | null>(null)
  if (typeof window !== 'undefined') {
    document.body.setAttribute('data-engine', 'rust')
  }

  function startWasmInit() {
    if (!wasmInitPromise) {
      wasmInitPromise = initWasmEngine()
        .then((success) => {
          rustEngineReadyLocal = success
          return success
        })
        .catch(() => {
          rustEngineReadyLocal = false
          return false
        })
    }
    return wasmInitPromise
  }


  function readDocId(): string {
    const w = window as Window & { __DOC_ID__?: string }
    if (w.__DOC_ID__) return String(w.__DOC_ID__)
    const bodyId = document.body?.getAttribute('data-doc-id')
    if (bodyId) return bodyId
    const fromMeta = document.querySelector('meta[name="doc-id"]')?.getAttribute('content')
    return fromMeta || ''
  }

  function formatElapsed() {
    if (!genStartTs) return new Date().toLocaleTimeString()
    const ms = Date.now() - genStartTs
    const total = Math.max(0, Math.floor(ms / 1000))
    const m = String(Math.floor(total / 60)).padStart(2, '0')
    const s = String(total % 60).padStart(2, '0')
    return `+${m}:${s}`
  }

  function mapStateName(name: string) {
    const n = (name || '').toUpperCase()
    if (n === 'PLAN') return '规划'
    if (n === 'WRITE') return '写作'
    if (n === 'DONE') return '完成'
    if (n === 'STOPPED') return '已停止'
    return name
  }

  function normalizeSectionKey(raw: string) {
    return decodeSectionTitle(String(raw || ''))
      .trim()
      .replace(/^#+\s*/, '')
      .replace(/^h[23]::/i, '')
      .replace(/\s+/g, '')
      .replace(/[：:，,。.!?？；;、（）()【】\[\]《》"'“”‘’]/g, '')
      .toLowerCase()
  }

  function isGenerationOrRenderBusy() {
    return $generating || typingActive || streamTypingActive || Date.now() - lastGenerateStartedAt < 1200
  }

  function hasMeaningfulDocContent(text: string) {
    const src = String(text || '').trim()
    if (!src) return false
    const stripped = src
      .replace(/[`~*#>\-\[\]\(\)_=|]/g, '')
      .replace(/\s+/g, '')
      .replace(/[，。！？；：,.!?;:]/g, '')
    return stripped.length >= 8
  }

  function inferComposeMode(inst: string): 'continue' | 'overwrite' | null {
    const text = String(inst || '').trim()
    if (!text) return null
    if (
      /(?:全文|整篇|整文|全部|从头).{0,4}(?:重写|改写)|覆盖重写|推倒重写|重新写一份|(?:rewrite|redo|start over|from scratch|replace).{0,14}(?:entire|whole|full|document|draft)|(?:entire|whole|full).{0,14}(?:rewrite|redo|replace)|overwrite(?:\s+the)?(?:\s+whole|\s+entire|\s+full)?(?:\s+document|\s+draft)?/i.test(
        text
      )
    ) {
      return 'overwrite'
    }
    if (
      /(?:续写|接着写|继续写|接续写|在原文基础上继续|延续写|(?:continue|keep writing|carry on|extend|add more|build on).{0,14}(?:current|existing|draft|document|text|content)?|(?:based on|on top of)\s+(?:the\s+)?(?:existing|current))/i.test(
        text
      )
    ) {
      return 'continue'
    }
    return null
  }

  function normalizeStringArray(raw: unknown): string[] {
    if (!Array.isArray(raw)) return []
    const out: string[] = []
    const seen = new Set<string>()
    for (const item of raw) {
      const v = String(item || '').trim()
      if (!v || seen.has(v)) continue
      seen.add(v)
      out.push(v)
    }
    return out
  }

  function normalizeResumeState(raw: any): ResumeState | null {
    if (!raw || typeof raw !== 'object') return null
    const status = String(raw.status || '').trim().toLowerCase()
    if (status !== 'running' && status !== 'interrupted') return null
    const composeModeRaw = String(raw.compose_mode || 'auto').trim().toLowerCase()
    const composeMode =
      composeModeRaw === 'continue' || composeModeRaw === 'overwrite' || composeModeRaw === 'auto'
        ? (composeModeRaw as ResumeState['compose_mode'])
        : 'auto'
    return {
      status: status as ResumeState['status'],
      updated_at: Number(raw.updated_at || 0),
      user_instruction: String(raw.user_instruction || '').trim(),
      request_instruction: String(raw.request_instruction || '').trim(),
      compose_mode: composeMode,
      partial_chars: Number(raw.partial_chars || 0),
      partial_preview: String(raw.partial_preview || '').trim(),
      plan_sections: normalizeStringArray(raw.plan_sections),
      completed_sections: normalizeStringArray(raw.completed_sections),
      pending_sections: normalizeStringArray(raw.pending_sections),
      cursor_anchor: String(raw.cursor_anchor || '').trim(),
      error: String(raw.error || '').trim()
    }
  }

  function normalizeGraphMeta(raw: unknown): GraphMeta | null {
    if (!raw || typeof raw !== 'object') return null
    const obj = raw as Record<string, unknown>
    const path = String(obj.path || '').trim()
    if (path !== 'route_graph') return null
    return {
      path: 'route_graph',
      trace_id: String(obj.trace_id || '').trim(),
      engine: String(obj.engine || '').trim(),
      route_id: String(obj.route_id || '').trim(),
      route_entry: String(obj.route_entry || '').trim()
    }
  }

  function summarizeGraphMeta(meta: GraphMeta) {
    const routeId = meta.route_id || 'default'
    const routeEntry = meta.route_entry || 'planner'
    const engine = meta.engine || 'legacy'
    const trace = meta.trace_id ? meta.trace_id.slice(0, 8) : '-'
    return `route=${routeId}; entry=${routeEntry}; engine=${engine}; trace=${trace}`
  }

  function normalizeOriginalitySummary(raw: unknown): OriginalitySummary | null {
    if (!raw || typeof raw !== 'object') return null
    const obj = raw as Record<string, unknown>
    const rowsRaw = Array.isArray(obj.rows) ? obj.rows : []
    const rows: OriginalityRiskRow[] = rowsRaw
      .filter((row) => row && typeof row === 'object')
      .map((row) => {
        const item = row as Record<string, unknown>
        return {
          section: String(item.section || '').trim(),
          section_id: String(item.section_id || '').trim(),
          title: String(item.title || item.section || '').trim(),
          phases: Array.isArray(item.phases) ? item.phases.map((v) => String(v || '').trim()).filter(Boolean) : [],
          checked_event_count: Number(item.checked_event_count || 0),
          failed_event_count: Number(item.failed_event_count || 0),
          rewrite_count: Number(item.rewrite_count || 0),
          retry_count: Number(item.retry_count || 0),
          cache_rejected_count: Number(item.cache_rejected_count || 0),
          fast_draft_rejected_count: Number(item.fast_draft_rejected_count || 0),
          latest_passed: Boolean(item.latest_passed ?? true),
          max_repeat_sentence_ratio: Number(item.max_repeat_sentence_ratio || 0),
          max_formulaic_opening_ratio: Number(item.max_formulaic_opening_ratio || 0),
          max_source_overlap_ratio: Number(item.max_source_overlap_ratio || 0)
        }
      })
    return {
      enabled: Boolean(obj.enabled ?? false),
      eventCount: Number(obj.event_count || 0),
      checkedSectionCount: Number(obj.checked_section_count || 0),
      failedSectionCount: Number(obj.failed_section_count || 0),
      failedSectionRatio: Number(obj.failed_section_ratio || 0),
      rewriteCount: Number(obj.rewrite_count || 0),
      retryCount: Number(obj.retry_count || 0),
      cacheRejectedCount: Number(obj.cache_rejected_count || 0),
      fastDraftRejectedCount: Number(obj.fast_draft_rejected_count || 0),
      rows
    }
  }

  function summarizeOriginalitySummary(summary: OriginalitySummary | null) {
    if (!summary) return '原创性热采样未启用'
    return `已检查 ${summary.checkedSectionCount} 节 · 风险 ${summary.failedSectionCount} 节 · 重写 ${summary.rewriteCount} 次 · 重试 ${summary.retryCount} 次`
  }

  function focusAssistantInput() {
    queueMicrotask(() => {
      const input = document.querySelector('.assistant-sheet .composer textarea') as HTMLTextAreaElement | null
      if (input) input.focus()
    })
  }

  function setAssistantOpen(next: boolean) {
    assistantOpen = next
    if (assistantOpen) focusAssistantInput()
  }

  function toggleAssistantOpen() {
    setAssistantOpen(!assistantOpen)
  }

  function switchWorkspaceMode(mode: WorkspaceMode) {
    workspaceMode = mode
    if (mode === 'library') {
      showDocList = true
    }
    if (mode !== 'collab') {
      setAssistantOpen(false)
    }
    if (mode === 'editor') {
      canvasOpen = false
    }
  }

  function openInfoDrawer() {
    infoDrawerOpen = true
  }

  function closeInfoDrawer() {
    infoDrawerOpen = false
  }

  function toggleInfoDrawer() {
    infoDrawerOpen = !infoDrawerOpen
  }

  function runBatchFromToolbar() {
    switchWorkspaceMode('library')
    pushToast('已切换到资料模式，可继续执行批处理。', 'info')
  }

  function switchSurface(tab: WorkbenchSurface) {
    surfaceTab = tab
    if (tab === 'chat') {
      switchWorkspaceMode('collab')
      setAssistantOpen(true)
      return
    }
    if (tab === 'canvas') {
      canvasOpen = true
      return
    }
    if (tab === 'library') {
      switchWorkspaceMode('library')
      return
    }
    if (tab === 'editor') {
      switchWorkspaceMode('editor')
    }
  }

  function guessDocTitle(text: string) {
    const src = String(text || '')
    const m = src.match(/^\s*#\s+(.+)$/m)
    if (m && m[1]) return m[1].trim()
    return '未命名文档'
  }

  function estimateKb(text: string) {
    const chars = String(text || '').length
    const bytes = chars * 2
    return Math.max(1, Math.round(bytes / 1024))
  }

  function metaPreviewSnippet() {
    const selected = selectedTargetPlainText()
    if (selected) return selected.slice(0, 140)
    return String($sourceText || '').replace(/\s+/g, ' ').trim().slice(0, 140)
  }

  function formatLibraryCardTime(ts: number) {
    const now = Date.now()
    const diff = Math.max(0, now - Number(ts || 0))
    const minute = 60 * 1000
    const hour = 60 * minute
    const day = 24 * hour
    if (diff < minute) return '刚刚更新'
    if (diff < hour) return `${Math.floor(diff / minute)} 分钟前`
    if (diff < day) return `${Math.floor(diff / hour)} 小时前`
    return `${Math.floor(diff / day)} 天前`
  }

  function buildTopStatusLine() {
    const parts: string[] = []
    parts.push($docStatus || '未加载')
    parts.push(`${Math.max(0, Number($wordCount || 0))} 词`)
    if (lastGraphMeta?.route_id || lastGraphMeta?.route_entry || lastGraphMeta?.engine) {
      parts.push(
        `路由 ${lastGraphMeta?.route_id || '默认'}/${lastGraphMeta?.route_entry || 'planner'} · ${lastGraphMeta?.engine || 'legacy'}`
      )
    }
    if (feedbackItems.length > 0) {
      parts.push(`满意度 ${feedbackItems[0].rating}/5`)
    }
    if (plagiarismResults.length > 0) {
      parts.push(`查重峰值 ${Math.round(plagiarismMaxScore * 100)}%`)
    }
    return parts.join(' · ')
  }

  function buildLibraryCards(): LibraryCard[] {
    const now = Date.now()
    const docTitle = guessDocTitle($sourceText)
    const wordLabel = `${Math.max(1, Number($wordCount || 0))} 词`
    const routeLabel = lastGraphMeta?.route_id ? `路由:${lastGraphMeta.route_id}` : '路由:default'
    const feedbackLabel =
      feedbackItems.length > 0 ? `满意度 ${feedbackItems[0].rating}/5` : '待收集反馈'
    const cards: LibraryCard[] = [
      {
        id: 'doc-main',
        title: docTitle,
        summary: metaPreviewSnippet() || '当前文档正文摘要',
        status: 'draft',
        status_label: '草稿',
        kind_label: '正文',
        tone: 'azure',
        tags: ['当前文档', routeLabel, feedbackLabel],
        updated_at: now - 2 * 60 * 1000,
        size_label: wordLabel,
        action: 'editor'
      },
      {
        id: 'route-context',
        title: '路由与上下文策略',
        summary: lastGraphMeta ? summarizeGraphMeta(lastGraphMeta) : '默认图路由生效，可用于追踪生成链路。',
        status: 'synced',
        status_label: '已同步',
        kind_label: '策略',
        tone: 'teal',
        tags: ['图路由', '上下文窗口', '可追踪'],
        updated_at: now - 17 * 60 * 1000,
        size_label: '策略卡',
        action: 'metrics'
      },
      {
        id: 'citation-kit',
        title: '引用与证据包',
        summary: '维护引用、脚注与来源一致性，导出前建议先核验。',
        status: 'review',
        status_label: '待核验',
        kind_label: '引用',
        tone: 'gold',
        tags: ['引用', '脚注', '导出检查'],
        updated_at: now - 48 * 60 * 1000,
        size_label: '证据集',
        action: 'citation'
      },
      {
        id: 'version-archive',
        title: '版本归档',
        summary: versionGroups.length > 0
          ? `已记录 ${versionGroups.length} 组版本，可随时回退。`
          : '尚未创建版本，建议在关键阶段手动归档。',
        status: versionGroups.length > 0 ? 'synced' : 'draft',
        status_label: versionGroups.length > 0 ? '已同步' : '草稿',
        kind_label: '版本',
        tone: 'violet',
        tags: ['回滚', '对比', '里程碑'],
        updated_at: now - 2 * 60 * 60 * 1000,
        size_label: `${versionGroups.length} 组`,
        action: 'version'
      },
      {
        id: 'asset-upload',
        title: '上传新素材',
        summary: '支持图片、文档、模板上传，自动纳入资料库并可插入正文。',
        status: 'draft',
        status_label: '待上传',
        kind_label: '素材',
        tone: 'azure',
        tags: ['图片', '文档', '模板'],
        updated_at: now - 8 * 60 * 60 * 1000,
        size_label: '上传入口',
        action: 'upload'
      }
    ]
    return cards
  }

  function openLibraryCard(card: LibraryCard) {
    selectedLibraryCardId = card.id
    if (card.action === 'editor') {
      switchSurface('editor')
      return
    }
    if (card.action === 'citation') {
      showCitations = true
      return
    }
    if (card.action === 'metrics') {
      showPerformanceMetrics = true
      return
    }
    if (card.action === 'version') {
      void openVersions()
      return
    }
    if (card.action === 'assistant') {
      switchWorkspaceMode('collab')
      setAssistantOpen(true)
      return
    }
    if (card.action === 'upload') {
      triggerLibraryUpload()
    }
  }

  function cardMatchesSearch(card: LibraryCard, query: string) {
    if (!query) return true
    const q = query.toLowerCase()
    const haystack = `${card.title} ${card.summary} ${card.tags.join(' ')}`.toLowerCase()
    return haystack.includes(q)
  }

  $effect(() => {
    const cards = buildLibraryCards()
    const query = librarySearch.trim()
    filteredLibraryCards = cards.filter((card) => cardMatchesSearch(card, query))
    if (!librarySelectAll && selectedLibraryCardId && !filteredLibraryCards.some((card) => card.id === selectedLibraryCardId)) {
      selectedLibraryCardId = ''
    }
  })

  let topStatusLine = $derived(buildTopStatusLine())
  let qualityOverview = $derived(buildQualityOverview())
  let qualityAdviceItems = $derived(buildQualityAdviceItems())

  function selectedSectionKeys() {
    const out: string[] = []
    const seen = new Set<string>()
    for (const block of selectedBlocks) {
      const key = normalizeSectionKey(block.sectionTitle || block.sectionId || '')
      if (!key || seen.has(key)) continue
      seen.add(key)
      out.push(key)
    }
    return out
  }

  function markStreamingSection(section: string, phase: string) {
    const key = normalizeSectionKey(section)
    if (!key) return
    if (phase === 'start') {
      if (!activeStreamingSections.includes(key)) {
        activeStreamingSections = [...activeStreamingSections, key]
      }
      return
    }
    if (phase === 'end') {
      activeStreamingSections = activeStreamingSections.filter((x) => x !== key)
      if (!completedStreamingSections.includes(key)) {
        completedStreamingSections = [...completedStreamingSections, key]
      }
    }
  }

  function resetStreamingSections() {
    activeStreamingSections = []
    completedStreamingSections = []
  }

  function canEditSelectedBlocksNow() {
    if (!isGenerationOrRenderBusy()) return true
    if (!$generating) return false
    const keys = selectedSectionKeys()
    if (!keys.length) return false
    return keys.every((key) => completedStreamingSections.includes(key) && !activeStreamingSections.includes(key))
  }

  function ensureInlineEditAllowed(actionLabel: string) {
    if (canEditSelectedBlocksNow()) return true
    const msg = inlineEditLockReason || `生成中，暂不支持${actionLabel}`
    blockEditError = msg
    pushToast(msg, 'info')
    return false
  }

  function queueGlobalInstruction(inst: string) {
    const next: QueuedInstruction = {
      id: ++queuedInstructionSeed,
      text: inst,
      createdAt: Date.now()
    }
    queuedGlobalInstructions = [...queuedGlobalInstructions, next].slice(-20)
    recentQueuedBadgeCount = Math.max(1, queuedGlobalInstructions.length)
    if (recentQueuedBadgeTimer) clearTimeout(recentQueuedBadgeTimer)
    recentQueuedBadgeTimer = setTimeout(() => {
      if (!queuedGlobalInstructions.length) recentQueuedBadgeCount = 0
      recentQueuedBadgeTimer = null
    }, 3000)
    appendChat('system', `当前正在生成，已加入待执行队列（${queuedGlobalInstructions.length}）`)
    pushToast(`已排队（${queuedGlobalInstructions.length}）`, 'info')
    queueMicrotask(() => {
      void drainQueuedGlobalInstructions()
    })
  }

  async function drainQueuedGlobalInstructions() {
    if (drainingQueuedGlobalInstructions) return
    if (!queuedGlobalInstructions.length) return
    drainingQueuedGlobalInstructions = true
    let busySince = 0
    let autoRecovered = false
    try {
      while (queuedGlobalInstructions.length) {
        if (isGenerationOrRenderBusy()) {
          if (!busySince) busySince = Date.now()
          const waited = Date.now() - busySince
          const staleRender =
            !$generating &&
            (typingActive || streamTypingActive) &&
            !streamQueue.length &&
            pendingFinalText === null &&
            Date.now() - renderActivityAt > 2500
          if (staleRender) {
            resetStreamTyping()
            if (!autoRecovered) {
              pushToast('检测到渲染状态卡住，已自动恢复并继续执行排队指令。', 'info')
              autoRecovered = true
            }
          } else if (waited > 150000) {
            generating.set(false)
            resetStreamTyping()
            if (!autoRecovered) {
              pushToast('排队指令等待超时，已强制恢复并继续。', 'info')
              autoRecovered = true
            }
          }
          await new Promise((resolve) => setTimeout(resolve, 100))
          continue
        }
        busySince = 0
        const [next, ...rest] = queuedGlobalInstructions
        queuedGlobalInstructions = rest
        appendChat('system', `开始执行排队指令（剩余 ${queuedGlobalInstructions.length}）`)
        await handleGenerate(next.text, { fromQueue: true })
      }
    } finally {
      drainingQueuedGlobalInstructions = false
    }
  }

  function pushWritingDelta(deltaText: string) {
    const chunk = String(deltaText || '')
    if (!chunk.trim()) return
    if (chunk.length < 8 && !/[\w\u4e00-\u9fa5]/.test(chunk)) return
    renderActivityAt = Date.now()
    writeBuffer += chunk
    if (writeTimer) clearTimeout(writeTimer)
    writeTimer = setTimeout(() => {
      const preview = writeBuffer.slice(-120)
      pushThought('写作', preview, formatElapsed())
      writeBuffer = ''
      writeTimer = null
    }, 500)
  }

  function scheduleDocIrRefresh(nextText?: string, force?: boolean) {
    if (!force && !streamingLive && !typingActive) return
    const snapshot = String(nextText ?? $sourceText ?? '')
    if (docIrRefreshTimer) clearTimeout(docIrRefreshTimer)
    docIrRefreshTimer = setTimeout(() => {
      if (!force && !streamingLive && !typingActive) return
      const doc = textToDocIr(snapshot)
      if (doc) {
        const normalized = normalizeDocIrParagraphBlocks(doc)
        docIr.set(normalized)
        docIrDirty.set(false)
      }
    }, 120)
  }

  function resetStreamTyping() {
    streamQueue = []
    streamPendingChars = 0
    streamFastDrain = false
    streamTypingActive = false
    pendingFinalText = null
    pendingFinalDocIr = null
    streamToken += 1
    typingActive = false
    if (streamTimer) {
      clearTimeout(streamTimer)
      streamTimer = null
    }
  }

  function streamTypingSpeed() {
    let chunk = 26
    let delayMs = 14
    if (streamPendingChars > 1600) {
      chunk = 120
      delayMs = 6
    } else if (streamPendingChars > 700) {
      chunk = 72
      delayMs = 8
    } else if (streamPendingChars > 260) {
      chunk = 46
      delayMs = 11
    }
    if (streamFastDrain) {
      chunk = Math.max(chunk, 140)
      delayMs = Math.min(delayMs, 5)
    }
    return { chunk, delayMs }
  }

  function applyStreamChunk(section: string, chunk: string, raw: boolean) {
    sourceText.update((cur) => {
      const base = String(cur || '')
      const next = raw ? base + chunk : insertDeltaIntoSection(base, section, chunk)
      scheduleDocIrRefresh(next)
      return next
    })
    schedulePartialDraftSave()
    pushWritingDelta(chunk)
  }

  function processStreamQueue(token: number) {
    if (token !== streamToken) return
    if (!streamQueue.length) {
      streamTypingActive = false
      streamFastDrain = false
      if (pendingFinalText !== null) {
        applyFinalSnapshot(pendingFinalText, pendingFinalDocIr)
        pendingFinalText = null
        pendingFinalDocIr = null
      }
      typingActive = false
      return
    }
    const item = streamQueue[0]
    const speed = streamTypingSpeed()
    const chunk = item.text.slice(0, speed.chunk)
    item.text = item.text.slice(chunk.length)
    streamPendingChars = Math.max(0, streamPendingChars - chunk.length)
    if (!item.text) streamQueue.shift()
    if (chunk) applyStreamChunk(item.section, chunk, item.raw)
    streamTimer = setTimeout(() => processStreamQueue(token), speed.delayMs)
  }

  function kickStreamTyping() {
    if (streamTypingActive) return
    if (!streamQueue.length) return
    streamTypingActive = true
    typingActive = true
    const token = ++streamToken
    processStreamQueue(token)
  }

  function enqueueStreamDelta(section: string, deltaText: string, opts?: { raw?: boolean }) {
    const text = String(deltaText || '')
    if (!text) return
    streamQueue.push({ section: String(section || ''), raw: Boolean(opts?.raw), text })
    streamPendingChars += text.length
    kickStreamTyping()
  }

  function applyFinalSnapshot(text: string, finalDoc?: Record<string, unknown> | null) {
    const txt = String(text || '')
    renderActivityAt = Date.now()
    sourceText.set(txt)
    if (finalDoc && typeof finalDoc === 'object') {
      const normalized = normalizeDocIrParagraphBlocks(finalDoc as Record<string, unknown>)
      docIr.set(normalized)
      docIrDirty.set(false)
    } else {
      const doc = textToDocIr(txt)
      if (doc) {
        const normalized = normalizeDocIrParagraphBlocks(doc)
        docIr.set(normalized)
        docIrDirty.set(false)
      } else {
        docIr.set(null)
        docIrDirty.set(true)
      }
    }
  }

  function finalizeStreamText(text: string, finalDoc?: Record<string, unknown> | null) {
    pendingFinalText = String(text || '')
    pendingFinalDocIr = finalDoc || null
    if (!streamQueue.length && !streamTypingActive) {
      applyFinalSnapshot(pendingFinalText, pendingFinalDocIr)
      pendingFinalText = null
      pendingFinalDocIr = null
      return
    }
    streamFastDrain = true
    kickStreamTyping()
  }

  let typingToken = $state(0)
  async function typewriterSetText(
    text: string,
    opts?: { chunk?: number; delayMs?: number; finalDocIr?: Record<string, unknown> | null }
  ) {
    const token = ++typingToken
    const chunkSize = Math.max(10, opts?.chunk ?? 36)
    const delayMs = Math.max(10, opts?.delayMs ?? 18)
    typingActive = true
    docIrDirty.set(true)
    sourceText.set('')
    try {
      let i = 0
      while (i < text.length) {
        if (token !== typingToken) return
        const next = text.slice(i, i + chunkSize)
        renderActivityAt = Date.now()
        sourceText.update((cur) => {
          const updated = String(cur || '') + next
          scheduleDocIrRefresh(updated)
          return updated
        })
        pushWritingDelta(next)
        i += chunkSize
        await new Promise((r) => setTimeout(r, delayMs))
      }
      if (token !== typingToken) return
      if (opts?.finalDocIr && typeof opts.finalDocIr === 'object') {
        const normalized = normalizeDocIrParagraphBlocks(opts.finalDocIr as Record<string, unknown>)
        docIr.set(normalized)
        docIrDirty.set(false)
      } else {
        scheduleDocIrRefresh(text, true)
      }
    } finally {
      if (token === typingToken) {
        typingActive = false
      }
    }
  }

  function ensureSkeletonInText(text: string, title: string, sections: string[]) {
    let t = String(text || '').replace(/\r/g, '')
    if (!/^#\s+/m.test(t)) {
      t = `# ${title || '自动生成文档'}\n\n` + t.trimStart()
    }
    for (const s of sections || []) {
      const name = decodeSectionTitle(String(s || '').trim())
      if (!name) continue
      const re = new RegExp(`^##\\s+${name.replace(/[.*+?^${}()|[\]\\\\]/g, '\\\\$&')}\\s*$`, 'm')
      if (!re.test(t)) t = (t.trimEnd() + `\n\n## ${name}\n\n`).replace(/\n{4,}/g, '\n\n')
    }
    return t
  }

  function decodeSectionTitle(raw: string) {
    const s = String(raw || '').trim()
    const m = /^H[23]::(.*)$/.exec(s)
    return (m ? m[1] : s).trim()
  }

  function escapeRegExp(value: string) {
    return value.replace(/[.*+?^${}()|[\]\\/]/g, '\\$&')
  }

  const SECTION_TARGET_PREFIX = 'sec:'
  const DOC_TITLE_TARGET_ID = 'doc:title'

  function isSectionTargetId(id: string) {
    return String(id || '').startsWith(SECTION_TARGET_PREFIX)
  }

  function isDocTitleTargetId(id: string) {
    return String(id || '') === DOC_TITLE_TARGET_ID
  }

  function sectionIdFromTarget(id: string) {
    if (!isSectionTargetId(id)) return ''
    return String(id || '').slice(SECTION_TARGET_PREFIX.length).trim()
  }

  function blockIdFromTarget(id: string) {
    const value = String(id || '').trim()
    if (!value) return ''
    if (isSectionTargetId(value) || isDocTitleTargetId(value)) return ''
    return value
  }

  function blockTargetIds(ids: string[]) {
    return (ids || []).map((id) => blockIdFromTarget(id)).filter(Boolean)
  }

  function sectionTargetIds(ids: string[]) {
    return (ids || []).map((id) => sectionIdFromTarget(id)).filter(Boolean)
  }

  function normalizeColorHex(raw: string) {
    const value = String(raw || '').trim().toLowerCase()
    if (!value) return ''
    if (/^#([0-9a-f]{3})$/.test(value)) {
      const v = value.slice(1)
      return `#${v[0]}${v[0]}${v[1]}${v[1]}${v[2]}${v[2]}`
    }
    if (/^#([0-9a-f]{6})$/.test(value)) return value
    const rgb = /^rgba?\(([^)]+)\)$/.exec(value)
    if (!rgb) return ''
    const parts = rgb[1]
      .split(',')
      .map((item) => Number(item.trim()))
      .filter((num) => Number.isFinite(num))
    if (parts.length < 3) return ''
    const hex = parts.slice(0, 3).map((num) => Math.max(0, Math.min(255, Math.round(num))).toString(16).padStart(2, '0'))
    return `#${hex.join('')}`
  }

  function cloneCandidates(candidates: Array<any>) {
    return (candidates || []).map((c) => ({ ...c }))
  }

  function buildBlockSessionKey(ids: string[]) {
    return (ids || [])
      .map((id) => String(id || '').trim())
      .filter(Boolean)
      .sort()
      .join('|')
  }

  function saveCurrentBlockSession() {
    if (!activeBlockSessionKey) return
    blockSessionStore.set(activeBlockSessionKey, {
      tab: inlinePanelTab,
      cmd: blockEditCmd,
      styleFontSize: blockStyleFontSize,
      styleLineHeight: blockStyleLineHeight,
      styleFontFamily: blockStyleFontFamily,
      styleColor: blockStyleColor,
      styleBackground: blockStyleBackground,
      styleAlign: blockStyleAlign,
      styleFontWeight: blockStyleFontWeight,
      styleFontStyle: blockStyleFontStyle,
      candidates: cloneCandidates(blockCandidates),
      activeIndex: activeCandidateIndex,
      originalText: blockOriginalText,
      error: blockEditError,
      dialogInput: blockDialogInput
    })
  }

  function restoreBlockSession(session: BlockSession) {
    inlinePanelTab = session.tab || 'rewrite'
    blockEditCmd = String(session.cmd || '')
    blockStyleFontSize = String(session.styleFontSize || '')
    blockStyleLineHeight = String(session.styleLineHeight || '')
    blockStyleFontFamily = String(session.styleFontFamily || '')
    blockStyleColor = normalizeColorHex(session.styleColor || '')
    blockStyleBackground = normalizeColorHex(session.styleBackground || '')
    blockStyleAlign = String(session.styleAlign || '')
    blockStyleFontWeight = String(session.styleFontWeight || '')
    blockStyleFontStyle = String(session.styleFontStyle || '')
    blockCandidates = cloneCandidates(session.candidates || [])
    activeCandidateIndex = Number.isFinite(session.activeIndex) ? Math.max(0, session.activeIndex) : 0
    blockOriginalText = String(session.originalText || selectedBlockText || '')
    blockEditError = String(session.error || '')
    blockDialogInput = String(session.dialogInput || '')
  }

  function initBlockSession(style: Record<string, unknown>) {
    inlinePanelTab = 'rewrite'
    blockStyleFontSize = String(style.fontSize || '')
    blockStyleLineHeight = String(style.lineHeight || '')
    blockStyleFontFamily = String(style.fontFamily || '')
    blockStyleColor = normalizeColorHex(String(style.color || ''))
    blockStyleBackground = normalizeColorHex(String(style.background || style.backgroundColor || ''))
    blockStyleAlign = String(style.align || style.textAlign || '')
    blockStyleFontWeight = String(style.fontWeight || '')
    blockStyleFontStyle = String(style.fontStyle || '')
    blockEditCmd = ''
    blockPreviewBusy = false
    blockEditError = ''
    blockOriginalText = selectedBlockText
    blockCandidates = []
    activeCandidateIndex = 0
    blockDialogInput = ''
  }

  function clamp(value: number, min: number, max: number) {
    return Math.min(max, Math.max(min, value))
  }

  function selectedBlocksRect(ids: string[]) {
    const cleanIds = (ids || []).map((id) => String(id || '').trim()).filter(Boolean)
    if (!cleanIds.length) return null
    const editable = document.querySelector('.editable') as HTMLElement | null
    if (!editable) return null
    let left = Number.POSITIVE_INFINITY
    let top = Number.POSITIVE_INFINITY
    let right = 0
    let bottom = 0
    let hit = 0
    for (const id of cleanIds) {
      let el: HTMLElement | null = null
      if (isSectionTargetId(id)) {
        const sectionId = sectionIdFromTarget(id)
        if (sectionId) {
          const sel = `[data-section-id="${CSS.escape(sectionId)}"]`
          el = editable.querySelector(sel) as HTMLElement | null
        }
      } else if (isDocTitleTargetId(id)) {
        el = editable.querySelector('.wa-title[data-doc-title="1"]') as HTMLElement | null
      } else {
        const blockId = blockIdFromTarget(id)
        if (blockId) {
          const sel = `[data-block-id="${CSS.escape(blockId)}"]`
          el = editable.querySelector(sel) as HTMLElement | null
        }
      }
      if (!el) continue
      const rect = el.getBoundingClientRect()
      left = Math.min(left, rect.left)
      top = Math.min(top, rect.top)
      right = Math.max(right, rect.right)
      bottom = Math.max(bottom, rect.bottom)
      hit += 1
    }
    if (!hit) return null
    return { left, top, right, bottom, width: Math.max(0, right - left), height: Math.max(0, bottom - top) }
  }

  function updateInlineOverlayPosition() {
    if (!selectedBlockIds.length) {
      inlineBarVisible = false
      inlinePopoverOpen = false
      return
    }
    const rect = selectedBlocksRect(selectedBlockIds)
    if (!rect) {
      inlineBarVisible = false
      inlinePopoverOpen = false
      return
    }
    const barWidth = Math.min(560, window.innerWidth - 24)
    inlineBarLeft = clamp(rect.left, 12, Math.max(12, window.innerWidth - barWidth - 12))
    inlineBarTop = clamp(rect.bottom + 10, 72, Math.max(72, window.innerHeight - 56))
    inlineBarVisible = true

    const popWidth = Math.min(720, window.innerWidth - 24)
    inlinePopoverLeft = clamp(rect.left, 12, Math.max(12, window.innerWidth - popWidth - 12))
    inlinePopoverTop = inlinePopoverPlacement === 'up'
      ? clamp(inlineBarTop - 10, 92, Math.max(92, window.innerHeight - 80))
      : clamp(inlineBarTop + 50, 92, Math.max(92, window.innerHeight - 80))
  }

  function openInlinePopover(tab: InlinePanelTab, placement: 'up' | 'down' = 'down') {
    if (!selectedBlockIds.length) return
    if (inlinePopoverOpen && inlinePanelTab === tab && inlinePopoverPlacement === placement) {
      inlinePopoverOpen = false
      return
    }
    inlinePanelTab = tab
    inlinePopoverPlacement = placement
    inlinePopoverOpen = true
    updateInlineOverlayPosition()
  }

  function closeInlinePopover() {
    inlinePopoverOpen = false
  }

  function toggleInlineTab(tab: InlinePanelTab) {
    if (inlinePopoverOpen && inlinePanelTab === tab) {
      inlinePopoverOpen = false
      return
    }
    inlinePanelTab = tab
    if (!inlinePopoverOpen) {
      inlinePopoverOpen = true
      updateInlineOverlayPosition()
    }
  }

  function eventPayload(event: any) {
    if (event && typeof event === 'object' && 'detail' in event) return event.detail || {}
    return event || {}
  }

  function handleBlockEdit(event: any) {
    const payload = eventPayload(event)
    if (payload.docIr && typeof payload.docIr === 'object') {
      const normalized = normalizeDocIrParagraphBlocks(payload.docIr as Record<string, unknown>)
      docIr.set(normalized)
      docIrDirty.set(false)
      lastSavedDocIr = normalized
    }
    if (payload.text) {
      const txt = String(payload.text || '')
      sourceText.set(txt)
      lastSavedText = txt
    }
    if (payload.meta && payload.meta.action) {
      pushToast('块已更新', 'ok')
    }
  }

  function handleToolbarState(event: any) {
    const payload = eventPayload(event)
    const detail = payload && typeof payload === 'object' ? payload : {}
    editorToolbarState = {
      focused: Boolean((detail as any).focused),
      readonly: Boolean((detail as any).readonly),
      bold: Boolean((detail as any).bold),
      italic: Boolean((detail as any).italic),
      underline: Boolean((detail as any).underline),
      hasSelection: Boolean((detail as any).hasSelection),
      canUndo: Boolean((detail as any).canUndo),
      canRedo: Boolean((detail as any).canRedo),
      canCopy: Boolean((detail as any).canCopy),
      canCut: Boolean((detail as any).canCut),
      canPaste: Boolean((detail as any).canPaste)
    }
  }

  function handleBlockSelect(event: any) {
    const detail = eventPayload(event)
    const incomingIds = Array.isArray(detail.blockIds)
      ? detail.blockIds.map((v: unknown) => String(v || '').trim()).filter(Boolean)
      : []
    const nextBlockId = String(detail.blockId || '')
    const nextIds = incomingIds.length ? incomingIds : nextBlockId ? [nextBlockId] : []
    const nextSessionKey = buildBlockSessionKey(nextIds)
    const prevSessionKey = activeBlockSessionKey
    if (!nextIds.length && selectedBlockIds.length) {
      const activeEl = document.activeElement as HTMLElement | null
      if (
        activeEl &&
        (activeEl.closest('.inline-edit-popover') || activeEl.closest('.inline-selection-bar') || activeEl.closest('.block-dialog'))
      ) {
        return
      }
    }
    if (prevSessionKey && prevSessionKey !== nextSessionKey) {
      saveCurrentBlockSession()
    }
    const incomingBlocks = Array.isArray(detail.blocks)
      ? detail.blocks
          .map((b: any) => ({
            id: String(b?.id || '').trim(),
            text: String(b?.text || ''),
            style: b?.style && typeof b.style === 'object' ? (b.style as Record<string, string>) : {},
            kind: ['block', 'section', 'title'].includes(String(b?.kind || ''))
              ? (String(b?.kind || '') as 'block' | 'section' | 'title')
              : ('block' as const),
            sectionId: String(b?.sectionId || '').trim(),
            sectionTitle: String(b?.sectionTitle || '').trim()
          }))
          .filter((b: any) => b.id)
      : []
    selectedBlockIds = nextIds
    selectedBlocks = incomingBlocks.length
      ? incomingBlocks
      : nextIds.map((id) => ({ id, text: String(detail.text || ''), style: {}, kind: 'block', sectionId: '', sectionTitle: '' }))
    selectedBlockId = nextIds[0] || ''
    selectedBlockText =
      selectedBlocks.length > 1
        ? selectedBlocks.map((b, idx) => `[块${idx + 1}] ${b.text}`.trim()).join('\n\n')
        : String(detail.text || '')
    const style = detail.style && typeof detail.style === 'object' ? detail.style : {}
    blockStyleFontFamily = String((style as any).fontFamily || '')
    blockStyleFontSize = String((style as any).fontSize || '')
    blockStyleLineHeight = String((style as any).lineHeight || '')
    blockStyleColor = normalizeColorHex(String((style as any).color || ''))
    blockStyleBackground = normalizeColorHex(String((style as any).background || (style as any).backgroundColor || ''))
    blockStyleAlign = String((style as any).align || (style as any).textAlign || '')
    blockStyleFontWeight = String((style as any).fontWeight || '')
    blockStyleFontStyle = String((style as any).fontStyle || '')
    if (!nextIds.length) {
      activeBlockSessionKey = ''
      inlineBarVisible = false
      inlinePopoverOpen = false
      blockOriginalText = ''
      blockCandidates = []
      activeCandidateIndex = 0
      blockEditError = ''
      return
    }
    if (nextSessionKey !== prevSessionKey) {
      const session = blockSessionStore.get(nextSessionKey)
      if (session) restoreBlockSession(session)
      else initBlockSession(style as Record<string, unknown>)
      activeBlockSessionKey = nextSessionKey
    }
    blockOriginalText = blockOriginalText || selectedBlockText
    requestAnimationFrame(() => updateInlineOverlayPosition())
  }

  function closeInlineTools() {
    saveCurrentBlockSession()
    selectedBlockId = ''
    selectedBlockIds = []
    selectedBlocks = []
    selectedBlockText = ''
    activeBlockSessionKey = ''
    inlineBarVisible = false
    inlinePopoverOpen = false
    blockStyleFontFamily = ''
    blockStyleFontSize = ''
    blockStyleLineHeight = ''
    blockStyleColor = ''
    blockStyleBackground = ''
    blockStyleAlign = ''
    blockStyleFontWeight = ''
    blockStyleFontStyle = ''
    blockCandidates = []
    activeCandidateIndex = 0
    blockEditError = ''
    blockDialogInput = ''
  }

  function updateDocIrBlockStyle(
    docObj: Record<string, unknown>,
    blockIds: string[],
    patch: Record<string, string>
  ): Record<string, unknown> | null {
    const targetIds = new Set((blockIds || []).map((v) => String(v || '').trim()).filter(Boolean))
    if (!targetIds.size) return null
    const sections = Array.isArray((docObj as any).sections) ? (docObj as any).sections : []
    let changed = false
    const applyPatch = (styleObj: Record<string, unknown>): Record<string, unknown> => {
      const nextStyle: Record<string, unknown> = { ...styleObj }
      for (const [k, v] of Object.entries(patch)) {
        const val = String(v || '').trim()
        if (!val) delete nextStyle[k]
        else nextStyle[k] = val
      }
      return nextStyle
    }
    const walk = (sec: any): any => {
      let localChanged = false
      const blocks = Array.isArray(sec?.blocks) ? sec.blocks : []
      const nextBlocks = blocks.map((b: any) => {
        if (!targetIds.has(String(b?.id || ''))) return b
        localChanged = true
        changed = true
        const baseStyle = b?.style && typeof b.style === 'object' ? b.style : {}
        return { ...b, style: applyPatch(baseStyle as Record<string, unknown>) }
      })
      const children = Array.isArray(sec?.children) ? sec.children : []
      const nextChildren = children.map((ch: any) => walk(ch))
      const childrenChanged = nextChildren.some((ch: any, idx: number) => ch !== children[idx])
      if (!localChanged && !childrenChanged) return sec
      const nextSec: any = { ...sec }
      if (localChanged) nextSec.blocks = nextBlocks
      if (childrenChanged) nextSec.children = nextChildren
      return nextSec
    }
    const nextSections = sections.map((sec: any) => walk(sec))
    if (!changed) return null
    return { ...docObj, sections: nextSections }
  }

  function updateDocIrSectionStyle(
    docObj: Record<string, unknown>,
    sectionIds: string[],
    patch: Record<string, string>
  ): Record<string, unknown> | null {
    const targets = new Set((sectionIds || []).map((id) => String(id || '').trim()).filter(Boolean))
    if (!targets.size) return null
    const sections = Array.isArray((docObj as any).sections) ? (docObj as any).sections : []
    let changed = false
    const applyPatch = (styleObj: Record<string, unknown>) => {
      const nextStyle: Record<string, unknown> = { ...styleObj }
      for (const [k, v] of Object.entries(patch)) {
        const val = String(v || '').trim()
        if (!val) delete nextStyle[k]
        else nextStyle[k] = val
      }
      return nextStyle
    }
    const walk = (sec: any): any => {
      let touched = false
      let nextSec = sec
      const sectionId = String(sec?.id || '').trim()
      if (sectionId && targets.has(sectionId)) {
        const baseStyle = sec?.style && typeof sec.style === 'object' ? sec.style : {}
        nextSec = { ...nextSec, style: applyPatch(baseStyle as Record<string, unknown>) }
        touched = true
      }
      const children = Array.isArray(sec?.children) ? sec.children : []
      const nextChildren = children.map((ch: any) => walk(ch))
      const childChanged = nextChildren.some((ch: any, idx: number) => ch !== children[idx])
      if (childChanged) {
        nextSec = { ...nextSec, children: nextChildren }
        touched = true
      }
      if (touched) changed = true
      return touched ? nextSec : sec
    }
    const nextSections = sections.map((sec: any) => walk(sec))
    if (!changed) return null
    return { ...docObj, sections: nextSections }
  }

  function updateDocTitleStyle(
    docObj: Record<string, unknown>,
    patch: Record<string, string>
  ): Record<string, unknown> | null {
    const base = (docObj as any).title_style
    const style = base && typeof base === 'object' ? { ...(base as Record<string, unknown>) } : {}
    let changed = false
    for (const [k, v] of Object.entries(patch)) {
      const val = String(v || '').trim()
      if (!val) {
        if (k in style) {
          delete style[k]
          changed = true
        }
      } else if (String(style[k] || '') !== val) {
        style[k] = val
        changed = true
      }
    }
    if (!changed) return null
    return { ...docObj, title_style: style }
  }

  function applyInlineBlockStyle(patch: Record<string, string>) {
    if (!ensureInlineEditAllowed('修改当前选中块')) return
    const targets = selectedBlockIds.length ? selectedBlockIds : selectedBlockId ? [selectedBlockId] : []
    if (!targets.length || !$docIr) return
    const blockTargets = blockTargetIds(targets)
    const sectionTargets = sectionTargetIds(targets)
    const touchesDocTitle = targets.includes(DOC_TITLE_TARGET_ID)
    let nextDoc = $docIr as Record<string, unknown>
    let changed = false
    if (blockTargets.length) {
      const updated = updateDocIrBlockStyle(nextDoc, blockTargets, patch)
      if (updated) {
        nextDoc = updated
        changed = true
      }
    }
    if (sectionTargets.length) {
      const updated = updateDocIrSectionStyle(nextDoc, sectionTargets, patch)
      if (updated) {
        nextDoc = updated
        changed = true
      }
    }
    if (touchesDocTitle) {
      const updated = updateDocTitleStyle(nextDoc, patch)
      if (updated) {
        nextDoc = updated
        changed = true
      }
    }
    if (!changed) return
    applyDocIrSnapshot(nextDoc)
    requestAnimationFrame(() => updateInlineOverlayPosition())
    saveDoc().catch(() => {})
  }

  function selectedTargetIds() {
    return selectedBlockIds.length ? selectedBlockIds.slice() : selectedBlockId ? [selectedBlockId] : []
  }

  function selectedTargetBlockIds() {
    return blockTargetIds(selectedTargetIds())
  }

  function hasNonBlockTargets() {
    const all = selectedTargetIds()
    if (!all.length) return false
    return selectedTargetBlockIds().length !== all.length
  }

  function selectedTargetText() {
    if (selectedBlocks.length > 1) {
      return selectedBlocks.map((b, idx) => `[块${idx + 1}] ${b.text}`.trim()).join('\n\n')
    }
    if (selectedBlocks.length === 1) return String(selectedBlocks[0].text || '')
    return selectedBlockText.trim()
  }

  function selectedTargetPlainText() {
    if (selectedBlocks.length > 1) {
      return selectedBlocks
        .map((b) => String(b.text || '').trim())
        .filter(Boolean)
        .join('\n\n')
        .trim()
    }
    if (selectedBlocks.length === 1) return String(selectedBlocks[0].text || '').trim()
    return String(selectedBlockText || '').trim()
  }

  function buildSelectedRevisionPayload(baseText: string) {
    const selectedIds = selectedTargetIds()
    if (!selectedIds.length) return null
    const selected = sanitizeAiInputText(selectedTargetPlainText(), { trim: true, maxChars: 16000 })
    if (!selected) return null
    const src = sanitizeAiDocumentText(baseText)
    if (!src) return sanitizeAiSelectionPayload({ text: selected })

    const candidates: string[] = [selected]
    const compact = selected.trim()
    if (compact && compact !== selected) candidates.push(compact)
    for (const candidate of candidates) {
      const idx = src.indexOf(candidate)
      if (idx < 0) continue
      const secondIdx = src.indexOf(candidate, idx + 1)
      if (secondIdx >= 0) {
        return sanitizeAiSelectionPayload({ text: candidate })
      }
      return sanitizeAiSelectionPayload({
        start: idx,
        end: idx + candidate.length,
        text: candidate
      })
    }
    return sanitizeAiSelectionPayload({ text: compact || selected })
  }

  function summarizeRevisionStatus(meta: Record<string, unknown>) {
    const ok = meta.ok === true
    const code = String(meta.error_code || '').trim() || (ok ? 'OK' : 'UNKNOWN')
    const source = String(meta.selection_source || '').trim()
    const left = Number(meta.left_window_chars || 0)
    const right = Number(meta.right_window_chars || 0)
    const trimmed = meta.trimmed_for_budget === true ? 'trim=1' : 'trim=0'
    const fallback = meta.fallback_triggered === true ? 'fallback=1' : 'fallback=0'
    const recovered = meta.fallback_recovered === true ? 'recover=1' : 'recover=0'
    const details: string[] = [`code=${code}`, trimmed, fallback, recovered]
    if (source) details.push(`source=${source}`)
    if (left > 0 || right > 0) details.push(`window=${left}/${right}`)
    if (ok) return `局部改写成功（${details.join('; ')}）`
    return `局部改写未命中（${details.join('; ')}），已切换全量生成兜底`
  }

  function openAssistantForBlock(customInstruction?: string) {
    inlinePanelTab = 'assistant'
    switchWorkspaceMode('collab')
    setAssistantOpen(true)
    const ids = selectedTargetIds()
    const base = selectedTargetText()
    const req = String(customInstruction || '').trim()
    if (base && ids.length > 0) {
      const hasTitleTarget = ids.some((id) => isSectionTargetId(id) || isDocTitleTargetId(id))
      const title = hasTitleTarget
        ? '请只修改我选中的标题或段落，不要改其他部分。'
        : ids.length > 1
          ? `请只修改我选中的 ${ids.length} 个段落块，不要改其他段落。`
          : '请只修改我选中的这段内容，不要改其他段落。'
      instruction.set(`${title}\n${base}\n\n修改要求：${req}`)
    }
    focusAssistantInput()
  }

  async function previewSelectedBlockEdit() {
    if (!ensureInlineEditAllowed('生成块改写候选')) return
    const targetIds = selectedTargetIds()
    const blockIds = selectedTargetBlockIds()
    if (!$docId || !targetIds.length) return
    if (!blockIds.length) {
      blockEditError = '当前选中为标题，建议在“样式设置”中修改，或直接在标题处输入。'
      return
    }
    if (blockIds.length !== targetIds.length) {
      blockEditError = '标题与正文混选时暂不支持候选生成，请只选段落块。'
      return
    }
    const input = sanitizeAiInputText(blockEditCmd, { trim: true, maxChars: 2400 })
    if (!input) return
    blockPreviewBusy = true
    blockEditError = ''
    blockCandidates = []
    try {
      if (!$docIr || typeof $docIr !== 'object') throw new Error('文档尚未就绪')
      const baseDoc = $docIr as Record<string, unknown>
      blockOriginalText = selectedTargetText()
      if (blockIds.length === 1) {
        const payload: Record<string, unknown> = {
          block_id: blockIds[0],
          instruction: input
        }
        if ($docIr) payload.doc_ir = $docIr
        const resp = await fetch(`/api/doc/${$docId}/block-edit/preview`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        })
        if (!resp.ok) throw new Error(await resp.text())
        const data = await resp.json()
        blockOriginalText = String(data.before || selectedBlockText || '')
        const rawCandidates = Array.isArray(data.candidates) ? data.candidates : []
        blockCandidates = rawCandidates
          .filter((c: any) => c && typeof c === 'object' && c.doc_ir && !c.error)
          .map((c: any, idx: number) => ({
            label: String(c.label || `方案${idx + 1}`),
            selectedAfter: sanitizeCandidateText(String(c.selected_after || ''), blockOriginalText),
            selectedBefore: String(c.selected_before || blockOriginalText || ''),
            docIr: c.doc_ir,
            diff: c.diff
          }))
      } else {
        const variants = [
          { label: '方案A', instruction: input },
          { label: '方案B', instruction: `${input}。请采用另一种表达方式，保持原意但在句式和组织上有明显差异。` }
        ]
        const collected: Array<any> = []
        for (const variant of variants) {
          let workingDoc = JSON.parse(JSON.stringify(baseDoc)) as Record<string, unknown>
          const beforeParts: string[] = []
          const afterParts: string[] = []
          for (const blockId of blockIds) {
            const payload: Record<string, unknown> = {
              block_id: blockId,
              instruction: sanitizeAiInputText(variant.instruction, { trim: true, maxChars: 2400 }),
              doc_ir: workingDoc,
              variants: [
                {
                  label: sanitizeAiInputText(variant.label, { trim: true, maxChars: 40 }),
                  instruction: sanitizeAiInputText(variant.instruction, { trim: true, maxChars: 2400 })
                }
              ]
            }
            const resp = await fetch(`/api/doc/${$docId}/block-edit/preview`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(payload)
            })
            if (!resp.ok) throw new Error(await resp.text())
            const data = await resp.json()
            const candidate = Array.isArray(data.candidates) ? data.candidates[0] : null
            if (!candidate || !candidate.doc_ir) {
              throw new Error(`未生成可用候选：${variant.label}`)
            }
            const before = String(data.before || '')
            const after = sanitizeCandidateText(String(candidate.selected_after || ''), before)
            if (before) beforeParts.push(before)
            if (after) afterParts.push(after)
            workingDoc = candidate.doc_ir as Record<string, unknown>
          }
          collected.push({
            label: variant.label,
            selectedAfter: afterParts.join('\n\n'),
            selectedBefore: beforeParts.join('\n\n') || blockOriginalText,
            docIr: workingDoc,
            diff: ''
          })
        }
        blockCandidates = collected
      }
      if (!blockCandidates.length) {
        throw new Error('没有生成可用候选版本')
      }
      activeCandidateIndex = 0
    } catch (err) {
      blockEditError = err instanceof Error ? err.message : '候选生成失败'
    } finally {
      blockPreviewBusy = false
    }
  }

  function useRewritePreset(preset: string) {
    const cur = blockEditCmd.trim()
    blockEditCmd = cur ? `${cur}；${preset}` : preset
    inlinePanelTab = 'rewrite'
  }

  function handleInlineShortcut(event: KeyboardEvent) {
    const key = String(event.key || '').toLowerCase()
    const withCmd = event.ctrlKey || event.metaKey
    if (withCmd && key === 'k') {
      event.preventDefault()
      switchWorkspaceMode('collab')
      toggleAssistantOpen()
      return
    }
    if (event.key === 'Escape') {
      if (assistantOpen) {
        setAssistantOpen(false)
        return
      }
      if (infoDrawerOpen) {
        closeInfoDrawer()
        return
      }
      if (inlinePopoverOpen) {
        inlinePopoverOpen = false
      }
      return
    }
    if (!selectedBlockIds.length) return
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
      event.preventDefault()
      const placement: 'up' | 'down' = event.shiftKey ? 'up' : 'down'
      openInlinePopover(inlinePanelTab as InlinePanelTab, placement)
      return
    }
  }

  function handleAssistantSheetKeydown(event: KeyboardEvent) {
    if (event.key !== 'Escape') return
    event.preventDefault()
    setAssistantOpen(false)
  }

  function handleGlobalKeydownCapture(event: KeyboardEvent) {
    if (event.key === 'Escape' && assistantOpen) {
      event.preventDefault()
      setAssistantOpen(false)
    }
  }

  function sanitizeCandidateText(after: string, before: string) {
    const src = String(after || '').trim()
    if (!src) return ''
    const original = String(before || '').trim()
    let out = src
      .replace(/^\s*```[a-zA-Z0-9_-]*\s*/g, '')
      .replace(/\s*```\s*$/g, '')
      .trim()
    const rewriteLabel = /(?:改写后(?:的)?(?:文本|版本)?|优化后(?:的)?(?:文本|版本)?|重写后(?:的)?(?:文本|版本)?|润色后(?:的)?(?:文本|版本)?|rewritten\s*text|revised\s*version|final\s*version)\s*[:：]\s*/gi
    let last: RegExpExecArray | null = null
    while (true) {
      const m = rewriteLabel.exec(out)
      if (!m) break
      last = m
    }
    if (last && last.index >= 0) {
      out = out.slice(last.index + last[0].length).trim()
    }
    if (original && out.startsWith(original)) {
      const tail = out.slice(original.length).replace(/^[\s:：\-—]+/, '')
      if (tail.length >= 4) out = tail
    }
    const parts = out.split(/\n{2,}/).map((p) => p.trim()).filter(Boolean)
    if (original && parts.length >= 2) {
      const kept = parts.filter((p) => p !== original)
      if (kept.length && kept.length < parts.length) out = kept.join('\n\n')
    }
    return out.trim()
  }

  function candidateLengthDelta(candidate: any) {
    const after = String(candidate?.selectedAfter || '')
    const before = String(candidate?.selectedBefore || blockOriginalText || '')
    const delta = after.length - before.length
    if (delta === 0) return '长度不变'
    return delta > 0 ? `增加 ${delta} 字` : `减少 ${Math.abs(delta)} 字`
  }

  function ignoreCandidateSuggestions() {
    blockCandidates = []
    activeCandidateIndex = 0
    blockEditError = ''
    pushToast('已忽略本轮建议', 'info')
  }

  async function applyCandidateVersion(index: number) {
    if (!ensureInlineEditAllowed('采纳候选改写')) return
    const candidate = blockCandidates[index]
    if (!candidate || !$docId || !candidate.docIr) return
    const nextDoc = candidate.docIr as Record<string, unknown>
    applyDocIrSnapshot(nextDoc)
    try {
      await fetch(`/api/doc/${$docId}/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ doc_ir: nextDoc })
      })
      await fetch(`/api/doc/${$docId}/version/commit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: `块修改:${candidate.label}`, author: 'user', kind: 'minor' })
      })
      pushToast(`已应用${candidate.label}`, 'ok')
      blockCandidates = []
      activeCandidateIndex = 0
      blockEditCmd = ''
      requestAnimationFrame(() => updateInlineOverlayPosition())
      await loadVersionLog()
    } catch (err) {
      blockEditError = err instanceof Error ? err.message : '应用候选失败'
    }
  }

  function applyDocIrSnapshot(nextDoc: Record<string, unknown>) {
    const normalized = normalizeDocIrParagraphBlocks(nextDoc)
    docIr.set(normalized)
    docIrDirty.set(false)
    lastSavedDocIr = normalized
    const nextText = docIrToMarkdown(normalized) || ''
    sourceText.set(nextText)
    lastSavedText = nextText
  }

  $effect(() => {
    if (!blockCandidates.length) {
      if (activeCandidateIndex !== 0) activeCandidateIndex = 0
      return
    }
    if (activeCandidateIndex >= blockCandidates.length) {
      activeCandidateIndex = 0
    }
  })

  let activeCandidate = $derived(blockCandidates[activeCandidateIndex] || null)

  function insertBlockAfterBlock(
    doc: Record<string, unknown>,
    blockId: string,
    blockToInsert: Record<string, unknown>
  ): Record<string, unknown> | null {
    if (!blockId) return null
    const sections = Array.isArray((doc as any).sections) ? ((doc as any).sections as Array<Record<string, unknown>>) : []
    if (!sections.length) return null
    let changed = false
    const walk = (items: Array<Record<string, unknown>>) => {
      let localChanged = false
      const next = items.map((sec) => {
        let touched = false
        let nextSec = sec
        const blocks = Array.isArray((sec as any).blocks) ? (((sec as any).blocks as Array<Record<string, unknown>>).slice()) : []
        const idx = blocks.findIndex((b) => String((b as any)?.id || '') === blockId)
        if (idx >= 0) {
          blocks.splice(idx + 1, 0, blockToInsert)
          nextSec = { ...nextSec, blocks }
          touched = true
        }
        const children = Array.isArray((sec as any).children)
          ? (((sec as any).children as Array<Record<string, unknown>>))
          : []
        if (children.length) {
          const nextChildren = walk(children)
          if (nextChildren !== children) {
            nextSec = { ...nextSec, children: nextChildren }
            touched = true
          }
        }
        if (touched) localChanged = true
        return touched ? nextSec : sec
      })
      if (localChanged) changed = true
      return localChanged ? next : items
    }
    const nextSections = walk(sections)
    if (!changed) return null
    return { ...doc, sections: nextSections }
  }

  function appendBlockToDoc(doc: Record<string, unknown>, blockToInsert: Record<string, unknown>): Record<string, unknown> | null {
    const sections = Array.isArray((doc as any).sections) ? ((doc as any).sections as Array<Record<string, unknown>>) : []
    if (!sections.length) return null
    const first = sections[0]
    const blocks = Array.isArray((first as any).blocks) ? (((first as any).blocks as Array<Record<string, unknown>>).slice()) : []
    blocks.push(blockToInsert)
    const nextFirst = { ...first, blocks }
    const nextSections = sections.slice()
    nextSections[0] = nextFirst
    return { ...doc, sections: nextSections }
  }

  function insertDiagramIntoDoc(spec: Record<string, unknown>, opts?: { targetIds?: string[] }) {
    if (!spec || typeof spec !== 'object') return
    const doc = $docIr
    if (!doc || typeof doc !== 'object') return
    const figureBlock = { id: Math.random().toString(36).slice(2), type: 'figure', figure: spec }
    const blockIds = blockTargetIds(opts?.targetIds || [])
    const anchor = blockIds.length ? blockIds[blockIds.length - 1] : ''
    const nextDoc =
      (anchor && insertBlockAfterBlock(doc as Record<string, unknown>, anchor, figureBlock)) ||
      appendBlockToDoc(doc as Record<string, unknown>, figureBlock)
    if (!nextDoc) return
    applyDocIrSnapshot(nextDoc as Record<string, unknown>)
  }

  function insertTableIntoDoc(opts?: { targetIds?: string[] }) {
    const doc = $docIr
    if (!doc || typeof doc !== 'object') return
    const tableBlock = {
      id: Math.random().toString(36).slice(2),
      type: 'table',
      table: {
        caption: '新建表格',
        columns: ['列1', '列2', '列3'],
        rows: [
          ['', '', ''],
          ['', '', '']
        ]
      }
    }
    const blockIds = blockTargetIds(opts?.targetIds || [])
    const anchor = blockIds.length ? blockIds[blockIds.length - 1] : ''
    const nextDoc =
      (anchor && insertBlockAfterBlock(doc as Record<string, unknown>, anchor, tableBlock)) ||
      appendBlockToDoc(doc as Record<string, unknown>, tableBlock)
    if (!nextDoc) return
    applyDocIrSnapshot(nextDoc as Record<string, unknown>)
    pushToast('已插入表格块，可直接编辑内容。', 'ok')
  }

  const blockCache = new Map<string, any>()

  async function fetchBlock(blockId: string) {
    if (!blockId) return null
    if (blockCache.has(blockId)) return blockCache.get(blockId)
    try {
      const resp = await fetch(`/api/text/${encodeURIComponent(blockId)}`)
      if (!resp.ok) throw new Error(await resp.text())
      const data = await resp.json()
      blockCache.set(blockId, data)
      return data
    } catch {
      return null
    }
  }

  function renderStoredBlock(data: any) {
    if (!data) return ''
    const kind = String(data.kind || '')
    const format = String(data.format || '')
    if (format === 'text') return String(data.text || '')
    if (format === 'json') {
      const payload = data.data || {}
      if (kind === 'list') {
        const items = Array.isArray(payload.items) ? payload.items : []
        return items.map((i) => `- ${String(i).trim()}`).join('\n')
      }
      if (kind === 'table') return `[[TABLE:${JSON.stringify(payload)}]]`
      if (kind === 'figure') return `[[FIGURE:${JSON.stringify(payload)}]]`
      if (payload.text) return String(payload.text)
    }
    return ''
  }

  async function insertBlockFromStore(section: string, blockId: string) {
    const data = await fetchBlock(blockId)
    const rendered = renderStoredBlock(data)
    if (!rendered) return
    enqueueStreamDelta(String(section || ''), rendered, { raw: !section })
  }

  function normalizeDocTextSpacing(text: string) {
    let out = String(text || '').replace(/\r/g, '')
    out = out.replace(/(\n(?:-|\d+\.)[^\n]*)(?:\n{2,})(?=(?:-|\d+\.)\s)/g, '$1\n')
    out = out.replace(/\n{3,}/g, '\n\n')
    return out
  }

  function splitParagraphForSelection(text: string): string[] {
    const src = String(text || '').replace(/\r/g, '').trim()
    if (!src) return []
    const hardParts = src
      .split(/\n+/)
      .map((part) => part.trim())
      .filter(Boolean)
    const out: string[] = []
    const splitChunk = (chunk: string) => {
      const clean = String(chunk || '').trim()
      if (!clean) return
      if (clean.length <= 92) {
        out.push(clean)
        return
      }
      let parts = clean
        .split(/(?<=[。！？!?；;])(?=[^”’」』）》】\]\s])/g)
        .map((part) => part.trim())
        .filter(Boolean)
      if (parts.length <= 1 && clean.length > 118) {
        const commas: number[] = []
        for (let i = 0; i < clean.length; i += 1) {
          const ch = clean[i]
          if (ch === '，' || ch === ',' || ch === '、') commas.push(i)
        }
        if (commas.length) {
          const target = Math.floor(clean.length / 2)
          let pick = commas[0]
          let best = Number.POSITIVE_INFINITY
          for (const idx of commas) {
            if (idx < 24 || idx > clean.length - 18) continue
            const d = Math.abs(idx - target)
            if (d < best) {
              best = d
              pick = idx
            }
          }
          const left = clean.slice(0, pick + 1).trim()
          const right = clean.slice(pick + 1).trim()
          parts = [left, right].filter(Boolean)
        }
      }
      if (parts.length <= 1) {
        out.push(clean)
        return
      }
      const merged: string[] = []
      for (const part of parts) {
        if (!part) continue
        if (merged.length && part.length < 24) {
          merged[merged.length - 1] = `${merged[merged.length - 1]}${part}`
        } else {
          merged.push(part)
        }
      }
      out.push(...merged.filter(Boolean))
    }
    for (const part of hardParts.length ? hardParts : [src]) splitChunk(part)
    return out.length ? out : [src]
  }

  function normalizeDocIrParagraphBlocks(docObj: Record<string, unknown>) {
    const sections = Array.isArray((docObj as any).sections) ? (docObj as any).sections : []
    if (!sections.length) return docObj
    let changed = false
    const tryMergeHeadingTail = (titleRaw: string, firstParagraphRaw: string) => {
      const title = String(titleRaw || '').trim()
      const para = String(firstParagraphRaw || '').trim()
      if (!title || !para) return null
      const pureTitle = title.replace(/^\d+(?:\.\d+){0,3}\s*/, '').trim()
      if (!pureTitle || pureTitle.length > 4) return null
      const m = /^([\u4e00-\u9fa5]{1,4})(自|是|在|由|通过|随着|并|可|将|会)([\s\S]*)$/.exec(para)
      if (!m) return null
      const tail = String(m[1] || '').trim()
      if (!tail || tail.length > 3) return null
      if (pureTitle.endsWith(tail)) return null
      const nextTitle = `${title}${tail}`.trim()
      const rest = `${String(m[2] || '')}${String(m[3] || '')}`.trim()
      if (!rest) return null
      return { title: nextTitle, rest }
    }
    const walk = (sec: any): any => {
      let touched = false
      let nextSec = sec
      const blocks = Array.isArray(sec?.blocks) ? sec.blocks : []
      if (blocks.length) {
        const first = blocks[0]
        const firstKind = String(first?.type || '').toLowerCase()
        if (firstKind === 'paragraph' || firstKind === 'text' || firstKind === 'p') {
          const merged = tryMergeHeadingTail(String(sec?.title || ''), String(first?.text || ''))
          if (merged) {
            const nextFirst = { ...first, text: merged.rest }
            const fixedBlocks = blocks.slice()
            fixedBlocks[0] = nextFirst
            nextSec = { ...nextSec, title: merged.title, blocks: fixedBlocks }
            touched = true
            changed = true
          }
        }
      }
      const currentBlocks = Array.isArray(nextSec?.blocks) ? nextSec.blocks : blocks
      const nextBlocks: any[] = []
      for (const block of currentBlocks) {
        const kind = String(block?.type || '').toLowerCase()
        const text = String(block?.text || '')
        const runs = Array.isArray(block?.runs) ? block.runs : null
        if ((kind === 'paragraph' || kind === 'text' || kind === 'p') && !runs && text.length > 92) {
          const parts = splitParagraphForSelection(text)
          if (parts.length > 1) {
            const rawId = String(block?.id || '')
            const baseId = rawId ? rawId.replace(/__\d+$/, '') : Math.random().toString(36).slice(2)
            const baseStyle =
              block?.style && typeof block.style === 'object' ? ({ ...(block.style as Record<string, unknown>) }) : {}
            const total = parts.length
            parts.forEach((part, idx) => {
              const style = { ...baseStyle }
              if (total > 1) {
                if (idx === 0) {
                  if (!style.marginBottom) style.marginBottom = '0'
                } else {
                  if (!style.marginTop) style.marginTop = '0'
                  if (!style.indent && !style.textIndent) style.indent = '0'
                  if (idx < total - 1 && !style.marginBottom) style.marginBottom = '0'
                }
              }
              nextBlocks.push({
                ...block,
                id: `${baseId}__${idx + 1}`,
                text: part,
                style
              })
            })
            changed = true
            touched = true
            continue
          }
        }
        nextBlocks.push(block)
      }
      if (touched) {
        nextSec = { ...nextSec, blocks: nextBlocks }
      }
      const children = Array.isArray(sec?.children) ? sec.children : []
      if (children.length) {
        const nextChildren = children.map((ch: any) => walk(ch))
        const childChanged = nextChildren.some((ch: any, idx: number) => ch !== children[idx])
        if (childChanged) {
          nextSec = { ...nextSec, children: nextChildren }
          changed = true
        }
      }
      return nextSec
    }
    const nextSections = sections.map((sec: any) => walk(sec))
    if (!changed) return docObj
    return { ...docObj, sections: nextSections }
  }

  function insertDeltaIntoSection(text: string, section: string, deltaText: string) {
    const name = decodeSectionTitle(section)
    const deltaRaw = String(deltaText || '').replace(/\r/g, '')
    if (!deltaRaw) return String(text || '')
    if (!deltaRaw.trim() && !deltaRaw.includes('\n')) return String(text || '')
    if (!name) {
      const base = String(text || '').replace(/\r/g, '')
      const merged = base + (base.endsWith('\n') || !base ? '' : '\n') + deltaRaw
      return normalizeDocTextSpacing(merged)
    }
    let t = String(text || '').replace(/\r/g, '')
    const headingRe = new RegExp(`^##\\s+${escapeRegExp(name)}\\s*$`, 'm')
    if (!headingRe.test(t)) {
      t = ensureSkeletonInText(t, '', [name])
    }
    const m = headingRe.exec(t)
    if (!m) {
      const merged = t + (t.endsWith('\n') ? '' : '\n') + deltaRaw
      return normalizeDocTextSpacing(merged)
    }
    const start = m.index + m[0].length
    const after = t.slice(start)
    const nextHeadingOffset = after.search(/^##\s+/m)
    const insertPos = nextHeadingOffset >= 0 ? start + nextHeadingOffset : t.length
    const prefix = t.slice(0, insertPos)
    const suffix = t.slice(insertPos)
    const combined = prefix + deltaRaw + suffix
    return normalizeDocTextSpacing(combined)
  }

  function parseSseBlock(block: string) {
    const lines = String(block || '').replace(/\r/g, '').split('\n')
    let event = 'message'
    const dataLines: string[] = []
    for (const line of lines) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
    }
    const dataText = dataLines.join('\n')
    let data: Record<string, unknown> = {}
    try {
      data = dataText ? JSON.parse(dataText) : {}
    } catch {
      data = { raw: dataText }
    }
    return { event, data }
  }

  async function streamSsePost(
    url: string,
    payload: Record<string, unknown>,
    handlers: (event: string, data: Record<string, any>) => void,
    signal?: AbortSignal
  ) {
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal
    })
    if (!resp.ok) {
      const body = await resp.text()
      const msg = body || resp.statusText || '请求失败'
      throw new Error(`HTTP ${resp.status}: ${msg}`)
    }
    if (!resp.body) throw new Error('当前环境不支持流式输出')
    const reader = resp.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buf = ''
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      let idx = buf.indexOf('\n\n')
      while (idx >= 0) {
        const block = buf.slice(0, idx)
        buf = buf.slice(idx + 2)
        if (block.trim()) {
          const { event, data } = parseSseBlock(block)
          handlers(event, data)
        }
        idx = buf.indexOf('\n\n')
      }
    }
  }

  async function loadDoc() {
    const id = $docId
    if (!id) return
    isLoading.set(true)
    try {
      const resp = await fetch(`/api/doc/${id}`)
      if (!resp.ok) throw new Error(await resp.text())
      const data = await resp.json()
      sourceText.set(String(data.text || ''))
      lastSavedText = String(data.text || '')
      partialSavedSnapshot = lastSavedText
      resumeState = normalizeResumeState(data.resume_state)
      feedbackItems = normalizeFeedbackItems(data.feedback_log)
      await loadLatestPlagiarismReport()
      await loadLatestAiRate()
      if (data.doc_ir && typeof data.doc_ir === 'object') {
        const normalized = normalizeDocIrParagraphBlocks(data.doc_ir as Record<string, unknown>)
        docIr.set(normalized)
        docIrDirty.set(false)
        lastSavedDocIr = normalized
      } else {
        docIr.set(null)
        lastSavedDocIr = null
      }
      loadVersionLog().catch(() => {})
    } catch (err) {
      pushToast(`加载失败: ${err instanceof Error ? err.message : '未知错误'}`, 'error')
    } finally {
      isLoading.set(false)
    }
  }

  function normalizeFeedbackItems(raw: any): FeedbackItem[] {
    const rows = Array.isArray(raw) ? raw : []
    const out: FeedbackItem[] = []
    for (const item of rows) {
      if (!item || typeof item !== 'object') continue
      const rating = Number((item as any).rating || 0)
      if (!Number.isFinite(rating) || rating < 1 || rating > 5) continue
      const id = String((item as any).id || '').trim() || `${Date.now()}-${Math.random()}`
      const note = String((item as any).note || '').trim()
      const stage = String((item as any).stage || 'general').trim() || 'general'
      const createdRaw = Number((item as any).created_at || 0)
      const created_at = Number.isFinite(createdRaw) && createdRaw > 0 ? createdRaw : Date.now() / 1000
      const tagsRaw = Array.isArray((item as any).tags) ? (item as any).tags : []
      const tags = tagsRaw.map((t: any) => String(t || '').trim()).filter(Boolean)
      out.push({ id, rating, note, stage, tags, created_at })
    }
    out.sort((a, b) => b.created_at - a.created_at)
    return out.slice(0, 80)
  }

  async function loadFeedback() {
    const id = $docId
    if (!id) return
    try {
      const resp = await fetch(`/api/doc/${id}/feedback`)
      if (!resp.ok) return
      const data = await resp.json()
      feedbackItems = normalizeFeedbackItems(data.items)
    } catch {
      // best effort
    }
  }

  function formatFeedbackTime(ts: number) {
    const n = Number(ts || 0)
    if (!Number.isFinite(n) || n <= 0) return '--'
    return new Date(n * 1000).toLocaleString()
  }

  async function submitSatisfaction() {
    const id = $docId
    if (!id) return
    if (satisfactionSaving) return
    if (!Number.isFinite(satisfactionRating) || satisfactionRating < 1 || satisfactionRating > 5) {
      pushToast('请选择 1-5 分满意度', 'info')
      return
    }
    satisfactionSaving = true
    lastLowFeedbackRecorded = 0
    const payload = {
      item: {
        rating: satisfactionRating,
        stage: satisfactionStage,
        note: String(satisfactionNote || '').trim(),
        created_at: Date.now() / 1000
      },
      context: {
        doc_status: String($docStatus || ''),
        flow_status: String($flowStatus || ''),
        char_count: String($sourceText || '').replace(/\s/g, '').length,
        word_count: Number($wordCount || 0),
        instruction_preview: String($instruction || '').trim().slice(0, 400)
      }
    }
    try {
      const resp = await fetch(`/api/doc/${id}/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      if (!resp.ok) throw new Error(await resp.text())
      const data = await resp.json()
      feedbackItems = normalizeFeedbackItems(data.items)
      const lowRecorded = Number(data.low_recorded || 0)
      lastLowFeedbackRecorded = Number.isFinite(lowRecorded) ? lowRecorded : 0
      if (lastLowFeedbackRecorded > 0) {
        pushToast('已记录低满意度样本，后续可用于学习改进。', 'info')
      } else {
        pushToast('满意度已提交', 'ok')
      }
      satisfactionNote = ''
    } catch (err) {
      const msg = err instanceof Error ? err.message : '提交失败'
      pushToast(`满意度提交失败: ${msg}`, 'bad')
    } finally {
      satisfactionSaving = false
    }
  }

  function parseReferenceDocIds(raw: string): string[] {
    const src = String(raw || '')
    if (!src.trim()) return []
    const parts = src
      .split(/[,\n;\s]+/)
      .map((x) => String(x || '').trim())
      .filter(Boolean)
    const out: string[] = []
    for (const one of parts) {
      if (out.includes(one)) continue
      out.push(one)
    }
    return out.slice(0, 50)
  }

  function normalizeScore(value: any): number {
    const n = Number(value || 0)
    if (!Number.isFinite(n)) return 0
    return Math.max(0, Math.min(1, n))
  }

  function plagiarismRiskLabel(score: number): string {
    const s = normalizeScore(score)
    if (s >= 0.7) return '高风险'
    if (s >= 0.45) return '中风险'
    if (s >= 0.2) return '低风险'
    return '很低'
  }

  function aiRateScore(): number {
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

  function buildQualityOverview(): QualityOverview {
    const aiScore = aiRateScore()
    const originalityRisk = normalizeScore(sectionOriginalitySummary?.failedSectionRatio || 0)
    const plagiarismScore = normalizeScore(plagiarismMaxScore)
    const worst = Math.max(aiScore, originalityRisk, plagiarismScore)
    if (!aiRateResult && !plagiarismLatestReport && !sectionOriginalitySummary) {
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

  function buildQualityAdviceItems(): QualityAdviceItem[] {
    const items: QualityAdviceItem[] = []
    const aiScore = aiRateScore()
    const repeated3gramRatio = normalizeScore(aiRateResult?.signals?.repeated_3gram_ratio)
    const lexicalDiversity = normalizeScore(aiRateResult?.signals?.lexical_diversity)
    const burstiness = normalizeScore(aiRateResult?.signals?.sentence_burstiness_cv)
    const failedRows = (sectionOriginalitySummary?.rows || []).filter((row) => !row.latest_passed)
    const overlapRows = plagiarismResults.filter((row) => row.suspected || row.score >= row.threshold)

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

    if (aiRateResult && (Boolean(aiRateResult.suspected_ai) || aiScore >= 0.45 || repeated3gramRatio >= 0.1)) {
      items.push({
        id: 'ai-style',
        tone: aiScore >= 0.6 || repeated3gramRatio >= 0.16 ? 'alert' : 'warn',
        title: '压缩模板化表达',
        detail: '优先改写连续重复的开头句、总分总套话和泛化过渡句，把段落改成“对象-动作-证据-结论”的具体表达。',
        action: 'open-ai-panel',
        actionLabel: '查看 AI 面板'
      })
    }

    if (aiRateResult && (lexicalDiversity > 0 && lexicalDiversity <= 0.42 || burstiness <= 0.18)) {
      items.push({
        id: 'ai-diversity',
        tone: 'warn',
        title: '提高词汇与句式多样性',
        detail: '不要只替换同义词。优先拆开长句、改变论证顺序，并引入具体案例、变量、时间窗和限制条件。',
        action: 'run-ai-check',
        actionLabel: '复测 AI 率'
      })
    }

    if (overlapRows.length > 0 || plagiarismMaxScore >= 0.35) {
      items.push({
        id: 'plagiarism-overlap',
        tone: plagiarismMaxScore >= 0.55 ? 'alert' : 'warn',
        title: '处理高重合片段',
        detail: `当前有 ${Math.max(overlapRows.length, plagiarismFlaggedCount)} 个来源超过或接近阈值。优先重写证据后的分析句群，而不是仅删除引用。`,
        action: 'open-plagiarism-panel',
        actionLabel: '查看查重面板'
      })
    }

    if (!aiRateResult) {
      items.push({
        id: 'run-ai',
        tone: 'good',
        title: '运行 AI 风险检测',
        detail: '先做一次检测，确认重复 3-gram、词汇多样性和句长波动是否已经回到正常范围。',
        action: 'run-ai-check',
        actionLabel: '开始检测'
      })
    }

    if (!plagiarismLatestReport && plagiarismResults.length === 0) {
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

  function runQualityAdviceAction(action?: QualityAdviceAction) {
    if (!action) return
    if (action === 'open-ai-panel') {
      showAiRatePanel = true
      return
    }
    if (action === 'open-plagiarism-panel') {
      showPlagiarismPanel = true
      return
    }
    if (action === 'run-ai-check') {
      showAiRatePanel = true
      void runAiRateCheck()
      return
    }
    if (action === 'run-plagiarism-check') {
      showPlagiarismPanel = true
      void runPlagiarismLibraryScan()
      return
    }
    if (action === 'revise-first-risk') {
      const first = (sectionOriginalitySummary?.rows || []).find((row) => !row.latest_passed)
      if (first) {
        void reviseRiskSection(first.title || first.section)
      }
    }
  }

  async function runPlagiarismCheck() {
    const id = $docId
    if (!id) return
    if (plagiarismLoading) return
    const refDocIds = parseReferenceDocIds(plagiarismReferenceDocIds)
    const manualText = String(plagiarismReferenceText || '').trim()
    if (!refDocIds.length && !manualText) {
      pushToast('请至少提供一个对比文档ID或粘贴参考文本', 'info')
      return
    }
    plagiarismLoading = true
    plagiarismResults = []
    plagiarismFlaggedCount = 0
    plagiarismMaxScore = 0
    try {
      const payload: Record<string, any> = {
        threshold: Math.max(0.05, Math.min(0.95, Number(plagiarismThreshold || 0.35))),
        reference_doc_ids: refDocIds
      }
      if (manualText) {
        payload.reference_texts = [{ id: 'manual_text', title: '手动粘贴文本', text: manualText }]
      }
      const resp = await fetch(`/api/doc/${id}/plagiarism/check`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      if (!resp.ok) throw new Error(await resp.text())
      const data = await resp.json()
      const rows = Array.isArray(data?.results) ? data.results : []
      plagiarismResults = rows.map((row: any) => ({
        reference_id: String(row?.reference_id || ''),
        reference_title: String(row?.reference_title || ''),
        score: normalizeScore(row?.score),
        threshold: normalizeScore(row?.threshold || payload.threshold),
        suspected: Boolean(row?.suspected),
        metrics: row?.metrics && typeof row.metrics === 'object' ? row.metrics : {},
        evidence: Array.isArray(row?.evidence) ? row.evidence : []
      }))
      plagiarismFlaggedCount = Number(data?.flagged_count || 0) || 0
      plagiarismMaxScore = normalizeScore(data?.max_score || 0)
      if (plagiarismResults.length === 0) {
        pushToast('查重完成：没有可分析的参考文本', 'info')
      } else if (plagiarismFlaggedCount > 0) {
        pushToast(`查重完成：发现 ${plagiarismFlaggedCount} 个疑似高重复来源`, 'bad')
      } else {
        pushToast('查重完成：未发现超阈值重复来源', 'ok')
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : '查重失败'
      pushToast(`查重失败: ${msg}`, 'bad')
    } finally {
      plagiarismLoading = false
    }
  }

  async function loadLatestPlagiarismReport() {
    const id = $docId
    if (!id) return
    try {
      const resp = await fetch(`/api/doc/${id}/plagiarism/library_scan/latest`)
      if (!resp.ok) return
      const data = await resp.json()
      plagiarismLatestReport = data?.has_report ? data.latest || null : null
    } catch {
      // best effort
    }
  }

  async function loadLatestAiRate() {
    const id = $docId
    if (!id) return
    try {
      const resp = await fetch(`/api/doc/${id}/ai_rate/latest`)
      if (!resp.ok) return
      const data = await resp.json()
      aiRateResult = data?.has_latest ? (data.latest || null) : null
    } catch {
      // best effort
    }
  }

  async function runAiRateCheck() {
    const id = $docId
    if (!id) return
    if (aiRateLoading) return
    aiRateLoading = true
    try {
      const payload = {
        threshold: Math.max(0.05, Math.min(0.95, Number(aiRateThreshold || 0.65)))
      }
      const resp = await fetch(`/api/doc/${id}/ai_rate/check`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      if (!resp.ok) throw new Error(await resp.text())
      const data = await resp.json()
      aiRateResult = data
      const percent = Number(data?.ai_rate_percent || 0)
      const risk = String(data?.risk_level || '')
      if (Boolean(data?.suspected_ai)) {
        pushToast(`AI率检测完成：${percent}%（${risk}）`, 'bad')
      } else {
        pushToast(`AI率检测完成：${percent}%（${risk}）`, 'ok')
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'AI率检测失败'
      pushToast(`AI率检测失败: ${msg}`, 'bad')
    } finally {
      aiRateLoading = false
    }
  }

  async function runPlagiarismLibraryScan() {
    const id = $docId
    if (!id) return
    if (plagiarismLibraryLoading) return
    plagiarismLibraryLoading = true
    try {
      const payload: Record<string, any> = {
        include_all_docs: true,
        threshold: Math.max(0.05, Math.min(0.95, Number(plagiarismThreshold || 0.35))),
        top_k: 30,
        max_docs: 120
      }
      const manualText = String(plagiarismReferenceText || '').trim()
      if (manualText) {
        payload.reference_texts = [{ id: 'manual_text', title: '手动粘贴文本', text: manualText }]
      }
      const resp = await fetch(`/api/doc/${id}/plagiarism/library_scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      if (!resp.ok) throw new Error(await resp.text())
      const data = await resp.json()
      plagiarismLatestReport = {
        report_id: String(data?.report_id || ''),
        created_at: Number(data?.created_at || 0),
        threshold: Number(data?.threshold || payload.threshold),
        source_chars: Number(data?.source_chars || 0),
        flagged_count: Number(data?.flagged_count || 0),
        total_references: Number(data?.total_references || 0),
        max_score: Number(data?.max_score || 0),
        suspected: Boolean(data?.suspected),
        paths: data?.paths && typeof data.paths === 'object' ? data.paths : {}
      }
      const rows = Array.isArray(data?.results) ? data.results : []
      plagiarismResults = rows.map((row: any) => ({
        reference_id: String(row?.reference_id || ''),
        reference_title: String(row?.reference_title || ''),
        score: normalizeScore(row?.score),
        threshold: normalizeScore(row?.threshold || payload.threshold),
        suspected: Boolean(row?.suspected),
        metrics: row?.metrics && typeof row.metrics === 'object' ? row.metrics : {},
        evidence: Array.isArray(row?.evidence) ? row.evidence : []
      }))
      plagiarismFlaggedCount = Number(data?.flagged_count || 0) || 0
      plagiarismMaxScore = normalizeScore(data?.max_score || 0)
      pushToast(
        `全库查重完成：来源 ${plagiarismLatestReport.total_references}，超阈值 ${plagiarismLatestReport.flagged_count}`,
        plagiarismLatestReport.flagged_count > 0 ? 'bad' : 'ok'
      )
    } catch (err) {
      const msg = err instanceof Error ? err.message : '全库查重失败'
      pushToast(`全库查重失败: ${msg}`, 'bad')
    } finally {
      plagiarismLibraryLoading = false
    }
  }

  function downloadPlagiarismReport(format: 'json' | 'md' | 'csv') {
    const id = $docId
    if (!id) return
    const rid = String(plagiarismLatestReport?.report_id || '').trim()
    if (!rid) {
      pushToast('暂无可下载的查重报告', 'info')
      return
    }
    window.location.href = `/api/doc/${id}/plagiarism/library_scan/download?report_id=${encodeURIComponent(rid)}&format=${format}`
  }

  function flattenSections(doc: any): any[] {
    const out: any[] = []
    const sections = Array.isArray(doc?.sections) ? doc.sections : []
    const walk = (sec: any) => {
      out.push(sec)
      const children = Array.isArray(sec?.children) ? sec.children : []
      children.forEach((child: any) => walk(child))
    }
    sections.forEach((sec: any) => walk(sec))
    return out
  }

  function sectionSignature(sec: any): string {
    const level = Math.max(1, Math.min(6, Number(sec?.level || 1)))
    const title = String(sec?.title || '').trim()
    const style = sec?.style && typeof sec.style === 'object' ? JSON.stringify(sec.style) : ''
    return `${level}:${title}:${style}`
  }

  function blockPayload(block: any): Record<string, unknown> {
    const t = String(block?.type || 'paragraph').toLowerCase()
    const style = block?.style && typeof block.style === 'object' ? block.style : null
    const runs = Array.isArray(block?.runs) ? block.runs : null
    if (t === 'list') {
      const items = Array.isArray(block?.items) ? block.items : []
      const ordered = Boolean(block?.ordered)
      const payload: Record<string, unknown> = { type: 'list', items, ordered }
      if (style) payload.style = style
      if (runs) payload.runs = runs
      return payload
    }
    if (t === 'table') {
      const payload: Record<string, unknown> = { type: 'table', table: block?.table || {} }
      if (style) payload.style = style
      if (runs) payload.runs = runs
      return payload
    }
    if (t === 'figure') {
      const payload: Record<string, unknown> = { type: 'figure', figure: block?.figure || {} }
      if (style) payload.style = style
      if (runs) payload.runs = runs
      return payload
    }
    const text = String(block?.text || '')
    const payload: Record<string, unknown> = { type: 'paragraph', text }
    if (style) payload.style = style
    if (runs) payload.runs = runs
    return payload
  }

  function blockKey(block: any): string {
    const t = String(block?.type || 'paragraph').toLowerCase()
    const styleSig = block?.style ? `:style=${JSON.stringify(block?.style || {})}` : ''
    const runSig = block?.runs ? `:runs=${JSON.stringify(block?.runs || [])}` : ''
    if (t === 'list') return `list:${JSON.stringify(block?.items || [])}:${Boolean(block?.ordered)}${styleSig}`
    if (t === 'table') return `table:${JSON.stringify(block?.table || {})}${styleSig}`
    if (t === 'figure') return `figure:${JSON.stringify(block?.figure || {})}${styleSig}`
    return `paragraph:${String(block?.text || '')}${styleSig}${runSig}`
  }

  function buildDocIrOps(baseDoc: any, nextDoc: any): Array<Record<string, unknown>> | null {
    if (!baseDoc || !nextDoc) return null
    const oldSecs = flattenSections(baseDoc)
    const newSecs = flattenSections(nextDoc)
    if (oldSecs.length !== newSecs.length) return null
    for (let i = 0; i < oldSecs.length; i++) {
      if (sectionSignature(oldSecs[i]) !== sectionSignature(newSecs[i])) return null
      if (!oldSecs[i]?.id) return null
    }
    const ops: Array<Record<string, unknown>> = []
    for (let i = 0; i < oldSecs.length; i++) {
      const oldSec = oldSecs[i]
      const newSec = newSecs[i]
      const oldBlocks = Array.isArray(oldSec?.blocks) ? oldSec.blocks : []
      const newBlocks = Array.isArray(newSec?.blocks) ? newSec.blocks : []
      const oldIds = oldBlocks.map((b: any) => String(b?.id || '')).filter(Boolean)
      const newIds = newBlocks.map((b: any) => String(b?.id || '')).filter(Boolean)
      const oldIdSet = new Set(oldIds)
      const newIdSet = new Set(newIds)
      const oldMap = new Map(oldBlocks.map((b: any) => [String(b?.id || ''), b]))
      for (const id of oldIds) {
        if (!newIdSet.has(id)) ops.push({ op: 'delete', target_id: id })
      }
      const sharedNew = newIds.filter((id) => oldIdSet.has(id))
      const working = oldIds.filter((id) => newIdSet.has(id))
      sharedNew.forEach((id, idx) => {
        const curIndex = working.indexOf(id)
        if (curIndex === -1) return
        if (curIndex !== idx) {
          ops.push({ op: 'move', target_id: id, parent_id: String(oldSec.id), index: idx })
          working.splice(curIndex, 1)
          working.splice(idx, 0, id)
        }
      })
      newBlocks.forEach((b: any, idx: number) => {
        const id = String(b?.id || '')
        if (id && oldIdSet.has(id)) {
          const prev = oldMap.get(id)
          if (prev && blockKey(prev) !== blockKey(b)) {
            ops.push({ op: 'update', target_id: id, payload: blockPayload(b) })
          }
          return
        }
        const payload = blockPayload(b)
        ops.push({ op: 'insert', parent_id: String(oldSec.id), index: idx, payload })
      })
    }
    return ops
  }

  async function savePartialDraft() {
    const id = $docId
    if (!id || !$generating || partialSaveInFlight) return
    const snapshot = String($sourceText || '')
    if (!snapshot.trim() || snapshot === partialSavedSnapshot) return
    partialSaveInFlight = true
    try {
      const resp = await fetch(`/api/doc/${id}/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: snapshot })
      })
      if (resp.ok) {
        partialSavedSnapshot = snapshot
      }
    } catch {
      // best-effort partial autosave during streaming
    } finally {
      partialSaveInFlight = false
    }
  }

  function schedulePartialDraftSave() {
    if (!$generating) return
    if (partialSaveTimer) clearTimeout(partialSaveTimer)
    partialSaveTimer = setTimeout(() => {
      void savePartialDraft()
    }, 1600)
  }

  async function saveDoc() {
    const id = $docId
    if (!id) return
    try {
      if ($docIr && !$docIrDirty && lastSavedDocIr) {
        const ops = buildDocIrOps(lastSavedDocIr, $docIr)
        if (ops && ops.length > 0) {
          const resp = await fetch(`/api/doc/${id}/doc_ir/ops`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ops })
          })
          if (resp.ok) {
            const data = await resp.json()
            if (data.doc_ir && typeof data.doc_ir === 'object') {
              const normalized = normalizeDocIrParagraphBlocks(data.doc_ir as Record<string, unknown>)
              docIr.set(normalized)
              docIrDirty.set(false)
              lastSavedDocIr = normalized
            }
            if (data.text) {
              const txt = String(data.text || '')
    const qualitySnapshot =
      data.quality_snapshot && typeof data.quality_snapshot === 'object'
        ? (data.quality_snapshot as Record<string, unknown>)
        : null
    sectionOriginalitySummary = normalizeOriginalitySummary(qualitySnapshot?.section_originality_hot_sample)
    if (sectionOriginalitySummary) {
      pushThought('原创性热采样', summarizeOriginalitySummary(sectionOriginalitySummary), formatElapsed())
    }
              sourceText.set(txt)
              lastSavedText = txt
              partialSavedSnapshot = txt
            } else {
              lastSavedText = $sourceText
              partialSavedSnapshot = $sourceText
            }
            pushToast('已保存', 'ok')
            return
          }
        } else if (ops && ops.length === 0) {
          lastSavedText = $sourceText
          partialSavedSnapshot = $sourceText
          lastSavedDocIr = $docIr
          return
        }
      }
      const payload: Record<string, unknown> = { text: $sourceText }
      if (!$docIrDirty && $docIr) payload.doc_ir = $docIr
      await fetch(`/api/doc/${id}/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      lastSavedText = $sourceText
      partialSavedSnapshot = $sourceText
      if (!$docIrDirty && $docIr) {
        lastSavedDocIr = $docIr
      } else {
        lastSavedDocIr = null
      }
      pushToast('已保存', 'ok')
    } catch (err) {
      pushToast(`保存失败: ${err instanceof Error ? err.message : '未知错误'}`, 'error')
    }
  }

  function formatVersionTime(ts: number) {
    if (!ts) return ''
    try {
      return new Date(ts * 1000).toLocaleString()
    } catch {
      return String(ts)
    }
  }

  function formatVersionSummary(summary: any) {
    if (!summary || typeof summary !== 'object') return ''
    const ins = Number(summary.insert || 0)
    const del = Number(summary.delete || 0)
    const rep = Number(summary.replace || 0)
    const parts: string[] = []
    if (ins) parts.push(`新增${ins}`)
    if (rep) parts.push(`修改${rep}`)
    if (del) parts.push(`删除${del}`)
    return parts.join(' / ')
  }

  function buildVersionGroups(list: Array<any>) {
    const groups: Array<any> = []
    let current: any = null
    list.forEach((v) => {
      const tags = Array.isArray(v?.tags) ? v.tags : []
      const kind = v?.kind || (tags.includes('major') ? 'major' : tags.includes('minor') ? 'minor' : '')
      const isMajor = kind === 'major'
      if (isMajor || !current) {
        current = { major: v, minors: [] }
        groups.push(current)
      } else {
        current.minors.push(v)
      }
    })
    return groups
  }

  async function loadVersionLog() {
    if (!$docId) return
    versionLoading = true
    versionError = ''
    try {
      const resp = await fetch(`/api/doc/${$docId}/version/log?branch=main&limit=50`)
      if (!resp.ok) throw new Error(await resp.text())
      const data = await resp.json()
      versionList = Array.isArray(data.versions) ? data.versions : []
      versionGroups = buildVersionGroups(versionList)
    } catch (err) {
      versionError = err instanceof Error ? err.message : '加载失败'
    } finally {
      versionLoading = false
    }
  }

  async function openVersions() {
    showVersions = true
    versionDiff = ''
    versionTree = ''
    await loadVersionLog()
  }

  async function commitVersion() {
    if (!$docId) return
    const msg = versionMessage.trim() || '定稿版本'
    try {
      const resp = await fetch(`/api/doc/${$docId}/version/commit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg, author: 'user', kind: 'major' })
      })
      if (!resp.ok) throw new Error(await resp.text())
      versionMessage = ''
      await loadVersionLog()
      pushToast('已提交版本', 'ok')
    } catch (err) {
      pushToast(`提交失败: ${err instanceof Error ? err.message : '未知错误'}`, 'error')
    }
  }

  async function checkoutVersion(vid: string) {
    if (!$docId || !vid) return
    try {
      const resp = await fetch(`/api/doc/${$docId}/version/checkout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ version_id: vid })
      })
      if (!resp.ok) throw new Error(await resp.text())
      const data = await resp.json()
      const txt = String(data.doc_text || '')
      applyFinalSnapshot(txt)
      lastSavedText = txt
      await loadVersionLog()
      pushToast('已切换版本', 'ok')
    } catch (err) {
      pushToast(`切换失败: ${err instanceof Error ? err.message : '未知错误'}`, 'error')
    }
  }

  async function loadVersionDiff(fromId: string, toId: string) {
    if (!$docId || !fromId || !toId) return
    versionDiff = ''
    versionDiffFrom = fromId
    versionDiffTo = toId
    try {
      const resp = await fetch(`/api/doc/${$docId}/version/diff?from_version=${fromId}&to_version=${toId}`)
      if (!resp.ok) throw new Error(await resp.text())
      const data = await resp.json()
      const diff = Array.isArray(data.diff) ? data.diff : []
      versionDiff = diff.join('\n')
    } catch (err) {
      versionDiff = err instanceof Error ? err.message : '对比失败'
    }
  }

  async function compareWithCurrent(targetId: string) {
    if (!targetId) return
    const current = versionList.find((v: any) => v.is_current)
    if (!current || current.version_id === targetId) return
    await loadVersionDiff(current.version_id, targetId)
  }

  async function loadVersionTree() {
    if (!$docId) return
    versionTree = ''
    try {
      const resp = await fetch(`/api/doc/${$docId}/version/tree`)
      if (!resp.ok) throw new Error(await resp.text())
      const data = await resp.json()
      const nodes = Array.isArray(data.nodes) ? data.nodes : []
      const edges = Array.isArray(data.edges) ? data.edges : []
      const lines: string[] = []
      lines.push('节点：')
      for (const n of nodes) {
        const id = String(n.id || '').slice(0, 7)
        const msg = String(n.message || '')
        const ts = formatVersionTime(Number(n.timestamp || 0))
        const cur = n.is_current ? ' *当前*' : ''
        lines.push(`- ${id} ${msg} ${ts}${cur}`)
      }
      lines.push('')
      lines.push('边：')
      for (const e of edges) {
        const from = String(e.from || '').slice(0, 7)
        const to = String(e.to || '').slice(0, 7)
        lines.push(`- ${from} -> ${to}`)
      }
      versionTree = lines.join('\n')
    } catch (err) {
      versionTree = err instanceof Error ? err.message : '版本树加载失败'
    }
  }


  async function preflightExport(format: 'docx' | 'pdf') {
    if (!$docId) return false
    try {
      const resp = await fetch(`/api/doc/${$docId}/export/check?format=${format}&auto_fix=1`)
      if (!resp.ok) {
        const msg = await resp.text()
        pushToast(`导出校验失败: ${msg || resp.statusText}`, 'bad')
        return false
      }
      const data = await resp.json()
      const canExport = Boolean(data?.can_export)
      const issues = Array.isArray(data?.issues) ? data.issues : []
      const warnings = Array.isArray(data?.warnings) ? data.warnings : []
      if (warnings.length > 0) {
        pushToast('导出前已自动修复文档结构。', 'info')
      }
      if (!canExport) {
        const first = issues[0]
        const msg = String(first?.message || '导出前校验未通过')
        const citationBlocked = issues.some((x: any) => String(x?.code || '').startsWith('citation_'))
        if (citationBlocked) {
          showCitations = true
          pushToast(`${msg} 已自动打开“引用”面板，请先点击“核验引用”。`, 'bad')
        } else {
          pushToast(msg, 'bad')
        }
        return false
      }
      return true
    } catch (err) {
      pushToast(`导出校验失败: ${err instanceof Error ? err.message : '未知错误'}`, 'bad')
      return false
    }
  }

  async function exportPdf() {
    if (!$docId) return
    const ready = await preflightExport('pdf')
    if (!ready) return
    pushToast('正在生成PDF...', 'info')
    window.location.href = `/download/${$docId}.pdf`
  }

  function handleDocSelect(selectedDocId: string) {
    showDocList = false
    window.location.href = `/workbench/${selectedDocId}`
  }

  async function exportDocx() {
    if (!$docId) return
    const ready = await preflightExport('docx')
    if (!ready) return
    pushToast('正在生成Word文档...', 'info')
    window.location.href = `/download/${$docId}.docx`
  }

  async function resumeInterruptedGeneration() {
    if (!resumeState || $generating) return
    const inst = String(resumeState.user_instruction || resumeState.request_instruction || '').trim()
    if (!inst) {
      pushToast('没有可续跑的历史指令', 'info')
      return
    }
    const pendingSections = pendingResumeSections(resumeState)
    await handleGenerate(inst, {
      fromResume: true,
      forcedComposeMode: 'continue',
      resumeSections: pendingSections,
      cursorAnchor: resumeState.cursor_anchor || ''
    })
  }

  function pendingResumeSections(state: ResumeState | null): string[] {
    if (!state) return []
    const pending = normalizeStringArray(state.pending_sections || [])
    if (pending.length) return pending
    const plan = normalizeStringArray(state.plan_sections || [])
    const completed = new Set(normalizeStringArray(state.completed_sections || []))
    return plan.filter((section) => !completed.has(section))
  }

  function clearPendingGenerateConfirmation() {
    pendingGenerateConfirmation = null
    confirmDialogBusy = false
  }

  function openPendingGenerateConfirmation(
    requestPayload: Record<string, unknown>,
    data: Record<string, unknown>,
    opts?: { fromStream?: boolean }
  ) {
    pendingGenerateConfirmation = {
      requestPayload: { ...requestPayload },
      note: String(data.note || ''),
      reason: String(data.confirmation_reason || 'high_risk_edit'),
      riskLevel: String(data.risk_level || 'high'),
      planSource: String(data.plan_source || 'rules'),
      operationsCount: Number(data.operations_count || 0)
    }
    confirmDialogBusy = false
    docStatus.set('待确认：检测到高风险编辑')
    flowStatus.set('待确认')
    const from = opts?.fromStream ? '流式生成' : '非流式生成'
    const reason = pendingGenerateConfirmation.note || `检测到高风险编辑，来源 ${from}。`
    appendChat('system', reason)
    pushThought('待确认', reason, formatElapsed())
    pushToast('检测到高风险编辑，请确认后执行。', 'info')
  }

  async function runNonStreamGenerate(
    requestPayload: Record<string, unknown>,
    opts?: { completionMsg?: string; fromStream?: boolean }
  ): Promise<'applied' | 'pending'> {
    lastGraphMeta = null
    const resp = await fetch(`/api/doc/${$docId}/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestPayload)
    })
    if (!resp.ok) {
      const msg = await resp.text()
      throw new Error(`HTTP ${resp.status}: ${msg || resp.statusText}`)
    }
    const data = (await resp.json()) as Record<string, unknown>
    if (Boolean(data.requires_confirmation)) {
      openPendingGenerateConfirmation(requestPayload, data, { fromStream: opts?.fromStream })
      return 'pending'
    }
    const revisionMeta =
      data.revision_meta && typeof data.revision_meta === 'object'
        ? (data.revision_meta as Record<string, unknown>)
        : null
    if (revisionMeta) {
      pushThought('改写诊断', summarizeRevisionStatus(revisionMeta), formatElapsed())
    }
    const graphMeta = normalizeGraphMeta(data.graph_meta)
    if (graphMeta) {
      lastGraphMeta = graphMeta
      pushThought('图路由', `非流式 ${summarizeGraphMeta(graphMeta)}`, formatElapsed())
    }
    const txt = String(data.text || '')
    if (!sawSectionDelta) {
      const finalDoc =
        data.doc_ir && typeof data.doc_ir === 'object' ? (data.doc_ir as Record<string, unknown>) : null
      void typewriterSetText(txt, { finalDocIr: finalDoc })
    } else {
      const finalDoc =
        data.doc_ir && typeof data.doc_ir === 'object' ? (data.doc_ir as Record<string, unknown>) : null
      finalizeStreamText(txt, finalDoc)
    }
    docStatus.set('完成')
    flowStatus.set('完成')
    resumeState = null
    const doneMsg = String(opts?.completionMsg || '已完成生成。')
    appendChat('system', doneMsg)
    pushThought('完成', doneMsg, formatElapsed())
    pushToast('生成完成（非流式）', 'ok')
    saveDoc().catch(() => {})
    clearPendingGenerateConfirmation()
    return 'applied'
  }

  async function confirmPendingGenerate() {
    if (!pendingGenerateConfirmation || !$docId || $generating) return
    confirmDialogBusy = true
    generating.set(true)
    docStatus.set('执行高风险编辑中…')
    try {
      const payload: Record<string, unknown> = {
        ...pendingGenerateConfirmation.requestPayload,
        confirm_apply: true
      }
      const status = await runNonStreamGenerate(payload, {
        completionMsg: '已完成高风险编辑（确认执行）。'
      })
      if (status === 'pending') {
        pushToast('服务端仍要求确认，请检查风险策略配置。', 'info')
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : '确认执行失败'
      docStatus.set(`生成失败: ${msg}`)
      appendChat('system', msg)
      pushThought('错误', String(msg), formatElapsed())
      pushToast(String(msg), 'bad')
    } finally {
      confirmDialogBusy = false
      generating.set(false)
    }
  }

  function cancelPendingGenerate() {
    if (!pendingGenerateConfirmation) return
    clearPendingGenerateConfirmation()
    docStatus.set('已取消高风险编辑')
    flowStatus.set('已停止')
    pushToast('已取消执行。', 'info')
  }

  function looksLikeImageFile(file: File) {
    const name = String(file?.name || '').toLowerCase()
    return String(file?.type || '').startsWith('image/') || /\.(png|jpe?g|gif|bmp|webp|svg)$/i.test(name)
  }

  async function uploadAsset(
    file: File,
    opts?: { source?: 'assistant' | 'inline-image'; targetIds?: string[] }
  ) {
    if (!$docId || !file) return
    const form = new FormData()
    form.append('file', file, file.name)
    const source = opts?.source || 'assistant'
    const isImage = looksLikeImageFile(file)
    if (source === 'inline-image' && !isImage) {
      pushToast('选中段落插图仅支持图片文件。', 'info')
      return
    }
    try {
      pushToast(isImage ? '正在上传图片...' : '正在上传文件...', 'info')
      const resp = await fetch(`/api/doc/${$docId}/upload`, {
        method: 'POST',
        body: form
      })
      if (!resp.ok) throw new Error(await resp.text())
      const data = await resp.json()
      const uploadKind = String(data.kind || '')
      if (source === 'inline-image' && isImage) {
        const caption = file.name.replace(/\.[^.]+$/, '')
        insertDiagramIntoDoc(
          { caption, source: 'upload', filename: file.name },
          { targetIds: opts?.targetIds || [] }
        )
        saveDoc().catch(() => {})
        pushToast('图片上传成功，已插入选中内容后。', 'ok')
        appendChat('system', `已插入图片：${file.name}`)
        return
      }
      if (uploadKind === 'template') {
        pushToast('模板文件上传成功，已解析结构。', 'ok')
        appendChat('system', `模板已上传并解析：${file.name}`)
      } else {
        const msg = isImage
          ? '图片已上传到资料库。若要插入正文，请选中段落后点击“插图”。'
          : '文件上传成功，已纳入资料库。'
        pushToast(msg, 'ok')
        appendChat('system', `${msg}（${file.name}）`)
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : '上传失败'
      pushToast(msg, 'bad')
    }
  }

  function triggerInlineImageUpload() {
    if (!selectedBlockIds.length) return
    if (!ensureInlineEditAllowed('插图')) return
    pendingInlineImageTargets = selectedBlockIds.slice()
    uploadImageInput?.click()
  }

  function triggerInlineTableInsert() {
    if (!selectedBlockIds.length) return
    if (!ensureInlineEditAllowed('插表')) return
    insertTableIntoDoc({ targetIds: selectedBlockIds.slice() })
    saveDoc().catch(() => {})
  }

  async function handleInlineImageSelect(event: Event) {
    const input = event.currentTarget as HTMLInputElement | null
    const file = input?.files?.[0]
    const targets = pendingInlineImageTargets.slice()
    pendingInlineImageTargets = []
    if (file) await uploadAsset(file, { source: 'inline-image', targetIds: targets })
    if (input) input.value = ''
  }

  async function handleAssistantUpload(event: any) {
    const payload = event && typeof event === 'object' && 'detail' in event ? event.detail : event
    const file = payload?.file
    if (!file) return
    await uploadAsset(file, { source: 'assistant' })
  }

  function triggerLibraryUpload() {
    libraryUploadInput?.click()
  }

  async function handleLibraryUploadSelect(event: Event) {
    const input = event.currentTarget as HTMLInputElement | null
    const file = input?.files?.[0]
    if (file) await uploadAsset(file, { source: 'assistant' })
    if (input) input.value = ''
  }

  async function handleLibraryDrop(event: DragEvent) {
    event.preventDefault()
    const files = event.dataTransfer?.files
    if (!files || files.length === 0) return
    const all = Array.from(files)
    for (const file of all.slice(0, 10)) {
      await uploadAsset(file, { source: 'assistant' })
    }
  }

  function toggleDarkMode() {
    darkMode.update(v => !v)
    document.body.classList.toggle('dark', !$darkMode)
  }

  async function persistPlanConfirmPreference() {
    if (!$docId) return
    const payload = {
      decision: planConfirmDecision,
      score: Math.max(0, Math.min(5, Math.round(Number(planConfirmScore) || 0))),
      note: String(planConfirmNote || '').trim().slice(0, 300)
    }
    try {
      await fetch(`/api/doc/${$docId}/plan/confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
    } catch {
      // Ignore persistence errors; payload still travels with current generate request.
    }
  }

  async function handleGenerate(
    text: string,
    opts?: {
      fromQueue?: boolean
      fromResume?: boolean
      forcedComposeMode?: 'auto' | 'continue' | 'overwrite'
      resumeSections?: string[]
      cursorAnchor?: string
    }
  ) {
    const inst = sanitizeAiInputText(text, { trim: true, maxChars: 12000 })
    if (!inst) return
    const realBusy = $generating || typingActive || streamTypingActive
    const recentlyStarted = Date.now() - lastGenerateStartedAt < 1200
    const shouldHoldForQueueBadge = recentlyStarted && queuedGlobalInstructions.length > 0
    if (realBusy || (!opts?.fromResume && shouldHoldForQueueBadge)) {
      if (!opts?.fromQueue) {
        appendChat('user', inst)
        instruction.set('')
        queueGlobalInstruction(inst)
      }
      return
    }
    if (!$docId) {
      const reason = '缺少文档ID，请刷新或从 /workbench/{id} 进入'
      docStatus.set(`已中止: ${reason}`)
      pushThought('中止', reason, new Date().toLocaleTimeString())
      pushToast(reason, 'info')
      return
    }
    clearPendingGenerateConfirmation()
    lastGraphMeta = null
    if (opts?.fromQueue) {
      appendChat('system', '正在执行排队指令…')
    } else if (opts?.fromResume) {
      appendChat('system', '正在续跑上次中断任务…')
    } else {
      appendChat('user', inst)
      instruction.set('')
    }
    runEditorCommand('commit')
    const latestText = sanitizeAiDocumentText($sourceText || '')
    const hasExistingText = hasMeaningfulDocContent(latestText)
    const inferredMode = inferComposeMode(inst)
    let composeMode: 'auto' | 'continue' | 'overwrite' = opts?.forcedComposeMode || inferredMode || 'auto'
    if (!opts?.forcedComposeMode && !inferredMode && hasExistingText) {
      if (opts?.fromQueue) {
        composeMode = 'continue'
      } else {
        const useContinue = window.confirm(
          '检测到编辑区已有内容。\n确定：在当前内容基础上续写\n取消：覆盖重写当前文档'
        )
        composeMode = useContinue ? 'continue' : 'overwrite'
      }
    }
    let requestInstruction = inst
    if (!inferredMode && composeMode === 'continue') {
      requestInstruction = `请在保留现有内容结构和已写段落的前提下继续写作，不要删除或改写已有内容。\n\n用户需求：${inst}`
    } else if (!inferredMode && composeMode === 'overwrite') {
      requestInstruction = `请忽略当前已有正文，按用户需求从头完整重写，并用新内容覆盖旧内容。\n\n用户需求：${inst}`
    }
    const resumeSections = sanitizeAiStringList(opts?.resumeSections || [], { maxItems: 64, maxItemChars: 120 })
    const cursorAnchor = sanitizeAiInputText(opts?.cursorAnchor || '', { trim: true, maxChars: 260 })
    requestInstruction = sanitizeAiInputText(requestInstruction, { trim: true, maxChars: 12000 })
    resumeState = {
      status: 'running',
      updated_at: Date.now() / 1000,
      user_instruction: inst,
      request_instruction: requestInstruction,
      compose_mode: composeMode,
      partial_chars: String($sourceText || '').trim().length,
      partial_preview: String($sourceText || '').trim().slice(-240),
      plan_sections: resumeSections,
      completed_sections: [],
      pending_sections: resumeSections,
      cursor_anchor: cursorAnchor,
      error: ''
    }
    typingToken += 1
    lastGenerateStartedAt = Date.now()
    resetStreamTyping()
    resetStreamingSections()
    generating.set(true)
    docIrDirty.set(true)
    streamingLive = true
    flowStatus.set('分析')
    docStatus.set('生成中…')
    genStartTs = Date.now()
    lastEventName = ''
    lastProgressMsg = ''
    sawFinal = false
    sawError = false
    sawSectionDelta = false
    lastEventAt = Date.now()
    renderActivityAt = Date.now()
    let observedPlanSections = resumeSections.slice()
    let observedCompletedSections: string[] = []
    fallbackTriggered = false
    progress = { current: 0, total: 0, percent: 0, etaS: 0, section: "" }
    progressStart = Date.now()
    progressEvents = []
    maxEventGap = 0
    sectionFailures = []
    sectionOriginalitySummary = null
    pushThought('启动', '开始生成', new Date().toLocaleTimeString())
    aborter = new AbortController()

    isLoading.set(false)
    if (stallTimer) clearInterval(stallTimer)
    stallTimer = setInterval(() => {
      if (!$generating) return
      const idleMs = Date.now() - lastEventAt
      const avgGap =
        progressEvents.length > 0
          ? Math.round(progressEvents.reduce((a, b) => a + b, 0) / progressEvents.length)
          : 0
      let thresholdMs = Math.max(baseIdleMs, avgGap * 6 || 0, maxEventGap * 3 || 0, 90000)
      thresholdMs = Math.min(600000, thresholdMs)
      const preparing =
        /model preparing/i.test(lastProgressMsg) ||
        /解析中/.test(lastProgressMsg) ||
        lastEventName === 'analysis'
      if (preparing) thresholdMs = Math.max(thresholdMs, 180000)
      if (idleMs > thresholdMs && !fallbackTriggered) {
        fallbackTriggered = true
        aborter?.abort(`客户端超时：${Math.round(idleMs / 1000)}秒无事件，切换非流式生成`)
      }
    }, 1000)

    const selectionPayload = buildSelectedRevisionPayload(latestText)
    const generatePayload = buildGenerateRequestPayload({
      instruction: requestInstruction,
      text: latestText,
      composeMode,
      selection: selectionPayload,
      resumeSections,
      cursorAnchor,
      planConfirm: {
        decision: planConfirmDecision,
        score: Math.max(0, Math.min(5, Math.round(Number(planConfirmScore) || 0))),
        note: String(planConfirmNote || '').trim().slice(0, 300)
      }
    })

    try {
      await streamSsePost(
        `/api/doc/${$docId}/generate/stream`,
        generatePayload,
        (event, data) => {
          const now = Date.now()
          lastEventName = String(event || '')
          if (lastEventAt > 0) {
            lastEventGap = now - lastEventAt
            if (lastEventGap > 0 && lastEventGap < 120000) {
              progressEvents = [...progressEvents, lastEventGap].slice(-8)
            }
            if (lastEventGap > maxEventGap && lastEventGap < 600000) {
              maxEventGap = lastEventGap
            }
          }
          lastEventAt = now
          if (event === 'state') {
            const name = mapStateName(String(data.name || ''))
            flowStatus.set(name || $flowStatus)
            pushThought('流程', name, formatElapsed())
            return
          }
          if (event === 'delta') {
            const msg = String(data.delta || '').trim()
            if (msg) {
              docStatus.set(msg)
              lastProgressMsg = msg
              pushThought('进度', msg, formatElapsed())
            }
            return
          }
          if (event === 'plan') {
            const title = String(data.title || '自动生成文档')
            const sectionsRaw = Array.isArray(data.sections) ? data.sections : []
            const sections = sectionsRaw.map((item) => decodeSectionTitle(String(item || ''))).filter(Boolean)
            observedPlanSections = sections.slice()
            observedCompletedSections = []
            if (resumeState) {
              resumeState = {
                ...resumeState,
                plan_sections: sections,
                completed_sections: [],
                pending_sections: sections
              }
            }
            pushThought('大纲', `标题：${title}；章节：${sections.join(' / ')}`, formatElapsed())
            const nextText = ensureSkeletonInText($sourceText, title, sections)
            sourceText.set(nextText)
            scheduleDocIrRefresh(nextText)
            return
          }
          if (event === 'section') {
            const phase = String(data.phase || '')
            const section = String(data.section_key || data.section || '')
            if (phase === 'start' || phase === 'end') {
              markStreamingSection(section, phase)
            }
            if (phase === 'end') {
              const sec = decodeSectionTitle(String(section || '')).trim()
              if (resumeState && sec) {
                const done = normalizeStringArray([...resumeState.completed_sections, sec])
                observedCompletedSections = normalizeStringArray([...observedCompletedSections, sec])
                const plan = resumeState.plan_sections || []
                const pending = plan.filter((item) => !done.includes(item))
                resumeState = {
                  ...resumeState,
                  completed_sections: done,
                  pending_sections: pending
                }
              }
            }
            if (phase === 'delta') {
              sawSectionDelta = true
              const blockId = String(data.block_id || '')
              const blockType = String(data.block_type || '')
              if (blockId) {
                insertBlockFromStore(section, blockId)
                return
              }
              const deltaText = String(data.delta || '')
              if (deltaText) {
                const isRawStream = !section && !blockType
                enqueueStreamDelta(section, deltaText, { raw: isRawStream })
              }
            }
            return
          }
          if (event === 'progress') {
            const current = Number(data.current || 0)
            const total = Number(data.total || 0)
            const percent = Number(data.percent || 0)
            const section = decodeSectionTitle(String(data.section || ''))
            const elapsedS = Number(data.elapsed_s || 0)
            if (progressStart === 0) progressStart = Date.now()
            if (current > 0) {
              const elapsed = elapsedS > 0 ? elapsedS : Math.max(1, Math.round((Date.now() - progressStart) / 1000))
              const avg = elapsed / current
              const remaining = Math.max(0, Math.round(avg * Math.max(0, total - current)))
              progress = { current, total, percent, etaS: remaining, section }
            } else {
              progress = { current, total, percent, etaS: 0, section }
            }
            return
          }
          if (event === 'section_error') {
            const section = String(data.section || '')
            const reason = String(data.reason || '未知')
            if (section) {
              sectionFailures = [...sectionFailures, { section, reason }]
              pushToast(`章节失败: ${section}`, 'bad')
            }
            return
          }
          if (event === 'analysis') {
            const summary = String(data.summary || '')
            const steps = Array.isArray(data.steps) ? data.steps : []
            const missing = Array.isArray(data.missing) ? data.missing : []
            thinkingSummary.set(summary || '等待解析…')
            thinkingSteps.set(steps)
            thinkingMissing.set(missing)
            pushThought('解析', summary || '解析完成', formatElapsed())
            if (data.raw) {
              const rawPreview = JSON.stringify(data.raw, null, 2).slice(0, 600)
              pushThought('解析JSON', rawPreview, formatElapsed())
            }
            return
          }
          if (event === 'revision_status') {
            const status = data && typeof data === 'object' ? (data as Record<string, unknown>) : {}
            const note = summarizeRevisionStatus(status)
            pushThought('改写诊断', note, formatElapsed())
            if (status.ok !== true) {
              pushToast(note, 'info')
            }
            return
          }
          if (event === 'confirmation_required') {
            sawFinal = true
            openPendingGenerateConfirmation(generatePayload, data as Record<string, unknown>, { fromStream: true })
            return
          }
          if (event === 'final') {
            const txt = String(data.text || '')
            const qualitySnapshot =
              data.quality_snapshot && typeof data.quality_snapshot === 'object'
                ? (data.quality_snapshot as Record<string, unknown>)
                : null
            sectionOriginalitySummary = normalizeOriginalitySummary(qualitySnapshot?.section_originality_hot_sample)
            if (sectionOriginalitySummary) {
              pushThought('原创性热采样', summarizeOriginalitySummary(sectionOriginalitySummary), formatElapsed())
            }
            const graphMeta = normalizeGraphMeta(data.graph_meta)
            const terminalStatusRaw = String(data.status || (data.graph_meta && (data.graph_meta as any).terminal_status) || 'success')
              .trim()
              .toLowerCase()
            const terminalStatus =
              terminalStatusRaw === 'failed' || terminalStatusRaw === 'interrupted' || terminalStatusRaw === 'success'
                ? terminalStatusRaw
                : 'success'
            const failureReason = String(data.failure_reason || (data.graph_meta && (data.graph_meta as any).failure_reason) || '').trim()
            const revisionMeta =
              data.revision_meta && typeof data.revision_meta === 'object'
                ? (data.revision_meta as Record<string, unknown>)
                : null
            if (graphMeta) {
              lastGraphMeta = graphMeta
              pushThought('图路由', `流式 ${summarizeGraphMeta(graphMeta)}`, formatElapsed())
            }
            if (revisionMeta) {
              pushThought('改写诊断', summarizeRevisionStatus(revisionMeta), formatElapsed())
            }
            if (!sawSectionDelta) {
              const finalDoc =
                data.doc_ir && typeof data.doc_ir === 'object' ? (data.doc_ir as Record<string, unknown>) : null
              void typewriterSetText(txt, { finalDocIr: finalDoc })
            } else {
              const finalDoc =
                data.doc_ir && typeof data.doc_ir === 'object' ? (data.doc_ir as Record<string, unknown>) : null
              finalizeStreamText(txt, finalDoc)
            }
            if (terminalStatus === 'interrupted') {
              docStatus.set(failureReason ? `已中断: ${failureReason}` : '已中断')
              flowStatus.set('已中断')
            } else if (terminalStatus === 'failed') {
              docStatus.set(failureReason ? `生成失败: ${failureReason}` : '生成失败')
              flowStatus.set('失败')
            } else {
              docStatus.set('完成')
              flowStatus.set('完成')
            }
            sawFinal = true
            resumeState = null
            if (terminalStatus === 'interrupted') {
              appendChat('system', failureReason ? `任务已中断：${failureReason}` : '任务已中断。')
              pushThought('中断', failureReason || '任务已中断', formatElapsed())
              pushToast(failureReason ? `任务已中断：${failureReason}` : '任务已中断', 'info')
            } else if (terminalStatus === 'failed') {
              appendChat('system', failureReason ? `生成失败：${failureReason}` : '生成失败。')
              pushThought('失败', failureReason || '生成失败', formatElapsed())
              pushToast(failureReason ? `生成失败：${failureReason}` : '生成失败', 'bad')
            } else {
              appendChat('system', '已完成生成。')
              pushThought('完成', '生成完成', formatElapsed())
              pushToast('生成完成', 'ok')
            }
            saveDoc().catch(() => {})
            return
          }
          if (event === 'error') {
            const msg = String(data.message || data.reason || data.detail || '服务端未返回具体原因')
            const code = String(data.code || data.type || '')
            const isAbort =
              code.toLowerCase().includes('abort') ||
              /aborted|stopped|取消|中止/i.test(msg)
            sawError = true
            docStatus.set(isAbort ? `已中止: ${msg}` : `生成失败: ${msg}`)
            appendChat('system', msg)
            pushThought(isAbort ? '中止' : '错误', msg, formatElapsed())
            pushToast(msg, isAbort ? 'info' : 'bad')
          }
        },
        aborter.signal
      )
      if (!sawFinal && !sawError) {
        const reason = lastProgressMsg
          ? `流式结束但未完成，最后进度: ${lastProgressMsg}`
          : lastEventName
            ? `流式结束但未完成，最后事件: ${lastEventName}`
            : '流式结束但未完成，服务端未返回原因'
        docStatus.set(`已中止: ${reason}`)
        appendChat('system', reason)
        pushThought('中止', reason, formatElapsed())
        pushToast(reason, 'info')
      }
    } catch (e: any) {
      if (String(e?.name || '') === 'AbortError') {
            const reason =
              (aborter?.signal as any)?.reason ||
              e?.message ||
              '用户中止'
        if (String(reason).includes('切换非流式生成')) {
          pushThought('中止', String(reason), formatElapsed())
          pushToast(String(reason), 'info')
          try {
            const status = await runNonStreamGenerate(generatePayload, {
              completionMsg: '已完成生成（非流式兜底）。',
              fromStream: true
            })
            if (status === 'applied' || status === 'pending') {
              sawFinal = true
            }
          } catch (err: any) {
            const msg = err?.message || '非流式生成失败'
            docStatus.set(`生成失败: ${msg}`)
            appendChat('system', msg)
            pushThought('错误', String(msg), formatElapsed())
            pushToast(String(msg), 'bad')
          }
        } else {
          docStatus.set(`已中止: ${reason}`)
          appendChat('system', `已中止生成：${reason}`)
          pushThought('中止', String(reason), formatElapsed())
          pushToast(String(reason), 'info')
        }
      } else {
        const msg = e?.message || '生成失败，请检查模型是否运行。'
        docStatus.set(`生成失败: ${msg}`)
        appendChat('system', msg)
        pushThought('错误', String(msg), formatElapsed())
        pushToast(String(msg), 'bad')
      }
    } finally {
      if (!sawFinal) {
        const preview = String($sourceText || '').trim()
        const prev = resumeState
        const planSections = normalizeStringArray(prev?.plan_sections?.length ? prev.plan_sections : observedPlanSections)
        const completedSections = normalizeStringArray(
          prev?.completed_sections?.length ? prev.completed_sections : observedCompletedSections
        )
        let pendingSections = normalizeStringArray(prev?.pending_sections || [])
        if (!pendingSections.length && planSections.length) {
          const completedSet = new Set(completedSections)
          pendingSections = planSections.filter((section) => !completedSet.has(section))
        }
        resumeState = {
          status: 'interrupted',
          updated_at: Date.now() / 1000,
          user_instruction: String(prev?.user_instruction || inst),
          request_instruction: String(prev?.request_instruction || requestInstruction),
          compose_mode: (prev?.compose_mode || composeMode) as ResumeState['compose_mode'],
          partial_chars: preview.length,
          partial_preview: preview.slice(-240),
          plan_sections: planSections,
          completed_sections: completedSections,
          pending_sections: pendingSections,
          cursor_anchor: String(prev?.cursor_anchor || cursorAnchor),
          error: String($docStatus || '')
        }
        void savePartialDraft()
      }
      generating.set(false)
      isLoading.set(false)
      streamingLive = false
      resetStreamingSections()
      if (partialSaveTimer) {
        clearTimeout(partialSaveTimer)
        partialSaveTimer = null
      }
      if (docIrRefreshTimer) {
        clearTimeout(docIrRefreshTimer)
        docIrRefreshTimer = null
      }
      if (stallTimer) {
        clearInterval(stallTimer)
        stallTimer = null
      }
      if (maxEventGap > 0 && typeof localStorage !== 'undefined') {
        const recommended = Math.min(600000, Math.max(baseIdleMs, maxEventGap * 3, 90000))
        baseIdleMs = recommended
        try {
          localStorage.setItem('wa_idle_base_ms', String(recommended))
        } catch {}
      }
      aborter = null
      if (queuedGlobalInstructions.length) {
        queueMicrotask(() => {
          void drainQueuedGlobalInstructions()
        })
      }
    }
  }

  async function refreshDocIr() {
    const id = $docId
    if (!id) return
    try {
      const resp = await fetch(`/api/doc/${id}`)
      if (!resp.ok) return
      const data = await resp.json()
      if (data.doc_ir && typeof data.doc_ir === 'object') {
        const normalized = normalizeDocIrParagraphBlocks(data.doc_ir as Record<string, unknown>)
        docIr.set(normalized)
        docIrDirty.set(false)
      }
    } catch {}
  }

  async function retrySection(section: string) {
    const id = $docId
    const target = sanitizeAiInputText(section, { trim: true, maxChars: 120 })
    if (!id || !target || $generating) return
    runEditorCommand('commit')
    await saveDoc().catch(() => {})
    generating.set(true)
    docStatus.set(`重试章节：${target}`)
    try {
      const resp = await fetch(`/api/doc/${id}/generate/section`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          section: target,
          instruction: sanitizeAiInputText($instruction || '', { trim: true, maxChars: 12000 }),
        })
      })
      if (!resp.ok) {
        throw new Error(await resp.text())
      }
      const data = await resp.json()
      const graphMeta = normalizeGraphMeta(data.graph_meta)
      if (graphMeta) {
        lastGraphMeta = graphMeta
        pushThought('图路由', `章节重试 ${summarizeGraphMeta(graphMeta)}`, new Date().toLocaleTimeString())
      }
      const text = String(data.text || '')
      if (text) {
        sourceText.set(text)
        docStatus.set('完成')
        appendChat('system', `章节重试完成：${target}`)
      }
      if (data.doc_ir && typeof data.doc_ir === 'object') {
        const normalized = normalizeDocIrParagraphBlocks(data.doc_ir as Record<string, unknown>)
        docIr.set(normalized)
        docIrDirty.set(false)
      } else if (text) {
        docIrDirty.set(true)
      }
      sectionFailures = sectionFailures.filter((f) => f.section !== target)
      pushToast(`章节重试完成: ${target}`, 'ok')
      saveDoc().catch(() => {})
    } catch (err) {
      const msg = err instanceof Error ? err.message : '章节重试失败'
      docStatus.set(`重试失败: ${msg}`)
      pushToast(`章节重试失败: ${msg}`, 'bad')
    } finally {
      generating.set(false)
    }
  }

  async function reviseRiskSection(section: string) {
    const id = $docId
    const target = sanitizeAiInputText(section, { trim: true, maxChars: 120 })
    if (!id || !target || $generating) return
    runEditorCommand('commit')
    await saveDoc().catch(() => {})
    generating.set(true)
    docStatus.set(`正在修订${target}`)
    try {
      const resp = await fetch(`/api/doc/${id}/revise`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          instruction:
            '仅重写指定章节，降低模板化和重复表达，保留原有论点、证据、引用与章节位置，不要改动其他章节，不要输出解释或元指令。',
          text: $sourceText || '',
          doc_ir: $docIr,
          target_section: target,
          allow_unscoped_fallback: false
        })
      })
      if (!resp.ok) {
        throw new Error(await resp.text())
      }
      const data = await resp.json()
      const revisedText = String(data.text || '')
      const revisionMeta =
        data.revision_meta && typeof data.revision_meta === 'object'
          ? (data.revision_meta as Record<string, unknown>)
          : null
      if (revisedText) {
        sourceText.set(revisedText)
        docStatus.set('已修订')
        appendChat('system', `已按风险定向修订章节：${target}`)
      }
      if (data.doc_ir && typeof data.doc_ir === 'object') {
        const normalized = normalizeDocIrParagraphBlocks(data.doc_ir as Record<string, unknown>)
        docIr.set(normalized)
        docIrDirty.set(false)
      } else if (revisedText) {
        docIrDirty.set(true)
      }
      if (revisionMeta) {
        pushThought('定向修订', `${target} · ${summarizeRevisionStatus(revisionMeta)}`, new Date().toLocaleTimeString())
      }
      pushToast(`已完成风险章节修订: ${target}`, 'ok')
      saveDoc().catch(() => {})
    } catch (err) {
      const msg = err instanceof Error ? err.message : '修订失败'
      docStatus.set(`修订失败: ${msg}`)
      pushToast(`修订失败: ${msg}`, 'bad')
    } finally {
      generating.set(false)
    }
  }

  function handleStop() {
    if (aborter) aborter.abort('用户点击停止')
  }

  function runEditorCommand(cmd: EditorCommand) {
    editorCommand.set(cmd)
  }

  $effect(() => {
    if ($sourceText && $sourceText !== lastSavedText && !$generating) {
      if (autoSaveTimer) clearTimeout(autoSaveTimer)
      autoSaveTimer = setTimeout(() => {
        saveDoc().catch(() => {})
      }, 3000)
    }
  })

  $effect(() => {
    if (!isGenerationOrRenderBusy()) {
      inlineEditLocked = false
      inlineEditLockReason = ''
    } else if (!$generating) {
      inlineEditLocked = true
      inlineEditLockReason = '当前内容仍在渲染，请等待打字机输出结束后再修改。'
    } else {
      const keys = selectedSectionKeys()
      if (!keys.length) {
        inlineEditLocked = true
        inlineEditLockReason = '当前仍在生成。请先选择已完成章节下的段落块。'
      } else {
        const waiting = keys.filter(
          (key) => !completedStreamingSections.includes(key) || activeStreamingSections.includes(key)
        )
        inlineEditLocked = waiting.length > 0
        inlineEditLockReason = inlineEditLocked
          ? '选中块所在章节仍在生成，请等待该章节完成后再修改。'
          : ''
      }
    }
  })

  onMount(() => {
    const savedDarkMode = localStorage.getItem('darkMode') === 'true'
    darkMode.set(savedDarkMode)
    if (savedDarkMode) document.body.classList.add('dark')
    const storedIdle = localStorage.getItem('wa_idle_base_ms')
    if (storedIdle) {
      const n = Number(storedIdle)
      if (Number.isFinite(n) && n > 0) baseIdleMs = n
    }
    startWasmInit()
    
    const onMove = (e: MouseEvent) => {
      if (!resizing) return
      const root = document.querySelector('.grid') as HTMLElement
      if (!root) return
      const rect = root.getBoundingClientRect()
      const x = Math.min(Math.max(e.clientX - rect.left, 220), rect.width - 260)
      leftWidth = Math.round((x / rect.width) * 100)
    }
    const onUp = () => {
      resizing = false
      document.body.style.cursor = ''
    }
    const onViewportChange = () => {
      updateInlineOverlayPosition()
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    window.addEventListener('resize', onViewportChange)
    window.addEventListener('scroll', onViewportChange, true)
    window.addEventListener('keydown', handleGlobalKeydownCapture, true)
    window.addEventListener('keydown', handleInlineShortcut)
    if (!$docId) {
      const id = readDocId()
      if (id) {
        docId.set(id)
        loadDoc().then(() => Promise.all([loadChat(), loadThoughts(), loadFeedback()])).catch(() => {})
      }
    }
    return () => {
      saveCurrentBlockSession()
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      window.removeEventListener('resize', onViewportChange)
      window.removeEventListener('scroll', onViewportChange, true)
      window.removeEventListener('keydown', handleGlobalKeydownCapture, true)
      window.removeEventListener('keydown', handleInlineShortcut)
      if (autoSaveTimer) clearTimeout(autoSaveTimer)
      if (recentQueuedBadgeTimer) clearTimeout(recentQueuedBadgeTimer)
    }
  })
</script>

<main class="app" class:dark={$darkMode}>
  <header class="topbar">
    <div class="brand">
      <div class="logo">IR</div>
      <div class="brand-text">
        <div class="brand-title">Astra 写作工作台</div>
        <div class="brand-sub">图路由引擎 · 结构化编辑</div>
      </div>
    </div>
    <div class="workspace-hub">
      <div class="workspace-status-line" title={topStatusLine}>
        <span class="dot"></span>
        <span>{topStatusLine}</span>
      </div>
      <nav class="menu" aria-label="工作区模式">
        <button class={`menu-item ${workspaceMode === 'editor' ? 'active' : ''}`} onclick={() => switchWorkspaceMode('editor')}>
          <span>编辑</span>
        </button>
        <button class={`menu-item ${workspaceMode === 'library' ? 'active' : ''}`} onclick={() => switchWorkspaceMode('library')}>
          <span>资料</span>
        </button>
        <button class={`menu-item ${workspaceMode === 'collab' ? 'active' : ''}`} onclick={() => switchWorkspaceMode('collab')}>
          <span>协作</span>
        </button>
      </nav>
      <div class="workspace-metrics" aria-label="工作台概览">
        <div class={`metric-pill tone-${qualityOverview.tone}`}>
          <span class="metric-label">质量</span>
          <strong>{qualityOverview.label}</strong>
        </div>
        <div class="metric-pill">
          <span class="metric-label">字数</span>
          <strong>{Math.max(0, Number($wordCount || 0))}</strong>
        </div>
        <div class="metric-pill">
          <span class="metric-label">路由</span>
          <strong>{lastGraphMeta?.route_id || '默认'}</strong>
        </div>
      </div>
    </div>
    <div class="top-actions">
      <button class="btn ghost icon-btn-text" onclick={saveDoc}>
        <Icon name="save" className="ui-icon" />
        <span>保存</span>
      </button>
      <button class="btn ghost icon-btn-text" onclick={exportDocx}>
        <Icon name="doc" className="ui-icon" />
        <span>导出 Word</span>
      </button>
      <button class="btn ghost icon-btn-text" onclick={exportPdf}>
        <Icon name="pdf" className="ui-icon" />
        <span>导出 PDF</span>
      </button>
      <button class="btn ghost icon-btn-text" onclick={toggleInfoDrawer}>
        <Icon name="doc" className="ui-icon" />
        <span>文档信息</span>
      </button>
      <LLMConfig />
      <Settings />
    </div>
  </header>

  <div class={`workspace ${hideLibraryInfo ? 'hide-info' : ''} mode-${workspaceMode}`}>
    <aside class="nav-rail">
      <div class="rail-search">
        <input
          type="text"
          placeholder="搜索资料卡片..."
          bind:value={librarySearch}
        />
      </div>
      <button class="rail-upload-btn icon-btn-text" onclick={triggerLibraryUpload}>
        <Icon name="upload" className="ui-icon" />
        <span>上传素材</span>
      </button>
      <div class="rail-tip">将图片、模板或参考文档拖入编辑区，可直接纳入当前工程。</div>

      <section class="rail-library">
        <div class="rail-group-head">
          <span>资料流</span>
          <em>{filteredLibraryCards.length}</em>
        </div>
        <div class={`library-card-stream ${libraryViewMode}`}>
          {#if filteredLibraryCards.length === 0}
            <div class="library-empty">没有匹配项，试试其他关键词。</div>
          {:else}
            {#each filteredLibraryCards as card}
              <button
                class={`library-card tone-${card.tone} ${librarySelectAll || selectedLibraryCardId === card.id ? 'selected' : ''}`}
                onclick={() => openLibraryCard(card)}
                title={card.summary}
              >
                <div class="library-card-cover">
                  <span class={`library-status status-${card.status}`}>{card.status_label}</span>
                  <span class="library-kind">{card.kind_label}</span>
                </div>
                <div class="library-card-body">
                  <div class="library-card-title-row">
                    <span class="library-card-title">{card.title}</span>
                    <span class="library-card-time">{formatLibraryCardTime(card.updated_at)}</span>
                  </div>
                  <div class="library-card-summary">{card.summary}</div>
                  <div class="library-card-tags">
                    {#each card.tags as tag}
                      <span>#{tag}</span>
                    {/each}
                  </div>
                </div>
              </button>
            {/each}
          {/if}
        </div>
      </section>

      <section class="rail-group workflow-group">
        <div class="rail-group-head">
          <span>快捷入口</span>
          <em>4</em>
        </div>
        <button class={`nav-btn ${workspaceMode === 'editor' ? 'active' : ''}`} onclick={() => switchWorkspaceMode('editor')} title="编辑器">
          <Icon name="editor" className="ui-icon" />
          <span>正文编辑</span>
        </button>
        <button class="nav-btn" onclick={() => (canvasOpen = true)} title="画布">
          <Icon name="canvas" className="ui-icon" />
          <span>图形画布</span>
        </button>
        <button class="nav-btn" title="引用" onclick={() => (showCitations = true)}>
          <Icon name="cite" className="ui-icon" />
          <span>引用管理</span>
        </button>
        <button class={`nav-btn ${workspaceMode === 'collab' ? 'active' : ''}`} title="协作助手" onclick={() => { switchWorkspaceMode('collab'); setAssistantOpen(true) }}>
          <Icon name="chat" className="ui-icon" />
          <span>协作助手</span>
        </button>
        <button class="nav-btn" title="性能" onclick={() => (showPerformanceMetrics = true)}>
          <Icon name="chart" className="ui-icon" />
          <span>性能指标</span>
        </button>
      </section>

      <button class="rail-reset icon-btn-text" onclick={() => { librarySearch = ''; librarySelectAll = false; selectedLibraryCardId = ''; }}>
        <Icon name="clearSelection" className="ui-icon" />
        <span>重置筛选</span>
      </button>
    </aside>

    <section class="doc-area">
      {#if workspaceMode === 'library'}
        <div class="library-command-bar">
          <div class="library-view-switch">
            <button
              class={`view-btn ${libraryViewMode === 'grid' ? 'active' : ''}`}
              onclick={() => (libraryViewMode = 'grid')}
              title="网格视图"
            >
              <Icon name="grid" className="ui-icon" />
            </button>
            <button
              class={`view-btn ${libraryViewMode === 'masonry' ? 'active' : ''}`}
              onclick={() => (libraryViewMode = 'masonry')}
              title="瀑布视图"
            >
              <Icon name="masonry" className="ui-icon" />
            </button>
            <button
              class={`view-btn ${libraryViewMode === 'list' ? 'active' : ''}`}
              onclick={() => (libraryViewMode = 'list')}
              title="列表视图"
            >
              <Icon name="list" className="ui-icon" />
            </button>
          </div>
          <div class="library-counter">{librarySearch ? `搜索：${librarySearch}` : '资料模式：拖拽素材、整理证据、批量管理'}</div>
          <div class="library-actions">
            <button class="btn ghost icon-btn-text" onclick={triggerLibraryUpload}>
              <Icon name="upload" className="ui-icon" />
              <span>上传素材</span>
            </button>
            <button class="btn ghost icon-btn-text" onclick={() => (librarySelectAll = !librarySelectAll)}>
              <Icon name="select" className="ui-icon" />
              <span>{librarySelectAll ? '取消全选' : '全选资料'}</span>
            </button>
            <button class="btn ghost icon-btn-text" onclick={() => switchWorkspaceMode('editor')}>
              <Icon name="open" className="ui-icon" />
              <span>返回编辑</span>
            </button>
          </div>
        </div>
        <section
          class="library-mode-stage"
          aria-label="资料模式拖拽工作区"
          ondragover={(e) => e.preventDefault()}
          ondrop={handleLibraryDrop}
        >
          <div class="library-mode-dropzone">
            <div class="panel-title">资料工作区</div>
            <div class="panel-sub">拖拽图片/文档到此处，或点击上传素材。资料模式默认不展示正文编辑器。</div>
            <div class="library-mode-actions">
              <button class="btn ghost icon-btn-text" onclick={triggerLibraryUpload}>
                <Icon name="upload" className="ui-icon" />
                <span>上传文件</span>
              </button>
              <button class="btn ghost icon-btn-text" onclick={() => (showCitations = true)}>
                <Icon name="cite" className="ui-icon" />
                <span>引用管理</span>
              </button>
              <button class="btn ghost icon-btn-text" onclick={openVersions}>
                <Icon name="clock" className="ui-icon" />
                <span>版本记录</span>
              </button>
            </div>
          </div>
          <div class={`library-mode-board ${libraryViewMode}`}>
            {#if filteredLibraryCards.length === 0}
              <div class="panel-empty">暂无匹配资料，请调整筛选条件或上传新素材。</div>
            {:else}
              {#each filteredLibraryCards as card}
                <button
                  class={`library-mode-card tone-${card.tone} ${librarySelectAll || selectedLibraryCardId === card.id ? 'selected' : ''}`}
                  onclick={() => openLibraryCard(card)}
                  title={card.summary}
                >
                  <div class="library-mode-card-head">
                    <span class={`library-status status-${card.status}`}>{card.status_label}</span>
                    <span class="library-kind">{card.kind_label}</span>
                  </div>
                  <div class="library-mode-card-title">{card.title}</div>
                  <div class="library-mode-card-summary">{card.summary}</div>
                  <div class="library-mode-card-foot">
                    <span>{formatLibraryCardTime(card.updated_at)}</span>
                    <span>{card.size_label}</span>
                  </div>
                </button>
              {/each}
            {/if}
          </div>
        </section>
      {:else}
      <div class="library-command-bar">
        <div class="library-view-switch">
          <button
            class={`view-btn ${libraryViewMode === 'grid' ? 'active' : ''}`}
            onclick={() => (libraryViewMode = 'grid')}
            title="网格视图"
          >
            <Icon name="grid" className="ui-icon" />
          </button>
          <button
            class={`view-btn ${libraryViewMode === 'masonry' ? 'active' : ''}`}
            onclick={() => (libraryViewMode = 'masonry')}
            title="瀑布视图"
          >
            <Icon name="masonry" className="ui-icon" />
          </button>
          <button
            class={`view-btn ${libraryViewMode === 'list' ? 'active' : ''}`}
            onclick={() => (libraryViewMode = 'list')}
            title="列表视图"
          >
            <Icon name="list" className="ui-icon" />
          </button>
        </div>
        <div class="library-counter">{librarySearch ? `搜索：${librarySearch}` : '实时文档工作区'}</div>
        <div class="library-actions">
          <button class="btn ghost icon-btn-text" onclick={() => (librarySelectAll = !librarySelectAll)}>
            <Icon name="select" className="ui-icon" />
            <span>{librarySelectAll ? '取消全选' : '全选资料'}</span>
          </button>
          <button class="btn ghost icon-btn-text">
            <Icon name="batch" className="ui-icon" />
            <span>批处理 ({librarySelectAll ? filteredLibraryCards.length : 1})</span>
          </button>
          <button class="btn ghost icon-btn-text" onclick={openInfoDrawer}>
            <Icon name="doc" className="ui-icon" />
            <span>文档信息</span>
          </button>
        </div>
      </div>
      <div class="doc-toolbar">
        <div class="toolbar-line primary">
          <div class="toolbar-cluster core">
            <span class="cluster-label">创作核心</span>
            <button class="tool-btn" onclick={() => runEditorCommand('heading1')} aria-label="一级标题">
              <Icon name="h1" size={14} className="ui-icon sm" />
            </button>
            <button class="tool-btn" onclick={() => runEditorCommand('heading2')} aria-label="二级标题">
              <Icon name="h2" size={14} className="ui-icon sm" />
            </button>
            <button
              class={`tool-btn ${editorToolbarState.bold ? 'active' : ''}`}
              title="加粗 Ctrl/Cmd+B"
              aria-label="加粗"
              onclick={() => runEditorCommand('bold')}
              disabled={editorToolbarState.readonly || !editorToolbarState.focused}
            >
              <Icon name="bold" size={14} className="ui-icon sm" />
            </button>
            <button class="tool-btn" onclick={() => runEditorCommand('list-bullet')} aria-label="无序列表">
              <Icon name="listBullet" size={14} className="ui-icon sm" />
            </button>
            <button class="tool-btn" onclick={() => runEditorCommand('list-number')} aria-label="有序列表">
              <Icon name="listNumber" size={14} className="ui-icon sm" />
            </button>
            <span class="tool-sep"></span>
            <button class="tool-btn" onclick={() => (canvasOpen = true)} aria-label="图形画布">
              <Icon name="diagram" size={14} className="ui-icon sm" />
            </button>
            <button class="tool-btn" onclick={() => (showCitations = true)} aria-label="引用管理">
              <Icon name="cite" size={14} className="ui-icon sm" />
            </button>
          </div>
          <button class="btn ghost btn-sm toolbar-advanced-toggle" onclick={() => (showAdvancedToolbar = !showAdvancedToolbar)}>
            {showAdvancedToolbar ? '收起高级' : '高级操作'}
          </button>
          <button class="btn primary icon-btn-text toolbar-generate-btn" onclick={() => handleGenerate($instruction)} disabled={$generating}>
            <Icon name="play" className="ui-icon" />
            <span>{$generating ? '生成中…' : '生成'}</span>
          </button>
        </div>
        {#if showAdvancedToolbar}
          <div class="toolbar-line secondary">
            <div class="toolbar-cluster">
              <span class="cluster-label">结构与编辑</span>
              <button class="tool-btn" title="撤销 Ctrl/Cmd+Z" aria-label="撤销" onclick={() => runEditorCommand('undo')} disabled={!editorToolbarState.canUndo}>
                <Icon name="undo" size={14} className="ui-icon sm" />
              </button>
              <button class="tool-btn" title="重做 Ctrl/Cmd+Y" aria-label="重做" onclick={() => runEditorCommand('redo')} disabled={editorToolbarState.readonly}>
                <Icon name="redo" size={14} className="ui-icon sm" />
              </button>
              <button class="tool-btn" title="复制 Ctrl/Cmd+C" aria-label="复制" onclick={() => runEditorCommand('copy')} disabled={!editorToolbarState.canCopy}>
                <Icon name="copy" size={14} className="ui-icon sm" />
              </button>
              <button class="tool-btn" title="剪切 Ctrl/Cmd+X" aria-label="剪切" onclick={() => runEditorCommand('cut')} disabled={!editorToolbarState.canCut}>
                <Icon name="cut" size={14} className="ui-icon sm" />
              </button>
              <button class="tool-btn" title="粘贴 Ctrl/Cmd+V" aria-label="粘贴" onclick={() => runEditorCommand('paste')} disabled={!editorToolbarState.canPaste}>
                <Icon name="paste" size={14} className="ui-icon sm" />
              </button>
              <button class="tool-btn" title="清除格式" aria-label="清除格式" onclick={() => runEditorCommand('clear-format')} disabled={editorToolbarState.readonly || !editorToolbarState.focused}>
                <Icon name="clear" size={14} className="ui-icon sm" />
              </button>
              <button class="tool-btn" onclick={() => runEditorCommand('quote')} aria-label="引用块">
                <Icon name="quote" size={14} className="ui-icon sm" />
              </button>
              <button class="tool-btn" onclick={() => runEditorCommand('code')} aria-label="代码块">
                <Icon name="code" size={14} className="ui-icon sm" />
              </button>
            </div>
            <div class="toolbar-cluster compact">
              <span class="cluster-label">高级操作</span>
              <button class="btn ghost icon-btn-text" onclick={runBatchFromToolbar}>
                <Icon name="batch" className="ui-icon" />
                <span>批处理</span>
              </button>
              <button
                class="btn ghost icon-btn-text"
                data-testid="ai-rate-toggle"
                onclick={() => (showAiRatePanel = !showAiRatePanel)}
              >
                <Icon name="ai" className="ui-icon" />
                <span>{showAiRatePanel ? '收起 AI 率' : 'AI 率检测'}</span>
              </button>
              <button
                class="btn ghost icon-btn-text"
                data-testid="plagiarism-toggle"
                onclick={() => (showPlagiarismPanel = !showPlagiarismPanel)}
              >
                <Icon name="shield" className="ui-icon" />
                <span>{showPlagiarismPanel ? '收起查重' : '查重检测'}</span>
              </button>
              <button
                class="btn ghost icon-btn-text"
                data-testid="feedback-toggle"
                onclick={() => (showFeedbackPanel = !showFeedbackPanel)}
              >
                <Icon name="star" className="ui-icon" />
                <span>{showFeedbackPanel ? '收起评分' : '满意度评分'}</span>
              </button>
              <div class="plan-confirm-inline">
                <span class="plan-confirm-label">计划确认</span>
                <select
                  class="plan-confirm-select"
                  bind:value={planConfirmDecision}
                  onchange={() => void persistPlanConfirmPreference()}
                >
                  <option value="approved">通过</option>
                  <option value="interrupted">终止</option>
                </select>
                <label class="plan-confirm-score">
                  <span>评分</span>
                  <input
                    type="number"
                    min="0"
                    max="5"
                    step="1"
                    bind:value={planConfirmScore}
                    onchange={() => void persistPlanConfirmPreference()}
                  />
                </label>
              </div>
              <button class="btn ghost icon-btn-text" onclick={handleStop} disabled={!$generating}>
                <Icon name="stop" className="ui-icon" />
                <span>停止</span>
              </button>
              {#if resumeState && !$generating}
                <button class="btn ghost icon-btn-text" onclick={resumeInterruptedGeneration}>
                  <Icon name="resume" className="ui-icon" />
                  <span>续跑</span>
                </button>
              {/if}
            </div>
          </div>
        {/if}
      </div>

      {#if $generating && progress.total > 0}
        <div class="generation-banner">
          生成中 {progress.current}/{progress.total} · {progress.percent}% · 预计剩余 {Math.ceil(progress.etaS / 60)} 分 {progress.etaS % 60} 秒
        </div>
      {/if}

      {#if resumeState && !$generating && resumeState.status === 'interrupted'}
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

      <div class="doc-stage">
        {#if $isLoading}
          <LoadingSkeleton />
        {:else}
          <Editor
            showToolbar={false}
            paper={true}
            lockEditing={typingActive || streamTypingActive}
            onblockedit={handleBlockEdit}
            onblockselect={handleBlockSelect}
            ontoolbarstate={handleToolbarState}
          />
        {/if}
      </div>
      {/if}

    </section>

    <aside class="side-panel">
      <div class="panel-card version-panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">版本树</div>
            <div class="panel-sub">自动小版本 · 手动大版本</div>
          </div>
          <button class="icon-btn" onclick={loadVersionLog} title="刷新">刷新</button>
        </div>
        <div class="major-commit">
          <input
            class="version-input"
            placeholder="输入版本说明"
            bind:value={versionMessage}
          />
          <button class="btn primary" onclick={commitVersion}>保存版本</button>
        </div>
        {#if versionLoading}
          <div class="panel-empty">加载中...</div>
        {:else if versionError}
          <div class="panel-empty">{versionError}</div>
        {:else if versionGroups.length === 0}
          <div class="panel-empty">暂无版本</div>
        {:else}
          <div class="version-groups">
            {#each versionGroups as group}
              <div class="version-group">
                <div class={`version-major ${group.major?.is_current ? 'current' : ''}`}>
                  <div class="version-title">
                    <span>{group.major?.message || '未命名'}</span>
                    <span class={`badge ${group.major?.kind === 'major' ? 'major' : 'minor'}`}>
                      {group.major?.kind === 'major' ? '大版本' : '小版本'}
                    </span>
                  </div>
                  <div class="version-meta">
                    <span>{formatVersionTime(group.major?.timestamp || 0)}</span>
                    <span>{String(group.major?.version_id || '').slice(0, 7)}</span>
                  </div>
                  {#if formatVersionSummary(group.major?.summary)}
                    <div class="version-summary">{formatVersionSummary(group.major?.summary)}</div>
                  {/if}
                  <div class="version-actions">
                    <button class="btn ghost" onclick={() => checkoutVersion(group.major?.version_id)} disabled={group.major?.is_current}>切换</button>
                    <button class="btn ghost" onclick={() => compareWithCurrent(group.major?.version_id)} disabled={group.major?.is_current}>对比</button>
                  </div>
                </div>
                {#if group.minors && group.minors.length}
                  <div class="version-minors">
                    {#each group.minors as v}
                      <div class={`version-minor ${v.is_current ? 'current' : ''}`}>
                        <div>
                          <div class="minor-title">{v.message || '未命名'}</div>
                          {#if formatVersionSummary(v.summary)}
                            <div class="version-summary">{formatVersionSummary(v.summary)}</div>
                          {/if}
                          <div class="minor-meta">{formatVersionTime(v.timestamp)}</div>
                        </div>
                        <div class="minor-actions">
                          <button class="btn ghost" onclick={() => checkoutVersion(v.version_id)} disabled={v.is_current}>切换</button>
                          <button class="btn ghost" onclick={() => compareWithCurrent(v.version_id)} disabled={v.is_current}>对比</button>
                        </div>
                      </div>
                    {/each}
                  </div>
                {/if}
              </div>
            {/each}
          </div>
        {/if}
        <div class="version-diff">
          <div class="panel-sub">对比结果</div>
          <pre>{versionDiff || '请选择版本进行对比'}</pre>
        </div>
      </div>

    </aside>
  </div>

  {#if infoDrawerOpen}
    <div class="info-drawer-backdrop" role="presentation">
      <button type="button" class="sheet-backdrop-hit" onclick={closeInfoDrawer} aria-label="关闭文档信息"></button>
      <div class="info-drawer panel-card media-meta-panel" role="dialog" aria-modal="true" aria-label="文档信息">
        <div class="panel-header">
          <div>
            <div class="panel-title">文档信息</div>
            <div class="panel-sub">当前工作区摘要</div>
          </div>
          <button class="btn ghost btn-sm" onclick={closeInfoDrawer}>关闭</button>
        </div>
        <div class="meta-hero">
          <div class="meta-hero-glow"></div>
          <div class="meta-hero-text">{metaPreviewSnippet() || '暂无内容预览'}</div>
        </div>
        <div class="meta-list">
          <div><span>名称</span><strong>{guessDocTitle($sourceText)}</strong></div>
          <div><span>类型</span><strong>text/markdown</strong></div>
          <div><span>大小</span><strong>{estimateKb($sourceText)} KB</strong></div>
          <div><span>词数</span><strong>{$wordCount}</strong></div>
          <div><span>选区</span><strong>{selectedBlockIds.length || 0}</strong></div>
          <div><span>路由</span><strong>{lastGraphMeta?.route_id || '默认'}</strong></div>
        </div>
        <div class="meta-actions">
          <button class="btn ghost icon-btn-text" onclick={() => switchWorkspaceMode('editor')}>
            <Icon name="open" className="ui-icon" />
            <span>定位到编辑区</span>
          </button>
          <button class="btn ghost danger icon-btn-text" onclick={() => { selectedBlockId = ''; selectedBlockIds = []; selectedBlocks = []; }}>
            <Icon name="clearSelection" className="ui-icon" />
            <span>清空选区</span>
          </button>
        </div>
      </div>
    </div>
  {/if}

  {#if selectedBlockIds.length > 0 && inlineBarVisible}
    <div
      class="inline-selection-bar"
      style={`left:${inlineBarLeft}px;top:${inlineBarTop}px;`}
      role="toolbar"
      aria-label="选中块快捷操作"
    >
      <div class="inline-selection-meta">
        已选中 {selectedBlockIds.length} 项
        <span>Ctrl/Cmd+Enter 下弹窗 · Ctrl/Cmd+Shift+Enter 上弹窗</span>
      </div>
      <div class="inline-selection-actions">
        <button class="mini-btn" onclick={() => openInlinePopover('rewrite', 'down')} disabled={inlineEditLocked}>改写</button>
        <button class="mini-btn" onclick={() => openInlinePopover('style', 'down')} disabled={inlineEditLocked}>样式</button>
        <button class="mini-btn" onclick={triggerInlineTableInsert} disabled={inlineEditLocked}>插表</button>
        <button class="mini-btn" onclick={triggerInlineImageUpload} disabled={inlineEditLocked}>插图</button>
        <button class="mini-btn" onclick={() => openInlinePopover('assistant', 'down')}>对话</button>
        <button class="mini-btn" onclick={() => openInlinePopover(inlinePanelTab as InlinePanelTab, 'up')}>上方</button>
        <button class="mini-btn" onclick={() => openInlinePopover(inlinePanelTab as InlinePanelTab, 'down')}>下方</button>
      </div>
    </div>
  {/if}

  {#if inlinePopoverOpen && selectedBlockIds.length > 0}
    <section
      class={`inline-edit-popover ${inlinePopoverPlacement}`}
      style={`left:${inlinePopoverLeft}px;top:${inlinePopoverTop}px;`}
      aria-label="选中内容修改窗口"
    >
      <div class="inline-popover-head">
        <div>
          <div class="panel-title">选中内容轻量修改</div>
          <div class="panel-sub">当前上下文独立于其他段落块，同一块会继承修改上下文。</div>
        </div>
        <div class="inline-popover-head-actions">
          <button class="btn ghost btn-sm" onclick={triggerInlineTableInsert} disabled={inlineEditLocked}>插表</button>
          <button class="btn ghost btn-sm" onclick={triggerInlineImageUpload} disabled={inlineEditLocked}>插图</button>
          <button class="btn ghost btn-sm" onclick={() => openInlinePopover(inlinePanelTab as InlinePanelTab, 'up')}>上方</button>
          <button class="btn ghost btn-sm" onclick={() => openInlinePopover(inlinePanelTab as InlinePanelTab, 'down')}>下方</button>
          <button class="btn ghost btn-sm" onclick={closeInlinePopover}>关闭</button>
        </div>
      </div>

      <div class="inline-tabs">
        <button class={`inline-tab ${inlinePanelTab === 'rewrite' ? 'active' : ''}`} onclick={() => toggleInlineTab('rewrite')}>
          改写建议
        </button>
        <button class={`inline-tab ${inlinePanelTab === 'style' ? 'active' : ''}`} onclick={() => toggleInlineTab('style')}>
          样式设置
        </button>
        <button class={`inline-tab ${inlinePanelTab === 'assistant' ? 'active' : ''}`} onclick={() => toggleInlineTab('assistant')}>
          改动对话
        </button>
      </div>

      <div class="selected-targets">
        {#each selectedBlocks as b, idx}
          <span class="selected-chip" title={b.text}>
            {b.kind === 'section' || b.kind === 'title' ? `标题${idx + 1}` : `块${idx + 1}`}
          </span>
        {/each}
      </div>
      {#if inlineEditLocked}
        <div class="block-error">{inlineEditLockReason}</div>
      {/if}

      {#if inlinePanelTab === 'style'}
        <div class="inline-style-row compact">
          <span>字体</span>
          <select
            bind:value={blockStyleFontFamily}
            disabled={inlineEditLocked}
            onchange={() => applyInlineBlockStyle({ fontFamily: blockStyleFontFamily })}
          >
            <option value="">默认</option>
            <option value="宋体">宋体</option>
            <option value="黑体">黑体</option>
            <option value="微软雅黑">微软雅黑</option>
            <option value="楷体">楷体</option>
            <option value="仿宋">仿宋</option>
          </select>
          <span>字号</span>
          <select
            bind:value={blockStyleFontSize}
            disabled={inlineEditLocked}
            onchange={() => applyInlineBlockStyle({ fontSize: blockStyleFontSize })}
          >
            <option value="">默认</option>
            <option value="12pt">12pt</option>
            <option value="14pt">14pt</option>
            <option value="16pt">16pt</option>
            <option value="18pt">18pt</option>
            <option value="20pt">20pt</option>
          </select>
          <span>行距</span>
          <select
            bind:value={blockStyleLineHeight}
            disabled={inlineEditLocked}
            onchange={() => applyInlineBlockStyle({ lineHeight: blockStyleLineHeight })}
          >
            <option value="">默认</option>
            <option value="1.2">1.2</option>
            <option value="1.5">1.5</option>
            <option value="1.75">1.75</option>
            <option value="2">2.0</option>
          </select>
          <span>对齐</span>
          <select
            bind:value={blockStyleAlign}
            disabled={inlineEditLocked}
            onchange={() => applyInlineBlockStyle({ align: blockStyleAlign })}
          >
            <option value="">默认</option>
            <option value="left">左对齐</option>
            <option value="center">居中</option>
            <option value="right">右对齐</option>
            <option value="justify">两端对齐</option>
          </select>
          <span>字重</span>
          <select
            bind:value={blockStyleFontWeight}
            disabled={inlineEditLocked}
            onchange={() => applyInlineBlockStyle({ fontWeight: blockStyleFontWeight })}
          >
            <option value="">默认</option>
            <option value="400">常规</option>
            <option value="500">中等</option>
            <option value="600">半粗</option>
            <option value="700">加粗</option>
          </select>
          <span>字形</span>
          <select
            bind:value={blockStyleFontStyle}
            disabled={inlineEditLocked}
            onchange={() => applyInlineBlockStyle({ fontStyle: blockStyleFontStyle })}
          >
            <option value="">默认</option>
            <option value="normal">正常</option>
            <option value="italic">斜体</option>
          </select>
          <span>文字色</span>
          <input
            type="text"
            placeholder="#1f2937"
            bind:value={blockStyleColor}
            disabled={inlineEditLocked}
            onchange={() => applyInlineBlockStyle({ color: blockStyleColor })}
          />
          <span>背景色</span>
          <input
            type="text"
            placeholder="#ffffff"
            bind:value={blockStyleBackground}
            disabled={inlineEditLocked}
            onchange={() => applyInlineBlockStyle({ background: blockStyleBackground })}
          />
        </div>
        <div class="panel-empty">样式栏会回显当前选中块的样式，修改仅作用于当前选区。</div>
      {/if}

      {#if inlinePanelTab === 'assistant'}
        <div class="assistant-inline-tip">
          <div>用于处理当前选中块的复杂语义修改。</div>
          <textarea
            class="inline-instruction"
            placeholder="例如：将选中内容改成课程设计报告语气，并补全术语解释。"
            bind:value={blockDialogInput}
          ></textarea>
          <div class="assistant-inline-actions">
            <button
              class="btn ghost"
              onclick={() => {
                blockEditCmd = blockDialogInput.trim()
                inlinePanelTab = 'rewrite'
              }}
            >
              同步到改写指令
            </button>
            <button class="btn ghost" onclick={() => openAssistantForBlock(blockDialogInput)}>发到右下角全局助手</button>
          </div>
        </div>
      {/if}

      {#if inlinePanelTab === 'rewrite'}
        <div class="inline-preset-row">
          <button class="preset-chip" onclick={() => useRewritePreset('语气更正式，保留原意')}>更正式</button>
          <button class="preset-chip" onclick={() => useRewritePreset('压缩到更简洁，控制在80字左右')}>更简洁</button>
          <button class="preset-chip" onclick={() => useRewritePreset('增加解释细节，但不要扩展事实')}>更详细</button>
          <button class="preset-chip" onclick={() => useRewritePreset('保持术语不变，仅调整表达')}>保留术语</button>
        </div>

        <div class="inline-ai-row">
          <textarea
            class="inline-instruction"
            placeholder="例如：仅重写选中段落，语气更正式，减少20%字数。"
            bind:value={blockEditCmd}
          ></textarea>
        </div>

        <div class="inline-action-row">
          <button class="btn ghost" onclick={() => openInlinePopover('assistant', inlinePopoverPlacement)}>切到改动对话</button>
          <button
            class="btn primary"
            onclick={previewSelectedBlockEdit}
            disabled={inlineEditLocked || blockPreviewBusy || !blockEditCmd.trim() || hasNonBlockTargets()}
          >
            {blockPreviewBusy ? '正在生成建议...' : '生成建议（不改原文）'}
          </button>
        </div>
        {#if hasNonBlockTargets()}
          <div class="panel-empty">当前选区包含标题，请直接编辑标题或切到“样式设置”。</div>
        {/if}
      {/if}

      {#if blockEditError}
        <div class="block-error">{blockEditError}</div>
      {/if}

      {#if blockCandidates.length > 0}
        <div class="candidate-compare compact">
          <div class="candidate-before">
            <div class="candidate-label">原文</div>
            <div class="candidate-text">{blockOriginalText || selectedBlockText}</div>
          </div>
          <div class="candidate-panel">
            <div class="candidate-switches">
              {#each blockCandidates as c, idx}
                <button
                  class={`candidate-switch ${activeCandidateIndex === idx ? 'active' : ''}`}
                  onclick={() => (activeCandidateIndex = idx)}
                >
                  <span>{c.label}</span>
                  <span>{candidateLengthDelta(c)}</span>
                </button>
              {/each}
            </div>
            {#if activeCandidate}
              <div class="candidate-card">
                <div class="candidate-head">
                  <span>{activeCandidate.label}</span>
                  <span class="candidate-meta">{candidateLengthDelta(activeCandidate)}</span>
                </div>
                <div class="candidate-actions">
                  <button class="btn primary" onclick={() => applyCandidateVersion(activeCandidateIndex)} disabled={inlineEditLocked}>采纳到正文</button>
                  <button class="btn ghost" onclick={previewSelectedBlockEdit}>重新生成</button>
                  <button class="btn ghost danger" onclick={ignoreCandidateSuggestions}>忽略建议</button>
                </div>
                <div class="candidate-label">建议文本</div>
                <div class="candidate-text">{activeCandidate.selectedAfter}</div>
              </div>
            {/if}
          </div>
        </div>
      {/if}
    </section>
  {/if}

  <button class="assistant-fab" onclick={toggleAssistantOpen} title="打开智能助手 (Ctrl/Cmd+K)">
    <Icon name="chat" className="ui-icon" />
    <span>助手</span>
    {#if assistantBadgeCount > 0}
      <span class="assistant-queue-badge">{assistantBadgeCount}</span>
    {/if}
  </button>

  {#if assistantOpen}
    <div class="assistant-sheet-backdrop" role="presentation">
      <button type="button" class="sheet-backdrop-hit" onclick={() => setAssistantOpen(false)} aria-label="关闭智能助手"></button>
      <div class="assistant-sheet" role="dialog" aria-modal="true" aria-label="智能助手" tabindex="-1" onkeydown={handleAssistantSheetKeydown}>
        <div class="assistant-sheet-head">
          <div>
            <div class="panel-title">智能助手</div>
            <div class="panel-sub">快捷键：Ctrl/Cmd + K</div>
          </div>
          {#if assistantBadgeCount > 0}
            <span class="assistant-queue-badge">{assistantBadgeCount}</span>
          {/if}
          <button class="btn ghost btn-sm" onclick={() => setAssistantOpen(false)}>关闭</button>
        </div>
        <Chat
          variant="assistant"
          onsend={(text) => handleGenerate(text)}
          onupload={handleAssistantUpload}
        />
      </div>
    </div>
  {/if}

  <input
    class="hidden-input"
    type="file"
    accept="image/*"
    bind:this={uploadImageInput}
    onchange={handleInlineImageSelect}
  />

  <input
    class="hidden-input"
    type="file"
    bind:this={libraryUploadInput}
    onchange={handleLibraryUploadSelect}
  />

  {#if pendingGenerateConfirmation}
    <div class="confirm-overlay" role="dialog" aria-modal="true" aria-label="高风险编辑确认">
      <section class="confirm-dialog">
        <div class="panel-title">检测到高风险编辑</div>
        <div class="panel-sub">
          风险等级 {pendingGenerateConfirmation.riskLevel} · 计划来源 {pendingGenerateConfirmation.planSource}
          · 操作数 {pendingGenerateConfirmation.operationsCount}
        </div>
        <div class="confirm-note">
          {pendingGenerateConfirmation.note || '该请求会执行高风险文本改动，请确认是否继续。'}
        </div>
        <div class="confirm-actions">
          <button class="btn ghost" onclick={cancelPendingGenerate} disabled={confirmDialogBusy}>取消</button>
          <button class="btn primary danger" onclick={confirmPendingGenerate} disabled={confirmDialogBusy}>
            {confirmDialogBusy ? '执行中...' : '确认执行'}
          </button>
        </div>
      </section>
    </div>
  {/if}

{#if $generating}
  <ProgressBar indeterminate={true} />
{/if}
</main>

<DiagramCanvas
  open={canvasOpen}
  docId={$docId}
  onclose={() => (canvasOpen = false)}
  oninsert={(payload) => insertDiagramIntoDoc(payload.spec)}
/>

<ErrorBoundary>
  <Toast />
  <DocList bind:visible={showDocList} onSelect={handleDocSelect} />
  <CitationManager bind:visible={showCitations} />
  <PerformanceMetrics bind:visible={showPerformanceMetrics} />
</ErrorBoundary>

<style>
  :global(body) {
    margin: 0;
    background: radial-gradient(700px 360px at 15% 10%, rgba(94, 175, 255, 0.12), transparent 60%),
      radial-gradient(520px 280px at 85% 12%, rgba(56, 230, 255, 0.14), transparent 60%),
      linear-gradient(180deg, #f6f9ff 0%, #eef3fb 50%, #f3f7ff 100%);
    color: #f5f3f0;
    font-family: "HarmonyOS Sans SC", "MiSans", "Noto Sans SC", "Source Han Sans SC", "Segoe UI", sans-serif;
  }

  :global(body)::before {
    content: "";
    position: fixed;
    inset: 0;
    pointer-events: none;
    background:
      repeating-linear-gradient(120deg, rgba(250, 249, 247, 0.04) 0, rgba(250, 249, 247, 0.04) 1px, transparent 1px, transparent 32px),
      repeating-linear-gradient(200deg, rgba(217, 119, 6, 0.06) 0, rgba(217, 119, 6, 0.06) 1px, transparent 1px, transparent 36px);
    opacity: 0.4;
    z-index: 0;
  }

  .app {
    --panel-bg: rgba(255, 255, 255, 0.88);
    --panel-border: rgba(148, 163, 184, 0.22);
    --panel-shadow: 0 18px 40px rgba(250, 249, 247, 0.12);
    --accent: #2563eb;
    --accent-weak: rgba(37, 99, 235, 0.12);
    --text-muted: rgba(245, 243, 240, 0.72);
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    position: relative;
    z-index: 1;
  }

  .topbar {
    display: grid;
    grid-template-columns: auto 1fr auto;
    align-items: center;
    gap: 20px;
    padding: 16px 28px;
    background: rgba(255, 255, 255, 0.86);
    border-bottom: 1px solid rgba(231, 229, 228, 1);
    
  }

  .brand {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .logo {
    width: 42px;
    height: 42px;
    border-radius: 14px;
    display: grid;
    place-items: center;
    font-weight: 700;
    color: #f5f3f0;
    background: #faf9f7;
    box-shadow: 0 10px 20px rgba(14, 165, 233, 0.25);
  }

  .brand-title {
    font-size: 16px;
    font-weight: 600;
  }

  .brand-sub {
    font-size: 12px;
    color: var(--text-muted);
  }

  .menu {
    display: flex;
    gap: 12px;
    align-items: center;
    justify-content: center;
  }

  .menu-item {
    border: none;
    background: transparent;
    font-size: 13px;
    color: #1e293b;
    padding: 6px 10px;
    border-radius: 8px;
    transition: background 0.2s ease, color 0.2s ease;
    cursor: pointer;
  }

  .menu-item:hover {
    background: rgba(37, 99, 235, 0.08);
    color: #1d4ed8;
  }

  .top-actions {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .feedback-panel {
    padding: 12px 14px;
    border-radius: 14px;
    border: 1px solid var(--panel-border);
    background: var(--panel-bg);
    box-shadow: var(--panel-shadow);
    display: grid;
    gap: 10px;
  }

  .feedback-panel-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .feedback-form {
    display: grid;
    gap: 8px;
  }

  .feedback-row {
    display: grid;
    grid-template-columns: auto 1fr auto 180px;
    gap: 8px;
    align-items: center;
  }

  .feedback-row textarea {
    grid-column: span 3;
    border: 1px solid var(--panel-border);
    border-radius: 10px;
    background: rgba(255, 255, 255, 0.82);
    color: var(--text-main);
    padding: 8px 10px;
    resize: vertical;
  }

  .feedback-row select {
    border: 1px solid var(--panel-border);
    border-radius: 10px;
    background: rgba(255, 255, 255, 0.86);
    color: var(--text-main);
    padding: 7px 8px;
  }

  .rating-group {
    display: inline-flex;
    gap: 6px;
  }

  .rating-btn {
    border: 1px solid var(--panel-border);
    border-radius: 8px;
    background: rgba(255, 255, 255, 0.88);
    padding: 6px 10px;
    min-width: 34px;
    font-weight: 600;
    cursor: pointer;
  }

  .rating-btn.active {
    background: rgba(37, 99, 235, 0.14);
    border-color: rgba(37, 99, 235, 0.5);
    color: #1d4ed8;
  }

  .feedback-actions {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .feedback-tip {
    font-size: 12px;
    color: #1d4ed8;
  }

  .feedback-history {
    margin-top: 4px;
    padding-top: 8px;
    border-top: 1px dashed var(--panel-border);
    display: grid;
    gap: 6px;
  }

  .feedback-item {
    border: 1px solid rgba(148, 163, 184, 0.35);
    border-radius: 10px;
    padding: 6px 8px;
    background: rgba(255, 255, 255, 0.72);
    display: grid;
    gap: 4px;
  }

  .feedback-item-head {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    font-size: 12px;
    color: var(--text-muted);
  }

  .feedback-item-note {
    font-size: 13px;
    color: var(--text-main);
    line-height: 1.45;
  }

  .plagiarism-grid {
    display: grid;
    grid-template-columns: auto 140px auto 1fr;
    gap: 8px;
    align-items: center;
  }

  .plagiarism-grid input {
    border: 1px solid var(--panel-border);
    border-radius: 10px;
    background: rgba(255, 255, 255, 0.86);
    color: var(--text-main);
    padding: 7px 8px;
  }

  .plagiarism-results {
    margin-top: 6px;
    border-top: 1px dashed var(--panel-border);
    padding-top: 10px;
    display: grid;
    gap: 8px;
  }

  .plagiarism-report-actions {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
    border-top: 1px dashed var(--panel-border);
    padding-top: 8px;
  }

  .plagiarism-item {
    border: 1px solid rgba(148, 163, 184, 0.35);
    border-radius: 10px;
    padding: 8px 10px;
    background: rgba(255, 255, 255, 0.72);
    display: grid;
    gap: 6px;
  }

  .plagiarism-item-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    font-size: 13px;
    color: var(--text-main);
  }

  .plagiarism-item-head em {
    font-style: normal;
    color: var(--text-muted);
    margin-left: 4px;
  }

  .plagiarism-item-head .danger {
    color: #b91c1c;
    font-weight: 600;
  }

  .plagiarism-item-metrics {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    font-size: 12px;
    color: var(--text-muted);
  }

  .plagiarism-evidence {
    font-size: 12px;
    color: #334155;
    border-left: 3px solid rgba(37, 99, 235, 0.35);
    padding-left: 8px;
    line-height: 1.45;
  }

  .workspace {
    flex: 1;
    display: grid;
    grid-template-columns: 74px minmax(0, 1fr) 430px;
    gap: 20px;
    padding: 14px 22px 48px;
  }

  .nav-rail {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 12px 0;
  }

  .nav-btn {
    border: 1px solid transparent;
    background: rgba(255, 255, 255, 0.9);
    color: #1e293b;
    border-radius: 16px;
    padding: 12px 8px;
    font-size: 12px;
    text-align: center;
    cursor: pointer;
    box-shadow: 0 10px 20px rgba(250, 249, 247, 0.08);
    transition: transform 0.2s ease, border 0.2s ease, box-shadow 0.2s ease;
  }

  .nav-btn.active {
    border-color: rgba(37, 99, 235, 0.5);
    box-shadow: 0 16px 24px rgba(37, 99, 235, 0.2);
  }

  .nav-btn:hover {
    transform: translateY(-2px);
  }

  .doc-area {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .doc-toolbar {
    display: grid;
    gap: 4px;
    padding: 8px 12px;
    background: var(--panel-bg);
    border: 1px solid var(--panel-border);
    border-radius: 16px;
    box-shadow: var(--panel-shadow);
  }

  .toolbar-line {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .toolbar-cluster {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 8px;
    border: 1px solid rgba(148, 163, 184, 0.22);
    border-radius: 12px;
    background: rgba(255, 255, 255, 0.78);
    flex-wrap: wrap;
  }

  .toolbar-cluster.compact {
    margin-left: auto;
  }

  .cluster-label {
    font-size: 11px;
    color: var(--text-muted);
    letter-spacing: 0.02em;
    margin-right: 2px;
    white-space: nowrap;
  }

  .tool-sep {
    width: 1px;
    height: 18px;
    background: rgba(231, 229, 228, 1);
    margin: 0 2px;
  }

  .tool-btn {
    min-width: 34px;
    height: 32px;
    border-radius: 10px;
    border: 1px solid rgba(231, 229, 228, 1);
    background: #fff;
    font-weight: 600;
    padding: 0 10px;
    cursor: pointer;
    transition: border 0.2s ease, box-shadow 0.2s ease;
  }

  .tool-btn:hover:not(:disabled) {
    border-color: rgba(37, 99, 235, 0.6);
    box-shadow: 0 6px 14px rgba(37, 99, 235, 0.15);
  }

  .tool-btn.active {
    border-color: rgba(37, 99, 235, 0.75);
    background: #faf9f7;
    color: #1d4ed8;
    box-shadow: 0 8px 18px rgba(37, 99, 235, 0.2);
  }

  .tool-btn:disabled {
    opacity: 0.38;
    cursor: not-allowed;
    box-shadow: none;
    transform: none;
    border-color: rgba(231, 229, 228, 1);
    border-style: dashed;
    background: rgba(241, 245, 249, 0.72);
    color: rgba(100, 116, 139, 0.9);
    filter: grayscale(0.45);
  }

  .hidden-input {
    display: none;
  }

  .generation-banner {
    padding: 10px 16px;
    border-radius: 14px;
    background: rgba(14, 165, 233, 0.12);
    color: #f5f3f0;
    font-size: 13px;
  }

  .section-failures {
    padding: 12px 16px;
    border-radius: 14px;
    background: rgba(239, 68, 68, 0.08);
    border: 1px dashed rgba(239, 68, 68, 0.35);
    display: grid;
    gap: 8px;
  }

  .failure-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 12px;
  }

  .originality-panel {
    background: rgba(217, 119, 6, 0.08);
    border-color: rgba(217, 119, 6, 0.28);
  }

  .risk-row {
    display: flex;
    justify-content: space-between;
    gap: 16px;
    align-items: center;
    padding: 10px 0;
    border-top: 1px dashed rgba(231, 229, 228, 1);
  }

  .risk-title {
    font-size: 13px;
    font-weight: 600;
  }

  .risk-metrics {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    font-size: 12px;
    color: rgba(250, 249, 247, 0.72);
    margin-top: 4px;
  }

  .risk-actions {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .risk-badge {
    display: inline-flex;
    align-items: center;
    padding: 4px 10px;
    border-radius: 999px;
    font-size: 12px;
    border: 1px solid rgba(148, 163, 184, 0.32);
    background: rgba(255, 255, 255, 0.56);
  }

  .risk-badge.ok {
    color: #166534;
    border-color: rgba(22, 163, 74, 0.32);
    background: rgba(220, 252, 231, 0.72);
  }

  .risk-badge.bad {
    color: #991b1b;
    border-color: rgba(239, 68, 68, 0.32);
    background: rgba(254, 226, 226, 0.76);
  }

  .doc-stage {
    flex: 1;
    background: var(--panel-bg);
    border: 1px solid var(--panel-border);
    border-radius: 20px;
    padding: 12px;
    box-shadow: var(--panel-shadow);
    min-height: 360px;
  }

  .inline-tabs {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }

  .inline-tab {
    border: 1px solid rgba(148, 163, 184, 0.32);
    border-radius: 999px;
    padding: 7px 14px;
    font-size: 13px;
    background: rgba(248, 250, 252, 0.94);
    color: #f5f3f0;
    cursor: pointer;
  }

  .inline-tab.active {
    border-color: rgba(37, 99, 235, 0.45);
    background: rgba(37, 99, 235, 0.14);
    color: #1e3a8a;
    font-weight: 600;
  }

  .inline-style-row {
    display: grid;
    grid-template-columns: auto 1fr auto 1fr auto 1fr;
    gap: 8px;
    align-items: center;
    font-size: 14px;
  }

  .inline-style-row select,
  .inline-style-row input {
    border: 1px solid rgba(148, 163, 184, 0.35);
    border-radius: 8px;
    padding: 7px 10px;
    background: #fff;
    font-size: 14px;
  }

  .inline-style-row input[type='text'] {
    min-height: 34px;
  }

  .inline-preset-row {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 8px;
  }

  .preset-chip {
    border: 1px solid rgba(37, 99, 235, 0.28);
    border-radius: 999px;
    background: rgba(37, 99, 235, 0.06);
    color: #1e3a8a;
    padding: 7px 10px;
    font-size: 12px;
    cursor: pointer;
  }

  .inline-ai-row {
    display: grid;
    grid-template-columns: 1fr;
    gap: 8px;
  }

  .inline-instruction {
    width: 100%;
    min-height: 96px;
    resize: vertical;
    border: 1px solid rgba(148, 163, 184, 0.35);
    border-radius: 12px;
    padding: 12px 14px;
    background: #fff;
    font-size: 15px;
    line-height: 1.5;
  }

  .inline-action-row {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }

  .assistant-inline-tip {
    border: 1px dashed rgba(37, 99, 235, 0.35);
    border-radius: 12px;
    background: rgba(239, 246, 255, 0.9);
    padding: 12px;
    font-size: 14px;
    color: #1e293b;
    display: grid;
    gap: 10px;
  }

  .assistant-inline-actions {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }

  .candidate-compare {
    display: grid;
    grid-template-columns: minmax(260px, 320px) minmax(0, 1fr);
    gap: 12px;
  }

  .candidate-before,
  .candidate-card {
    border: 1px solid rgba(231, 229, 228, 1);
    border-radius: 12px;
    background: rgba(248, 250, 252, 0.95);
    padding: 12px;
  }

  .candidate-before {
    position: sticky;
    top: 0;
    align-self: start;
  }

  .candidate-panel {
    display: grid;
    gap: 10px;
  }

  .candidate-switches {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }

  .candidate-switch {
    border: 1px solid rgba(148, 163, 184, 0.32);
    border-radius: 10px;
    background: rgba(241, 245, 249, 0.9);
    color: #f5f3f0;
    padding: 7px 10px;
    font-size: 12px;
    display: grid;
    justify-items: start;
    gap: 2px;
    cursor: pointer;
    min-width: 120px;
  }

  .candidate-switch.active {
    border-color: rgba(37, 99, 235, 0.45);
    background: rgba(37, 99, 235, 0.14);
    color: #1e3a8a;
    font-weight: 600;
  }

  .candidate-label {
    font-size: 12px;
    color: var(--text-muted);
    margin-bottom: 6px;
  }

  .candidate-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    font-size: 18px;
    font-weight: 600;
    margin-bottom: 8px;
  }

  .candidate-meta {
    font-size: 12px;
    color: var(--text-muted);
    font-weight: 500;
  }

  .candidate-actions {
    display: flex;
    gap: 8px;
    margin-bottom: 8px;
    flex-wrap: wrap;
  }

  .candidate-text {
    max-height: 300px;
    overflow: auto;
    white-space: pre-wrap;
    font-size: 16px;
    line-height: 1.55;
    color: #f5f3f0;
  }

  .btn.ghost.danger {
    background: rgba(239, 68, 68, 0.1);
    color: #991b1b;
  }

  .btn-sm {
    padding: 6px 10px;
    font-size: 12px;
  }

  .side-panel {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .panel-card {
    background: var(--panel-bg);
    border: 1px solid var(--panel-border);
    border-radius: 18px;
    padding: 14px;
    box-shadow: var(--panel-shadow);
  }

  .version-panel {
    order: 1;
  }

  .panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
  }

  .panel-title {
    font-weight: 600;
    font-size: 14px;
  }

  .panel-sub {
    font-size: 12px;
    color: var(--text-muted);
  }

  .panel-empty {
    padding: 12px;
    color: var(--text-muted);
    font-size: 12px;
  }

  .major-commit {
    display: flex;
    gap: 8px;
    margin-bottom: 12px;
  }

  .version-input,
  .block-input {
    flex: 1;
    border: 1px solid rgba(148, 163, 184, 0.35);
    border-radius: 10px;
    padding: 8px 10px;
    background: #fff;
    font-size: 12px;
  }

  .version-groups {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .version-major {
    padding: 10px;
    border-radius: 14px;
    border: 1px solid rgba(37, 99, 235, 0.2);
    background: rgba(37, 99, 235, 0.05);
  }

  .version-major.current {
    border-color: rgba(22, 163, 74, 0.5);
  }

  .version-title {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-weight: 600;
    margin-bottom: 4px;
  }

  .badge {
    font-size: 11px;
    padding: 2px 6px;
    border-radius: 999px;
    background: rgba(231, 229, 228, 1);
  }

  .badge.major {
    background: rgba(37, 99, 235, 0.15);
    color: #1e3a8a;
  }

  .version-meta {
    display: flex;
    gap: 10px;
    font-size: 11px;
    color: var(--text-muted);
  }

  .version-summary {
    margin-top: 6px;
    font-size: 11px;
    color: #f5f3f0;
  }

  .version-actions,
  .minor-actions {
    display: flex;
    gap: 6px;
    margin-top: 8px;
  }

  .version-minors {
    margin-top: 10px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .version-minor {
    padding: 8px 10px;
    border-radius: 12px;
    border: 1px dashed rgba(231, 229, 228, 1);
    display: flex;
    justify-content: space-between;
    gap: 8px;
  }

  .version-minor.current {
    border-color: rgba(22, 163, 74, 0.5);
  }

  .minor-title {
    font-size: 12px;
    font-weight: 500;
  }

  .minor-meta {
    font-size: 11px;
    color: var(--text-muted);
  }

  .version-diff pre {
    background: rgba(250, 249, 247, 0.06);
    padding: 10px;
    border-radius: 12px;
    font-size: 11px;
    white-space: pre-wrap;
    max-height: 160px;
    overflow: auto;
  }

  .block-preview {
    font-size: 12px;
    color: #f5f3f0;
    background: rgba(250, 249, 247, 0.04);
    border-radius: 10px;
    padding: 8px;
    max-height: 80px;
    overflow: auto;
    margin-bottom: 8px;
  }

  .block-actions {
    display: flex;
    gap: 8px;
    margin-top: 8px;
  }

  .block-error {
    color: #dc2626;
    font-size: 12px;
    margin-top: 6px;
  }

  .selected-targets {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 8px;
  }

  .selected-chip {
    border: 1px solid rgba(37, 99, 235, 0.3);
    background: rgba(37, 99, 235, 0.1);
    color: #1e3a8a;
    font-size: 12px;
    border-radius: 999px;
    padding: 4px 10px;
    max-width: 100%;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .inline-style-row.compact {
    grid-template-columns: auto 1fr;
    gap: 6px 8px;
  }

  .inline-preset-row {
    grid-template-columns: 1fr 1fr;
  }

  .inline-instruction {
    min-height: 88px;
  }

  .candidate-compare.compact {
    grid-template-columns: 1fr;
  }

  .candidate-before {
    position: static;
  }

  .inline-selection-bar {
    position: fixed;
    z-index: 16;
    width: min(560px, calc(100vw - 24px));
    border-radius: 12px;
    border: 1px solid rgba(37, 99, 235, 0.28);
    background: rgba(255, 255, 255, 0.97);
    box-shadow: 0 16px 30px rgba(250, 249, 247, 0.22);
    padding: 8px 10px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }

  .inline-selection-meta {
    font-size: 12px;
    color: #f5f3f0;
    display: grid;
    gap: 2px;
  }

  .inline-selection-meta > span {
    font-size: 11px;
    color: var(--text-muted);
  }

  .inline-selection-actions {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .mini-btn {
    border: 1px solid rgba(231, 229, 228, 1);
    background: rgba(248, 250, 252, 0.95);
    color: #f5f3f0;
    border-radius: 9px;
    padding: 6px 9px;
    font-size: 12px;
    cursor: pointer;
    transition: border 0.2s ease, background 0.2s ease;
  }

  .mini-btn:hover {
    border-color: rgba(37, 99, 235, 0.52);
    background: rgba(239, 246, 255, 0.95);
  }

  .mini-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    background: rgba(168, 162, 158, 0.7);
  }

  .inline-edit-popover {
    position: fixed;
    z-index: 17;
    width: min(720px, calc(100vw - 24px));
    max-height: min(80vh, 860px);
    overflow: auto;
    border-radius: 16px;
    border: 1px solid rgba(37, 99, 235, 0.32);
    background: rgba(255, 255, 255, 0.98);
    box-shadow: 0 24px 48px rgba(250, 249, 247, 0.28);
    padding: 12px;
    display: grid;
    gap: 10px;
  }

  .inline-edit-popover.up {
    transform: translateY(calc(-100% - 8px));
  }

  .inline-popover-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 10px;
  }

  .inline-popover-head-actions {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .assistant-queue-badge {
    min-width: 18px;
    height: 18px;
    border-radius: 999px;
    background: rgba(250, 249, 247, 0.8);
    color: #fff;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    padding: 0 5px;
  }

  .btn {
    border: none;
    background: rgba(250, 249, 247, 0.08);
    color: #f5f3f0;
    padding: 8px 12px;
    border-radius: 10px;
    font-size: 12px;
    cursor: pointer;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
  }

  .btn.primary {
    background: linear-gradient(135deg, #2563eb, #0ea5e9);
    color: #fff;
  }

  .btn.ghost {
    background: rgba(250, 249, 247, 0.06);
  }

  .btn.primary.danger {
    background: linear-gradient(135deg, #dc2626, #dc2626);
  }

  .confirm-overlay {
    position: fixed;
    inset: 0;
    z-index: 40;
    background: rgba(250, 249, 247, 0.38);
    display: grid;
    place-items: center;
    padding: 16px;
  }

  .confirm-dialog {
    width: min(560px, calc(100vw - 32px));
    border-radius: 16px;
    border: 1px solid rgba(220, 38, 38, 0.25);
    background: rgba(255, 255, 255, 0.98);
    box-shadow: 0 26px 48px rgba(250, 249, 247, 0.3);
    padding: 16px;
    display: grid;
    gap: 10px;
  }

  .confirm-note {
    border-radius: 10px;
    border: 1px solid rgba(231, 229, 228, 1);
    background: rgba(248, 250, 252, 0.92);
    color: #334155;
    padding: 10px 12px;
    line-height: 1.55;
    font-size: 13px;
    white-space: pre-wrap;
  }

  .confirm-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }

  .btn:hover,
  .tool-btn:hover:not(:disabled) {
    transform: translateY(-1px);
  }

  .icon-btn {
    border: none;
    background: rgba(250, 249, 247, 0.08);
    width: 28px;
    height: 28px;
    border-radius: 8px;
    cursor: pointer;
  }

  @media (max-width: 1200px) {
    .workspace {
      grid-template-columns: 64px 1fr;
    }
    .side-panel {
      grid-column: 1 / -1;
      flex-direction: row;
      flex-wrap: wrap;
    }
    .panel-card {
      flex: 1 1 320px;
    }
  }

  @media (max-width: 900px) {
    .topbar {
      grid-template-columns: 1fr;
      gap: 10px;
    }
    .menu {
      flex-wrap: wrap;
      justify-content: flex-start;
    }
    .workspace {
      grid-template-columns: 1fr;
    }
    .nav-rail {
      flex-direction: row;
      justify-content: center;
    }
    .assistant-fab {
      right: 12px;
      bottom: 12px;
    }
    .assistant-sheet,
    .info-drawer {
      width: min(92vw, 560px);
      min-width: 0;
    }
    .inline-selection-bar {
      left: 12px !important;
      right: 12px;
      width: auto;
      top: auto;
      bottom: 86px;
      flex-direction: column;
      align-items: stretch;
    }
    .inline-edit-popover {
      left: 12px !important;
      right: 12px;
      width: auto;
      top: auto !important;
      bottom: 146px;
      max-height: 52vh;
      transform: none !important;
    }
    .inline-style-row {
      grid-template-columns: auto 1fr;
    }
    .inline-preset-row {
      grid-template-columns: 1fr 1fr;
    }
    .candidate-compare {
      grid-template-columns: 1fr;
    }
    .candidate-before {
      position: static;
    }
    .candidate-switches {
      display: grid;
      grid-template-columns: 1fr 1fr;
    }
    .candidate-text {
      font-size: 16px;
      max-height: 180px;
    }
    .feedback-row {
      grid-template-columns: 1fr;
      align-items: stretch;
    }
    .plagiarism-grid {
      grid-template-columns: 1fr;
      align-items: stretch;
    }
    .feedback-row textarea {
      grid-column: auto;
    }
  }
  /* FilmLab-style dark skin overrides */
  :global(body) {
    background: radial-gradient(1200px 620px at -6% -18%, rgba(217, 119, 6, 0.16), transparent 68%),
      radial-gradient(920px 520px at 106% -12%, rgba(234, 179, 8, 0.14), transparent 70%),
      linear-gradient(180deg, #0c1220 0%, #141c2e 100%);
    color: #e8eefb;
  }

  :global(body)::before {
    background:
      repeating-linear-gradient(130deg, rgba(255, 255, 255, 0.05) 0, rgba(255, 255, 255, 0.05) 1px, transparent 1px, transparent 40px),
      repeating-linear-gradient(210deg, rgba(249, 222, 126, 0.05) 0, rgba(249, 222, 126, 0.05) 1px, transparent 1px, transparent 44px);
    opacity: 0.44;
  }

  .app {
    --panel-bg: rgba(10, 17, 32, 0.88);
    --panel-bg-soft: rgba(16, 24, 42, 0.82);
    --panel-border: rgba(159, 183, 216, 0.2);
    --panel-shadow: 0 24px 44px rgba(0, 0, 0, 0.44);
    --text-main: #e8eefb;
    --text-muted: rgba(190, 205, 233, 0.72);
    --accent: #8fc6ff;
    --accent-weak: rgba(143, 198, 255, 0.16);
    color: var(--text-main);
    font-family: "Sora", "Manrope", "PingFang SC", "Noto Sans SC", "Segoe UI", sans-serif;
  }

  :global(*) {
    box-sizing: border-box;
  }

  .topbar {
    background: rgba(7, 13, 26, 0.72);
    border-bottom: 1px solid rgba(167, 189, 220, 0.2);
    box-shadow: inset 0 -1px 0 rgba(255, 255, 255, 0.03);
    
    display: grid;
    grid-template-columns: 280px minmax(0, 1fr) auto;
    gap: 14px;
    align-items: center;
    padding: 14px 20px;
  }

  .logo {
    color: #fff;
    background: linear-gradient(135deg, #2563eb, #3b82f6);
    box-shadow: 0 14px 28px rgba(35, 121, 255, 0.35);
  }

  .brand-title {
    color: #f7fbff;
    letter-spacing: 0.02em;
  }

  .brand-sub {
    color: rgba(199, 213, 239, 0.7);
  }

  .menu {
    gap: 10px;
    justify-content: flex-start;
  }

  .menu-item {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: rgba(198, 214, 241, 0.9);
    border-radius: 999px;
    border: 1px solid rgba(170, 193, 227, 0.25);
    background: rgba(18, 28, 50, 0.7);
    padding: 7px 14px;
  }

  .menu-item:hover {
    color: #f4f8ff;
    background: rgba(45, 65, 108, 0.78);
    border-color: rgba(174, 206, 252, 0.42);
  }

  .menu-item.active {
    color: #ffffff;
    background: linear-gradient(135deg, #2563eb, #3b82f6);
    border-color: rgba(189, 220, 255, 0.66);
    box-shadow: 0 10px 22px rgba(53, 117, 236, 0.36);
  }

  .top-actions {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    justify-content: flex-end;
    gap: 8px;
  }

  .workspace-hub {
    min-width: 0;
    display: grid;
    gap: 8px;
  }

  .ui-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 16px;
    height: 16px;
    flex: 0 0 auto;
  }

  .ui-icon.sm {
    width: 14px;
    height: 14px;
  }

  .ui-icon :global(svg) {
    width: 100%;
    height: 100%;
    stroke: currentColor;
    stroke-width: 1.85;
    stroke-linecap: round;
    stroke-linejoin: round;
  }

  .icon-btn-text {
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }

  .btn {
    background: rgba(44, 61, 96, 0.54);
    color: #e6eefc;
    border: 1px solid rgba(149, 177, 219, 0.26);
  }

  .btn.ghost {
    background: rgba(28, 39, 68, 0.58);
    color: rgba(224, 235, 253, 0.92);
    border: 1px solid rgba(154, 181, 221, 0.24);
  }

  .btn.primary {
    background: linear-gradient(135deg, #3b82f6, #0ea5e9);
    border: 1px solid rgba(59, 130, 246, 0.5);
    color: #fff;
    box-shadow: 0 12px 24px rgba(57, 126, 245, 0.34);
  }

  .btn.primary.danger {
    background: #faf9f7;
    border: 1px solid rgba(255, 189, 189, 0.45);
  }

  .btn.ghost.danger {
    background: rgba(254, 242, 242, 0.4);
    color: #fee2e2;
    border: 1px solid rgba(220, 38, 38, 0.45);
  }

  .btn:hover,
  .tool-btn:hover:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: 0 10px 20px rgba(0, 0, 0, 0.26);
  }

  .workspace {
    grid-template-columns: 228px minmax(0, 1fr) 286px;
    gap: 18px;
    padding: 16px 20px 44px;
  }

  .workspace > * {
    animation: rise-in 0.38s cubic-bezier(0.2, 0.62, 0.2, 1) both;
  }

  .workspace > *:nth-child(2) {
    animation-delay: 0.06s;
  }

  .workspace > *:nth-child(3) {
    animation-delay: 0.12s;
  }

  .workspace.hide-info {
    grid-template-columns: 228px minmax(0, 1fr);
  }

  .workspace.hide-info .side-panel {
    display: none;
  }

  .nav-rail {
    gap: 12px;
    padding: 14px;
    border-radius: 18px;
    border: 1px solid rgba(164, 190, 226, 0.2);
    background: rgba(12, 18, 32, 0.85);
    box-shadow: 0 22px 38px rgba(0, 0, 0, 0.4);
  }

  .rail-search {
    display: block;
  }

  .rail-search input {
    width: 100%;
    border-radius: 12px;
    border: 1px solid rgba(165, 190, 228, 0.24);
    background: rgba(13, 23, 42, 0.82);
    color: #ecf3ff;
    padding: 8px 10px;
    outline: none;
  }

  .rail-search input:focus {
    border-color: rgba(160, 205, 255, 0.66);
    box-shadow: 0 0 0 3px rgba(217, 119, 6, 0.2);
  }

  .rail-upload-btn {
    border: 1px solid rgba(214, 178, 97, 0.45);
    background: #faf9f7;
    color: #fbe4ac;
    border-radius: 12px;
    padding: 8px 10px;
    font-weight: 600;
    cursor: pointer;
    transition: border 0.2s ease, background 0.2s ease;
  }

  .rail-upload-btn:hover {
    border-color: rgba(250, 214, 127, 0.74);
    background: #faf9f7;
  }

  .rail-tip {
    border-left: 3px solid rgba(132, 171, 255, 0.58);
    padding-left: 10px;
    color: rgba(187, 204, 235, 0.78);
    font-size: 12px;
    line-height: 1.5;
  }

  .rail-library {
    border: 1px solid rgba(160, 184, 220, 0.2);
    border-radius: 12px;
    background: rgba(14, 24, 44, 0.54);
    padding: 10px;
    display: grid;
    gap: 10px;
  }

  .rail-group {
    border: 1px solid rgba(160, 184, 220, 0.2);
    border-radius: 12px;
    background: rgba(14, 24, 44, 0.54);
    padding: 10px;
    display: grid;
    gap: 8px;
  }

  .rail-group-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    font-size: 11px;
    letter-spacing: 0.08em;
    color: rgba(168, 162, 158, 0.82);
  }

  .rail-group-head em {
    font-style: normal;
    color: rgba(238, 216, 143, 0.9);
    font-weight: 600;
  }

  .library-card-stream {
    display: grid;
    grid-template-columns: 1fr;
    gap: 8px;
    max-height: 360px;
    overflow: auto;
    padding-right: 2px;
  }

  .library-card-stream.list .library-card-summary {
    display: none;
  }

  .library-card-stream.masonry .library-card {
    padding-bottom: 10px;
  }

  .library-empty {
    padding: 12px 10px;
    border: 1px dashed rgba(152, 177, 216, 0.32);
    border-radius: 10px;
    color: rgba(185, 204, 233, 0.78);
    font-size: 12px;
    text-align: center;
    background: rgba(20, 31, 54, 0.56);
  }

  .library-card {
    border: 1px solid rgba(231, 229, 228, 1);
    background: rgba(23, 35, 62, 0.78);
    border-radius: 11px;
    padding: 8px;
    display: grid;
    gap: 8px;
    cursor: pointer;
    text-align: left;
    transition: border 0.2s ease, transform 0.2s ease, box-shadow 0.2s ease;
  }

  .library-card:hover {
    border-color: rgba(165, 208, 255, 0.54);
    transform: translateY(-1px);
    box-shadow: 0 12px 20px rgba(0, 0, 0, 0.26);
  }

  .library-card.selected {
    border-color: rgba(164, 208, 255, 0.74);
    box-shadow: 0 0 0 1px rgba(115, 180, 255, 0.26), 0 12px 22px rgba(40, 95, 195, 0.28);
  }

  .library-card-cover {
    border-radius: 9px;
    min-height: 52px;
    padding: 8px 9px;
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 8px;
  }

  .library-card.tone-azure .library-card-cover {
    background: #faf9f7;
  }

  .library-card.tone-gold .library-card-cover {
    background: #faf9f7;
  }

  .library-card.tone-violet .library-card-cover {
    background: #faf9f7;
  }

  .library-card.tone-teal .library-card-cover {
    background: #faf9f7;
  }

  .library-status,
  .library-kind {
    border-radius: 999px;
    font-size: 11px;
    line-height: 1;
    padding: 5px 8px;
    border: 1px solid transparent;
  }

  .library-status {
    color: #edf6ff;
    background: rgba(10, 19, 35, 0.52);
    border-color: rgba(182, 204, 238, 0.34);
  }

  .library-status.status-synced {
    border-color: rgba(94, 234, 212, 0.45);
  }

  .library-status.status-draft {
    border-color: rgba(253, 230, 138, 0.48);
  }

  .library-status.status-review {
    border-color: rgba(220, 38, 38, 0.5);
  }

  .library-kind {
    color: rgba(227, 236, 252, 0.88);
    border-color: rgba(174, 198, 232, 0.3);
    background: rgba(7, 14, 26, 0.34);
  }

  .library-card-body {
    display: grid;
    gap: 6px;
  }

  .library-card-title-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }

  .library-card-title {
    font-size: 12px;
    color: #1c1917;
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .library-card-time {
    font-size: 11px;
    color: rgba(184, 202, 230, 0.7);
    flex: 0 0 auto;
  }

  .library-card-summary {
    font-size: 12px;
    color: rgba(194, 210, 235, 0.84);
    line-height: 1.45;
    max-height: 52px;
    overflow: hidden;
  }

  .library-card-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .library-card-tags span {
    font-size: 11px;
    color: rgba(184, 211, 248, 0.88);
    border: 1px solid rgba(145, 175, 216, 0.32);
    background: rgba(20, 33, 58, 0.72);
    border-radius: 999px;
    padding: 3px 8px;
  }

  .rail-filter {
    border: 1px solid rgba(154, 180, 218, 0.24);
    background: rgba(245, 243, 240, 0.7);
    color: rgba(210, 224, 247, 0.9);
    border-radius: 10px;
    padding: 6px 8px;
    cursor: pointer;
    text-align: left;
    font-size: 12px;
  }

  .rail-filter.active {
    border-color: rgba(158, 206, 255, 0.66);
    background: #faf9f7;
    color: #ffffff;
  }

  .rail-reset {
    margin-top: auto;
    border: 1px dashed rgba(153, 178, 214, 0.36);
    background: rgba(20, 31, 54, 0.56);
    color: rgba(168, 162, 158, 0.88);
    border-radius: 10px;
    padding: 8px 10px;
    font-size: 12px;
    cursor: pointer;
  }

  .nav-btn {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    border-radius: 10px;
    padding: 8px 10px;
    text-align: left;
    border: 1px solid rgba(231, 229, 228, 1);
    background: rgba(245, 243, 240, 0.78);
    color: rgba(214, 228, 247, 0.9);
    box-shadow: none;
  }

  .nav-btn.active {
    border-color: rgba(217, 119, 6, 0.2);
    box-shadow: 0 8px 18px rgba(217, 119, 6, 0.32);
    background: #faf9f7;
    color: #ffffff;
  }

  .workflow-group {
    margin-top: 2px;
  }

  .doc-area {
    gap: 14px;
  }

  .library-command-bar {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: 12px;
    padding: 10px 12px;
    border-radius: 14px;
    border: 1px solid rgba(231, 229, 228, 1);
    background: #ffffff;
    box-shadow: 0 16px 30px rgba(0, 0, 0, 0.01);
  }

  .library-view-switch {
    display: inline-flex;
    gap: 6px;
    padding: 4px;
    border-radius: 12px;
    background: rgba(245, 243, 240, 0.88);
    border: 1px solid rgba(148, 173, 212, 0.24);
  }

  .view-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border: 1px solid transparent;
    border-radius: 9px;
    background: transparent;
    color: rgba(201, 218, 242, 0.76);
    min-width: 32px;
    height: 30px;
    cursor: pointer;
  }

  .view-btn.active {
    color: #ffffff;
    border-color: rgba(217, 119, 6, 0.25);
    background: #faf9f7;
    box-shadow: 0 8px 16px rgba(217, 119, 6, 0.32);
  }

  .library-counter {
    font-size: 13px;
    color: rgba(209, 224, 249, 0.84);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .library-actions {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .doc-toolbar,
  .doc-stage,
  .panel-card,
  .feedback-panel {
    border-color: rgba(231, 229, 228, 1);
    background: #ffffff;
    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.01);
  }

  .panel-card,
  .feedback-panel,
  .doc-toolbar,
  .doc-stage {
    position: relative;
    overflow: hidden;
  }

  .panel-card::before,
  .feedback-panel::before,
  .doc-toolbar::before,
  .doc-stage::before {
    content: "";
    position: absolute;
    inset: 0;
    pointer-events: none;
    border-radius: inherit;
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.045), transparent 38%);
    opacity: 0.85;
  }

  .toolbar-cluster {
    border-color: rgba(231, 229, 228, 1);
    background: rgba(250, 249, 247, 0.76);
  }

  .cluster-label {
    color: rgba(168, 162, 158, 0.72);
  }

  .tool-sep {
    background: rgba(231, 229, 228, 1);
  }

  .tool-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border: 1px solid rgba(231, 229, 228, 1);
    background: rgba(245, 243, 240, 0.82);
    color: #1c1917;
  }

  .tool-btn .ui-icon {
    width: 14px;
    height: 14px;
  }

  .tool-btn.active {
    border-color: rgba(217, 119, 6, 0.25);
    background: #faf9f7;
    color: #ffffff;
    box-shadow: 0 10px 18px rgba(217, 119, 6, 0.36);
  }

  .tool-btn:disabled {
    color: rgba(157, 176, 206, 0.62);
    border-color: rgba(132, 153, 186, 0.22);
    background: rgba(250, 249, 247, 0.58);
  }

  .generation-banner {
    border: 1px solid rgba(217, 119, 6, 0.2);
    background: rgba(250, 249, 247, 0.56);
    color: rgba(214, 228, 252, 0.9);
  }

  .section-failures {
    background: rgba(254, 242, 242, 0.34);
    border: 1px dashed rgba(220, 38, 38, 0.44);
    color: #fee2e2;
  }

  .failure-row {
    color: rgba(254, 202, 202, 0.94);
  }

  .originality-panel {
    background: rgba(255, 251, 235, 0.34);
    border-color: rgba(217, 119, 6, 0.32);
    color: #fef3c7;
  }

  .risk-row {
    border-top-color: rgba(217, 119, 6, 0.22);
  }

  .risk-metrics {
    color: rgba(253, 230, 138, 0.78);
  }

  .risk-badge {
    background: rgba(17, 24, 39, 0.45);
    color: rgba(168, 162, 158, 0.92);
  }

  .risk-badge.ok {
    color: #166534;
    background: rgba(22, 163, 74, 0.46);
    border-color: rgba(22, 163, 74, 0.28);
  }

  .risk-badge.bad {
    color: #fee2e2;
    background: rgba(254, 242, 242, 0.48);
    border-color: rgba(220, 38, 38, 0.3);
  }

  .panel-title {
    color: #1c1917;
    letter-spacing: 0.025em;
  }

  .media-meta-panel .panel-title {
    color: #f8dfab;
    letter-spacing: 0.12em;
    font-size: 12px;
  }

  .panel-sub,
  .panel-empty {
    color: rgba(189, 204, 231, 0.74);
  }

  .feedback-row textarea,
  .feedback-row select,
  .feedback-row input,
  .plagiarism-grid input,
  .version-input,
  .inline-style-row select,
  .inline-style-row input,
  .inline-instruction {
    border: 1px solid rgba(231, 229, 228, 1);
    background: rgba(14, 25, 46, 0.84);
    color: #1c1917;
  }

  .rating-btn {
    border: 1px solid rgba(152, 178, 216, 0.3);
    background: rgba(245, 243, 240, 0.82);
    color: #1c1917;
  }

  .rating-btn.active {
    border-color: rgba(217, 119, 6, 0.2);
    background: #faf9f7;
    color: #fff;
  }

  .feedback-tip {
    color: rgba(217, 119, 6, 0.9);
  }

  .feedback-history,
  .plagiarism-results,
  .plagiarism-report-actions {
    border-top-color: rgba(231, 229, 228, 1);
  }

  .feedback-item,
  .plagiarism-item,
  .candidate-before,
  .candidate-card {
    border: 1px solid rgba(231, 229, 228, 1);
    background: rgba(245, 243, 240, 0.72);
  }

  .feedback-item-note,
  .plagiarism-item-head,
  .candidate-text {
    color: #1c1917;
  }

  .plagiarism-item-head em,
  .plagiarism-item-metrics,
  .candidate-label,
  .candidate-meta,
  .inline-selection-meta > span {
    color: rgba(188, 205, 232, 0.72);
  }

  .plagiarism-evidence {
    color: rgba(214, 226, 247, 0.86);
    border-left-color: rgba(217, 119, 6, 0.2);
  }

  .candidate-switch {
    border: 1px solid rgba(231, 229, 228, 1);
    background: rgba(245, 243, 240, 0.72);
    color: rgba(168, 162, 158, 0.9);
  }

  .candidate-switch.active {
    border-color: rgba(217, 119, 6, 0.2);
    background: #faf9f7;
    color: #ffffff;
  }

  .inline-tabs {
    gap: 6px;
  }

  .inline-tab {
    border: 1px solid rgba(231, 229, 228, 1);
    background: rgba(245, 243, 240, 0.72);
    color: rgba(168, 162, 158, 0.9);
  }

  .inline-tab.active {
    border-color: rgba(217, 119, 6, 0.2);
    background: #faf9f7;
    color: #ffffff;
  }

  .assistant-inline-tip {
    border-color: rgba(217, 119, 6, 0.15);
    background: rgba(245, 243, 240, 0.72);
    color: rgba(168, 162, 158, 0.92);
  }

  .preset-chip {
    border-color: rgba(217, 119, 6, 0.2);
    background: rgba(245, 243, 240, 0.58);
    color: rgba(205, 223, 251, 0.94);
  }

  .inline-selection-bar {
    border: 1px solid rgba(217, 119, 6, 0.15);
    background: rgba(250, 249, 247, 0.94);
    box-shadow: 0 18px 36px rgba(0, 0, 0, 0.06);
  }

  .inline-selection-meta {
    color: #1c1917;
  }

  .mini-btn {
    border: 1px solid rgba(150, 176, 214, 0.3);
    background: rgba(250, 249, 247, 0.86);
    color: #1c1917;
  }

  .mini-btn:hover {
    border-color: rgba(217, 119, 6, 0.2);
    background: rgba(245, 243, 240, 0.92);
  }

  .inline-edit-popover,
  .confirm-dialog {
    border: 1px solid rgba(231, 229, 228, 1);
    background: rgba(255, 255, 255, 0.96);
    box-shadow: 0 28px 52px rgba(0, 0, 0, 0.08);
  }

  .confirm-note {
    border-color: rgba(149, 174, 214, 0.28);
    background: rgba(245, 243, 240, 0.74);
    color: rgba(214, 228, 250, 0.88);
  }

  .selected-chip {
    border: 1px solid rgba(217, 119, 6, 0.15);
    background: rgba(217, 119, 6, 0.28);
    color: #dceaff;
  }

  .media-meta-panel {
    border-color: rgba(208, 176, 106, 0.34);
    background:
      none, transparent 70%),
      #ffffff;
  }

  .meta-hero {
    position: relative;
    overflow: hidden;
    border-radius: 14px;
    border: 1px solid rgba(205, 169, 95, 0.34);
    background: #faf9f7;
    min-height: 96px;
    padding: 14px 12px;
  }

  .meta-hero-glow {
    position: absolute;
    width: 170px;
    height: 170px;
    right: -46px;
    top: -70px;
    border-radius: 50%;
    background: none, rgba(245, 200, 112, 0.05) 66%, transparent 76%);
    filter: blur(2px);
  }

  .meta-hero-text {
    position: relative;
    font-size: 13px;
    line-height: 1.52;
    color: rgba(168, 162, 158, 0.92);
    max-height: 74px;
    overflow: hidden;
  }

  .meta-list {
    margin-top: 10px;
    display: grid;
    gap: 8px;
  }

  .meta-list > div {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    border-bottom: 1px dashed rgba(231, 229, 228, 1);
    padding-bottom: 6px;
  }

  .meta-list span {
    color: rgba(179, 196, 225, 0.72);
    font-size: 12px;
  }

  .meta-list strong {
    color: #1c1917;
    font-size: 12px;
    text-align: right;
    font-weight: 600;
    max-width: 62%;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .meta-actions {
    margin-top: 12px;
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }

  .version-groups {
    display: grid;
    gap: 10px;
    max-height: 340px;
    overflow: auto;
    padding-right: 2px;
  }

  .version-group {
    border: 1px solid rgba(152, 177, 215, 0.2);
    border-radius: 12px;
    background: rgba(19, 30, 54, 0.6);
    padding: 10px;
  }

  .version-major,
  .version-minor {
    border: 1px solid rgba(153, 179, 218, 0.22);
    border-radius: 10px;
    background: rgba(245, 243, 240, 0.74);
    padding: 10px;
  }

  .version-major.current,
  .version-minor.current {
    border-color: rgba(158, 205, 255, 0.72);
    box-shadow: inset 0 0 0 1px rgba(217, 119, 6, 0.1);
  }

  .version-title {
    display: flex;
    justify-content: space-between;
    gap: 8px;
    color: #1c1917;
    font-size: 13px;
    font-weight: 600;
  }

  .badge {
    border-radius: 999px;
    font-size: 11px;
    padding: 2px 8px;
    border: 1px solid rgba(231, 229, 228, 1);
  }

  .badge.major {
    color: #fef3c7;
    border-color: rgba(245, 204, 113, 0.46);
    background: rgba(255, 251, 235, 0.3);
  }

  .badge.minor {
    color: #57534e;
    border-color: rgba(147, 191, 245, 0.42);
    background: rgba(30, 80, 164, 0.3);
  }

  .version-meta,
  .minor-meta,
  .version-summary {
    margin-top: 6px;
    color: rgba(186, 203, 232, 0.74);
    font-size: 12px;
  }

  .version-actions,
  .minor-actions {
    margin-top: 8px;
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }

  .version-minors {
    margin-top: 8px;
    display: grid;
    gap: 8px;
  }

  .version-diff {
    margin-top: 12px;
  }

  .version-diff pre {
    margin: 8px 0 0;
    max-height: 180px;
    overflow: auto;
    border-radius: 10px;
    border: 1px solid rgba(148, 173, 210, 0.26);
    background: rgba(250, 249, 247, 0.9);
    color: rgba(213, 228, 251, 0.88);
    padding: 10px;
    font-size: 12px;
    line-height: 1.4;
  }

  .icon-btn {
    border: 1px solid rgba(149, 174, 212, 0.28);
    background: rgba(245, 243, 240, 0.8);
    color: rgba(168, 162, 158, 0.9);
  }

  .assistant-queue-badge {
    background: rgba(250, 249, 247, 0.84);
    color: #1c1917;
  }

  /* Focus-first simplification */
  :global(body) {
    background: radial-gradient(1200px 720px at 18% -12%, rgba(217, 119, 6, 0.14), transparent 60%),
      none, transparent 58%),
      linear-gradient(180deg, #faf8f5 0%, #f5f3f0 34%, #eeede9 100%) !important;
    color: #1c1917;
  }

  :global(body)::before {
    display: none !important;
    content: none !important;
    background: none !important;
  }

  .app {
    --panel-bg: #ffffff;
    --panel-bg-soft: #ffffff;
    --panel-border: rgba(164, 183, 208, 0.18);
    --panel-shadow: 0 18px 40px rgba(0, 0, 0, 0.34);
    --text-main: #1c1917;
    --text-muted: rgba(171, 188, 209, 0.78);
    --accent: #d97706;
    --accent-weak: rgba(217, 119, 6, 0.14);
    background: radial-gradient(620px 360px at 12% 0%, rgba(217, 119, 6, 0.08), transparent 58%);
    font-family: "Sora", "Manrope", "PingFang SC", "Noto Sans SC", "Segoe UI", sans-serif;
  }

  .topbar {
    position: sticky;
    top: 0;
    z-index: 22;
    
    background: #ffffff;
    border-bottom: 1px solid rgba(231, 229, 228, 1);
    box-shadow: 0 14px 34px rgba(0, 0, 0, 0.24);
  }

  .brand-sub {
    display: block;
    color: rgba(168, 162, 158, 0.66);
    letter-spacing: 0.04em;
  }

  .workspace-status-line {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
    color: #78716c;
    font-size: 12px;
    line-height: 1.4;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

   .workspace-hub {
    gap: 10px;
  }

  .workspace-metrics {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    align-items: center;
  }

  .metric-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    min-height: 34px;
    padding: 7px 12px;
    border-radius: 999px;
    border: 1px solid rgba(231, 229, 228, 1);
    background: rgba(250, 249, 247, 0.72);
    color: #1c1917;
  }

  .metric-pill strong {
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.01em;
  }

  .metric-label {
    font-size: 11px;
    color: rgba(175, 191, 211, 0.74);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .metric-pill.tone-good {
    border-color: rgba(22, 163, 74, 0.26);
    background: rgba(22, 163, 74, 0.68);
  }

  .metric-pill.tone-warn {
    border-color: rgba(217, 119, 6, 0.26);
    background: rgba(255, 251, 235, 0.7);
  }

  .metric-pill.tone-alert {
    border-color: rgba(220, 38, 38, 0.3);
    background: rgba(254, 242, 242, 0.72);
  }

  .workspace-status-line .dot {
    width: 7px;
    height: 7px;
    border-radius: 999px;
    background: #16a34a;
    box-shadow: 0 0 0 4px rgba(22, 163, 74, 0.14);
    flex: 0 0 auto;
  }

  .menu-item {
    background: transparent;
    border: 1px solid transparent;
    color: #78716c;
    box-shadow: none;
  }

  .menu-item:hover {
    background: rgba(245, 243, 240, 0.8);
    border-color: rgba(231, 229, 228, 1);
    color: #44403c;
  }

  .menu-item.active {
    background: rgba(245, 243, 240, 0.88);
    border-color: rgba(231, 229, 228, 1);
    color: #1c1917;
    box-shadow: none;
  }

  .workspace {
    grid-template-columns: 82px minmax(0, 1fr) 338px;
    gap: 16px;
    padding: 14px 18px 34px;
  }

  .workspace.mode-editor {
    grid-template-columns: minmax(0, 1fr);
  }

  .workspace.mode-editor .nav-rail,
  .workspace.mode-editor .side-panel,
  .workspace.mode-editor .library-command-bar {
    display: none;
  }

  .workspace.mode-library {
    grid-template-columns: 252px minmax(0, 1fr);
  }

  .workspace.mode-library .side-panel {
    display: none;
  }

  .workspace.mode-library .nav-rail {
    width: 100%;
    min-width: 0;
    padding: 14px 0;
    transition: none;
  }

  .nav-rail {
    position: sticky;
    top: 98px;
    align-self: start;
    box-shadow: 0 18px 36px rgba(0, 0, 0, 0.34);
  }

  .doc-toolbar {
    position: sticky;
    top: 98px;
    z-index: 12;
    
  }

  .doc-stage {
    min-height: calc(100vh - 238px);
    background:
      none, transparent 56%),
      #ffffff;
  }

  .side-panel {
    position: sticky;
    top: 98px;
    align-self: start;
    max-height: calc(100vh - 118px);
    overflow: auto;
    padding-right: 4px;
  }

  .library-mode-stage {
    display: grid;
    gap: 12px;
    min-height: 360px;
    border: 1px dashed rgba(231, 229, 228, 1);
    border-radius: 14px;
    padding: 12px;
    background: rgba(250, 249, 247, 0.56);
  }

  .library-mode-dropzone {
    border: 1px dashed rgba(231, 229, 228, 1);
    border-radius: 12px;
    padding: 12px;
    background: rgba(245, 243, 240, 0.36);
    display: grid;
    gap: 10px;
  }

  .library-mode-actions {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .library-mode-board {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
  }

  .library-mode-board.list {
    grid-template-columns: 1fr;
  }

  .library-mode-card {
    border: 1px solid rgba(231, 229, 228, 1);
    border-radius: 12px;
    background: rgba(250, 249, 247, 0.78);
    color: #44403c;
    padding: 10px;
    text-align: left;
    display: grid;
    gap: 8px;
    cursor: pointer;
  }

  .library-mode-card.selected {
    border-color: rgba(217, 119, 6, 0.68);
    box-shadow: inset 0 0 0 1px rgba(217, 119, 6, 0.24);
  }

  .library-mode-card-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }

  .library-mode-card-title {
    font-size: 14px;
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .library-mode-card-summary {
    font-size: 12px;
    line-height: 1.5;
    color: #78716c;
    min-height: 38px;
  }

  .library-mode-card-foot {
    display: flex;
    justify-content: space-between;
    gap: 8px;
    color: #a8a29e;
    font-size: 11px;
  }

  .workspace.mode-collab {
    grid-template-columns: minmax(0, 1fr) 320px;
  }

  .workspace.mode-collab .nav-rail,
  .workspace.mode-collab .library-command-bar {
    display: none;
  }

  .doc-toolbar,
  .doc-stage,
  .panel-card,
  .feedback-panel {
    background: var(--panel-bg);
    border: 1px solid var(--panel-border);
    box-shadow: none;
  }

  .panel-card::before,
  .feedback-panel::before,
  .doc-toolbar::before,
  .doc-stage::before {
    display: none;
  }

  .feedback-row textarea,
  .feedback-row select,
  .plagiarism-grid input,
  .version-input,
  .block-input {
    background: rgba(250, 249, 247, 0.9);
    border-color: rgba(164, 183, 208, 0.22);
    color: #1c1917;
  }

  .feedback-item,
  .plagiarism-item,
  .version-major,
  .version-minor {
    background: rgba(15, 25, 42, 0.84);
    border-color: rgba(164, 183, 208, 0.2);
  }

  .version-summary,
  .plagiarism-item-head,
  .plagiarism-evidence,
  .risk-metrics {
    color: rgba(201, 214, 233, 0.82);
  }

  .generation-banner {
    color: #1c1917;
    border: 1px solid rgba(217, 119, 6, 0.22);
    background: #faf9f7;
  }

  .section-failures {
    background: #faf9f7;
    border-color: rgba(220, 38, 38, 0.32);
  }

  .quality-advice-panel {
    border-color: rgba(241, 184, 76, 0.26);
    background: radial-gradient(360px 180px at 100% 0%, rgba(217, 119, 6, 0.09), transparent 60%),
      #faf9f7;
  }

  .quality-advice-note {
    font-size: 12px;
    color: rgba(191, 205, 226, 0.72);
    line-height: 1.5;
  }

  .quality-advice-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
  }

  .quality-advice-card {
    display: grid;
    gap: 10px;
    padding: 12px 13px;
    border-radius: 14px;
    border: 1px solid rgba(231, 229, 228, 1);
    background: rgba(14, 23, 39, 0.76);
  }

  .quality-advice-card.tone-good {
    border-color: rgba(22, 163, 74, 0.22);
    background: rgba(19, 38, 31, 0.7);
  }

  .quality-advice-card.tone-warn {
    border-color: rgba(217, 119, 6, 0.22);
    background: rgba(46, 34, 15, 0.72);
  }

  .quality-advice-card.tone-alert {
    border-color: rgba(220, 38, 38, 0.24);
    background: rgba(254, 242, 242, 0.74);
  }

  .quality-advice-title-row {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 10px;
  }

  .quality-advice-title {
    font-size: 14px;
    font-weight: 700;
    color: #1c1917;
    line-height: 1.4;
  }

  .quality-advice-detail {
    font-size: 12px;
    line-height: 1.6;
    color: rgba(211, 223, 241, 0.84);
  }

  .quality-advice-actions {
    display: flex;
    justify-content: flex-end;
  }

  .quality-overview-badge,
  .quality-tone-chip {
    display: inline-flex;
    align-items: center;
    border-radius: 999px;
    border: 1px solid rgba(168, 187, 214, 0.24);
    padding: 4px 9px;
    font-size: 11px;
    line-height: 1;
    white-space: nowrap;
  }

  .quality-overview-badge.tone-good,
  .quality-tone-chip.tone-good {
    color: #166534;
    border-color: rgba(22, 163, 74, 0.24);
    background: rgba(22, 163, 74, 0.7);
  }

  .quality-overview-badge.tone-warn,
  .quality-tone-chip.tone-warn {
    color: #fef3c7;
    border-color: rgba(217, 119, 6, 0.24);
    background: rgba(50, 39, 13, 0.74);
  }

  .quality-overview-badge.tone-alert,
  .quality-tone-chip.tone-alert {
    color: #fee2e2;
    border-color: rgba(220, 38, 38, 0.26);
    background: rgba(56, 21, 21, 0.74);
  }

  .toolbar-line.primary {
    justify-content: space-between;
  }

  .toolbar-line.secondary {
    padding-top: 8px;
    border-top: 1px solid rgba(231, 229, 228, 1);
  }

  .toolbar-cluster {
    border-radius: 10px;
    border: 1px solid rgba(231, 229, 228, 1);
    background: rgba(250, 249, 247, 0.74);
  }

  .toolbar-cluster.core {
    flex: 1;
  }

  .plan-confirm-inline {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 8px;
    border: 1px dashed rgba(231, 229, 228, 1);
    border-radius: 10px;
    background: rgba(250, 249, 247, 0.52);
  }

  .plan-confirm-label {
    font-size: 11px;
    color: #78716c;
  }

  .plan-confirm-select,
  .plan-confirm-score input {
    height: 28px;
    border: 1px solid rgba(231, 229, 228, 1);
    border-radius: 8px;
    background: rgba(250, 249, 247, 0.84);
    color: #44403c;
    font-size: 12px;
    padding: 0 8px;
  }

  .plan-confirm-score {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: #78716c;
    font-size: 11px;
  }

  .plan-confirm-score input {
    width: 52px;
    text-align: center;
  }

  .toolbar-advanced-toggle {
    margin-left: auto;
  }

  .toolbar-generate-btn {
    min-width: 96px;
  }

  .tool-btn {
    background: rgba(250, 249, 247, 0.82);
    border: 1px solid rgba(231, 229, 228, 1);
    color: #a8a29e;
    box-shadow: none;
  }

  .tool-btn.active {
    background: rgba(217, 119, 6, 0.22);
    border-color: rgba(217, 119, 6, 0.72);
    color: #57534e;
    box-shadow: none;
  }

  .btn {
    background: transparent;
    border: 1px solid rgba(231, 229, 228, 1);
    color: #a8a29e;
    box-shadow: none;
  }

  .btn.ghost {
    background: transparent;
    color: #a8a29e;
    border: 1px solid rgba(231, 229, 228, 1);
  }

  .btn.primary {
    background: transparent;
    border: 1px solid rgba(231, 229, 228, 1);
    color: #a8a29e;
    box-shadow: none;
  }

  .toolbar-generate-btn.btn.primary {
    background: linear-gradient(135deg, #3b82f6, #0ea5e9);
    border-color: rgba(59, 130, 246, 0.5);
    color: #fff;
  }

  .btn.primary.danger {
    background: #b91c1c;
    border-color: #dc2626;
    color: #fff;
  }

  .top-actions .btn {
    background: transparent;
    border-color: rgba(148, 163, 184, 0.26);
  }

  .info-drawer-backdrop {
    position: fixed;
    inset: 0;
    z-index: 33;
    background: rgba(0, 0, 0, 0.01);
    display: flex;
    justify-content: flex-end;
  }

  .sheet-backdrop-hit {
    flex: 1;
    border: none;
    background: transparent;
    cursor: default;
  }

  .info-drawer {
    width: min(420px, 40vw);
    min-width: 320px;
    height: 100vh;
    margin: 0;
    border-radius: 0;
    border-left: 1px solid rgba(231, 229, 228, 1);
    padding: 16px 14px;
    overflow: auto;
  }

  .assistant-fab {
    position: fixed;
    right: 16px;
    bottom: 16px;
    width: 48px;
    height: 48px;
    border-radius: 999px;
    z-index: 34;
    border: 1px solid rgba(148, 163, 184, 0.32);
    background: rgba(250, 249, 247, 0.95);
    color: #44403c;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
  }

  .assistant-fab > span:not(.assistant-queue-badge) {
    display: none;
  }

  .assistant-sheet-backdrop {
    position: fixed;
    inset: 0;
    z-index: 35;
    background: rgba(2, 6, 23, 0.48);
    display: flex;
    justify-content: flex-end;
  }

  .assistant-sheet {
    width: min(40vw, 560px);
    min-width: 320px;
    height: 100vh;
    background: #f5f3f0;
    border-left: 1px solid rgba(148, 163, 184, 0.26);
    padding: 14px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .assistant-sheet-head {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 10px;
  }

  :global(.assistant-sheet .chat-shell.assistant) {
    width: 100%;
    height: 100%;
    border-radius: 12px;
    background: rgba(250, 249, 247, 0.85);
    border: 1px solid rgba(231, 229, 228, 1);
    box-shadow: none;
  }

  @keyframes rise-in {
    from {
      opacity: 0;
      transform: translateY(9px) scale(0.992);
      filter: blur(1px);
    }
    to {
      opacity: 1;
      transform: translateY(0) scale(1);
      filter: blur(0);
    }
  }

  @media (max-width: 1320px) {
    .workspace {
      grid-template-columns: 214px minmax(0, 1fr) 292px;
    }
  }

  @media (max-width: 1120px) {
    .workspace {
      grid-template-columns: 198px minmax(0, 1fr);
    }

    .side-panel {
      position: static;
      max-height: none;
      overflow: visible;
      grid-column: 1 / -1;
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }

    .workspace.hide-info .side-panel {
      display: none;
    }
  }

  @media (max-width: 960px) {
    .topbar {
      grid-template-columns: 1fr;
      gap: 10px;
      padding: 14px 16px;
    }

    .workspace-hub {
      gap: 10px;
    }

    .workspace-status-line {
      justify-content: flex-start;
    }

    .menu {
      justify-content: flex-start;
      flex-wrap: wrap;
    }

    .workspace {
      grid-template-columns: 1fr;
      padding: 12px 12px 36px;
      gap: 12px;
    }

    .nav-rail,
    .doc-toolbar {
      position: static;
      top: auto;
    }

    .workspace.hide-info {
      grid-template-columns: 1fr;
    }

    .nav-rail {
      order: 0;
    }

    .library-card-stream {
      max-height: 280px;
    }

    .doc-area {
      order: 1;
    }

    .side-panel {
      order: 2;
      grid-template-columns: 1fr;
    }

    .library-command-bar {
      grid-template-columns: 1fr;
      align-items: stretch;
      gap: 8px;
    }

    .library-view-switch {
      justify-content: flex-start;
      width: max-content;
    }

    .library-actions {
      justify-content: flex-start;
    }

    .library-mode-board {
      grid-template-columns: 1fr;
    }

    .quality-advice-grid {
      grid-template-columns: 1fr;
    }
  }

  @media (max-width: 760px) {
    .top-actions {
      justify-content: flex-start;
    }

    .icon-btn-text {
      gap: 6px;
    }

    .top-actions .btn {
      font-size: 12px;
      padding: 7px 9px;
    }

    .workspace-metrics {
      gap: 6px;
    }

    .metric-pill {
      width: 100%;
      justify-content: space-between;
    }

    .toolbar-line {
      gap: 6px;
    }

    .toolbar-cluster {
      width: 100%;
    }

    .inline-preset-row {
      grid-template-columns: 1fr 1fr;
    }

    .assistant-fab {
      right: 10px;
      bottom: 10px;
    }
    .assistant-sheet,
    .info-drawer {
      width: min(96vw, 560px);
    }
  }
</style>
