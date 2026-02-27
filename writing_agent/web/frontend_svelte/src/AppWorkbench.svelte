<script lang="ts">
  import { onMount } from 'svelte'
  import Chat from './lib/components/Chat.svelte'
  import Editor from './lib/components/Editor.svelte'
  import DiagramCanvas from './lib/components/DiagramCanvas.svelte'
  import Toast from './lib/components/Toast.svelte'
  import Settings from './lib/components/Settings.svelte'
  import DocList from './lib/components/DocList.svelte'
  import LoadingSkeleton from './lib/components/LoadingSkeleton.svelte'
  import ProgressBar from './lib/components/ProgressBar.svelte'
  import ErrorBoundary from './lib/components/ErrorBoundary.svelte'
  import CitationManager from './lib/components/CitationManager.svelte'
  import PerformanceMetrics from './lib/components/PerformanceMetrics.svelte'
  import { initWasmEngine, isWasmAvailable } from './lib/engine/wasmLoader'
  import { textToDocIr, docIrToMarkdown } from './lib/utils/markdown'
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

  let aborter: AbortController | null = null
  let writeBuffer = ''
  let writeTimer: ReturnType<typeof setTimeout> | null = null
  let docIrRefreshTimer: ReturnType<typeof setTimeout> | null = null
  let streamingLive = false
  let typingActive = false
  let streamQueue: Array<{ section: string; raw: boolean; text: string }> = []
  let streamTimer: ReturnType<typeof setTimeout> | null = null
  let streamToken = 0
  let streamPendingChars = 0
  let streamFastDrain = false
  let streamTypingActive = false
  let pendingFinalText: string | null = null
  let pendingFinalDocIr: Record<string, unknown> | null = null
  let genStartTs = 0
  let lastEventName = ''
  let lastProgressMsg = ''
  let sawFinal = false
  let sawError = false
  let sawSectionDelta = false
  let lastEventAt = 0
  let lastEventGap = 0
  let maxEventGap = 0
  let baseIdleMs = 90000
  let stallTimer: ReturnType<typeof setInterval> | null = null
  let fallbackTriggered = false
  let progress = { current: 0, total: 0, percent: 0, etaS: 0, section: "" }
  let progressStart = 0
  let progressEvents: number[] = []
  let sectionFailures: { section: string; reason: string }[] = []
  let leftWidth = 46
  let resizing = false
  let autoSaveTimer: ReturnType<typeof setTimeout> | null = null
  let partialSaveTimer: ReturnType<typeof setTimeout> | null = null
  let partialSaveInFlight = false
  let partialSavedSnapshot = ''
  let lastSavedText = ''
  let lastSavedDocIr: Record<string, unknown> | null = null
  type ResumeState = {
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
  let resumeState: ResumeState | null = null
  let showDocList = false
  let showCitations = false
  let showPerformanceMetrics = false
  let showVersions = false
  let showFeedbackPanel = false
  type FeedbackItem = {
    id: string
    rating: number
    note: string
    stage: string
    tags?: string[]
    created_at: number
  }
  let feedbackItems: FeedbackItem[] = []
  let satisfactionRating = 0
  let satisfactionStage = 'general'
  let satisfactionNote = ''
  let satisfactionSaving = false
  let lastLowFeedbackRecorded = 0
  let showPlagiarismPanel = false
  let plagiarismLoading = false
  let plagiarismLibraryLoading = false
  let plagiarismThreshold = 0.35
  let plagiarismReferenceDocIds = ''
  let plagiarismReferenceText = ''
  let showAiRatePanel = false
  let aiRateLoading = false
  let aiRateThreshold = 0.65
  let aiRateResult: Record<string, any> | null = null
  type PlagiarismEvidence = {
    source_start: number
    reference_start: number
    match_chars: number
    snippet: string
  }
  type PlagiarismResult = {
    reference_id: string
    reference_title: string
    score: number
    threshold: number
    suspected: boolean
    metrics: Record<string, any>
    evidence: PlagiarismEvidence[]
  }
  let plagiarismResults: PlagiarismResult[] = []
  let plagiarismFlaggedCount = 0
  let plagiarismMaxScore = 0
  let plagiarismLatestReport: Record<string, any> | null = null
  let versionLoading = false
  let versionList: Array<any> = []
  let versionGroups: Array<any> = []
  let versionDiff = ''
  let versionDiffFrom = ''
  let versionDiffTo = ''
  let versionTree = ''
  let versionMessage = ''
  let versionError = ''
  let assistantOpen = true
  let canvasOpen = false
  let selectedBlockId = ''
  let selectedBlockIds: string[] = []
  let selectedBlocks: Array<{
    id: string
    text: string
    style: Record<string, string>
    kind?: 'block' | 'section' | 'title'
    sectionId?: string
    sectionTitle?: string
  }> = []
  let selectedBlockText = ''
  let blockStyleFontSize = ''
  let blockStyleLineHeight = ''
  let blockStyleFontFamily = ''
  let blockStyleColor = ''
  let blockStyleBackground = ''
  let blockStyleAlign = ''
  let blockStyleFontWeight = ''
  let blockStyleFontStyle = ''
  let blockEditCmd = ''
  let inlinePanelTab: 'rewrite' | 'style' | 'assistant' = 'rewrite'
  let blockPreviewBusy = false
  let blockEditError = ''
  let blockOriginalText = ''
  let blockCandidates: Array<any> = []
  let activeCandidateIndex = 0
  let activeCandidate: any = null
  let blockDialogInput = ''
  type InlinePanelTab = 'rewrite' | 'style' | 'assistant'
  type BlockSession = {
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
  const blockSessionStore = new Map<string, BlockSession>()
  let activeBlockSessionKey = ''
  let inlineBarVisible = false
  let inlineBarLeft = 0
  let inlineBarTop = 0
  let inlinePopoverOpen = false
  let inlinePopoverPlacement: 'up' | 'down' = 'down'
  let inlinePopoverLeft = 0
  let inlinePopoverTop = 0
  let activeStreamingSections: string[] = []
  let completedStreamingSections: string[] = []
  let inlineEditLocked = false
  let inlineEditLockReason = ''
  let uploadImageInput: HTMLInputElement | null = null
  let pendingInlineImageTargets: string[] = []
  let renderActivityAt = Date.now()
  let editorToolbarState = {
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
  }
  type QueuedInstruction = { id: number; text: string; createdAt: number }
  let queuedInstructionSeed = 0
  let queuedGlobalInstructions: QueuedInstruction[] = []
  let drainingQueuedGlobalInstructions = false
  let rustEngineReadyLocal = false
  let wasmInitPromise: Promise<boolean> | null = null
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
    return $generating || typingActive || streamTypingActive
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

  let typingToken = 0
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

  function handleBlockEdit(event: CustomEvent) {
    const payload = event.detail || {}
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
      pushToast('Block updated', 'ok')
    }
  }

  function handleToolbarState(event: CustomEvent) {
    const detail = event.detail && typeof event.detail === 'object' ? event.detail : {}
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

  function handleBlockSelect(event: CustomEvent) {
    const detail = event.detail || {}
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

  function openAssistantForBlock(customInstruction?: string) {
    inlinePanelTab = 'assistant'
    assistantOpen = true
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
    queueMicrotask(() => {
      const input = document.querySelector('.assistant-dock .composer textarea') as HTMLTextAreaElement | null
      if (input) input.focus()
    })
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
    const input = blockEditCmd.trim()
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
              instruction: variant.instruction,
              doc_ir: workingDoc,
              variants: [{ label: variant.label, instruction: variant.instruction }]
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
    if (!selectedBlockIds.length) return
    if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
      event.preventDefault()
      const placement: 'up' | 'down' = event.shiftKey ? 'up' : 'down'
      openInlinePopover(inlinePanelTab as InlinePanelTab, placement)
      return
    }
    if (event.key === 'Escape') {
      if (inlinePopoverOpen) inlinePopoverOpen = false
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

  $: if (activeCandidateIndex >= blockCandidates.length) {
    activeCandidateIndex = 0
  }

  $: activeCandidate = blockCandidates[activeCandidateIndex] || null

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
      lines.push('Nodes:')
      for (const n of nodes) {
        const id = String(n.id || '').slice(0, 7)
        const msg = String(n.message || '')
        const ts = formatVersionTime(Number(n.timestamp || 0))
        const cur = n.is_current ? ' *current*' : ''
        lines.push(`- ${id} ${msg} ${ts}${cur}`)
      }
      lines.push('')
      lines.push('Edges:')
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
    await handleGenerate(inst, {
      fromResume: true,
      forcedComposeMode: 'continue',
      resumeSections: resumeState.pending_sections || [],
      cursorAnchor: resumeState.cursor_anchor || ''
    })
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

  async function handleAssistantUpload(event: CustomEvent<{ file: File }>) {
    const file = event?.detail?.file
    if (!file) return
    await uploadAsset(file, { source: 'assistant' })
  }

  function toggleDarkMode() {
    darkMode.update(v => !v)
    document.body.classList.toggle('dark', !$darkMode)
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
    const inst = String(text || '').trim()
    if (!inst) return
    if (isGenerationOrRenderBusy()) {
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
    if (opts?.fromQueue) {
      appendChat('system', '正在执行排队指令…')
    } else if (opts?.fromResume) {
      appendChat('system', '正在续跑上次中断任务…')
    } else {
      appendChat('user', inst)
      instruction.set('')
    }
    runEditorCommand('commit')
    const latestText = String($sourceText || '')
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
    const resumeSections = normalizeStringArray(opts?.resumeSections || [])
    const cursorAnchor = String(opts?.cursorAnchor || '').trim()
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
    fallbackTriggered = false
    progress = { current: 0, total: 0, percent: 0, etaS: 0, section: "" }
    progressStart = Date.now()
    progressEvents = []
    maxEventGap = 0
    sectionFailures = []
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

    const generatePayload: Record<string, unknown> = {
      instruction: requestInstruction,
      text: latestText,
      compose_mode: composeMode
    }
    if (resumeSections.length > 0) {
      generatePayload.resume_sections = resumeSections
    }
    if (cursorAnchor) {
      generatePayload.cursor_anchor = cursorAnchor
    }

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
            const reason = String(data.reason || 'unknown')
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
          if (event === 'final') {
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
            sawFinal = true
            resumeState = null
            appendChat('system', '已完成生成。')
            pushThought('完成', '生成完成', formatElapsed())
            pushToast('生成完成', 'ok')
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
            const resp = await fetch(`/api/doc/${$docId}/generate`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(generatePayload)
            })
            if (!resp.ok) {
              const msg = await resp.text()
              throw new Error(`HTTP ${resp.status}: ${msg || resp.statusText}`)
            }
            const data = await resp.json()
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
            appendChat('system', '已完成生成（非流式兜底）。')
            pushThought('完成', '非流式生成完成', formatElapsed())
            pushToast('生成完成（非流式）', 'ok')
            saveDoc().catch(() => {})
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
        resumeState = {
          status: 'interrupted',
          updated_at: Date.now() / 1000,
          user_instruction: String(prev?.user_instruction || inst),
          request_instruction: String(prev?.request_instruction || requestInstruction),
          compose_mode: (prev?.compose_mode || composeMode) as ResumeState['compose_mode'],
          partial_chars: preview.length,
          partial_preview: preview.slice(-240),
          plan_sections: normalizeStringArray(prev?.plan_sections || []),
          completed_sections: normalizeStringArray(prev?.completed_sections || []),
          pending_sections: normalizeStringArray(prev?.pending_sections || []),
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
    const target = String(section || '').trim()
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
          instruction: String($instruction || '').trim(),
        })
      })
      if (!resp.ok) {
        throw new Error(await resp.text())
      }
      const data = await resp.json()
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

  function handleStop() {
    if (aborter) aborter.abort('用户点击停止')
  }

  function runEditorCommand(cmd: EditorCommand) {
    editorCommand.set(cmd)
  }

  $: {
    if ($sourceText && $sourceText !== lastSavedText && !$generating) {
      if (autoSaveTimer) clearTimeout(autoSaveTimer)
      autoSaveTimer = setTimeout(() => {
        saveDoc().catch(() => {})
      }, 3000)
    }
  }

  $: {
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
  }

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
      window.removeEventListener('keydown', handleInlineShortcut)
      if (autoSaveTimer) clearTimeout(autoSaveTimer)
    }
  })
</script>

<main class="app" class:dark={$darkMode}>
  <header class="topbar">
    <div class="brand">
      <div class="logo">IR</div>
      <div class="brand-text">
        <div class="brand-title">写作引擎</div>
        <div class="brand-sub">Doc IR · 语义写作</div>
      </div>
    </div>
    <nav class="menu">
      <button class="menu-item">概览</button>
      <button class="menu-item">模板</button>
      <button class="menu-item">协作</button>
      <button class="menu-item">历史</button>
      <button class="menu-item">帮助</button>
    </nav>
    <div class="top-actions">
      <div class="status-chip">
        <span class="dot"></span>
        <span>{$docStatus || '未加载'}</span>
      </div>
      <div class="status-chip light">字数 {$wordCount}</div>
      {#if feedbackItems.length > 0}
        <div class="status-chip light">最近满意度 {feedbackItems[0].rating}/5</div>
      {/if}
      {#if plagiarismResults.length > 0}
        <div class="status-chip light">查重最高 {Math.round(plagiarismMaxScore * 100)}%</div>
      {/if}
      <button class="btn ghost" on:click={saveDoc}>保存</button>
      <button class="btn ghost" on:click={exportDocx}>导出 Word</button>
      <button class="btn ghost" on:click={exportPdf}>导出 PDF</button>
      <button
        class="btn ghost"
        data-testid="ai-rate-toggle"
        on:click={() => (showAiRatePanel = !showAiRatePanel)}
      >
        {showAiRatePanel ? '收起AI率' : 'AI率检测'}
      </button>
      <button
        class="btn ghost"
        data-testid="plagiarism-toggle"
        on:click={() => (showPlagiarismPanel = !showPlagiarismPanel)}
      >
        {showPlagiarismPanel ? '收起查重' : '查重检测'}
      </button>
      <button
        class="btn ghost"
        data-testid="feedback-toggle"
        on:click={() => (showFeedbackPanel = !showFeedbackPanel)}
      >
        {showFeedbackPanel ? '收起评分' : '满意度评分'}
      </button>
      <Settings />
    </div>
  </header>

  <div class="workspace">
    <aside class="nav-rail">
      <button class="nav-btn active" title="文档">
        <span>文档</span>
      </button>
      <button class="nav-btn" title="画布" on:click={() => (canvasOpen = true)}>
        <span>画布</span>
      </button>
      <button class="nav-btn" title="引用" on:click={() => (showCitations = true)}>
        <span>引用</span>
      </button>
      <button class="nav-btn" title="性能" on:click={() => (showPerformanceMetrics = true)}>
        <span>性能</span>
      </button>
      <button class="nav-btn" title="文档库" on:click={() => (showDocList = true)}>
        <span>文档库</span>
      </button>
    </aside>

    <section class="doc-area">
      <div class="doc-toolbar">
        <div class="toolbar-line">
          <div class="toolbar-cluster">
            <span class="cluster-label">文本</span>
            <button class="tool-btn" title="撤销 Ctrl/Cmd+Z" on:click={() => runEditorCommand('undo')} disabled={!editorToolbarState.canUndo}>↶</button>
            <button class="tool-btn" title="重做 Ctrl/Cmd+Y" on:click={() => runEditorCommand('redo')} disabled={!editorToolbarState.canRedo}>↷</button>
            <button class="tool-btn" title="复制 Ctrl/Cmd+C" on:click={() => runEditorCommand('copy')} disabled={!editorToolbarState.canCopy}>复制</button>
            <button class="tool-btn" title="剪切 Ctrl/Cmd+X" on:click={() => runEditorCommand('cut')} disabled={!editorToolbarState.canCut}>剪切</button>
            <button class="tool-btn" title="粘贴 Ctrl/Cmd+V" on:click={() => runEditorCommand('paste')} disabled={!editorToolbarState.canPaste}>粘贴</button>
            <button class="tool-btn" title="清除格式" on:click={() => runEditorCommand('clear-format')} disabled={editorToolbarState.readonly || !editorToolbarState.focused}>Tx</button>
            <span class="tool-sep"></span>
            <button
              class={`tool-btn ${editorToolbarState.bold ? 'active' : ''}`}
              title="加粗 Ctrl/Cmd+B"
              on:click={() => runEditorCommand('bold')}
              disabled={editorToolbarState.readonly || !editorToolbarState.focused}
            >
              B
            </button>
            <button
              class={`tool-btn ${editorToolbarState.italic ? 'active' : ''}`}
              title="斜体 Ctrl/Cmd+I"
              on:click={() => runEditorCommand('italic')}
              disabled={editorToolbarState.readonly || !editorToolbarState.focused}
            >
              I
            </button>
            <button
              class={`tool-btn ${editorToolbarState.underline ? 'active' : ''}`}
              title="下划线 Ctrl/Cmd+U"
              on:click={() => runEditorCommand('underline')}
              disabled={editorToolbarState.readonly || !editorToolbarState.focused}
            >
              U
            </button>
          </div>
          <div class="toolbar-cluster">
            <span class="cluster-label">结构</span>
            <button class="tool-btn" on:click={() => runEditorCommand('heading1')}>H1</button>
            <button class="tool-btn" on:click={() => runEditorCommand('heading2')}>H2</button>
            <button class="tool-btn" on:click={() => runEditorCommand('quote')}>引用</button>
            <button class="tool-btn" on:click={() => runEditorCommand('code')}>代码</button>
            <button class="tool-btn" on:click={() => runEditorCommand('list-bullet')}>列表</button>
            <button class="tool-btn" on:click={() => runEditorCommand('list-number')}>1.</button>
          </div>
          <div class="toolbar-cluster">
            <span class="cluster-label">插入</span>
            <button class="tool-btn" on:click={() => (canvasOpen = true)}>画布</button>
            <button class="tool-btn" on:click={() => (showCitations = true)}>引用</button>
          </div>
          <div class="toolbar-cluster compact">
            <span class="cluster-label">智能写作</span>
            <button class="btn ghost" on:click={() => handleGenerate($instruction)} disabled={$generating}>生成</button>
            <button class="btn ghost" on:click={handleStop} disabled={!$generating}>停止</button>
            {#if resumeState && !$generating}
              <button class="btn ghost" on:click={resumeInterruptedGeneration}>续跑</button>
            {/if}
          </div>
        </div>
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
              <button class="btn ghost" on:click={() => retrySection(f.section)}>重试</button>
            </div>
          {/each}
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
                on:click={runAiRateCheck}
                disabled={aiRateLoading}
                data-testid="ai-rate-run"
              >
                {aiRateLoading ? '检测中...' : '开始 AI 率检测'}
              </button>
              {#if aiRateResult}
                <span class="feedback-tip">
                  估计 AI 率 {Math.round(Number(aiRateResult.ai_rate || 0) * 100)}%，
                  风险 {String(aiRateResult.risk_level || 'unknown')}，
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
                on:click={runPlagiarismCheck}
                disabled={plagiarismLoading}
                data-testid="plagiarism-run"
              >
                {plagiarismLoading ? '检测中...' : '开始查重'}
              </button>
              <button
                class="btn ghost"
                on:click={runPlagiarismLibraryScan}
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
                <button class="btn ghost" on:click={() => downloadPlagiarismReport('json')}>下载 JSON</button>
                <button class="btn ghost" on:click={() => downloadPlagiarismReport('md')}>下载 MD</button>
                <button class="btn ghost" on:click={() => downloadPlagiarismReport('csv')}>下载 CSV</button>
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
                    on:click={() => (satisfactionRating = score)}
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
                on:click={submitSatisfaction}
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
            on:blockedit={handleBlockEdit}
            on:blockselect={handleBlockSelect}
            on:toolbarstate={handleToolbarState}
          />
        {/if}
      </div>

    </section>

    <aside class="side-panel">
      <div class="panel-card version-panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">版本树</div>
            <div class="panel-sub">自动小版本 · 手动大版本</div>
          </div>
          <button class="icon-btn" on:click={loadVersionLog} title="刷新">刷新</button>
        </div>
        <div class="major-commit">
          <input
            class="version-input"
            placeholder="输入版本说明"
            bind:value={versionMessage}
          />
          <button class="btn primary" on:click={commitVersion}>保存版本</button>
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
                    <button class="btn ghost" on:click={() => checkoutVersion(group.major?.version_id)} disabled={group.major?.is_current}>切换</button>
                    <button class="btn ghost" on:click={() => compareWithCurrent(group.major?.version_id)} disabled={group.major?.is_current}>对比</button>
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
                          <button class="btn ghost" on:click={() => checkoutVersion(v.version_id)} disabled={v.is_current}>切换</button>
                          <button class="btn ghost" on:click={() => compareWithCurrent(v.version_id)} disabled={v.is_current}>对比</button>
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
        <button class="mini-btn" on:click={() => openInlinePopover('rewrite', 'down')} disabled={inlineEditLocked}>改写</button>
        <button class="mini-btn" on:click={() => openInlinePopover('style', 'down')} disabled={inlineEditLocked}>样式</button>
        <button class="mini-btn" on:click={triggerInlineTableInsert} disabled={inlineEditLocked}>插表</button>
        <button class="mini-btn" on:click={triggerInlineImageUpload} disabled={inlineEditLocked}>插图</button>
        <button class="mini-btn" on:click={() => openInlinePopover('assistant', 'down')}>对话</button>
        <button class="mini-btn" on:click={() => openInlinePopover(inlinePanelTab as InlinePanelTab, 'up')}>上方</button>
        <button class="mini-btn" on:click={() => openInlinePopover(inlinePanelTab as InlinePanelTab, 'down')}>下方</button>
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
          <button class="btn ghost btn-sm" on:click={triggerInlineTableInsert} disabled={inlineEditLocked}>插表</button>
          <button class="btn ghost btn-sm" on:click={triggerInlineImageUpload} disabled={inlineEditLocked}>插图</button>
          <button class="btn ghost btn-sm" on:click={() => openInlinePopover(inlinePanelTab as InlinePanelTab, 'up')}>上方</button>
          <button class="btn ghost btn-sm" on:click={() => openInlinePopover(inlinePanelTab as InlinePanelTab, 'down')}>下方</button>
          <button class="btn ghost btn-sm" on:click={closeInlinePopover}>关闭</button>
        </div>
      </div>

      <div class="inline-tabs">
        <button class={`inline-tab ${inlinePanelTab === 'rewrite' ? 'active' : ''}`} on:click={() => toggleInlineTab('rewrite')}>
          改写建议
        </button>
        <button class={`inline-tab ${inlinePanelTab === 'style' ? 'active' : ''}`} on:click={() => toggleInlineTab('style')}>
          样式设置
        </button>
        <button class={`inline-tab ${inlinePanelTab === 'assistant' ? 'active' : ''}`} on:click={() => toggleInlineTab('assistant')}>
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
            on:change={() => applyInlineBlockStyle({ fontFamily: blockStyleFontFamily })}
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
            on:change={() => applyInlineBlockStyle({ fontSize: blockStyleFontSize })}
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
            on:change={() => applyInlineBlockStyle({ lineHeight: blockStyleLineHeight })}
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
            on:change={() => applyInlineBlockStyle({ align: blockStyleAlign })}
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
            on:change={() => applyInlineBlockStyle({ fontWeight: blockStyleFontWeight })}
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
            on:change={() => applyInlineBlockStyle({ fontStyle: blockStyleFontStyle })}
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
            on:change={() => applyInlineBlockStyle({ color: blockStyleColor })}
          />
          <span>背景色</span>
          <input
            type="text"
            placeholder="#ffffff"
            bind:value={blockStyleBackground}
            disabled={inlineEditLocked}
            on:change={() => applyInlineBlockStyle({ background: blockStyleBackground })}
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
              on:click={() => {
                blockEditCmd = blockDialogInput.trim()
                inlinePanelTab = 'rewrite'
              }}
            >
              同步到改写指令
            </button>
            <button class="btn ghost" on:click={() => openAssistantForBlock(blockDialogInput)}>发到右下角全局助手</button>
          </div>
        </div>
      {/if}

      {#if inlinePanelTab === 'rewrite'}
        <div class="inline-preset-row">
          <button class="preset-chip" on:click={() => useRewritePreset('语气更正式，保留原意')}>更正式</button>
          <button class="preset-chip" on:click={() => useRewritePreset('压缩到更简洁，控制在80字左右')}>更简洁</button>
          <button class="preset-chip" on:click={() => useRewritePreset('增加解释细节，但不要扩展事实')}>更详细</button>
          <button class="preset-chip" on:click={() => useRewritePreset('保持术语不变，仅调整表达')}>保留术语</button>
        </div>

        <div class="inline-ai-row">
          <textarea
            class="inline-instruction"
            placeholder="例如：仅重写选中段落，语气更正式，减少20%字数。"
            bind:value={blockEditCmd}
          ></textarea>
        </div>

        <div class="inline-action-row">
          <button class="btn ghost" on:click={() => openInlinePopover('assistant', inlinePopoverPlacement)}>切到改动对话</button>
          <button
            class="btn primary"
            on:click={previewSelectedBlockEdit}
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
                  on:click={() => (activeCandidateIndex = idx)}
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
                  <button class="btn primary" on:click={() => applyCandidateVersion(activeCandidateIndex)} disabled={inlineEditLocked}>采纳到正文</button>
                  <button class="btn ghost" on:click={previewSelectedBlockEdit}>重新生成</button>
                  <button class="btn ghost danger" on:click={ignoreCandidateSuggestions}>忽略建议</button>
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

  <div class={`assistant-dock ${assistantOpen ? 'open' : ''}`}>
    <button class="assistant-toggle" on:click={() => (assistantOpen = !assistantOpen)}>
      {assistantOpen ? '收起助手' : '打开助手'}
      {#if queuedGlobalInstructions.length > 0}
        <span class="assistant-queue-badge">{queuedGlobalInstructions.length}</span>
      {/if}
    </button>
    {#if assistantOpen}
      <Chat
        variant="assistant"
        on:send={(e) => handleGenerate(e.detail)}
        on:upload={handleAssistantUpload}
      />
    {/if}
  </div>

  <input
    class="hidden-input"
    type="file"
    accept="image/*"
    bind:this={uploadImageInput}
    on:change={handleInlineImageSelect}
  />

{#if $generating}
  <ProgressBar indeterminate={true} />
{/if}
</main>

<DiagramCanvas
  open={canvasOpen}
  docId={$docId}
  on:close={() => (canvasOpen = false)}
  on:insert={(e) => insertDiagramIntoDoc(e.detail.spec)}
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
    background:
      radial-gradient(700px 360px at 15% 10%, rgba(94, 175, 255, 0.12), transparent 60%),
      radial-gradient(520px 280px at 85% 12%, rgba(56, 230, 255, 0.14), transparent 60%),
      linear-gradient(180deg, #f6f9ff 0%, #eef3fb 50%, #f3f7ff 100%);
    color: #0f172a;
    font-family: "HarmonyOS Sans SC", "MiSans", "Noto Sans SC", "Source Han Sans SC", "Segoe UI", sans-serif;
  }

  :global(body)::before {
    content: "";
    position: fixed;
    inset: 0;
    pointer-events: none;
    background:
      repeating-linear-gradient(120deg, rgba(15, 23, 42, 0.04) 0, rgba(15, 23, 42, 0.04) 1px, transparent 1px, transparent 32px),
      repeating-linear-gradient(200deg, rgba(56, 189, 248, 0.06) 0, rgba(56, 189, 248, 0.06) 1px, transparent 1px, transparent 36px);
    opacity: 0.4;
    z-index: 0;
  }

  .app {
    --panel-bg: rgba(255, 255, 255, 0.88);
    --panel-border: rgba(148, 163, 184, 0.22);
    --panel-shadow: 0 18px 40px rgba(15, 23, 42, 0.12);
    --accent: #2563eb;
    --accent-weak: rgba(37, 99, 235, 0.12);
    --text-muted: rgba(51, 65, 85, 0.72);
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
    border-bottom: 1px solid rgba(148, 163, 184, 0.18);
    backdrop-filter: blur(12px);
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
    color: #0f172a;
    background: linear-gradient(135deg, rgba(59, 130, 246, 0.9), rgba(14, 165, 233, 0.9));
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

  .status-chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 10px;
    border-radius: 999px;
    background: rgba(15, 23, 42, 0.06);
    font-size: 12px;
    color: #0f172a;
  }

  .status-chip.light {
    background: rgba(37, 99, 235, 0.08);
    color: #1e40af;
  }

  .status-chip .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #22c55e;
    box-shadow: 0 0 0 4px rgba(34, 197, 94, 0.18);
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
    box-shadow: 0 10px 20px rgba(15, 23, 42, 0.08);
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
    background: rgba(148, 163, 184, 0.36);
    margin: 0 2px;
  }

  .tool-btn {
    min-width: 34px;
    height: 32px;
    border-radius: 10px;
    border: 1px solid rgba(148, 163, 184, 0.3);
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
    background: linear-gradient(135deg, rgba(219, 234, 254, 0.95), rgba(186, 230, 253, 0.9));
    color: #1d4ed8;
    box-shadow: 0 8px 18px rgba(37, 99, 235, 0.2);
  }

  .tool-btn:disabled {
    opacity: 0.38;
    cursor: not-allowed;
    box-shadow: none;
    transform: none;
    border-color: rgba(148, 163, 184, 0.24);
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
    color: #0f172a;
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
    color: #0f172a;
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
    border: 1px solid rgba(148, 163, 184, 0.25);
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
    color: #0f172a;
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
    color: #0f172a;
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
    border-color: rgba(16, 185, 129, 0.5);
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
    background: rgba(148, 163, 184, 0.2);
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
    color: #0f172a;
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
    border: 1px dashed rgba(148, 163, 184, 0.3);
    display: flex;
    justify-content: space-between;
    gap: 8px;
  }

  .version-minor.current {
    border-color: rgba(16, 185, 129, 0.5);
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
    background: rgba(15, 23, 42, 0.06);
    padding: 10px;
    border-radius: 12px;
    font-size: 11px;
    white-space: pre-wrap;
    max-height: 160px;
    overflow: auto;
  }

  .block-preview {
    font-size: 12px;
    color: #0f172a;
    background: rgba(15, 23, 42, 0.04);
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
    color: #ef4444;
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
    box-shadow: 0 16px 30px rgba(15, 23, 42, 0.22);
    padding: 8px 10px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }

  .inline-selection-meta {
    font-size: 12px;
    color: #0f172a;
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
    border: 1px solid rgba(148, 163, 184, 0.38);
    background: rgba(248, 250, 252, 0.95);
    color: #0f172a;
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
    background: rgba(226, 232, 240, 0.7);
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
    box-shadow: 0 24px 48px rgba(15, 23, 42, 0.28);
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

  .assistant-dock {
    position: fixed;
    right: 28px;
    bottom: 24px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    z-index: 5;
    align-items: flex-end;
  }

  .assistant-toggle {
    border: none;
    background: linear-gradient(135deg, #2563eb, #38bdf8);
    color: #fff;
    padding: 10px 16px;
    border-radius: 999px;
    font-size: 12px;
    cursor: pointer;
    box-shadow: 0 12px 20px rgba(37, 99, 235, 0.3);
    display: inline-flex;
    align-items: center;
    gap: 8px;
  }

  .assistant-queue-badge {
    min-width: 18px;
    height: 18px;
    border-radius: 999px;
    background: rgba(15, 23, 42, 0.8);
    color: #fff;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    padding: 0 5px;
  }

  .btn {
    border: none;
    background: rgba(15, 23, 42, 0.08);
    color: #0f172a;
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
    background: rgba(15, 23, 42, 0.06);
  }

  .btn:hover,
  .tool-btn:hover:not(:disabled) {
    transform: translateY(-1px);
  }

  .icon-btn {
    border: none;
    background: rgba(15, 23, 42, 0.08);
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
    .assistant-dock {
      right: 12px;
      bottom: 12px;
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
</style>
