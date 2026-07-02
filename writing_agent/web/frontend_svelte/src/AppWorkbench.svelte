<script lang="ts">
  import './AppWorkbench.css'
  import { onMount } from 'svelte'
  import Editor from './lib/components/Editor.svelte'
  import DiagramCanvas from './lib/components/DiagramCanvas.svelte'
  import Toast from './lib/components/Toast.svelte'
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
  import { buildDocIrOps } from './lib/workbench/docIrOps'
  import {
    buildLibraryCards,
    cardMatchesSearch,
    estimateKb,
    guessDocTitle
  } from './lib/workbench/libraryCards'
  import AssistantSheet from './lib/workbench/AssistantSheet.svelte'
  import ConfirmDialog from './lib/workbench/ConfirmDialog.svelte'
  import EditorCommandBar from './lib/workbench/EditorCommandBar.svelte'
  import GenerationStatusPanels from './lib/workbench/GenerationStatusPanels.svelte'
  import InfoDrawer from './lib/workbench/InfoDrawer.svelte'
  import LibraryModeStage from './lib/workbench/LibraryModeStage.svelte'
  import LibraryRail from './lib/workbench/LibraryRail.svelte'
  import QualityPanels from './lib/workbench/QualityPanels.svelte'
  import VersionPanel from './lib/workbench/VersionPanel.svelte'
  import WorkbenchTopbar from './lib/workbench/WorkbenchTopbar.svelte'
  import {
    DOC_TITLE_TARGET_ID,
    blockIdFromTarget,
    blockTargetIds,
    buildBlockSessionKey,
    clamp,
    isDocTitleTargetId,
    isSectionTargetId,
    normalizeColorHex,
    sectionIdFromTarget,
    sectionTargetIds
  } from './lib/workbench/inlineTargets'
  import {
    buildQualityAdviceItems,
    buildQualityOverview,
    normalizeScore,
    plagiarismRiskLabel
  } from './lib/workbench/quality'
  import { buildVersionGroups } from './lib/workbench/versions'
  import {
    normalizeGraphMeta,
    normalizeOriginalitySummary,
    normalizeResumeState,
    normalizeStringArray,
    summarizeGraphMeta,
    summarizeOriginalitySummary
  } from './lib/workbench/metadata'
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

  function metaPreviewSnippet() {
    const selected = selectedTargetPlainText()
    if (selected) return selected.slice(0, 140)
    return String($sourceText || '').replace(/\s+/g, ' ').trim().slice(0, 140)
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

  $effect(() => {
    const cards = buildLibraryCards({
      sourceText: $sourceText,
      wordCount: Number($wordCount || 0),
      previewSnippet: metaPreviewSnippet(),
      lastGraphMeta,
      feedbackItems,
      versionGroupCount: versionGroups.length
    })
    const query = librarySearch.trim()
    filteredLibraryCards = cards.filter((card) => cardMatchesSearch(card, query))
    if (!librarySelectAll && selectedLibraryCardId && !filteredLibraryCards.some((card) => card.id === selectedLibraryCardId)) {
      selectedLibraryCardId = ''
    }
  })

  let topStatusLine = $derived(buildTopStatusLine())
  let qualityOverview = $derived(
    buildQualityOverview({
      aiRateResult,
      sectionOriginalitySummary,
      plagiarismLatestReport,
      plagiarismResults,
      plagiarismMaxScore,
      plagiarismFlaggedCount
    })
  )
  let qualityAdviceItems = $derived(
    buildQualityAdviceItems({
      aiRateResult,
      sectionOriginalitySummary,
      plagiarismLatestReport,
      plagiarismResults,
      plagiarismMaxScore,
      plagiarismFlaggedCount
    })
  )

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

  function cloneCandidates(candidates: Array<any>) {
    return (candidates || []).map((c) => ({ ...c }))
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
  <WorkbenchTopbar
    {workspaceMode}
    {qualityOverview}
    wordCount={Number($wordCount || 0)}
    routeId={lastGraphMeta?.route_id || '默认'}
    {topStatusLine}
    onSwitchMode={switchWorkspaceMode}
    onSave={saveDoc}
    onExportDocx={exportDocx}
    onExportPdf={exportPdf}
    onToggleInfo={toggleInfoDrawer}
  />

  <div class={`workspace ${hideLibraryInfo ? 'hide-info' : ''} mode-${workspaceMode}`}>
    <LibraryRail
      {workspaceMode}
      bind:librarySearch
      bind:librarySelectAll
      bind:selectedLibraryCardId
      {libraryViewMode}
      {filteredLibraryCards}
      onUpload={triggerLibraryUpload}
      onOpenCard={openLibraryCard}
      onSwitchMode={switchWorkspaceMode}
      onOpenCanvas={() => (canvasOpen = true)}
      onOpenCitations={() => (showCitations = true)}
      onOpenAssistant={() => { switchWorkspaceMode('collab'); setAssistantOpen(true) }}
      onOpenMetrics={() => (showPerformanceMetrics = true)}
    />

    <section class="doc-area">
      {#if workspaceMode === 'library'}
        <LibraryModeStage
          bind:libraryViewMode
          {librarySearch}
          {filteredLibraryCards}
          {librarySelectAll}
          {selectedLibraryCardId}
          onUpload={triggerLibraryUpload}
          onOpenCitations={() => (showCitations = true)}
          onOpenVersions={openVersions}
          onOpenCard={openLibraryCard}
          onDrop={handleLibraryDrop}
          onBack={() => switchWorkspaceMode('editor')}
        />
      {:else}
      <EditorCommandBar
        bind:libraryViewMode
        {librarySearch}
        bind:librarySelectAll
        filteredCount={filteredLibraryCards.length}
        bind:showAdvancedToolbar
        bind:showAiRatePanel
        bind:showPlagiarismPanel
        bind:showFeedbackPanel
        bind:planConfirmDecision
        bind:planConfirmScore
        {editorToolbarState}
        generating={$generating}
        instruction={$instruction}
        {resumeState}
        onRunEditorCommand={runEditorCommand}
        onOpenCanvas={() => (canvasOpen = true)}
        onOpenCitations={() => (showCitations = true)}
        onOpenInfoDrawer={openInfoDrawer}
        onRunBatch={runBatchFromToolbar}
        onGenerate={handleGenerate}
        onPersistPlanConfirmPreference={persistPlanConfirmPreference}
        onStop={handleStop}
        onResume={resumeInterruptedGeneration}
      />

      <GenerationStatusPanels
        generating={$generating}
        {progress}
        {resumeState}
        {sectionFailures}
        {sectionOriginalitySummary}
        {retrySection}
        {reviseRiskSection}
      />

      <QualityPanels
        {qualityAdviceItems}
        {qualityOverview}
        {runQualityAdviceAction}
        {showAiRatePanel}
        bind:aiRateThreshold
        {aiRateLoading}
        {aiRateResult}
        {runAiRateCheck}
        {showPlagiarismPanel}
        bind:plagiarismThreshold
        bind:plagiarismReferenceDocIds
        bind:plagiarismReferenceText
        {plagiarismLoading}
        {plagiarismLibraryLoading}
        {plagiarismResults}
        {plagiarismMaxScore}
        {plagiarismFlaggedCount}
        {plagiarismLatestReport}
        {runPlagiarismCheck}
        {runPlagiarismLibraryScan}
        {downloadPlagiarismReport}
        {plagiarismRiskLabel}
        {showFeedbackPanel}
        bind:satisfactionRating
        bind:satisfactionStage
        bind:satisfactionNote
        {satisfactionSaving}
        {lastLowFeedbackRecorded}
        {feedbackItems}
        {submitSatisfaction}
        {formatFeedbackTime}
      />

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

    <VersionPanel
      {versionLoading}
      {versionError}
      {versionGroups}
      bind:versionMessage
      {versionDiff}
      onRefresh={loadVersionLog}
      onCommit={commitVersion}
      onCheckout={checkoutVersion}
      onCompare={compareWithCurrent}
    />
  </div>

  {#if infoDrawerOpen}
    <InfoDrawer
      preview={metaPreviewSnippet()}
      title={guessDocTitle($sourceText)}
      sizeKb={estimateKb($sourceText)}
      wordCount={Number($wordCount || 0)}
      selectedCount={selectedBlockIds.length}
      routeId={lastGraphMeta?.route_id || '默认'}
      onClose={closeInfoDrawer}
      onSwitchToEditor={() => switchWorkspaceMode('editor')}
      onClearSelection={() => { selectedBlockId = ''; selectedBlockIds = []; selectedBlocks = []; }}
    />
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
    <AssistantSheet
      badgeCount={assistantBadgeCount}
      onClose={() => setAssistantOpen(false)}
      onKeydown={handleAssistantSheetKeydown}
      onSend={(text) => handleGenerate(text)}
      onUpload={handleAssistantUpload}
    />
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
    <ConfirmDialog
      confirmation={pendingGenerateConfirmation}
      busy={confirmDialogBusy}
      onCancel={cancelPendingGenerate}
      onConfirm={confirmPendingGenerate}
    />
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


