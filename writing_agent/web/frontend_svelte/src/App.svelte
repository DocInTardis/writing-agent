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
  let lastSavedText = ''
  let lastSavedDocIr: Record<string, unknown> | null = null
  let showDocList = false
  let showCitations = false
  let showVersions = false
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
  let selectedBlockText = ''
  let blockEditCmd = ''
  let blockEditBusy = false
  let blockEditError = ''
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

  function pushWritingDelta(deltaText: string) {
    const chunk = String(deltaText || '')
    if (!chunk.trim()) return
    if (chunk.length < 8 && !/[\w\u4e00-\u9fa5]/.test(chunk)) return
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
        docIr.set(doc)
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
    sourceText.set(txt)
    if (finalDoc && typeof finalDoc === 'object') {
      docIr.set(finalDoc)
      docIrDirty.set(false)
    } else {
      const doc = textToDocIr(txt)
      if (doc) {
        docIr.set(doc)
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
    let i = 0
    while (i < text.length) {
      if (token !== typingToken) return
      const next = text.slice(i, i + chunkSize)
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
      docIr.set(opts.finalDocIr)
      docIrDirty.set(false)
    } else {
      scheduleDocIrRefresh(text, true)
    }
    typingActive = false
  }

  function ensureSkeletonInText(text: string, title: string, sections: string[]) {
    let t = String(text || '').replace(/\r/g, '')
    if (!/^#\s+/m.test(t)) {
      t = `# ${title || '自动生成文档'}\n\n` + t.trimStart()
    }
    for (const s of sections || []) {
      const name = String(s || '').trim()
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

  function handleBlockEdit(event: CustomEvent) {
    const payload = event.detail || {}
    if (payload.docIr && typeof payload.docIr === 'object') {
      docIr.set(payload.docIr as Record<string, unknown>)
      docIrDirty.set(false)
      lastSavedDocIr = payload.docIr as Record<string, unknown>
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

  function handleBlockSelect(event: CustomEvent) {
    const detail = event.detail || {}
    selectedBlockId = String(detail.blockId || '')
    selectedBlockText = String(detail.text || '')
    blockEditError = ''
  }

  function applyDocIrSnapshot(nextDoc: Record<string, unknown>) {
    docIr.set(nextDoc)
    docIrDirty.set(false)
    lastSavedDocIr = nextDoc
    const nextText = docIrToMarkdown(nextDoc) || ''
    sourceText.set(nextText)
    lastSavedText = nextText
  }

  async function applySelectedBlockEdit() {
    if (!$docId || !selectedBlockId) return
    const instruction = blockEditCmd.trim()
    if (!instruction) return
    blockEditBusy = true
    blockEditError = ''
    try {
      const payload: Record<string, unknown> = { block_id: selectedBlockId, instruction }
      if ($docIr) payload.doc_ir = $docIr
      const resp = await fetch(`/api/doc/${$docId}/block-edit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      if (!resp.ok) throw new Error(await resp.text())
      const data = await resp.json()
      if (data.doc_ir && typeof data.doc_ir === 'object') {
        applyDocIrSnapshot(data.doc_ir as Record<string, unknown>)
      } else if (data.text) {
        const txt = String(data.text || '')
        sourceText.set(txt)
        lastSavedText = txt
      }
      blockEditCmd = ''
      pushToast('已应用修改', 'ok')
    } catch (err) {
      blockEditError = err instanceof Error ? err.message : '修改失败'
    } finally {
      blockEditBusy = false
    }
  }

  function insertDiagramIntoDoc(spec: Record<string, unknown>) {
    if (!spec || typeof spec !== 'object') return
    const doc = $docIr
    if (!doc || typeof doc !== 'object') return
    const sections = Array.isArray((doc as any).sections) ? (doc as any).sections : []
    if (!sections.length) return
    const first = sections[0]
    const blocks = Array.isArray(first.blocks) ? first.blocks.slice() : []
    const figureBlock = { id: Math.random().toString(36).slice(2), type: 'figure', figure: spec }
    blocks.push(figureBlock)
    const nextFirst = { ...first, blocks }
    const nextSections = sections.slice()
    nextSections[0] = nextFirst
    const nextDoc = { ...doc, sections: nextSections }
    applyDocIrSnapshot(nextDoc as Record<string, unknown>)
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
      const merged = t + (t.endsWith('\n') ? '' : '\n') + delta
      return normalizeDocTextSpacing(merged)
    }
    const start = m.index + m[0].length
    const after = t.slice(start)
    const nextHeadingOffset = after.search(/^##\s+/m)
    const insertPos = nextHeadingOffset >= 0 ? start + nextHeadingOffset : t.length
    const prefix = t.slice(0, insertPos)
    const suffix = t.slice(insertPos)
    const prefixClean = prefix.replace(/\s+$/, '')
    const combined = prefixClean + `\n\n${deltaRaw}\n` + suffix
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
    // Avoid blocking UI with skeleton during generation.
    try {
      const resp = await fetch(`/api/doc/${id}`)
      if (!resp.ok) throw new Error(await resp.text())
      const data = await resp.json()
      sourceText.set(String(data.text || ''))
      lastSavedText = String(data.text || '')
      if (data.doc_ir && typeof data.doc_ir === 'object') {
        docIr.set(data.doc_ir as Record<string, unknown>)
        docIrDirty.set(false)
        lastSavedDocIr = data.doc_ir as Record<string, unknown>
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
              docIr.set(data.doc_ir as Record<string, unknown>)
              docIrDirty.set(false)
              lastSavedDocIr = data.doc_ir as Record<string, unknown>
            }
            if (data.text) {
              const txt = String(data.text || '')
              sourceText.set(txt)
              lastSavedText = txt
            } else {
              lastSavedText = $sourceText
            }
            pushToast('已保存', 'ok')
            return
          }
        } else if (ops && ops.length === 0) {
          lastSavedText = $sourceText
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


  function exportPdf() {
    if (!$docId) return
    pushToast('正在生成PDF...', 'info')
    window.location.href = `/download/${$docId}.pdf`
  }

  function handleDocSelect(selectedDocId: string) {
    showDocList = false
    window.location.href = `/workbench/${selectedDocId}`
  }

  function exportDocx() {
    if (!$docId) return
    pushToast('正在生成Word文档...', 'info')
    window.location.href = `/download/${$docId}.docx`
  }

  function toggleDarkMode() {
    darkMode.update(v => !v)
    document.body.classList.toggle('dark', !$darkMode)
  }

  async function handleGenerate(text: string) {
    if ($generating) return
    const inst = String(text || '').trim()
    if (!inst) return
    if (!$docId) {
      const reason = '缺少文档ID，请刷新或从 /workbench/{id} 进入'
      docStatus.set(`已中止: ${reason}`)
      pushThought('中止', reason, new Date().toLocaleTimeString())
      pushToast(reason, 'info')
      return
    }
    typingToken += 1
    resetStreamTyping()
    appendChat('user', inst)
    instruction.set('')
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
    
    try {
      await streamSsePost(
        `/api/doc/${$docId}/generate/stream`,
        { instruction: inst, text: $sourceText || '' },
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
            const sections = Array.isArray(data.sections) ? data.sections : []
            pushThought('大纲', `标题：${title}；章节：${sections.join(' / ')}`, formatElapsed())
            const nextText = ensureSkeletonInText($sourceText, title, sections)
            sourceText.set(nextText)
            scheduleDocIrRefresh(nextText)
            return
          }
          if (event === 'section') {
            if (String(data.phase || '') === 'delta') {
              sawSectionDelta = true
              const blockId = String(data.block_id || '')
              const section = String(data.section || '')
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
            const section = String(data.section || '')
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
              body: JSON.stringify({ instruction: inst, text: $sourceText || '' })
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
      generating.set(false)
      isLoading.set(false)
      streamingLive = false
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
        docIr.set(data.doc_ir as Record<string, unknown>)
        docIrDirty.set(false)
      }
    } catch {}
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
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    if (!$docId) {
      const id = readDocId()
      if (id) {
        docId.set(id)
        loadDoc().then(() => Promise.all([loadChat(), loadThoughts()])).catch(() => {})
      }
    }
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      if (autoSaveTimer) clearTimeout(autoSaveTimer)
    }
  })
</script>

<main class="app" class:dark={$darkMode}>
  <header class="topbar">
    <div class="brand">
      <div class="logo">IR</div>
      <div class="brand-text">
        <div class="brand-title">??????</div>
        <div class="brand-sub">Doc IR ? ?????</div>
      </div>
    </div>
    <nav class="menu">
      <button class="menu-item">??</button>
      <button class="menu-item">??</button>
      <button class="menu-item">??</button>
      <button class="menu-item">??</button>
      <button class="menu-item">??</button>
    </nav>
    <div class="top-actions">
      <div class="status-chip">
        <span class="dot"></span>
        <span>{$docStatus || '???'}</span>
      </div>
      <div class="status-chip light">?? {$wordCount}</div>
      <button class="btn ghost" on:click={saveDoc}>??</button>
      <button class="btn ghost" on:click={exportDocx}>?? Word</button>
      <button class="btn ghost" on:click={exportPdf}>?? PDF</button>
      <Settings />
    </div>
  </header>

  <div class="workspace">
    <aside class="nav-rail">
      <button class="nav-btn active" title="??">
        <span>??</span>
      </button>
      <button class="nav-btn" title="??" on:click={() => (canvasOpen = true)}>
        <span>??</span>
      </button>
      <button class="nav-btn" title="??" on:click={() => (showCitations = true)}>
        <span>??</span>
      </button>
      <button class="nav-btn" title="???" on:click={() => (showDocList = true)}>
        <span>???</span>
      </button>
    </aside>

    <section class="doc-area">
      <div class="doc-toolbar">
        <div class="tool-group">
          <button class="tool-btn" on:click={() => runEditorCommand('bold')}>B</button>
          <button class="tool-btn" on:click={() => runEditorCommand('italic')}>I</button>
          <button class="tool-btn" on:click={() => runEditorCommand('underline')}>U</button>
          <button class="tool-btn" on:click={() => runEditorCommand('heading1')}>H1</button>
          <button class="tool-btn" on:click={() => runEditorCommand('heading2')}>H2</button>
          <button class="tool-btn" on:click={() => runEditorCommand('list-bullet')}>?</button>
          <button class="tool-btn" on:click={() => runEditorCommand('list-number')}>1.</button>
          <button class="tool-btn" on:click={() => runEditorCommand('table')}>??</button>
          <button class="tool-btn" on:click={() => runEditorCommand('image')}>??</button>
        </div>
        <div class="tool-group right">
          <button class="btn ghost" on:click={() => handleGenerate($instruction)} disabled={$generating}>??</button>
          <button class="btn ghost" on:click={handleStop} disabled={!$generating}>??</button>
        </div>
      </div>

      {#if $generating && progress.total > 0}
        <div class="generation-banner">
          ????? {progress.current}/{progress.total} ??{progress.percent}%????? {Math.ceil(progress.etaS / 60)} ? {progress.etaS % 60} ?
        </div>
      {/if}

      {#if sectionFailures.length > 0}
        <section class="section-failures">
          <div class="panel-title">????</div>
          {#each sectionFailures as f}
            <div class="failure-row">
              <span>{f.section}</span>
              <button class="btn ghost" on:click={() => retrySection(f.section)}>??</button>
            </div>
          {/each}
        </section>
      {/if}

      <div class="doc-stage">
        {#if $isLoading}
          <LoadingSkeleton />
        {:else}
          <Editor showToolbar={false} paper={true} on:blockedit={handleBlockEdit} on:blockselect={handleBlockSelect} />
        {/if}
      </div>
    </section>

    <aside class="side-panel">
      <div class="panel-card version-panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">???</div>
            <div class="panel-sub">???? ? ????</div>
          </div>
          <button class="icon-btn" on:click={loadVersionLog} title="??">?</button>
        </div>
        <div class="major-commit">
          <input
            class="version-input"
            placeholder="????????"
            bind:value={versionMessage}
          />
          <button class="btn primary" on:click={commitVersion}>??</button>
        </div>
        {#if versionLoading}
          <div class="panel-empty">???...</div>
        {:else if versionError}
          <div class="panel-empty">{versionError}</div>
        {:else if versionGroups.length === 0}
          <div class="panel-empty">????</div>
        {:else}
          <div class="version-groups">
            {#each versionGroups as group}
              <div class="version-group">
                <div class={`version-major ${group.major?.is_current ? 'current' : ''}`}>
                  <div class="version-title">
                    <span>{group.major?.message || '????'}</span>
                    <span class={`badge ${group.major?.kind === 'major' ? 'major' : 'minor'}`}>
                      {group.major?.kind === 'major' ? '??' : '??'}
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
                    <button class="btn ghost" on:click={() => checkoutVersion(group.major?.version_id)} disabled={group.major?.is_current}>??</button>
                    <button class="btn ghost" on:click={() => compareWithCurrent(group.major?.version_id)} disabled={group.major?.is_current}>??</button>
                  </div>
                </div>
                {#if group.minors && group.minors.length}
                  <div class="version-minors">
                    {#each group.minors as v}
                      <div class={`version-minor ${v.is_current ? 'current' : ''}`}>
                        <div>
                          <div class="minor-title">{v.message || '????'}</div>
                          {#if formatVersionSummary(v.summary)}
                            <div class="version-summary">{formatVersionSummary(v.summary)}</div>
                          {/if}
                          <div class="minor-meta">{formatVersionTime(v.timestamp)}</div>
                        </div>
                        <div class="minor-actions">
                          <button class="btn ghost" on:click={() => checkoutVersion(v.version_id)} disabled={v.is_current}>??</button>
                          <button class="btn ghost" on:click={() => compareWithCurrent(v.version_id)} disabled={v.is_current}>??</button>
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
          <div class="panel-sub">????</div>
          <pre>{versionDiff || '?????????'}</pre>
        </div>
      </div>

      <div class="panel-card block-panel">
        <div class="panel-header">
          <div>
            <div class="panel-title">??????</div>
            <div class="panel-sub">????????</div>
          </div>
        </div>
        {#if selectedBlockId}
          <div class="block-preview">{selectedBlockText || '?????'}</div>
          <input
            class="block-input"
            placeholder="??????????????"
            bind:value={blockEditCmd}
          />
          <div class="block-actions">
            <button class="btn primary" on:click={applySelectedBlockEdit} disabled={blockEditBusy || !blockEditCmd.trim()}>
              {blockEditBusy ? '????' : '????'}
            </button>
            <button class="btn ghost" on:click={() => { blockEditCmd = ''; }}>??</button>
          </div>
          {#if blockEditError}
            <div class="block-error">{blockEditError}</div>
          {/if}
        {:else}
          <div class="panel-empty">???????????????????? AI ????</div>
        {/if}
      </div>
    </aside>
  </div>

  <div class={`assistant-dock ${assistantOpen ? 'open' : ''}`}>
    <button class="assistant-toggle" on:click={() => (assistantOpen = !assistantOpen)}>
      {assistantOpen ? '????' : '????'}
    </button>
    {#if assistantOpen}
      <Chat variant="assistant" on:send={(e) => handleGenerate(e.detail)} />
    {/if}
  </div>

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

  .workspace {
    flex: 1;
    display: grid;
    grid-template-columns: 74px minmax(0, 1fr) 340px;
    gap: 20px;
    padding: 20px 28px 100px;
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
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px 16px;
    background: var(--panel-bg);
    border: 1px solid var(--panel-border);
    border-radius: 16px;
    box-shadow: var(--panel-shadow);
  }

  .tool-group {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }

  .tool-group.right {
    justify-content: flex-end;
  }

  .tool-btn {
    width: 34px;
    height: 32px;
    border-radius: 10px;
    border: 1px solid rgba(148, 163, 184, 0.3);
    background: #fff;
    font-weight: 600;
    cursor: pointer;
    transition: border 0.2s ease, box-shadow 0.2s ease;
  }

  .tool-btn:hover {
    border-color: rgba(37, 99, 235, 0.6);
    box-shadow: 0 6px 14px rgba(37, 99, 235, 0.15);
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
    padding: 18px;
    box-shadow: var(--panel-shadow);
    min-height: 420px;
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
  .tool-btn:hover {
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
  }
</style>

