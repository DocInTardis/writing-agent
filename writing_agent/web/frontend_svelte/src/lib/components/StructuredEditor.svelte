<script lang="ts">
  import { get } from 'svelte/store'
  import { onDestroy, onMount, untrack } from 'svelte'
  import type { Editor, JSONContent } from '@tiptap/core'
  import { NodeSelection, TextSelection } from '@tiptap/pm/state'
  import { CellSelection } from '@tiptap/pm/tables'

  import {
    docId,
    docIr,
    docIrDirty,
    documentV3,
    editorCommand,
    sourceText
  } from '../stores'
  import { createNodeCommand, createShortcutCommand, createUserCommand, executeDocumentCommand, type DocumentCommand } from '../editor-v3/commands'
  import {
    createEditorKernel,
    applyPaginationLayout,
    documentV3ToTiptap,
    documentV3ToText,
    plainTextToTiptapContent,
    selectBlock,
    selectedBlocks,
    styleSheetForDocument,
    tiptapToDocumentV3
  } from '../editor-v3/kernel'
  import { DEFAULT_NUMBERING, DEFAULT_STYLES, cloneJson, isDocumentV3, migrateLegacyDocIr, refreshDocumentFields, resolvedStyleProperties, type DocumentV3, type StyleDefinition, type StyleProperties } from '../editor-v3/model'
  import { documentV3ToMarkdown, replaceDocumentContentFromMarkdown } from '../editor-v3/markdown'
  import { addDocumentComment, buildRevision, resolveDocumentComment, settleRevision, type DocumentRevision } from '../editor-v3/revisions'
  import { paginateDocumentV3 } from '../engine/documentEngine'
  import type { EditorCommand } from '../types'

  let {
    paper = true,
    lockEditing = false,
    onblockedit,
    onblockselect,
    onblockai,
    ontextai,
    onblockdrag,
    ontoolbarstate
  }: {
    showToolbar?: boolean
    paper?: boolean
    lockEditing?: boolean
    onblockedit?: (payload: any) => void
    onblockselect?: (payload: any) => void
    onblockai?: () => void
    ontextai?: (payload: { text: string; from: number; to: number }) => void
    onblockdrag?: (active: boolean) => void
    ontoolbarstate?: (state: any) => void
  } = $props()

  let host: HTMLDivElement
  let editor: Editor | null = null
  // Keep the canonical document reactive by reference but never wrap the
  // JSON tree in a deep Proxy. ProseMirror updates and exporters expect a
  // plain serializable object, and Svelte's Proxy cannot be cloned safely.
  let activeDocument = $state.raw<DocumentV3 | null>(null)
  let styleElement: HTMLStyleElement | null = null
  let unsubscribeCommand = () => {}
  let unsubscribeDocIr = () => {}
  let mountedLegacyRef: Record<string, unknown> | null = null
  let clipboardError = $state('')
  let clipboardErrorTimer: ReturnType<typeof setTimeout> | null = null
  let shell: HTMLDivElement
  let blockHandleVisible = $state(false)
  let blockHandleTop = $state(0)
  let blockHandleLeft = $state(0)
  let activeBlockId = $state('')
  let blockSelectionAnchorId = ''
  let blockSelectionActive = $state(false)
  let selectedBlockIds = $state<string[]>([])
  let selectedBlocksCollapsed = $state(false)
  let dragTargetId = $state('')
  let dragPlacement = $state<'before' | 'after'>('before')
  let dragIndicatorTop = $state(0)
  let blockPointerId: number | null = null
  let blockPointerStartY = 0
  let blockPointerDragging = false
  let blockDragClientX = 0
  let blockDragClientY = 0
  let blockDragScrollElement: HTMLElement | null = null
  let blockDragScrollFrame: number | null = null
  let suppressHandleClick = false
  let slashQuery = $state('')
  let slashMenuVisible = $state(false)
  let slashMenuTop = $state(0)
  let slashMenuLeft = $state(0)
  let slashMenuIndex = $state(0)
  let paginationTimer: ReturnType<typeof setTimeout> | null = null
  let paginationRevision = 0
  let pageCount = $state(1)
  let paginationState = $state<'loading' | 'ready' | 'unavailable' | 'error'>('loading')
  let composingText = false
  let paginationPendingAfterComposition = false
  let resizeObserver: ResizeObserver | null = null
  let observedShellWidth = 0
  let findPanelVisible = $state(false)
  let findQuery = $state('')
  let replaceText = $state('')
  let findStatus = $state('')
  let outlineVisible = $state(false)
  let outlineTab: 'headings' | 'search' = $state('headings')
  let outlineQuery = $state('')
  let zoomPercent = $state(100)
  let selectionToolbarVisible = $state(false)
  let selectionToolbarTop = $state(0)
  let selectionToolbarLeft = $state(0)
  let proofPanelVisible = $state(false)
  let proofIssues = $state<Array<{ id: string; message: string; excerpt: string; from: number; to: number }>>([])
  let markdownInput: HTMLInputElement
  let wordInput: HTMLInputElement
  let imageInput: HTMLInputElement
  let markdownExportVisible = $state(false)
  let markdownExportText = $state('')
  let markdownExportWarnings = $state<string[]>([])
  let markdownNotice = $state('')
  let shortcutPanelVisible = $state(false)
  let styleManagerVisible = $state(false)
  let managedStyleId = $state('normal')
  let managedStyleName = $state('正文')
  let managedBasedOn = $state('')
  let managedNextStyle = $state('normal')
  let managedFontFamily = $state('')
  let managedFontSizePt: number | '' = $state('')
  type InheritedToggle = 'inherit' | 'on' | 'off'
  let managedBold: InheritedToggle = $state('inherit')
  let managedItalic: InheritedToggle = $state('inherit')
  let managedUnderline: InheritedToggle = $state('inherit')
  let managedColor = $state('')
  let managedBackgroundColor = $state('')
  let managedLetterSpacingPt: number | '' = $state('')
  let managedTextTransform: '' | 'none' | 'uppercase' | 'lowercase' | 'capitalize' = $state('')
  let managedAlignment = $state<'' | 'left' | 'center' | 'right' | 'justify'>('')
  let managedLineSpacing: number | '' = $state('')
  let managedFirstLineIndentEm: number | '' = $state('')
  let managedLeftIndentEm: number | '' = $state('')
  let managedRightIndentEm: number | '' = $state('')
  let managedSpaceBeforePt: number | '' = $state('')
  let managedSpaceAfterPt: number | '' = $state('')
  let managedOutlineLevel: number | '' = $state('')
  let managedKeepWithNext: InheritedToggle = $state('inherit')
  let managedKeepLinesTogether: InheritedToggle = $state('inherit')
  let managedPageBreakBefore: InheritedToggle = $state('inherit')
  let managedBorderColor = $state('')
  let managedBorderWidthPt: number | '' = $state('')
  let managedBorderStyle: '' | 'none' | 'solid' | 'dashed' | 'double' = $state('')
  let managedShadingColor = $state('')
  let managedTabStops = $state('')
  let managedNumberingId = $state('')
  let managedNumberingLevel: number | '' = $state('')
  let creatingStyle = $state(false)
  let styleManagerNotice = $state('')
  let styleRevision = $state(0)
  let referenceDialog = $state<'link' | 'equation' | 'blockEquation' | 'footnote' | 'endnote' | 'citation' | 'crossReference' | ''>('')
  let referenceHref = $state('https://')
  let referenceTitle = $state('')
  let referenceLatex = $state('')
  let referenceNoteText = $state('')
  let referenceTargetId = $state('')
  let referenceCitationId = $state('')
  let figureDialogVisible = $state(false)
  let figureCaption = $state('')
  let figureAlt = $state('')
  let figureWidthPercent = $state(100)
  let figureAlignment = $state<'left' | 'center' | 'right'>('center')
  let figureWrap = $state<'inline' | 'square'>('inline')
  let figureCrop = $state<'none' | 'fill' | 'cover'>('none')
  let figureSourceSpec: Record<string, unknown> | null = $state.raw(null)
  let figureEditInstruction = $state('')
  let figureRegenerating = $state(false)
  let objectNotice = $state('')
  let reviewPanelVisible = $state(false)
  let trackChanges = $state(false)
  let commentDraft = $state('')
  let revisionTimer: ReturnType<typeof setTimeout> | null = null
  let revisionBatchBefore: DocumentV3 | null = null
  let suppressRevisionCapture = false
  let aiProposals = $state<Array<{ command: DocumentCommand; selection: { from: number; to: number } }>>([])
  let appliedEditable: boolean | null = null

  function handleAiProposal(event: Event) {
    const detail = (event as CustomEvent<{ command?: DocumentCommand; selection?: { from: number; to: number } }>).detail
    if (!detail?.command || !detail.selection) return
    aiProposals = [...aiProposals.filter((item) => item.command.id !== detail.command?.id), { command: detail.command, selection: detail.selection }]
    reviewPanelVisible = true
  }

  function settleAiProposal(commandId: string, accept: boolean) {
    const proposal = aiProposals.find((item) => item.command.id === commandId)
    aiProposals = aiProposals.filter((item) => item.command.id !== commandId)
    if (!accept || !proposal || !editor) return
    editor.chain().focus().setTextSelection(proposal.selection).run()
    executeDocumentCommand(editor, { ...proposal.command, reviewMode: 'direct' })
  }

  function flushTrackedRevision() {
    if (revisionTimer) clearTimeout(revisionTimer)
    revisionTimer = null
    if (!revisionBatchBefore || !activeDocument) return
    const revision = buildRevision(revisionBatchBefore, activeDocument)
    revisionBatchBefore = null
    if (!revision) return
    activeDocument.revisions = [...activeDocument.revisions, revision]
    documentV3.set(activeDocument)
    docIrDirty.set(true)
  }

  function queueTrackedRevision(before: DocumentV3) {
    revisionBatchBefore ||= cloneJson(before)
    if (revisionTimer) clearTimeout(revisionTimer)
    revisionTimer = setTimeout(flushTrackedRevision, 700)
  }

  function addCommentFromSelection() {
    if (!editor || !activeDocument) return
    const text = commentDraft.trim()
    if (!text) return
    const blocks = selectedBlocks(editor)
    const { from, to } = editor.state.selection
    const quote = editor.state.doc.textBetween(from, to, '\n', '\n')
    activeDocument = addDocumentComment(activeDocument, blocks.map((block) => block.id), text, { from, to, quote })
    documentV3.set(activeDocument)
    docIrDirty.set(true)
    commentDraft = ''
    reviewPanelVisible = true
  }

  function settleComment(commentId: string, resolved: boolean) {
    if (!activeDocument) return
    activeDocument = resolveDocumentComment(activeDocument, commentId, resolved)
    documentV3.set(activeDocument)
    docIrDirty.set(true)
  }

  function settleTrackedRevision(revisionId: string, accept: boolean) {
    if (!activeDocument) return
    flushTrackedRevision()
    suppressRevisionCapture = true
    const next = settleRevision(activeDocument, revisionId, accept)
    loadDocument(next)
    suppressRevisionCapture = false
    docIrDirty.set(true)
  }

  function documentRevisions(): DocumentRevision[] {
    return (activeDocument?.revisions || []) as DocumentRevision[]
  }

  async function importImageFile(event: Event) {
    const input = event.currentTarget as HTMLInputElement
    const file = input.files?.[0]
    input.value = ''
    if (!file || !editor) return
    if (!file.type.startsWith('image/')) {
      objectNotice = '请选择图片文件。'
      return
    }
    if (file.size > 10 * 1024 * 1024) {
      objectNotice = '图片不能超过 10 MiB；请先压缩后再插入。'
      return
    }
    const src = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(String(reader.result || ''))
      reader.onerror = () => reject(reader.error || new Error('读取图片失败'))
      reader.readAsDataURL(file)
    }).catch(() => '')
    if (!src) {
      objectNotice = '图片读取失败。'
      return
    }
    const result = executeDocumentCommand(editor, createUserCommand('insert_figure', {
      src,
      mimeType: file.type,
      fileName: file.name,
      alt: file.name.replace(/\.[^.]+$/, ''),
      caption: '',
      widthPercent: 100,
      alignment: 'center',
      wrap: 'inline'
    }))
    objectNotice = result.ok ? `已插入 ${file.name}` : '图片插入失败。'
  }

  function openFigureEditor() {
    if (!editor || !editor.isActive('figure')) return false
    const payload = editor.getAttributes('figure').payload as Record<string, unknown> | undefined
    figureCaption = String(payload?.caption || '')
    figureAlt = String(payload?.alt || '')
    figureWidthPercent = Math.max(10, Math.min(100, Number(payload?.widthPercent || 100)))
    figureAlignment = (['left', 'center', 'right'].includes(String(payload?.alignment)) ? payload?.alignment : 'center') as typeof figureAlignment
    figureWrap = (['inline', 'square'].includes(String(payload?.wrap)) ? payload?.wrap : 'inline') as typeof figureWrap
    figureCrop = (['none', 'fill', 'cover'].includes(String(payload?.crop)) ? payload?.crop : 'none') as typeof figureCrop
    figureSourceSpec = payload?.editableSource && payload.spec && typeof payload.spec === 'object'
      ? cloneJson(payload.spec as Record<string, unknown>)
      : null
    figureEditInstruction = ''
    figureDialogVisible = true
    return true
  }

  async function applyFigureSettings() {
    if (!editor) return
    const result = executeDocumentCommand(editor, createUserCommand('update_figure', {
      caption: figureCaption,
      alt: figureAlt,
      widthPercent: figureWidthPercent,
      alignment: figureAlignment,
      wrap: figureWrap,
      crop: figureCrop
    }))
    if (result.ok) figureDialogVisible = false
  }

  async function regenerateFigureFromInstruction() {
    if (!editor || !figureSourceSpec || figureRegenerating) return
    const instruction = figureEditInstruction.trim()
    const currentDocId = get(docId)
    if (!instruction || !currentDocId) return
    figureRegenerating = true
    objectNotice = ''
    try {
      const kind = String(figureSourceSpec.type || 'flow')
      const prompt = `修改现有图表：${instruction}\n当前图表结构：${JSON.stringify(figureSourceSpec).slice(0, 2400)}`
      const response = await fetch(`/api/doc/${currentDocId}/diagram/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, kind })
      })
      if (!response.ok) throw new Error(await response.text())
      const payload = await response.json()
      const nextSpec = payload?.spec
      if (!nextSpec || typeof nextSpec !== 'object') throw new Error('没有返回可编辑的图表结构')
      const render = await fetch('/api/figure/render', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ spec: nextSpec })
      })
      if (!render.ok) throw new Error(await render.text())
      const rendered = await render.json()
      const svg = String(rendered.svg || '')
      if (!svg) throw new Error('图表渲染结果为空')
      const result = executeDocumentCommand(editor, createUserCommand('update_figure', {
        spec: nextSpec,
        svg,
        src: `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`,
        editableSource: true
      }))
      if (!result.ok) throw new Error('图表更新失败')
      figureSourceSpec = cloneJson(nextSpec as Record<string, unknown>)
      figureEditInstruction = ''
      objectNotice = '图表已更新，可继续输入要求修改。'
    } catch (error) {
      objectNotice = `图表修改失败：${error instanceof Error ? error.message : '未知错误'}`
    } finally {
      figureRegenerating = false
    }
  }

  function openReferenceDialog(kind: typeof referenceDialog) {
    if (!editor || !kind) return
    referenceDialog = kind
    if (kind === 'link') {
      const attrs = editor.getAttributes('link')
      referenceHref = String(attrs.href || 'https://')
      referenceTitle = String(attrs.title || '')
    } else if (kind === 'equation') referenceLatex = ''
    else if (kind === 'blockEquation') referenceLatex = editor.isActive('equationBlock') ? String((editor.getAttributes('equationBlock').payload as Record<string, unknown> | undefined)?.latex || '') : ''
    else if (kind === 'footnote' || kind === 'endnote') referenceNoteText = ''
    else if (kind === 'citation') referenceCitationId = citationEntries()[0]?.id || ''
    else if (kind === 'crossReference') referenceTargetId = outlineHeadings()[0]?.id || ''
  }

  function applyReferenceDialog() {
    if (!editor || !referenceDialog) return
    if (referenceDialog === 'link') {
      const result = executeDocumentCommand(editor, createUserCommand('set_link', { href: referenceHref, title: referenceTitle }))
      if (!result.ok) return
    } else if (referenceDialog === 'equation') {
      const result = executeDocumentCommand(editor, createUserCommand('insert_inline_equation', { latex: referenceLatex }))
      if (!result.ok) return
    } else if (referenceDialog === 'blockEquation') {
      const type = editor.isActive('equationBlock') ? 'update_equation' : 'insert_equation'
      const result = executeDocumentCommand(editor, createUserCommand(type, { latex: referenceLatex }))
      if (!result.ok) return
    } else if (referenceDialog === 'footnote' || referenceDialog === 'endnote') {
      const text = referenceNoteText.trim()
      if (!text || !activeDocument) return
      const noteKind = referenceDialog === 'footnote' ? 'footnotes' : 'endnotes'
      const noteId = `${referenceDialog}_${crypto.randomUUID().replace(/-/g, '')}`
      const notes = activeDocument.notes && typeof activeDocument.notes === 'object' ? activeDocument.notes : {}
      const items = Array.isArray(notes[noteKind]) ? [...notes[noteKind] as unknown[]] : []
      const label = String(items.length + 1)
      items.push({ id: noteId, label, text })
      activeDocument.notes = { ...notes, [noteKind]: items }
      const result = executeDocumentCommand(editor, createUserCommand(referenceDialog === 'footnote' ? 'insert_footnote_reference' : 'insert_endnote_reference', { noteId, label, text }))
      if (!result.ok) return
    } else if (referenceDialog === 'citation') {
      const citation = citationEntries().find((item) => item.id === referenceCitationId)
      if (!citation) return
      const result = executeDocumentCommand(editor, createUserCommand('insert_citation', { citationId: citation.id, label: citation.label, text: citation.text }))
      if (!result.ok) return
    } else if (referenceDialog === 'crossReference') {
      const target = outlineHeadings().find((heading) => heading.id === referenceTargetId)
      if (!target) return
      const result = executeDocumentCommand(editor, createUserCommand('insert_cross_reference', {
        targetId: target.id,
        targetText: target.text,
        label: target.text
      }))
      if (!result.ok) return
    }
    referenceDialog = ''
    emitSelection()
  }

  function citationEntries() {
    const raw = activeDocument?.citations || {}
    return Object.entries(raw).map(([id, value]) => {
      const item = value && typeof value === 'object' ? value as Record<string, unknown> : {}
      return { id, label: String(item.label || item.key || `[${id}]`), text: String(item.text || item.title || item.label || id) }
    })
  }

  function refreshProofIssues() {
    if (!editor) return
    const issues: Array<{ id: string; message: string; excerpt: string; from: number; to: number }> = []
    editor.state.doc.descendants((node, position) => {
      if (!node.isText || !node.text) return
      const rules: Array<{ expression: RegExp; message: string }> = [
        { expression: /([，。！？；：,.!?;:])\1+/g, message: '连续重复标点' },
        { expression: / {2,}/g, message: '连续多余空格' },
        { expression: /\b([A-Za-z]{2,})\s+\1\b/gi, message: '疑似重复单词' },
        { expression: /[^。！？!?]{121,}[。！？!?]?/g, message: '句子较长，建议检查断句' }
      ]
      for (const rule of rules) {
        for (const match of node.text.matchAll(rule.expression)) {
          const index = match.index || 0
          const value = match[0]
          issues.push({
            id: `${position}-${index}-${rule.message}`,
            message: rule.message,
            excerpt: value.length > 34 ? `${value.slice(0, 34)}…` : value,
            from: position + index,
            to: position + index + value.length
          })
        }
      }
    })
    proofIssues = issues
  }

  function jumpToProofIssue(issue: { from: number; to: number }) {
    editor?.chain().focus().setTextSelection({ from: issue.from, to: issue.to }).scrollIntoView().run()
  }

  function textMatches(query: string) {
    if (!editor || !query) return [] as Array<{ from: number; to: number }>
    const matches: Array<{ from: number; to: number }> = []
    editor.state.doc.descendants((node, position) => {
      if (!node.isText || !node.text) return
      let offset = 0
      while (offset <= node.text.length - query.length) {
        const found = node.text.indexOf(query, offset)
        if (found < 0) break
        matches.push({ from: position + found, to: position + found + query.length })
        offset = found + Math.max(1, query.length)
      }
    })
    return matches
  }

  function findNext(reverse = false) {
    if (!editor || !findQuery) return
    const matches = textMatches(findQuery)
    if (!matches.length) {
      findStatus = '未找到'
      return
    }
    const cursor = editor.state.selection.from
    const ordered = reverse ? [...matches].reverse() : matches
    const match = ordered.find((item) => reverse ? item.from < cursor : item.from > cursor) || ordered[0]
    editor.chain().focus().setTextSelection(match).scrollIntoView().run()
    findStatus = `${matches.findIndex((item) => item.from === match.from) + 1} / ${matches.length}`
  }

  function replaceCurrent() {
    if (!editor || !findQuery) return
    const { from, to } = editor.state.selection
    if (editor.state.doc.textBetween(from, to) !== findQuery) {
      findNext()
      return
    }
    editor.chain().focus().insertContentAt({ from, to }, replaceText).run()
    findNext()
  }

  function replaceAll() {
    if (!editor || !findQuery) return
    const matches = textMatches(findQuery)
    let transaction = editor.state.tr
    for (const match of [...matches].reverse()) transaction = transaction.insertText(replaceText, match.from, match.to)
    if (matches.length) editor.view.dispatch(transaction)
    findStatus = `已替换 ${matches.length} 处`
  }

  function outlineHeadings() {
    if (!editor) return [] as Array<{ id: string; text: string; level: number; position: number }>
    const headings: Array<{ id: string; text: string; level: number; position: number }> = []
    editor.state.doc.descendants((node, position) => {
      if (node.type.name === 'heading') headings.push({ id: String(node.attrs.nodeId || position), text: node.textContent || '未命名标题', level: Number(node.attrs.level || 1), position })
    })
    return headings
  }

  function navigationSearchResults() {
    if (!editor) return []
    const query = outlineQuery.trim().toLocaleLowerCase()
    if (!query) return []
    const results: Array<{ position: number; excerpt: string }> = []
    editor.state.doc.descendants((node, position) => {
      if (results.length >= 100 || !node.isTextblock) return
      const text = node.textContent
      const comparable = text.toLocaleLowerCase()
      let searchFrom = 0
      while (results.length < 100) {
        const matchAt = comparable.indexOf(query, searchFrom)
        if (matchAt < 0) break
        const start = Math.max(0, matchAt - 24)
        const end = Math.min(text.length, matchAt + query.length + 42)
        results.push({
          position: position + matchAt,
          excerpt: `${start > 0 ? '…' : ''}${text.slice(start, end)}${end < text.length ? '…' : ''}`
        })
        searchFrom = matchAt + Math.max(1, query.length)
      }
    })
    return results
  }

  function requestAiForTextSelection() {
    if (!editor || editor.state.selection.empty) return
    const { from, to } = editor.state.selection
    const text = editor.state.doc.textBetween(from, to, '\n', '\n').trim()
    if (!text) return
    ontextai?.({ text, from, to })
  }

  function jumpToOutline(position: number) {
    editor?.chain().focus().setTextSelection(position + 1).scrollIntoView().run()
  }

  function setZoom(next: number) {
    zoomPercent = Math.max(50, Math.min(200, next))
    shell?.style.setProperty('--editor-zoom', String(zoomPercent / 100))
  }

  function visibleStyles(): StyleDefinition[] {
    void styleRevision
    return (activeDocument?.styles || []).filter((style) => style.visible && style.kind === 'paragraph')
  }

  function loadManagedStyle(styleId: string) {
    const style = activeDocument?.styles.find((candidate) => candidate.id === styleId)
    if (!style) return
    const properties = style.properties || {}
    managedStyleId = style.id
    managedStyleName = style.name
    managedBasedOn = style.basedOn || ''
    managedNextStyle = style.nextStyle || 'normal'
    managedFontFamily = properties.fontFamily || ''
    managedFontSizePt = properties.fontSizePt ?? ''
    managedBold = toggleFromProperty(properties.bold)
    managedItalic = toggleFromProperty(properties.italic)
    managedUnderline = toggleFromProperty(properties.underline)
    managedColor = properties.color || ''
    managedBackgroundColor = properties.backgroundColor || ''
    managedLetterSpacingPt = properties.letterSpacingPt ?? ''
    managedTextTransform = properties.textTransform || ''
    managedAlignment = properties.alignment || ''
    managedLineSpacing = properties.lineSpacing ?? ''
    managedFirstLineIndentEm = properties.firstLineIndentEm ?? ''
    managedLeftIndentEm = properties.leftIndentEm ?? ''
    managedRightIndentEm = properties.rightIndentEm ?? ''
    managedSpaceBeforePt = properties.spaceBeforePt ?? ''
    managedSpaceAfterPt = properties.spaceAfterPt ?? ''
    managedOutlineLevel = properties.outlineLevel ?? ''
    managedKeepWithNext = toggleFromProperty(properties.keepWithNext)
    managedKeepLinesTogether = toggleFromProperty(properties.keepLinesTogether)
    managedPageBreakBefore = toggleFromProperty(properties.pageBreakBefore)
    managedBorderColor = properties.borderColor || ''
    managedBorderWidthPt = properties.borderWidthPt ?? ''
    managedBorderStyle = properties.borderStyle || ''
    managedShadingColor = properties.shadingColor || ''
    managedTabStops = (properties.tabStops || []).map((tab) => `${tab.positionEm}:${tab.alignment}`).join(', ')
    managedNumberingId = properties.numberingId || ''
    managedNumberingLevel = properties.numberingLevel ?? ''
    creatingStyle = false
    styleManagerNotice = ''
  }

  function beginCreateStyle() {
    if (!editor) return
    const paragraphAttrs = editor.getAttributes(editor.isActive('heading') ? 'heading' : 'paragraph')
    const textAttrs = editor.getAttributes('textStyle')
    managedStyleId = `user-style-${crypto.randomUUID().replace(/-/g, '').slice(0, 12)}`
    managedStyleName = '新样式'
    managedBasedOn = String(paragraphAttrs.styleId || 'normal')
    managedNextStyle = 'normal'
    managedFontFamily = String(textAttrs.fontFamily || '')
    const fontSize = Number.parseFloat(String(textAttrs.fontSize || ''))
    managedFontSizePt = Number.isFinite(fontSize) ? fontSize * 0.75 : ''
    managedBold = editor.isActive('bold') ? 'on' : 'inherit'
    managedItalic = editor.isActive('italic') ? 'on' : 'inherit'
    managedUnderline = editor.isActive('underline') ? 'on' : 'inherit'
    managedColor = String(textAttrs.color || '')
    managedBackgroundColor = String(textAttrs.backgroundColor || '')
    const letterSpacing = Number.parseFloat(String(textAttrs.letterSpacing || ''))
    managedLetterSpacingPt = Number.isFinite(letterSpacing) ? letterSpacing * 0.75 : ''
    managedTextTransform = (textAttrs.textTransform || '') as typeof managedTextTransform
    managedAlignment = (paragraphAttrs.textAlign || '') as typeof managedAlignment
    managedLineSpacing = paragraphAttrs.lineSpacing ?? ''
    managedFirstLineIndentEm = paragraphAttrs.firstLineIndentEm ?? ''
    managedLeftIndentEm = paragraphAttrs.leftIndentEm ?? ''
    managedRightIndentEm = paragraphAttrs.rightIndentEm ?? ''
    managedSpaceBeforePt = paragraphAttrs.spaceBeforePt ?? ''
    managedSpaceAfterPt = paragraphAttrs.spaceAfterPt ?? ''
    managedOutlineLevel = ''
    managedKeepWithNext = 'inherit'
    managedKeepLinesTogether = 'inherit'
    managedPageBreakBefore = 'inherit'
    managedBorderColor = paragraphAttrs.borderColor || ''
    managedBorderWidthPt = paragraphAttrs.borderWidthPt ?? ''
    managedBorderStyle = paragraphAttrs.borderStyle || ''
    managedShadingColor = paragraphAttrs.shadingColor || ''
    managedTabStops = ''
    managedNumberingId = ''
    managedNumberingLevel = ''
    creatingStyle = true
    styleManagerNotice = '正在基于当前段落创建样式。'
  }

  function publishStyleChange(next: DocumentV3, message: string) {
    activeDocument = next
    styleRevision += 1
    documentV3.set(next)
    docIrDirty.set(true)
    if (styleElement) styleElement.textContent = styleSheetForDocument(next)
    const text = documentV3ToText(next)
    onblockedit?.({ documentV3: next, text })
    schedulePagination(true)
    emitToolbarState()
    styleManagerNotice = message
  }

  function toggleFromProperty(value: boolean | null | undefined): InheritedToggle {
    return value == null ? 'inherit' : value ? 'on' : 'off'
  }

  function toggleProperty(value: InheritedToggle): boolean | undefined {
    return value === 'inherit' ? undefined : value === 'on'
  }

  function numberProperty(value: number | ''): number | undefined {
    if (value === '') return undefined
    const result = Number(value)
    return Number.isFinite(result) ? result : undefined
  }

  function parseTabStops(value: string): StyleProperties['tabStops'] | undefined {
    const input = value.trim()
    if (!input) return undefined
    return input.split(',').map((raw) => {
      const [positionText, alignmentText = 'left'] = raw.trim().split(':')
      const positionEm = Number(positionText)
      const alignment = alignmentText.trim() as 'left' | 'center' | 'right' | 'decimal'
      if (!Number.isFinite(positionEm) || positionEm < 0 || !['left', 'center', 'right', 'decimal'].includes(alignment)) {
        throw new Error(`无效制表位“${raw.trim()}”，请使用“位置:对齐”，例如 4:left。`)
      }
      return { positionEm, alignment }
    })
  }

  function stylePropertiesFromForm(): StyleProperties {
    const properties: StyleProperties = {
      fontFamily: managedFontFamily.trim() || undefined,
      fontSizePt: numberProperty(managedFontSizePt),
      bold: toggleProperty(managedBold),
      italic: toggleProperty(managedItalic),
      underline: toggleProperty(managedUnderline),
      color: managedColor || undefined,
      backgroundColor: managedBackgroundColor || undefined,
      letterSpacingPt: numberProperty(managedLetterSpacingPt),
      textTransform: managedTextTransform || undefined,
      alignment: managedAlignment || undefined,
      lineSpacing: numberProperty(managedLineSpacing),
      firstLineIndentEm: numberProperty(managedFirstLineIndentEm),
      leftIndentEm: numberProperty(managedLeftIndentEm),
      rightIndentEm: numberProperty(managedRightIndentEm),
      spaceBeforePt: numberProperty(managedSpaceBeforePt),
      spaceAfterPt: numberProperty(managedSpaceAfterPt),
      outlineLevel: numberProperty(managedOutlineLevel),
      keepWithNext: toggleProperty(managedKeepWithNext),
      keepLinesTogether: toggleProperty(managedKeepLinesTogether),
      pageBreakBefore: toggleProperty(managedPageBreakBefore),
      borderColor: managedBorderColor || undefined,
      borderWidthPt: numberProperty(managedBorderWidthPt),
      borderStyle: managedBorderStyle || undefined,
      shadingColor: managedShadingColor || undefined,
      tabStops: parseTabStops(managedTabStops),
      numberingId: managedNumberingId || undefined,
      numberingLevel: managedNumberingId ? numberProperty(managedNumberingLevel) ?? 0 : undefined
    }
    const ranges: Array<[keyof StyleProperties, number, number, string]> = [
      ['fontSizePt', 6, 96, '字号'], ['letterSpacingPt', -5, 30, '字间距'],
      ['lineSpacing', 0.8, 4, '行距'], ['firstLineIndentEm', -10, 20, '首行缩进'],
      ['leftIndentEm', -10, 40, '左缩进'], ['rightIndentEm', -10, 40, '右缩进'],
      ['spaceBeforePt', 0, 144, '段前'], ['spaceAfterPt', 0, 144, '段后'],
      ['outlineLevel', 0, 9, '大纲级别'], ['borderWidthPt', 0, 12, '边框宽度'],
      ['numberingLevel', 0, 8, '编号级别']
    ]
    for (const [key, min, max, label] of ranges) {
      const value = properties[key]
      if (typeof value === 'number' && (value < min || value > max)) throw new Error(`${label}必须在 ${min}–${max} 之间。`)
    }
    if (properties.outlineLevel !== undefined && !Number.isInteger(properties.outlineLevel)) throw new Error('大纲级别必须是整数。')
    if (properties.numberingLevel !== undefined && !Number.isInteger(properties.numberingLevel)) throw new Error('编号级别必须是整数。')
    if (properties.numberingId && !activeDocument?.numbering.some((definition) => definition.id === properties.numberingId)) throw new Error('选择的编号定义不存在。')
    for (const [value, label] of [[properties.color, '文字颜色'], [properties.backgroundColor, '文字底色'], [properties.borderColor, '边框颜色'], [properties.shadingColor, '段落底纹']] as const) {
      if (value && !/^#[0-9a-f]{6}$/i.test(value)) throw new Error(`${label}必须使用 #RRGGBB 格式。`)
    }
    return properties
  }

  function previewStyle(): string {
    let properties: StyleProperties
    try {
      const own = stylePropertiesFromForm()
      if (activeDocument) {
        const previewDocument = cloneJson(activeDocument)
        const definition: StyleDefinition = {
          id: managedStyleId,
          name: managedStyleName || '预览',
          kind: 'paragraph',
          basedOn: managedBasedOn || undefined,
          nextStyle: managedNextStyle || 'normal',
          visible: true,
          properties: own
        }
        const index = previewDocument.styles.findIndex((style) => style.id === definition.id)
        if (index >= 0) previewDocument.styles[index] = definition
        else previewDocument.styles.push(definition)
        properties = resolvedStyleProperties(previewDocument, definition.id)
      } else properties = own
    } catch { return '' }
    return [
      properties.fontFamily ? `font-family:${properties.fontFamily}` : '',
      properties.fontSizePt ? `font-size:${properties.fontSizePt}pt` : '',
      properties.bold === true ? 'font-weight:700' : properties.bold === false ? 'font-weight:400' : '',
      properties.italic === true ? 'font-style:italic' : properties.italic === false ? 'font-style:normal' : '',
      properties.underline === true ? 'text-decoration:underline' : properties.underline === false ? 'text-decoration:none' : '',
      properties.color ? `color:${properties.color}` : '',
      properties.backgroundColor ? `background-color:${properties.backgroundColor}` : '',
      properties.alignment ? `text-align:${properties.alignment}` : '',
      properties.lineSpacing ? `line-height:${properties.lineSpacing}` : '',
      properties.firstLineIndentEm !== undefined ? `text-indent:${properties.firstLineIndentEm}em` : ''
    ].filter(Boolean).join(';')
  }

  function saveManagedStyle() {
    if (!activeDocument) return
    const name = managedStyleName.trim()
    if (!name) {
      styleManagerNotice = '样式名称不能为空。'
      return
    }
    if (managedBasedOn === managedStyleId) {
      styleManagerNotice = '样式不能继承自身。'
      return
    }
    let properties: StyleProperties
    try {
      properties = stylePropertiesFromForm()
    } catch (error) {
      styleManagerNotice = error instanceof Error ? error.message : String(error)
      return
    }
    const definition: StyleDefinition = {
      id: managedStyleId,
      name,
      kind: 'paragraph',
      basedOn: managedBasedOn || undefined,
      nextStyle: managedNextStyle || 'normal',
      visible: true,
      properties
    }
    const next = cloneJson(activeDocument)
    const index = next.styles.findIndex((style) => style.id === definition.id)
    if (index >= 0) next.styles[index] = definition
    else next.styles.push(definition)
    const styleMap = new Map(next.styles.map((style) => [style.id, style]))
    const visited = new Set<string>()
    let cursor: StyleDefinition | undefined = definition
    while (cursor?.basedOn) {
      if (visited.has(cursor.id) || cursor.basedOn === definition.id) {
        styleManagerNotice = '样式继承关系不能形成循环。'
        return
      }
      visited.add(cursor.id)
      cursor = styleMap.get(cursor.basedOn)
    }
    creatingStyle = false
    publishStyleChange(next, index >= 0 ? `已全局更新“${name}”。` : `已创建“${name}”。`)
  }

  function duplicateManagedStyle() {
    const source = activeDocument?.styles.find((style) => style.id === managedStyleId)
    if (!source) return
    beginCreateStyle()
    managedStyleName = `${source.name} 副本`
    managedBasedOn = source.basedOn || 'normal'
    const properties = cloneJson(source.properties)
    managedFontFamily = properties.fontFamily || ''
    managedFontSizePt = properties.fontSizePt ?? ''
    managedBold = toggleFromProperty(properties.bold)
    managedItalic = toggleFromProperty(properties.italic)
    managedUnderline = toggleFromProperty(properties.underline)
    managedColor = properties.color || ''
    managedBackgroundColor = properties.backgroundColor || ''
    managedLetterSpacingPt = properties.letterSpacingPt ?? ''
    managedTextTransform = properties.textTransform || ''
    managedAlignment = properties.alignment || ''
    managedLineSpacing = properties.lineSpacing ?? ''
    managedFirstLineIndentEm = properties.firstLineIndentEm ?? ''
    managedLeftIndentEm = properties.leftIndentEm ?? ''
    managedRightIndentEm = properties.rightIndentEm ?? ''
    managedSpaceBeforePt = properties.spaceBeforePt ?? ''
    managedSpaceAfterPt = properties.spaceAfterPt ?? ''
    managedOutlineLevel = properties.outlineLevel ?? ''
    managedKeepWithNext = toggleFromProperty(properties.keepWithNext)
    managedKeepLinesTogether = toggleFromProperty(properties.keepLinesTogether)
    managedPageBreakBefore = toggleFromProperty(properties.pageBreakBefore)
    managedBorderColor = properties.borderColor || ''
    managedBorderWidthPt = properties.borderWidthPt ?? ''
    managedBorderStyle = properties.borderStyle || ''
    managedShadingColor = properties.shadingColor || ''
    managedTabStops = (properties.tabStops || []).map((tab) => `${tab.positionEm}:${tab.alignment}`).join(', ')
    managedNumberingId = properties.numberingId || ''
    managedNumberingLevel = properties.numberingLevel ?? ''
    styleManagerNotice = `正在复制“${source.name}”。`
  }

  function resetManagedStyle() {
    const builtin = DEFAULT_STYLES.find((style) => style.id === managedStyleId)
    if (!builtin || !activeDocument) {
      styleManagerNotice = '只有内置样式可以恢复默认值。'
      return
    }
    const next = cloneJson(activeDocument)
    const index = next.styles.findIndex((style) => style.id === builtin.id)
    if (index >= 0) next.styles[index] = cloneJson(builtin)
    else next.styles.push(cloneJson(builtin))
    publishStyleChange(next, `已恢复“${builtin.name}”的默认设置。`)
    loadManagedStyle(builtin.id)
  }

  function deleteManagedStyle() {
    if (!activeDocument) return
    if (DEFAULT_STYLES.some((style) => style.id === managedStyleId)) {
      styleManagerNotice = '内置样式不能删除，可以恢复默认值。'
      return
    }
    const replacement = managedBasedOn && managedBasedOn !== managedStyleId ? managedBasedOn : 'normal'
    const next = cloneJson(activeDocument)
    next.styles = next.styles.filter((style) => style.id !== managedStyleId)
    for (const style of next.styles) {
      if (style.basedOn === managedStyleId) style.basedOn = replacement
      if (style.nextStyle === managedStyleId) style.nextStyle = replacement
    }
    const reassign = (nodes: any[]) => {
      for (const node of nodes || []) {
        if (node?.styleId === managedStyleId) node.styleId = replacement
        if (Array.isArray(node?.content)) reassign(node.content)
      }
    }
    for (const section of next.sections) reassign(section.content)
    publishStyleChange(next, '样式已删除，引用它的段落已安全改用父样式或正文。')
    loadManagedStyle(replacement)
    if (editor) loadDocument(next)
  }

  function applyManagedStyle() {
    if (!editor) return
    if (creatingStyle) {
      saveManagedStyle()
      if (creatingStyle) return
    }
    const properties = activeDocument ? resolvedStyleProperties(activeDocument, managedStyleId) : {}
    const numbering = activeDocument?.numbering.find((definition) => definition.id === properties.numberingId)
    executeDocumentCommand(editor, createUserCommand('apply_style', {
      styleId: managedStyleId,
      numberingId: numbering?.id || '',
      numberingLevel: properties.numberingLevel ?? 0,
      numberingFormat: numbering?.levels[properties.numberingLevel ?? 0]?.format || ''
    }))
    emitSelection()
  }

  function prepareMarkdownExport() {
    if (!activeDocument) return
    const result = documentV3ToMarkdown(activeDocument)
    markdownExportText = result.markdown
    markdownExportWarnings = result.warnings
    markdownExportVisible = true
  }

  function downloadMarkdown() {
    if (!activeDocument || !markdownExportText) return
    const blob = new Blob([markdownExportText], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    const safeName = (activeDocument.title || 'document').replace(/[\\/:*?"<>|]+/g, '_')
    anchor.href = url
    anchor.download = `${safeName}.md`
    anchor.click()
    URL.revokeObjectURL(url)
    markdownExportVisible = false
    markdownNotice = 'Markdown 已导出；Document V3 原文档未改变。'
  }

  async function importMarkdownFile(event: Event) {
    const input = event.currentTarget as HTMLInputElement
    const file = input.files?.[0]
    input.value = ''
    if (!file || !activeDocument) return
    try {
      const markdown = await file.text()
      const next = replaceDocumentContentFromMarkdown(activeDocument, markdown, file.name)
      loadDocument(next)
      const text = documentV3ToText(next)
      sourceText.set(text)
      docIrDirty.set(true)
      onblockedit?.({ documentV3: next, text })
      markdownNotice = `已导入 ${file.name}：页面设置和样式库继续由 Document V3 管理。`
    } catch (error) {
      markdownNotice = `Markdown 导入失败：${error instanceof Error ? error.message : String(error)}`
    }
  }

  async function importWordFile(event: Event) {
    const input = event.currentTarget as HTMLInputElement
    const file = input.files?.[0]
    input.value = ''
    const currentDocId = get(docId)
    if (!file || !currentDocId) return
    markdownNotice = '正在读取 Word 文档结构…'
    try {
      const body = new FormData()
      body.append('file', file)
      const response = await fetch(`/api/doc/${encodeURIComponent(currentDocId)}/import`, { method: 'POST', body })
      const result = await response.json().catch(() => ({}))
      if (!response.ok || !isDocumentV3(result.document_v3)) throw new Error(String(result.detail || 'Word 导入失败'))
      const next = cloneJson(result.document_v3 as DocumentV3)
      loadDocument(next)
      const imported = result.imported || {}
      markdownNotice = `已导入 Word：${Number(imported.paragraphs || 0)} 段、${Number(imported.tables || 0)} 个表格、${Number(imported.styles || 0)} 个样式。`
    } catch (error) {
      markdownNotice = error instanceof Error ? error.message : String(error)
    }
  }

  function handlePageSettingsChanged() {
    const next = get(documentV3)
    if (next && isDocumentV3(next)) loadDocument(cloneJson(next))
  }

  function handleEditorContext(event: Event) {
    const kind = String((event as CustomEvent<{ kind?: string }>).detail?.kind || '')
    if (kind !== 'page') return
    selectionToolbarVisible = false
    blockSelectionActive = false
    selectedBlockIds = []
    styleManagerVisible = false
  }

  function applyPaperGeometry(document: DocumentV3) {
    if (!shell) return
    const layout = document.sections[0]?.layout
    if (!layout) return
    let width = layout.widthMm || (layout.pageSize === 'A3' ? 297 : layout.pageSize === 'A5' ? 148 : layout.pageSize === 'Letter' ? 215.9 : 210)
    let height = layout.heightMm || (layout.pageSize === 'A3' ? 420 : layout.pageSize === 'A5' ? 210 : layout.pageSize === 'Letter' ? 279.4 : 297)
    if (layout.orientation === 'landscape') [width, height] = [height, width]
    shell.style.setProperty('--page-width', `${width}mm`)
    shell.style.setProperty('--page-height', `${height}mm`)
    shell.style.setProperty('--margin-top', `${layout.marginTopMm}mm`)
    shell.style.setProperty('--margin-right', `${layout.marginRightMm}mm`)
    shell.style.setProperty('--margin-bottom', `${layout.marginBottomMm}mm`)
    shell.style.setProperty('--margin-left', `${layout.marginLeftMm}mm`)
  }

  function schedulePagination(immediate = false) {
    if (composingText && !immediate) {
      paginationPendingAfterComposition = true
      return
    }
    if (paginationTimer) clearTimeout(paginationTimer)
    const revision = ++paginationRevision
    paginationTimer = setTimeout(async () => {
      if (!editor || !activeDocument || revision !== paginationRevision) return
      paginationState = 'loading'
      try {
        const selected = editor.state.selection.$from.depth > 0 ? editor.state.selection.$from.node(1) : null
        const anchorId = String(selected?.attrs?.nodeId || '')
        const anchorBefore = anchorId ? shell.querySelector<HTMLElement>(`[data-node-id="${CSS.escape(anchorId)}"]`)?.getBoundingClientRect().top : undefined
        const layout = await paginateDocumentV3(activeDocument, revision)
        if (!editor || revision !== paginationRevision) return
        pageCount = Math.max(1, layout?.pageCount || 1)
        paginationState = layout ? 'ready' : 'unavailable'
        applyPaginationLayout(editor, layout)
        if (anchorId !== '' && anchorBefore !== undefined) {
          requestAnimationFrame(() => {
            const after = shell.querySelector<HTMLElement>(`[data-node-id="${CSS.escape(anchorId)}"]`)?.getBoundingClientRect().top
            if (after !== undefined && Math.abs(after - anchorBefore) > 1) window.scrollBy({ top: after - anchorBefore, behavior: 'auto' })
          })
        }
        if (shell) shell.dataset.pageCount = String(pageCount)
      } catch (error) {
        paginationState = 'error'
        if (shell) shell.dataset.paginationError = error instanceof Error ? error.message : String(error)
        console.error('Rust pagination failed.', error)
      }
    }, immediate ? 0 : 120)
  }

  const slashCommands = [
    { label: '正文', keywords: 'paragraph 正文', command: 'apply_style', params: { styleId: 'normal' } },
    { label: '标题 1', keywords: 'heading title 标题', command: 'apply_style', params: { styleId: 'heading-1' } },
    { label: '标题 2', keywords: 'heading title 标题', command: 'apply_style', params: { styleId: 'heading-2' } },
    { label: '标题 3', keywords: 'heading title 标题', command: 'apply_style', params: { styleId: 'heading-3' } },
    { label: '项目列表', keywords: 'bullet list 列表', command: 'toggle_bullet_list', params: {} },
    { label: '编号列表', keywords: 'number ordered list 编号', command: 'toggle_ordered_list', params: {} },
    { label: '引用', keywords: 'quote 引用', command: 'toggle_blockquote', params: {} },
    { label: '代码块', keywords: 'code 代码', command: 'toggle_code_block', params: {} },
    { label: '分页符', keywords: 'page break 分页', command: 'insert_page_break', params: {} },
    { label: '图片/图表', keywords: 'figure image 图片 图表', command: 'insert_figure', params: {} },
    { label: '表格', keywords: 'table 表格', command: 'insert_table', params: {} },
    { label: '公式', keywords: 'equation math 公式', command: 'insert_equation', params: {} }
  ]

  function filteredSlashCommands() {
    const query = slashQuery.trim().toLocaleLowerCase()
    return slashCommands.filter((item) => !query || `${item.label} ${item.keywords}`.toLocaleLowerCase().includes(query))
  }

  function handleSlashQuery(query: string | null, position: number, currentEditor: Editor) {
    if (query === null) {
      slashMenuVisible = false
      return
    }
    slashQuery = query
    slashMenuIndex = Math.min(slashMenuIndex, Math.max(0, filteredSlashCommands().length - 1))
    const caret = currentEditor.view.coordsAtPos(position)
    const shellRect = shell.getBoundingClientRect()
    slashMenuTop = caret.bottom - shellRect.top + 6
    slashMenuLeft = Math.max(0, caret.left - shellRect.left)
    slashMenuVisible = true
  }

  function runSlashCommand(index: number) {
    if (!editor) return
    const item = filteredSlashCommands()[index]
    if (!item) return
    const resolvedFrom = editor.state.selection.$from
    const from = editor.state.selection.from
    editor.chain().focus().deleteRange({ from: resolvedFrom.start(), to: from }).run()
    executeDocumentCommand(editor, createUserCommand(item.command, item.params))
    slashMenuVisible = false
    emitSelection()
  }

  function handleShellKeyDown(event: KeyboardEvent) {
    if (!editor) return
    if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.code === 'Space') {
      event.preventDefault()
      const current = selectedBlocks(editor)[0]
      if (current && selectBlock(editor, current.id)) {
        blockSelectionAnchorId = current.id
        blockSelectionActive = true
        emitSelection(true)
      }
      return
    }
    if (blockSelectionActive && (event.key === 'ArrowUp' || event.key === 'ArrowDown')) {
      event.preventDefault()
      const ids: string[] = []
      editor.state.doc.forEach((node) => {
        const id = String(node.attrs?.nodeId || '')
        if (id) ids.push(id)
      })
      const edgeId = event.key === 'ArrowUp' ? selectedBlockIds[0] : selectedBlockIds[selectedBlockIds.length - 1]
      const currentIndex = ids.indexOf(edgeId)
      const targetIndex = Math.max(0, Math.min(ids.length - 1, currentIndex + (event.key === 'ArrowUp' ? -1 : 1)))
      const targetId = ids[targetIndex]
      if (targetId && selectBlock(editor, targetId, event.shiftKey ? blockSelectionAnchorId : '')) {
        if (!event.shiftKey) blockSelectionAnchorId = targetId
        blockSelectionActive = true
        emitSelection(true)
      }
      return
    }
    if (blockSelectionActive && ['Escape', 'Enter', 'ArrowLeft', 'ArrowRight'].includes(event.key)) {
      event.preventDefault()
      const target = selectedBlockIds.length ? editor.state.doc.resolve(editor.state.selection.from) : null
      const position = target ? TextSelection.near(target, event.key === 'ArrowLeft' ? -1 : 1) : editor.state.selection
      if (position instanceof TextSelection) editor.view.dispatch(editor.state.tr.setSelection(position).scrollIntoView())
      blockSelectionActive = false
      emitSelection()
      return
    }
    if (!slashMenuVisible) return
    const items = filteredSlashCommands()
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const delta = event.key === 'ArrowDown' ? 1 : -1
      slashMenuIndex = (slashMenuIndex + delta + items.length) % Math.max(1, items.length)
    } else if (event.key === 'Enter' && items.length) {
      event.preventDefault()
      runSlashCommand(slashMenuIndex)
    } else if (event.key === 'Escape') {
      event.preventDefault()
      slashMenuVisible = false
    }
  }

  function handleObjectDoubleClick(event: MouseEvent) {
    if (!editor) return
    const element = (event.target as Element | null)?.closest<HTMLElement>('[data-v3-node]')
    if (!element) return
    const nodeId = String(element.dataset.nodeId || '')
    if (nodeId) selectBlock(editor, nodeId)
    const type = String(element.dataset.v3Node || '')
    if (type === 'figure') openFigureEditor()
    else if (type === 'equationBlock') openReferenceDialog('blockEquation')
    else if (type === 'tableOfContents') executeDocumentCommand(editor, createUserCommand('update_table_of_contents'))
    else if (type === 'bibliography') executeDocumentCommand(editor, createUserCommand('update_bibliography', { entries: citationEntries() }))
  }

  function topLevelBlockElement(element: Element | null): HTMLElement | null {
    let candidate = element?.closest<HTMLElement>('[data-node-id]') || null
    while (candidate?.parentElement && !candidate.parentElement.classList.contains('tiptap')) {
      candidate = candidate.parentElement.closest<HTMLElement>('[data-node-id]')
    }
    return candidate
  }

  function positionBlockHandle(element: HTMLElement | null) {
    if (!element || !shell) return
    const blockId = String(element.dataset.nodeId || '')
    if (!blockId) return
    const shellRect = shell.getBoundingClientRect()
    const blockRect = element.getBoundingClientRect()
    activeBlockId = blockId
    blockHandleTop = blockRect.top - shellRect.top + Math.min(4, Math.max(0, (blockRect.height - 24) / 2))
    blockHandleLeft = blockRect.left - shellRect.left - 30
    blockHandleVisible = true
  }

  function positionBlockHandleById(nodeId: string) {
    if (!host || !nodeId) return
    const element = Array.from(host.querySelectorAll<HTMLElement>('[data-node-id]'))
      .find((candidate) => candidate.dataset.nodeId === nodeId && candidate.parentElement?.classList.contains('tiptap'))
    positionBlockHandle(element || null)
  }

  function handleEditorPointerMove(event: PointerEvent) {
    if (blockPointerId === event.pointerId) {
      if (!blockPointerDragging && Math.abs(event.clientY - blockPointerStartY) >= 4) {
        blockPointerDragging = true
        onblockdrag?.(true)
      }
      if (blockPointerDragging) {
        event.preventDefault()
        scheduleBlockAutoScroll(event.clientX, event.clientY)
        updateBlockDropTarget(event.clientY, event.target instanceof Element ? event.target : null)
        return
      }
    }
    positionBlockHandle(topLevelBlockElement(event.target instanceof Element ? event.target : null))
  }

  function handleBlockHandleClick(event: MouseEvent) {
    if (suppressHandleClick) {
      suppressHandleClick = false
      return
    }
    if (!editor || !activeBlockId) return
    const extend = event.shiftKey && Boolean(blockSelectionAnchorId)
    if (selectBlock(editor, activeBlockId, extend ? blockSelectionAnchorId : '')) {
      if (!extend) blockSelectionAnchorId = activeBlockId
      blockSelectionActive = true
      emitSelection(true)
      positionBlockHandleById(activeBlockId)
    }
  }

  function runBlockCommand(type: 'move_block_up' | 'move_block_down' | 'duplicate_block' | 'delete_block' | 'insert_block_before' | 'insert_block_after' | 'toggle_block_collapsed') {
    if (!editor) return
    executeDocumentCommand(editor, createUserCommand(type))
    emitSelection()
  }

  function showClipboardStatus(message: string) {
    clipboardError = message
    if (clipboardErrorTimer) clearTimeout(clipboardErrorTimer)
    clipboardErrorTimer = setTimeout(() => (clipboardError = ''), 3000)
  }

  async function copySelectedBlockContent() {
    if (!editor) return
    const text = selectedBlocks(editor).map((block) => block.text).join('\n\n').trim()
    if (!text) {
      showClipboardStatus('所选块没有可复制的文字。')
      return
    }
    try {
      await navigator.clipboard.writeText(text)
      showClipboardStatus(`已复制 ${selectedBlockIds.length || 1} 个块的内容。`)
    } catch {
      showClipboardStatus('系统未允许访问剪贴板，请使用 Ctrl+C。')
    }
  }

  function openBlockAi() {
    emitSelection()
    onblockai?.()
  }

  function convertSelectedBlock(event: Event) {
    if (!editor) return
    const type = (event.currentTarget as HTMLSelectElement).value
    if (!type) return
    executeDocumentCommand(editor, createUserCommand('convert_block', { type }))
    ;(event.currentTarget as HTMLSelectElement).value = ''
    emitSelection()
  }

  function handleBlockPointerDown(event: PointerEvent) {
    if (!editor || !activeBlockId || event.button !== 0) return
    if (!selectedBlockIds.includes(activeBlockId)) selectBlock(editor, activeBlockId)
    const ids = selectedBlocks(editor).map((block) => block.id)
    selectedBlockIds = ids.length ? ids : [activeBlockId]
    blockPointerId = event.pointerId
    blockPointerStartY = event.clientY
    blockDragScrollElement = nearestScrollableAncestor(shell)
    blockPointerDragging = false
    ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  }

  function nearestScrollableAncestor(element: HTMLElement): HTMLElement | null {
    let parent = element.parentElement
    while (parent) {
      const overflowY = getComputedStyle(parent).overflowY
      if (/(auto|scroll)/.test(overflowY) && parent.scrollHeight > parent.clientHeight) return parent
      parent = parent.parentElement
    }
    return null
  }

  function stopBlockAutoScroll() {
    if (blockDragScrollFrame !== null) cancelAnimationFrame(blockDragScrollFrame)
    blockDragScrollFrame = null
    blockDragScrollElement = null
  }

  function runBlockAutoScroll() {
    blockDragScrollFrame = null
    if (!blockPointerDragging) return
    const edge = 72
    const viewport = blockDragScrollElement?.getBoundingClientRect()
    const top = viewport?.top ?? 0
    const bottom = viewport?.bottom ?? window.innerHeight
    const distanceTop = blockDragClientY - top
    const distanceBottom = bottom - blockDragClientY
    const delta = distanceTop < edge
      ? -Math.max(4, Math.round((edge - distanceTop) / 4))
      : distanceBottom < edge
        ? Math.max(4, Math.round((edge - distanceBottom) / 4))
        : 0
    if (!delta) return
    if (blockDragScrollElement) blockDragScrollElement.scrollTop += delta
    else window.scrollBy(0, delta)
    const hit = document.elementFromPoint(
      Math.max(0, Math.min(window.innerWidth - 1, blockDragClientX)),
      Math.max(0, Math.min(window.innerHeight - 1, blockDragClientY))
    )
    updateBlockDropTarget(blockDragClientY, hit)
    blockDragScrollFrame = requestAnimationFrame(runBlockAutoScroll)
  }

  function scheduleBlockAutoScroll(clientX: number, clientY: number) {
    blockDragClientX = clientX
    blockDragClientY = clientY
    if (blockDragScrollFrame === null) blockDragScrollFrame = requestAnimationFrame(runBlockAutoScroll)
  }

  function nearestTopLevelBlock(clientY: number): HTMLElement | null {
    const blocks = Array.from(host.querySelectorAll<HTMLElement>(':scope > .tiptap > [data-node-id], .tiptap > [data-node-id]'))
      .filter((element) => element.parentElement?.classList.contains('tiptap'))
    let nearest: HTMLElement | null = null
    let distance = Number.POSITIVE_INFINITY
    for (const block of blocks) {
      const rect = block.getBoundingClientRect()
      const candidate = Math.abs(clientY - (rect.top + rect.height / 2))
      if (candidate < distance) {
        nearest = block
        distance = candidate
      }
    }
    return nearest
  }

  function updateBlockDropTarget(clientY: number, eventTarget: Element | null) {
    const element = topLevelBlockElement(eventTarget) || nearestTopLevelBlock(clientY)
    const targetId = String(element?.dataset.nodeId || '')
    if (!element || !targetId || selectedBlockIds.includes(targetId)) return
    const shellRect = shell.getBoundingClientRect()
    const rect = element.getBoundingClientRect()
    dragTargetId = targetId
    dragPlacement = clientY >= rect.top + rect.height / 2 ? 'after' : 'before'
    dragIndicatorTop = (dragPlacement === 'after' ? rect.bottom : rect.top) - shellRect.top
  }

  function clearBlockDrag() {
    dragTargetId = ''
    stopBlockAutoScroll()
    onblockdrag?.(false)
  }

  function handleBlockPointerUp(event: PointerEvent) {
    if (blockPointerId !== event.pointerId) return
    suppressHandleClick = blockPointerDragging
    if (blockPointerDragging && editor && dragTargetId) {
      executeDocumentCommand(editor, createNodeCommand('move_blocks', selectedBlockIds, { targetId: dragTargetId, placement: dragPlacement }))
      emitSelection()
    }
    blockPointerId = null
    blockPointerDragging = false
    clearBlockDrag()
  }

  function emitToolbarState() {
    if (!editor) return
    const selection = editor.state.selection
    const tableAttrs = editor.getAttributes('table')
    const cellAttrs = editor.isActive('tableHeader')
      ? editor.getAttributes('tableHeader')
      : editor.getAttributes('tableCell')
    const textBlocks: Array<{ attrs: Record<string, unknown>; from: number; to: number }> = []
    const seenBlocks = new Set<string>()
    editor.state.doc.nodesBetween(selection.from, selection.to || selection.from, (node, position) => {
      if (!node.isTextblock) return
      const key = String(node.attrs.nodeId || position)
      if (seenBlocks.has(key)) return
      seenBlocks.add(key)
      textBlocks.push({ attrs: node.attrs as Record<string, unknown>, from: position + 1, to: position + node.nodeSize - 1 })
    })
    if (!textBlocks.length && selection.$from.parent.isTextblock) {
      const start = selection.$from.start()
      textBlocks.push({ attrs: selection.$from.parent.attrs as Record<string, unknown>, from: start, to: start + selection.$from.parent.content.size })
    }
    const unique = (values: unknown[]) => new Set(values.map((value) => JSON.stringify(value ?? null)))
    const paragraphValue = (block: { attrs: Record<string, unknown> }, key: string) => {
      const styleId = String(block.attrs.styleId || 'normal')
      const computed = activeDocument ? resolvedStyleProperties(activeDocument, styleId) : {}
      if (key === 'styleId') return styleId
      if (key === 'alignment') return block.attrs.textAlign ?? computed.alignment ?? 'left'
      return block.attrs[key] ?? computed[key as keyof StyleProperties] ?? null
    }
    const paragraphFields = ['styleId', 'alignment', 'lineSpacing', 'firstLineIndentEm', 'leftIndentEm', 'rightIndentEm', 'spaceBeforePt', 'spaceAfterPt', 'keepWithNext', 'keepLinesTogether', 'pageBreakBefore', 'tabStops']
    const mixedFields = paragraphFields.filter((key) => unique(textBlocks.map((block) => paragraphValue(block, key))).size > 1)
    const inlineValues: Record<string, unknown[]> = {
      bold: [], italic: [], underline: [], strike: [], subscript: [], superscript: [],
      fontFamily: [], fontSize: [], letterSpacing: [], textTransform: [], color: [], backgroundColor: []
    }
    for (const block of textBlocks) {
      const style = activeDocument ? resolvedStyleProperties(activeDocument, String(block.attrs.styleId || 'normal')) : {}
      const from = selection.empty ? selection.from : Math.max(selection.from, block.from)
      const to = selection.empty ? selection.from : Math.min(selection.to, block.to)
      let foundText = false
      editor.state.doc.nodesBetween(from, Math.max(from, to), (node) => {
        if (!node.isText) return
        foundText = true
        const mark = (name: string) => node.marks.find((candidate) => candidate.type.name === name)
        const textStyleMark = mark('textStyle')
        inlineValues.bold.push(Boolean(mark('bold')) || Boolean(style.bold))
        inlineValues.italic.push(Boolean(mark('italic')) || Boolean(style.italic))
        inlineValues.underline.push(Boolean(mark('underline')) || Boolean(style.underline))
        inlineValues.strike.push(Boolean(mark('strike')))
        inlineValues.subscript.push(Boolean(mark('subscript')))
        inlineValues.superscript.push(Boolean(mark('superscript')))
        inlineValues.fontFamily.push(textStyleMark?.attrs.fontFamily || style.fontFamily || '')
        inlineValues.fontSize.push(textStyleMark?.attrs.fontSize || (style.fontSizePt ? `${style.fontSizePt}pt` : ''))
        inlineValues.letterSpacing.push(textStyleMark?.attrs.letterSpacing || (style.letterSpacingPt !== undefined ? `${style.letterSpacingPt}pt` : ''))
        inlineValues.textTransform.push(textStyleMark?.attrs.textTransform || style.textTransform || 'none')
        inlineValues.color.push(textStyleMark?.attrs.color || style.color || '')
        inlineValues.backgroundColor.push(mark('highlight')?.attrs.color || style.backgroundColor || '')
      })
      if (!foundText) {
        const stored = editor.state.storedMarks || selection.$from.marks()
        const mark = (name: string) => stored.find((candidate) => candidate.type.name === name)
        const textStyleMark = mark('textStyle')
        inlineValues.bold.push(Boolean(mark('bold')) || Boolean(style.bold))
        inlineValues.italic.push(Boolean(mark('italic')) || Boolean(style.italic))
        inlineValues.underline.push(Boolean(mark('underline')) || Boolean(style.underline))
        inlineValues.strike.push(Boolean(mark('strike')))
        inlineValues.subscript.push(Boolean(mark('subscript')))
        inlineValues.superscript.push(Boolean(mark('superscript')))
        inlineValues.fontFamily.push(textStyleMark?.attrs.fontFamily || style.fontFamily || '')
        inlineValues.fontSize.push(textStyleMark?.attrs.fontSize || (style.fontSizePt ? `${style.fontSizePt}pt` : ''))
        inlineValues.letterSpacing.push(textStyleMark?.attrs.letterSpacing || (style.letterSpacingPt !== undefined ? `${style.letterSpacingPt}pt` : ''))
        inlineValues.textTransform.push(textStyleMark?.attrs.textTransform || style.textTransform || 'none')
        inlineValues.color.push(textStyleMark?.attrs.color || style.color || '')
        inlineValues.backgroundColor.push(mark('highlight')?.attrs.color || style.backgroundColor || '')
      }
    }
    for (const [key, values] of Object.entries(inlineValues)) if (unique(values).size > 1) mixedFields.push(key)
    const headingAttrs = editor.getAttributes('heading')
    const paragraphAttrs = editor.getAttributes('paragraph')
    const blockAttrs = editor.isActive('heading') ? headingAttrs : paragraphAttrs
    const styleId = String(paragraphValue(textBlocks[0] || { attrs: blockAttrs }, 'styleId') || 'normal')
    const computedStyle = activeDocument ? resolvedStyleProperties(activeDocument, styleId) : {}
    const textStyle = editor.getAttributes('textStyle')
    const firstInline = (key: string, fallback: unknown) => mixedFields.includes(key) ? fallback : (inlineValues[key]?.[0] ?? fallback)
    ontoolbarstate?.({
      focused: editor.isFocused,
      readonly: !editor.isEditable,
      bold: Boolean(firstInline('bold', false)),
      italic: Boolean(firstInline('italic', false)),
      underline: Boolean(firstInline('underline', false)),
      strike: Boolean(firstInline('strike', false)),
      subscript: Boolean(firstInline('subscript', false)),
      superscript: Boolean(firstInline('superscript', false)),
      hasSelection: !selection.empty,
      canUndo: editor.can().undo(),
      canRedo: editor.can().redo(),
      canCopy: !selection.empty,
      canCut: !selection.empty && editor.isEditable,
      canPaste: editor.isEditable,
      inTable: editor.isActive('table'),
      canMergeCells: editor.isActive('table') && editor.can().mergeCells(),
      canSplitCell: editor.isActive('table') && editor.can().splitCell(),
      tableCaption: String(tableAttrs.caption || ''),
      tableRepeatHeader: Boolean(tableAttrs.repeatHeader),
      tableAlignment: String(tableAttrs.tableAlignment || 'left'),
      tableWidthPercent: Number(tableAttrs.widthPercent || 100),
      tableCellBackground: String(cellAttrs.backgroundColor || ''),
      tableCellVerticalAlign: String(cellAttrs.verticalAlign || 'top'),
      blockType: editor.isActive('heading') ? 'heading' : 'paragraph',
      headingLevel: headingAttrs.level || null,
      styleId,
      fontFamily: String(firstInline('fontFamily', textStyle.fontFamily || computedStyle.fontFamily || '')),
      fontSize: String(firstInline('fontSize', textStyle.fontSize || (computedStyle.fontSizePt ? `${computedStyle.fontSizePt}pt` : ''))),
      color: String(firstInline('color', '')),
      backgroundColor: String(firstInline('backgroundColor', '')),
      alignment: paragraphValue(textBlocks[0] || { attrs: blockAttrs }, 'alignment'),
      lineSpacing: paragraphValue(textBlocks[0] || { attrs: blockAttrs }, 'lineSpacing'),
      letterSpacing: String(firstInline('letterSpacing', textStyle.letterSpacing || (computedStyle.letterSpacingPt !== undefined ? `${computedStyle.letterSpacingPt}pt` : ''))),
      textTransform: String(firstInline('textTransform', textStyle.textTransform || computedStyle.textTransform || 'none')),
      firstLineIndentEm: paragraphValue(textBlocks[0] || { attrs: blockAttrs }, 'firstLineIndentEm'),
      leftIndentEm: paragraphValue(textBlocks[0] || { attrs: blockAttrs }, 'leftIndentEm'),
      rightIndentEm: paragraphValue(textBlocks[0] || { attrs: blockAttrs }, 'rightIndentEm'),
      keepWithNext: Boolean(paragraphValue(textBlocks[0] || { attrs: blockAttrs }, 'keepWithNext')),
      keepLinesTogether: Boolean(paragraphValue(textBlocks[0] || { attrs: blockAttrs }, 'keepLinesTogether')),
      pageBreakBefore: Boolean(paragraphValue(textBlocks[0] || { attrs: blockAttrs }, 'pageBreakBefore')),
      tabStops: paragraphValue(textBlocks[0] || { attrs: blockAttrs }, 'tabStops') || [],
      spaceBeforePt: paragraphValue(textBlocks[0] || { attrs: blockAttrs }, 'spaceBeforePt'),
      spaceAfterPt: paragraphValue(textBlocks[0] || { attrs: blockAttrs }, 'spaceAfterPt'),
      styles: visibleStyles().map((style) => ({ id: style.id, name: style.name })),
      mixedFields
    })
  }

  function emitSelection(forceBlockSelection = false) {
    if (!editor) return
    const { from, to, empty } = editor.state.selection
    const blocks = selectedBlocks(editor)
    if (forceBlockSelection || editor.state.selection instanceof NodeSelection) blockSelectionActive = true
    else if (!empty) blockSelectionActive = false
    else blockSelectionActive = false
    // Text and block selection are separate contexts. A normal text range may
    // cross several blocks but must not summon block actions.
    const exposedBlocks = blockSelectionActive ? blocks : []
    const blockIds = exposedBlocks.map((block) => block.id)
    selectedBlockIds = blockIds
    selectedBlocksCollapsed = exposedBlocks.length > 0 && exposedBlocks.every((block) => block.collapsed)
    if (blocks.length === 1) positionBlockHandleById(blocks[0].id)
    const text = empty ? '' : editor.state.doc.textBetween(from, to, '\n')
    selectionToolbarVisible = !empty
      && !blockSelectionActive
      && !(editor.state.selection instanceof NodeSelection)
      && !(editor.state.selection instanceof CellSelection)
    const contextKind = blockSelectionActive ? 'block' : selectionToolbarVisible ? 'text' : 'editor'
    window.dispatchEvent(new CustomEvent('wa-editor-context', { detail: { kind: contextKind } }))
    if (selectionToolbarVisible && shell) {
      const start = editor.view.coordsAtPos(from)
      const end = editor.view.coordsAtPos(to)
      const shellRect = shell.getBoundingClientRect()
      selectionToolbarTop = Math.max(4, Math.min(start.top, end.top) - shellRect.top - 38)
      selectionToolbarLeft = Math.max(4, Math.min((start.left + end.right) / 2 - shellRect.left - 112, shellRect.width - 230))
    }
    onblockselect?.({
      blockId: blockIds[0] || '',
      blockIds,
      blocks: exposedBlocks.map((block) => ({ ...block, kind: 'block' })),
      text,
      selection: selectionToolbarVisible ? { kind: 'text', from, to } : null,
      rect: null,
      style: {}
    })
    emitToolbarState()
  }

  function updateDocument(json: JSONContent) {
    if (!activeDocument) return
    const before = activeDocument
    activeDocument = refreshDocumentFields(tiptapToDocumentV3(activeDocument, json))
    if (trackChanges && !suppressRevisionCapture) queueTrackedRevision(before)
    if (editor) {
      const currentBlocks = selectedBlocks(editor)
      selectedBlocksCollapsed = currentBlocks.length > 0 && currentBlocks.every((block) => block.collapsed)
    }
    documentV3.set(activeDocument)
    const text = documentV3ToText(activeDocument)
    sourceText.set(text)
    docIrDirty.set(true)
    if (styleElement) styleElement.textContent = styleSheetForDocument(activeDocument)
    onblockedit?.({ documentV3: activeDocument, text })
    emitToolbarState()
    schedulePagination()
    if (proofPanelVisible) refreshProofIssues()
  }

  function runLegacyCommand(command: EditorCommand, commandParams: Record<string, unknown> = {}) {
    if (!editor) return
    if (command === 'copy' || command === 'cut' || command === 'paste') {
      void runClipboardCommand(command)
      return
    }
    if (command === 'find-replace') {
      findPanelVisible = !findPanelVisible
      return
    }
    if (command === 'proofread') {
      proofPanelVisible = !proofPanelVisible
      if (proofPanelVisible) refreshProofIssues()
      return
    }
    if (command === 'add-comment') {
      reviewPanelVisible = true
      return
    }
    if (command === 'track-changes') {
      if (trackChanges) flushTrackedRevision()
      trackChanges = !trackChanges
      reviewPanelVisible = true
      return
    }
    if (command === 'review-revisions') {
      flushTrackedRevision()
      reviewPanelVisible = !reviewPanelVisible
      return
    }
    if (command === 'view-outline') {
      outlineVisible = !outlineVisible
      return
    }
    if (command === 'markdown-import') {
      markdownInput?.click()
      return
    }
    if (command === 'word-import') {
      wordInput?.click()
      return
    }
    if (command === 'markdown-export') {
      prepareMarkdownExport()
      return
    }
    if (command === 'image') {
      if (!openFigureEditor()) imageInput?.click()
      return
    }
    if (command === 'diagram') {
      const spec: Record<string, unknown> = commandParams.spec && typeof commandParams.spec === 'object'
        ? commandParams.spec as Record<string, unknown>
        : {}
      const svg = String(commandParams.svg || '')
      const src = svg ? `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}` : ''
      executeDocumentCommand(editor, createUserCommand('insert_figure', {
        ...spec,
        spec,
        svg,
        src,
        editableSource: true,
        figureKind: String(commandParams.kind || spec.type || 'flow'),
        caption: String(spec.caption || '图形'),
        alt: String(spec.caption || '可编辑图形'),
        widthPercent: 100,
        alignment: 'center',
        wrap: 'inline'
      }))
      emitSelection()
      return
    }
    if (command === 'view-shortcuts') {
      shortcutPanelVisible = !shortcutPanelVisible
      return
    }
    if (command === 'style-manager') {
      styleManagerVisible = !styleManagerVisible
      if (styleManagerVisible) {
        const currentStyleId = editor.getAttributes(editor.isActive('heading') ? 'heading' : 'paragraph').styleId || 'normal'
        loadManagedStyle(String(currentStyleId))
      }
      return
    }
    if (command === 'link') {
      if (editor.state.selection.empty && editor.isActive('link')) executeDocumentCommand(editor, createUserCommand('unset_link'))
      else openReferenceDialog('link')
      return
    }
    if (command === 'math-inline') {
      openReferenceDialog('equation')
      return
    }
    if (command === 'math-block') {
      openReferenceDialog('blockEquation')
      return
    }
    if (command === 'footnote') {
      openReferenceDialog('footnote')
      return
    }
    if (command === 'endnote') {
      openReferenceDialog('endnote')
      return
    }
    if (command === 'citation') {
      openReferenceDialog('citation')
      return
    }
    if (command === 'bibliography') {
      executeDocumentCommand(editor, createUserCommand('update_bibliography', { entries: citationEntries() }))
      emitSelection()
      return
    }
    if (command === 'cross-reference') {
      openReferenceDialog('crossReference')
      return
    }
    if (command === 'toc') {
      executeDocumentCommand(editor, createUserCommand('update_table_of_contents'))
      emitSelection()
      return
    }
    if (command === 'zoom-in' || command === 'zoom-out' || command === 'zoom-100') {
      setZoom(command === 'zoom-100' ? 100 : zoomPercent + (command === 'zoom-in' ? 10 : -10))
      return
    }
    const simple: Partial<Record<EditorCommand, string>> = {
      bold: 'toggle_bold',
      italic: 'toggle_italic',
      underline: 'toggle_underline',
      strikethrough: 'toggle_strike',
      superscript: 'toggle_superscript',
      subscript: 'toggle_subscript',
      paragraph: 'apply_style',
      heading1: 'apply_style',
      heading2: 'apply_style',
      heading3: 'apply_style',
      heading4: 'apply_style',
      heading5: 'apply_style',
      heading6: 'apply_style',
      'list-bullet': 'toggle_bullet_list',
      'list-number': 'toggle_ordered_list',
      quote: 'toggle_blockquote',
      code: 'toggle_code_block',
      'clear-format': 'clear_formatting',
      undo: 'undo',
      redo: 'redo',
      image: 'insert_figure',
      table: 'insert_table',
      'table-row-before': 'table_add_row_before',
      'table-row-after': 'table_add_row_after',
      'table-row-delete': 'table_delete_row',
      'table-column-before': 'table_add_column_before',
      'table-column-after': 'table_add_column_after',
      'table-column-delete': 'table_delete_column',
      'table-merge-cells': 'table_merge_cells',
      'table-split-cell': 'table_split_cell',
      'table-toggle-header-row': 'table_toggle_header_row',
      'table-toggle-header-column': 'table_toggle_header_column',
      'table-toggle-header-cell': 'table_toggle_header_cell',
      'table-distribute-columns': 'table_distribute_columns',
      'table-distribute-rows': 'table_distribute_rows',
      'table-toggle-repeat-header': 'table_set_repeat_header',
      'table-delete': 'table_delete',
      'page-break': 'insert_page_break',
      'section-break-next': 'insert_section_break',
      'section-break-continuous': 'insert_section_break',
      hr: 'insert_horizontal_rule',
      caption: 'apply_style'
    }
    let type = simple[command]
    let params: Record<string, unknown> = { ...commandParams }
    if (command === 'paragraph') params = { styleId: 'normal' }
    if (command === 'caption') params = { styleId: 'caption' }
    if (/^heading[1-6]$/.test(command)) params = { styleId: `heading-${command.slice(-1)}` }
    if (command === 'table-toggle-repeat-header') params = { enabled: !Boolean(editor.getAttributes('table').repeatHeader) }
    if (command === 'section-break-next') params = { breakType: 'nextPage' }
    if (command === 'section-break-continuous') params = { breakType: 'continuous' }
    if (command.startsWith('style:')) {
      type = 'apply_style'
      const styleId = command.slice(6)
      const properties = activeDocument ? resolvedStyleProperties(activeDocument, styleId) : {}
      const numbering = activeDocument?.numbering.find((definition) => definition.id === properties.numberingId)
      params = {
        styleId,
        numberingId: numbering?.id || '',
        numberingLevel: properties.numberingLevel ?? 0,
        numberingFormat: numbering?.levels[properties.numberingLevel ?? 0]?.format || ''
      }
    } else if (command.startsWith('font:')) {
      type = 'set_font_family'
      params = { fontFamily: command.slice(5) }
    } else if (command.startsWith('size:')) {
      type = 'set_font_size'
      params = { fontSize: command.slice(5) }
    } else if (command.startsWith('color:')) {
      type = 'set_text_color'
      params = { color: command.slice(6) }
    } else if (command.startsWith('bgcolor:')) {
      type = 'set_highlight'
      params = { color: command.slice(8) }
    } else if (command.startsWith('table-cell-bg:')) {
      type = 'table_set_cell_background'
      params = { color: command.slice(14) === 'none' ? null : command.slice(14) }
    } else if (command.startsWith('table-cell-valign:')) {
      type = 'table_set_vertical_align'
      params = { alignment: command.slice(18) }
    } else if (command.startsWith('table-cell-border:')) {
      type = 'table_set_cell_border'
      params = { color: command.slice(18), widthPt: 0.75 }
    } else if (command.startsWith('table-row-height:')) {
      type = 'table_set_row_height'
      params = { heightPx: Number(command.slice(17)) }
    } else if (command.startsWith('table-caption:')) {
      type = 'table_set_caption'
      params = { caption: command.slice(14) }
    } else if (command.startsWith('table-align:')) {
      type = 'table_set_alignment'
      params = { alignment: command.slice(12) }
    } else if (command.startsWith('table-width:')) {
      type = 'table_set_width'
      params = { widthPercent: Number(command.slice(12)) }
    } else if (command.startsWith('align-')) {
      type = 'set_alignment'
      params = { alignment: command.slice(6) }
    } else if (command.startsWith('line-height:')) {
      type = 'set_paragraph_format'
      params = { lineSpacing: Number(command.slice(12)) }
    } else if (command === 'indent-first') {
      type = 'set_paragraph_format'
      params = { firstLineIndentEm: 2 }
    } else if (command === 'indent' || command === 'outdent') {
      if (editor.isActive('listItem')) {
        type = command === 'indent' ? 'list_indent' : 'list_outdent'
        params = {}
      } else {
      const attrs = editor.getAttributes(editor.isActive('heading') ? 'heading' : 'paragraph')
      const current = Number(attrs.leftIndentEm || 0)
      type = 'set_paragraph_format'
      params = { leftIndentEm: Math.max(0, current + (command === 'indent' ? 1 : -1)) }
      }
    } else if (command.startsWith('margin:')) {
      type = 'set_paragraph_format'
      params = { spaceBeforePt: 6, spaceAfterPt: 6 }
    } else if (command.startsWith('letter-spacing:')) {
      type = 'set_character_format'
      params = { letterSpacing: command.slice(15) }
    } else if (command.startsWith('text-transform:')) {
      type = 'set_character_format'
      params = { textTransform: command.slice(15) }
    } else if (command.startsWith('font-weight:')) {
      type = 'set_character_format'
      params = { fontWeight: command.slice(12) }
    } else if (command.startsWith('font-style:')) {
      type = 'set_character_format'
      params = { fontStyle: command.slice(11) }
    } else if (command.startsWith('font-variant:')) {
      type = 'set_character_format'
      params = { fontVariant: command.slice(13) }
    } else if (command.startsWith('text-shadow:')) {
      type = 'set_character_format'
      params = { textShadow: command.slice(12) === 'none' ? null : command.slice(12) }
    } else if (command.startsWith('space-before:')) {
      type = 'set_paragraph_format'
      params = { spaceBeforePt: Number(command.slice(13)) }
    } else if (command.startsWith('space-after:')) {
      type = 'set_paragraph_format'
      params = { spaceAfterPt: Number(command.slice(12)) }
    } else if (command.startsWith('left-indent:')) {
      type = 'set_paragraph_format'
      params = { leftIndentEm: Number(command.slice(12)) }
    } else if (command.startsWith('right-indent:')) {
      type = 'set_paragraph_format'
      params = { rightIndentEm: Number(command.slice(13)) }
    } else if (command.startsWith('first-indent:')) {
      type = 'set_paragraph_format'
      params = { firstLineIndentEm: Number(command.slice(13)) }
    } else if (command.startsWith('keep-with-next:')) {
      type = 'set_paragraph_format'
      params = { keepWithNext: command.slice(15) === 'true' }
    } else if (command.startsWith('keep-lines:')) {
      type = 'set_paragraph_format'
      params = { keepLinesTogether: command.slice(11) === 'true' }
    } else if (command.startsWith('page-break-before:')) {
      type = 'set_paragraph_format'
      params = { pageBreakBefore: command.slice(18) === 'true' }
    } else if (command.startsWith('tab-stop:')) {
      const positionEm = Number(command.slice(9))
      type = 'set_paragraph_format'
      params = { tabStops: Number.isFinite(positionEm) && positionEm > 0 ? [{ positionEm, alignment: 'left' }] : [] }
    } else if (command.startsWith('border-color:')) {
      type = 'set_paragraph_format'
      params = { borderColor: command.slice(13), borderWidthPt: 0.75, borderStyle: 'solid' }
    } else if (command.startsWith('shading-color:')) {
      type = 'set_paragraph_format'
      params = { shadingColor: command.slice(14) }
    }
    if (command === 'list-bullet') params = { numberingId: 'bullet-default', numberingLevel: 0 }
    if (command === 'list-number') params = { numberingId: 'decimal-default', numberingLevel: 0 }
    if (!type) return
    executeDocumentCommand(editor, createUserCommand(type, params))
    emitToolbarState()
  }

  async function runClipboardCommand(command: 'copy' | 'cut' | 'paste') {
    if (!editor || !navigator.clipboard) return
    try {
      if (command === 'paste') {
        const text = await navigator.clipboard.readText()
        if (!text) return
        editor.chain().focus().insertContent(plainTextToTiptapContent(text)).run()
        return
      }
      const { from, to, empty } = editor.state.selection
      if (empty) return
      const text = editor.state.doc.textBetween(from, to, '\n\n', '\n').replace(/^\n+|\n+$/g, '')
      await navigator.clipboard.writeText(text)
      if (command === 'cut') editor.chain().focus().deleteSelection().run()
    } catch {
      clipboardError = '系统未允许访问剪贴板，请使用 Ctrl+C、Ctrl+X 或 Ctrl+V。'
      if (clipboardErrorTimer) clearTimeout(clipboardErrorTimer)
      clipboardErrorTimer = setTimeout(() => (clipboardError = ''), 4000)
    }
  }

  function loadDocument(next: DocumentV3) {
    if (!editor) return
    activeDocument = next
    if (!activeDocument.numbering?.length) activeDocument.numbering = cloneJson(DEFAULT_NUMBERING)
    styleRevision += 1
    documentV3.set(next)
    styleElement && (styleElement.textContent = styleSheetForDocument(next))
    editor.commands.setContent(documentV3ToTiptap(next), { emitUpdate: false })
    applyPaperGeometry(next)
    schedulePagination(true)
    emitToolbarState()
  }

  onMount(() => {
    const stored = get(documentV3)
    activeDocument = stored && isDocumentV3(stored) ? cloneJson(stored) : migrateLegacyDocIr(get(docIr))
    if (!activeDocument.numbering?.length) activeDocument.numbering = cloneJson(DEFAULT_NUMBERING)
    documentV3.set(activeDocument)
    mountedLegacyRef = get(docIr)
    styleElement = document.createElement('style')
    styleElement.dataset.editorV3Styles = '1'
    styleElement.textContent = styleSheetForDocument(activeDocument)
    document.head.appendChild(styleElement)
    editor = createEditorKernel({
      element: host,
      document: activeDocument,
      editable: !lockEditing,
      onUpdate: updateDocument,
      onSelectionUpdate: () => emitSelection(),
      onSlashQuery: handleSlashQuery,
      onShortcutCommand: (type, params = {}) => {
        if (!editor) return false
        let commandType = type
        let commandParams = params
        if (type === 'split_with_next_style') {
          const currentStyleId = String(params.styleId || '')
          const nextStyleId = activeDocument?.styles.find((style) => style.id === currentStyleId)?.nextStyle
          if (!nextStyleId || nextStyleId === currentStyleId) return false
          commandType = 'split_block_with_style'
          commandParams = { styleId: nextStyleId }
        }
        const result = executeDocumentCommand(editor, createShortcutCommand(commandType, commandParams))
        if (result.ok) emitSelection()
        return result.ok
      }
    })
    applyPaperGeometry(activeDocument)
    schedulePagination(true)
    observedShellWidth = shell.getBoundingClientRect().width
    resizeObserver = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width || 0
      if (Math.abs(width - observedShellWidth) < 1) return
      observedShellWidth = width
      schedulePagination()
    })
    resizeObserver.observe(shell)
    window.addEventListener('wa-page-settings-changed', handlePageSettingsChanged)
    window.addEventListener('wa-editor-context', handleEditorContext)
    window.addEventListener('wa-ai-command-proposal', handleAiProposal)
    unsubscribeCommand = editorCommand.subscribe((command) => {
      if (!command || !editor) return
      if (typeof command === 'string') runLegacyCommand(command)
      else runLegacyCommand(command.command, command.params || {})
      editorCommand.set(null)
    })
    unsubscribeDocIr = docIr.subscribe((next) => {
      if (!editor || get(docIrDirty) || !next || next === mountedLegacyRef) return
      mountedLegacyRef = next
      loadDocument(migrateLegacyDocIr(next))
    })
    emitToolbarState()
  })

  $effect(() => {
    const editable = !lockEditing
    if (appliedEditable === editable) return
    appliedEditable = editable
    untrack(() => {
      if (editor && editor.isEditable !== editable) editor.setEditable(editable)
      emitToolbarState()
    })
  })

  onDestroy(() => {
    unsubscribeCommand()
    unsubscribeDocIr()
    editor?.destroy()
    styleElement?.remove()
    if (clipboardErrorTimer) clearTimeout(clipboardErrorTimer)
    if (paginationTimer) clearTimeout(paginationTimer)
    flushTrackedRevision()
    resizeObserver?.disconnect()
    stopBlockAutoScroll()
    window.removeEventListener('wa-page-settings-changed', handlePageSettingsChanged)
    window.removeEventListener('wa-editor-context', handleEditorContext)
    window.removeEventListener('wa-ai-command-proposal', handleAiProposal)
  })
</script>

<!-- svelte-ignore a11y_no_noninteractive_element_interactions: wrapper delegates input to the ProseMirror application below -->
<div
  class:paper
  class="structured-editor-shell"
  role="application"
  tabindex="-1"
  aria-label="Document V3 编辑区"
  data-page-count={pageCount}
  data-pagination-state={paginationState}
  bind:this={shell}
  onpointermove={handleEditorPointerMove}
  onkeydowncapture={handleShellKeyDown}
  ondblclick={handleObjectDoubleClick}
  onpointerleave={() => { if (!blockSelectionActive) blockHandleVisible = false }}
  onpointerup={handleBlockPointerUp}
  onpointercancel={handleBlockPointerUp}
  oncompositionstart={() => { composingText = true }}
  oncompositionend={() => { composingText = false; if (paginationPendingAfterComposition) { paginationPendingAfterComposition = false; schedulePagination() } }}
>
  <input class="hidden-file-input" bind:this={markdownInput} type="file" accept=".md,.markdown,text/markdown,text/plain" onchange={importMarkdownFile} />
  <input class="hidden-file-input" bind:this={wordInput} type="file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document" onchange={importWordFile} />
  <input class="hidden-file-input" bind:this={imageInput} type="file" accept="image/png,image/jpeg,image/gif,image/webp" onchange={importImageFile} />
  {#if blockHandleVisible}
    <button
      class="block-handle"
      style:top={`${blockHandleTop}px`}
      style:left={`${blockHandleLeft}px`}
      aria-label="选择当前块"
      title="选择块；Shift 点击选择连续块"
      onpointerdown={handleBlockPointerDown}
      onclick={handleBlockHandleClick}
    >⋮⋮</button>
  {/if}
  {#if dragTargetId}<div class="block-drop-indicator" style:top={`${dragIndicatorTop}px`}></div>{/if}
  {#if slashMenuVisible}
    <div class="slash-menu" style:top={`${slashMenuTop}px`} style:left={`${slashMenuLeft}px`} role="listbox" aria-label="插入块">
      {#each filteredSlashCommands() as item, index}
        <button
          class:active={index === slashMenuIndex}
          role="option"
          aria-selected={index === slashMenuIndex}
          onmousedown={(event) => event.preventDefault()}
          onclick={() => runSlashCommand(index)}
        >{item.label}</button>
      {/each}
      {#if !filteredSlashCommands().length}<div class="slash-empty">没有匹配的命令</div>{/if}
    </div>
  {/if}
  {#if selectionToolbarVisible}
    <div class="selection-toolbar" style:top={`${selectionToolbarTop}px`} style:left={`${selectionToolbarLeft}px`} role="toolbar" aria-label="文字选区操作">
      <button title="加粗" onmousedown={(event) => event.preventDefault()} onclick={() => runLegacyCommand('bold')}>B</button>
      <button title="斜体" onmousedown={(event) => event.preventDefault()} onclick={() => runLegacyCommand('italic')}><em>I</em></button>
      <button title="下划线" onmousedown={(event) => event.preventDefault()} onclick={() => runLegacyCommand('underline')}><u>U</u></button>
      <button title="突出显示" onmousedown={(event) => event.preventDefault()} onclick={() => runLegacyCommand('bgcolor:#fff2cc')}>▨</button>
      <button title="清除格式" onmousedown={(event) => event.preventDefault()} onclick={() => runLegacyCommand('clear-format')}>Tx</button>
      <button class="selection-ai" title="让 AI 修改所选文字" onmousedown={(event) => event.preventDefault()} onclick={requestAiForTextSelection}>AI</button>
    </div>
  {/if}
  {#if findPanelVisible}
    <div class="find-panel" role="search" aria-label="查找和替换">
      <input aria-label="查找内容" placeholder="查找" bind:value={findQuery} onkeydown={(event) => { if (event.key === 'Enter') findNext(event.shiftKey) }} />
      <input aria-label="替换内容" placeholder="替换为" bind:value={replaceText} />
      <div><button onclick={() => findNext(true)}>上一个</button><button onclick={() => findNext(false)}>下一个</button><button onclick={replaceCurrent}>替换</button><button onclick={replaceAll}>全部替换</button><button aria-label="关闭查找和替换" onclick={() => (findPanelVisible = false)}>×</button></div>
      {#if findStatus}<small>{findStatus}</small>{/if}
    </div>
  {/if}
  {#if outlineVisible}
    <aside class="outline-panel" aria-label="文档导航大纲">
      <header><strong>导航</strong><button aria-label="关闭导航" onclick={() => (outlineVisible = false)}>×</button></header>
      <div class="outline-tabs" role="tablist" aria-label="导航方式">
        <button class:active={outlineTab === 'headings'} role="tab" aria-selected={outlineTab === 'headings'} onclick={() => (outlineTab = 'headings')}>标题 {outlineHeadings().length}</button>
        <button class:active={outlineTab === 'search'} role="tab" aria-selected={outlineTab === 'search'} onclick={() => (outlineTab = 'search')}>搜索</button>
      </div>
      {#if outlineTab === 'headings'}
        <div class="outline-results">
          {#each outlineHeadings() as heading (heading.id)}
            <button style:padding-left={`${8 + (heading.level - 1) * 12}px`} onclick={() => jumpToOutline(heading.position)}>{heading.text}</button>
          {:else}<small>应用标题样式后将在这里形成文档大纲。</small>{/each}
        </div>
      {:else}
        <input class="outline-search" aria-label="搜索文档" placeholder="搜索当前文档" bind:value={outlineQuery} />
        <div class="outline-results search-results">
          {#each navigationSearchResults() as result, index (`${result.position}-${index}`)}
            <button onclick={() => jumpToOutline(result.position)}>{result.excerpt}</button>
          {:else}<small>{outlineQuery.trim() ? '没有找到匹配内容。' : '输入文字即可定位正文内容。'}</small>{/each}
        </div>
      {/if}
    </aside>
  {/if}
  {#if proofPanelVisible}
    <aside class="proof-panel" aria-label="基础校对结果">
      <header><strong>基础校对</strong><button aria-label="关闭基础校对" onclick={() => (proofPanelVisible = false)}>×</button></header>
      <p>系统拼写检查已开启；下列是可确定的文本问题。</p>
      {#each proofIssues as issue (issue.id)}
        <button class="proof-issue" onclick={() => jumpToProofIssue(issue)}><strong>{issue.message}</strong><span>{issue.excerpt}</span></button>
      {:else}<div class="proof-empty">未发现重复标点、多余空格、重复英文单词或超长句。</div>{/each}
    </aside>
  {/if}
  {#if reviewPanelVisible}
    <aside class="review-panel" aria-label="批注与修订">
      <header><strong>批注与修订</strong><button aria-label="关闭批注与修订" onclick={() => (reviewPanelVisible = false)}>×</button></header>
      <label class="track-toggle"><input type="checkbox" bind:checked={trackChanges} onchange={() => { if (!trackChanges) flushTrackedRevision() }} />记录后续修改</label>
      <div class="comment-composer">
        <textarea bind:value={commentDraft} rows="2" placeholder="为当前文字或块添加批注"></textarea>
        <button onclick={addCommentFromSelection} disabled={!commentDraft.trim()}>添加批注</button>
      </div>
      <section><h3>批注</h3>
        {#each activeDocument?.comments || [] as comment (String(comment.id))}
          <article class:resolved={Boolean(comment.resolved)}><p>{String(comment.text || '')}</p><small>{String(comment.author || '用户')}</small><button onclick={() => settleComment(String(comment.id), !Boolean(comment.resolved))}>{comment.resolved ? '重新打开' : '解决'}</button></article>
        {:else}<p class="review-empty">尚无批注。</p>{/each}
      </section>
      <section><h3>修订</h3>
        {#each documentRevisions() as revision (revision.id)}
          <article class:resolved={revision.status !== 'pending'}><p>{revision.summary}</p><small>{revision.author} · {new Date(revision.createdAt).toLocaleString()}</small>
            {#if revision.status === 'pending'}<div><button onclick={() => settleTrackedRevision(revision.id, true)}>接受</button><button onclick={() => settleTrackedRevision(revision.id, false)}>拒绝</button></div>{:else}<span>{revision.status === 'accepted' ? '已接受' : '已拒绝'}</span>{/if}
          </article>
        {:else}<p class="review-empty">尚无修订记录。</p>{/each}
      </section>
      <section><h3>AI 修改建议</h3>
        {#each aiProposals as proposal (proposal.command.id)}
          <article><p>{proposal.command.type} · {proposal.command.target.kind}</p><small>等待确认，不会自动改动正文</small><div><button onclick={() => settleAiProposal(proposal.command.id, true)}>应用</button><button onclick={() => settleAiProposal(proposal.command.id, false)}>拒绝</button></div></article>
        {:else}<p class="review-empty">没有待处理的 AI 建议。</p>{/each}
      </section>
    </aside>
  {/if}
  {#if shortcutPanelVisible}
    <aside class="shortcut-panel" aria-label="编辑快捷键">
      <header><strong>编辑快捷键</strong><button aria-label="关闭快捷键" onclick={() => (shortcutPanelVisible = false)}>×</button></header>
      <dl>
        <dt>Ctrl / ⌘ + Alt + 0</dt><dd>转为正文</dd>
        <dt>Ctrl / ⌘ + Alt + 1–3</dt><dd>转为标题 1–3</dd>
        <dt>Alt + Shift + ↑ / ↓</dt><dd>移动当前段落或所选块</dd>
        <dt>Ctrl / ⌘ + Shift + Space</dt><dd>选择当前块</dd>
        <dt>↑ / ↓（已选块）</dt><dd>选择相邻块</dd>
        <dt>Esc / Enter（已选块）</dt><dd>回到文字编辑</dd>
      </dl>
      <p>输入法正在组合文字时，系统不会接管这些快捷键。</p>
    </aside>
  {/if}
  {#if styleManagerVisible}
    <aside class="style-manager" aria-label="文档样式管理">
      <header><strong>文档样式</strong><button aria-label="关闭样式管理" onclick={() => (styleManagerVisible = false)}>×</button></header>
      <div class="style-manager-actions">
        <select aria-label="选择要编辑的样式" value={managedStyleId} onchange={(event) => loadManagedStyle(event.currentTarget.value)}>
          {#each visibleStyles() as style (style.id)}<option value={style.id}>{style.name}</option>{/each}
          {#if creatingStyle}<option value={managedStyleId}>{managedStyleName}</option>{/if}
        </select>
        <button onclick={beginCreateStyle}>基于当前格式新建</button>
      </div>
      <label>名称<input bind:value={managedStyleName} /></label>
      <div class="style-preview" style={previewStyle()}><span>样式预览：中文正文与 English 123</span></div>
      <div class="style-grid">
        <label>基于<select bind:value={managedBasedOn}><option value="">无</option>{#each visibleStyles().filter((style) => style.id !== managedStyleId) as style}<option value={style.id}>{style.name}</option>{/each}</select></label>
        <label>后续段落<select bind:value={managedNextStyle}>{#each visibleStyles() as style}<option value={style.id}>{style.name}</option>{/each}</select></label>
        <label>字体<input bind:value={managedFontFamily} placeholder="继承" /></label>
        <label>字号 pt<input type="number" min="6" max="96" step="0.5" bind:value={managedFontSizePt} /></label>
        <label>文字颜色<input bind:value={managedColor} placeholder="#000000；留空继承" /></label>
        <label>文字底色<input bind:value={managedBackgroundColor} placeholder="#ffffff；留空继承" /></label>
        <label>字间距 pt<input type="number" min="-5" max="30" step="0.1" bind:value={managedLetterSpacingPt} /></label>
        <label>大小写<select bind:value={managedTextTransform}><option value="">继承</option><option value="none">无转换</option><option value="uppercase">大写</option><option value="lowercase">小写</option><option value="capitalize">首字母大写</option></select></label>
        <label>对齐<select bind:value={managedAlignment}><option value="">继承</option><option value="left">左对齐</option><option value="center">居中</option><option value="right">右对齐</option><option value="justify">两端对齐</option></select></label>
        <label>行距<input type="number" min="0.8" max="4" step="0.05" bind:value={managedLineSpacing} /></label>
        <label>首行缩进 em<input type="number" min="-10" max="20" step="0.5" bind:value={managedFirstLineIndentEm} /></label>
        <label>左缩进 em<input type="number" min="-10" max="40" step="0.5" bind:value={managedLeftIndentEm} /></label>
        <label>右缩进 em<input type="number" min="-10" max="40" step="0.5" bind:value={managedRightIndentEm} /></label>
        <label>段前 pt<input type="number" min="0" max="144" bind:value={managedSpaceBeforePt} /></label>
        <label>段后 pt<input type="number" min="0" max="144" bind:value={managedSpaceAfterPt} /></label>
        <label>大纲级别<input type="number" min="0" max="9" step="1" bind:value={managedOutlineLevel} /></label>
        <label>边框样式<select bind:value={managedBorderStyle}><option value="">继承</option><option value="none">无</option><option value="solid">实线</option><option value="dashed">虚线</option><option value="double">双线</option></select></label>
        <label>边框颜色<input bind:value={managedBorderColor} placeholder="#000000；留空继承" /></label>
        <label>边框宽度 pt<input type="number" min="0" max="12" step="0.25" bind:value={managedBorderWidthPt} /></label>
        <label>段落底纹<input bind:value={managedShadingColor} placeholder="#ffffff；留空继承" /></label>
        <label>项目符号/编号<select bind:value={managedNumberingId}><option value="">无或继承</option>{#each activeDocument?.numbering || [] as definition (definition.id)}<option value={definition.id}>{definition.name}</option>{/each}</select></label>
        <label>编号级别<select bind:value={managedNumberingLevel} disabled={!managedNumberingId}>{#each Array.from({ length: 9 }, (_, index) => index) as level}<option value={level}>级别 {level + 1}</option>{/each}</select></label>
      </div>
      <div class="style-grid style-toggles">
        <label>加粗<select bind:value={managedBold}><option value="inherit">继承</option><option value="on">开启</option><option value="off">关闭</option></select></label>
        <label>斜体<select bind:value={managedItalic}><option value="inherit">继承</option><option value="on">开启</option><option value="off">关闭</option></select></label>
        <label>下划线<select bind:value={managedUnderline}><option value="inherit">继承</option><option value="on">开启</option><option value="off">关闭</option></select></label>
        <label>与下段同页<select bind:value={managedKeepWithNext}><option value="inherit">继承</option><option value="on">开启</option><option value="off">关闭</option></select></label>
        <label>段中不分页<select bind:value={managedKeepLinesTogether}><option value="inherit">继承</option><option value="on">开启</option><option value="off">关闭</option></select></label>
        <label>段前分页<select bind:value={managedPageBreakBefore}><option value="inherit">继承</option><option value="on">开启</option><option value="off">关闭</option></select></label>
      </div>
      <label>制表位<input bind:value={managedTabStops} placeholder="例如 4:left, 12:decimal" /></label>
      {#if styleManagerNotice}<p>{styleManagerNotice}</p>{/if}
      <footer class="style-manager-footer">
        <button onclick={duplicateManagedStyle}>复制</button>
        <button onclick={resetManagedStyle}>恢复默认</button>
        <button class="danger" onclick={deleteManagedStyle}>删除</button>
        <span></span>
        <button onclick={applyManagedStyle}>应用到所选段落</button>
        <button class="primary" onclick={saveManagedStyle}>保存并全局更新</button>
      </footer>
    </aside>
  {/if}
  {#if referenceDialog}
    <div class="reference-dialog-backdrop" role="presentation">
      <form class="reference-dialog" aria-label="插入引用对象" onsubmit={(event) => { event.preventDefault(); applyReferenceDialog() }}>
        <header>
          <strong>{referenceDialog === 'link' ? '插入链接' : referenceDialog === 'equation' ? '插入行内公式' : referenceDialog === 'blockEquation' ? '编辑公式块' : referenceDialog === 'footnote' ? '插入脚注' : referenceDialog === 'endnote' ? '插入尾注' : referenceDialog === 'citation' ? '插入引文' : '插入交叉引用'}</strong>
          <button type="button" aria-label="关闭引用对象窗口" onclick={() => (referenceDialog = '')}>×</button>
        </header>
        {#if referenceDialog === 'link'}
          <label>地址<input bind:value={referenceHref} placeholder="https://example.com 或 #书签" /></label>
          <label>提示文字<input bind:value={referenceTitle} placeholder="可选" /></label>
          <p>先选择文字再插入链接；光标位于已有链接中时可再次编辑。</p>
        {:else if referenceDialog === 'equation' || referenceDialog === 'blockEquation'}
          <label>LaTeX<input bind:value={referenceLatex} placeholder="例如 E = mc^2" /></label>
        {:else if referenceDialog === 'footnote' || referenceDialog === 'endnote'}
          <label>{referenceDialog === 'footnote' ? '脚注' : '尾注'}内容<textarea bind:value={referenceNoteText} rows="4"></textarea></label>
          <p>注释正文保存在 Document V3 的 notes 中，正文只保存稳定引用 ID。</p>
        {:else if referenceDialog === 'citation'}
          <label>文献<select bind:value={referenceCitationId}>{#each citationEntries() as citation (citation.id)}<option value={citation.id}>{citation.label} {citation.text}</option>{/each}</select></label>
          {#if !citationEntries().length}<p>请先在引文管理中添加文献。</p>{/if}
        {:else}
          <label>引用标题<select bind:value={referenceTargetId}>
            {#each outlineHeadings() as heading (heading.id)}
              <option value={heading.id}>{'　'.repeat(Math.max(0, heading.level - 1))}{heading.text}</option>
            {/each}
          </select></label>
          {#if !outlineHeadings().length}<p>当前文档还没有可引用的标题。</p>{/if}
        {/if}
        <footer><button type="button" onclick={() => (referenceDialog = '')}>取消</button><button class="primary" type="submit">插入</button></footer>
      </form>
    </div>
  {/if}
  {#if figureDialogVisible}
    <div class="reference-dialog-backdrop" role="presentation">
      <form class="reference-dialog" aria-label="图片属性" onsubmit={(event) => { event.preventDefault(); void applyFigureSettings() }}>
        <header><strong>图片属性</strong><button type="button" aria-label="关闭图片属性" onclick={() => (figureDialogVisible = false)}>×</button></header>
        <label>题注<input bind:value={figureCaption} placeholder="例如：图 1 系统架构" /></label>
        <label>替代文字<input bind:value={figureAlt} placeholder="用于无障碍和导出" /></label>
        <label>宽度 {figureWidthPercent}%<input type="range" min="10" max="100" step="5" bind:value={figureWidthPercent} /></label>
        <label>对齐<select bind:value={figureAlignment}><option value="left">左对齐</option><option value="center">居中</option><option value="right">右对齐</option></select></label>
        <label>环绕<select bind:value={figureWrap}><option value="inline">嵌入型</option><option value="square">四周型</option></select></label>
        <label>裁剪方式<select bind:value={figureCrop}><option value="none">完整显示</option><option value="fill">拉伸填充</option><option value="cover">裁剪填充</option></select></label>
        {#if figureSourceSpec}
          <label>修改图表内容<textarea bind:value={figureEditInstruction} rows="3" placeholder="例如：增加审核节点，并用虚线表示退回路径"></textarea></label>
          <button type="button" class="secondary" disabled={figureRegenerating || !figureEditInstruction.trim()} onclick={regenerateFigureFromInstruction}>{figureRegenerating ? '正在修改…' : '按要求修改图表'}</button>
          <p>图表源数据会随文档保存，无需手动编辑代码。</p>
        {/if}
        <footer><button type="button" onclick={() => (figureDialogVisible = false)}>取消</button><button class="primary" type="submit">应用</button></footer>
      </form>
    </div>
  {/if}
  {#if markdownExportVisible}
    <div class="markdown-dialog-backdrop" role="presentation">
      <div class="markdown-dialog" role="dialog" aria-modal="true" aria-labelledby="markdown-export-title" tabindex="-1">
        <header><strong id="markdown-export-title">导出 Markdown</strong><button aria-label="取消导出 Markdown" onclick={() => (markdownExportVisible = false)}>×</button></header>
        <p>Markdown 适合交换纯文本结构，不是本软件的主文档格式。导出不会修改当前 Document V3 文档。</p>
        <ul>{#each markdownExportWarnings as warning}<li>{warning}</li>{/each}</ul>
        <div><button onclick={() => (markdownExportVisible = false)}>取消</button><button class="primary" onclick={downloadMarkdown}>了解并导出</button></div>
      </div>
    </div>
  {/if}
  {#if blockSelectionActive && selectedBlockIds.length}
    <div class="block-actions" style:top={`${blockHandleTop}px`} style:left={`${blockHandleLeft + 32}px`} role="toolbar" aria-label="块操作">
      <button title="在前面插入段落" aria-label="在前面插入段落" onmousedown={(event) => event.preventDefault()} onclick={() => runBlockCommand('insert_block_before')}>＋↑</button>
      <button title="在后面插入段落" aria-label="在后面插入段落" onmousedown={(event) => event.preventDefault()} onclick={() => runBlockCommand('insert_block_after')}>＋↓</button>
      <button title="上移块" aria-label="上移块" onmousedown={(event) => event.preventDefault()} onclick={() => runBlockCommand('move_block_up')}>↑</button>
      <button title="下移块" aria-label="下移块" onmousedown={(event) => event.preventDefault()} onclick={() => runBlockCommand('move_block_down')}>↓</button>
      <button title="复制块内容" aria-label="复制块内容" onmousedown={(event) => event.preventDefault()} onclick={copySelectedBlockContent}>⎘</button>
      <button title="创建块副本" aria-label="创建块副本" onmousedown={(event) => event.preventDefault()} onclick={() => runBlockCommand('duplicate_block')}>⧉</button>
      <button title={selectedBlocksCollapsed ? '展开块' : '折叠块'} aria-label={selectedBlocksCollapsed ? '展开块' : '折叠块'} onmousedown={(event) => event.preventDefault()} onclick={() => runBlockCommand('toggle_block_collapsed')}>{selectedBlocksCollapsed ? '▾' : '▸'}</button>
      <button class="ai" title="使用 AI 处理所选块" aria-label="使用 AI 处理所选块" onmousedown={(event) => event.preventDefault()} onclick={openBlockAi}>AI</button>
      <select title="转换块类型" aria-label="转换块类型" onchange={convertSelectedBlock}>
        <option value="">转换</option>
        <option value="paragraph">正文</option>
        <option value="heading-1">标题 1</option>
        <option value="heading-2">标题 2</option>
        <option value="heading-3">标题 3</option>
        <option value="blockquote">引用</option>
        <option value="codeBlock">代码</option>
        <option value="bulletList">项目列表</option>
        <option value="orderedList">编号列表</option>
      </select>
      <button class="danger" title="删除块" aria-label="删除块" onmousedown={(event) => event.preventDefault()} onclick={() => runBlockCommand('delete_block')}>×</button>
    </div>
  {/if}
  <div class="structured-editor" bind:this={host}></div>
  {#if clipboardError}<div class="clipboard-error" role="status">{clipboardError}</div>{/if}
  {#if markdownNotice}<div class="markdown-notice" role="status"><span>{markdownNotice}</span><button aria-label="关闭 Markdown 提示" onclick={() => (markdownNotice = '')}>×</button></div>{/if}
  {#if objectNotice}<div class="markdown-notice" role="status"><span>{objectNotice}</span><button aria-label="关闭对象提示" onclick={() => (objectNotice = '')}>×</button></div>{/if}
</div>

<style>
  .structured-editor-shell {
    position: relative;
    box-sizing: border-box;
    width: min(100%, var(--page-width, 21cm));
    min-height: var(--page-height, 29.7cm);
    margin: 0 auto 64px;
    background: #fff;
    color: #1f2328;
    zoom: var(--editor-zoom, 1);
  }
  .hidden-file-input { display: none; }
  .structured-editor-shell.paper {
    padding: var(--margin-top, 2.54cm) var(--margin-right, 2.54cm) var(--margin-bottom, 2.54cm) var(--margin-left, 3.18cm);
    border: 1px solid #d7dde5;
    border-radius: 3px;
    box-shadow: 0 8px 28px rgba(38, 50, 66, 0.12);
  }
  .structured-editor-shell:not(.paper) {
    width: min(100%, 1100px);
    min-height: calc(100vh - 220px);
    padding: 52px clamp(40px, 8vw, 96px) 96px;
    border: 1px solid #dfe3e8;
    border-radius: 3px;
  }
  .structured-editor-shell:not(.paper) :global(.wa-page-boundary),
  .structured-editor-shell:not(.paper) :global(.wa-page-end),
  .structured-editor-shell:not(.paper) :global(.wa-first-page-header) { display: none; }
  .structured-editor :global(.tiptap) {
    min-height: 24cm;
    outline: none;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    caret-color: #1a73e8;
  }
  .structured-editor :global(.tiptap p),
  .structured-editor :global(.tiptap h1),
  .structured-editor :global(.tiptap h2),
  .structured-editor :global(.tiptap h3),
  .structured-editor :global(.tiptap h4),
  .structured-editor :global(.tiptap h5),
  .structured-editor :global(.tiptap h6) {
    min-height: 1.35em;
    border-radius: 2px;
    transition: background-color 80ms ease, box-shadow 80ms ease;
  }
  .structured-editor :global(.tiptap > [data-collapsed="true"]) {
    position: relative;
    max-height: 1.45em;
    overflow: hidden;
    padding-right: 24px;
    white-space: nowrap;
    text-overflow: ellipsis;
  }
  .structured-editor :global(.tiptap > [data-collapsed="true"]::after) {
    position: absolute;
    right: 4px;
    bottom: 0;
    content: '…';
    color: #6f7b8d;
    background: #fff;
    pointer-events: none;
  }
  .structured-editor :global(.tiptap > [data-node-id]:hover) {
    box-shadow: inset 2px 0 0 #c7d8f4;
  }
  .structured-editor :global(.tiptap > .ProseMirror-selectednode) {
    background: #eef5ff;
    box-shadow: inset 3px 0 0 #2f6fca;
    outline: none;
  }
  .block-handle {
    position: absolute;
    z-index: 3;
    display: grid;
    width: 24px;
    height: 24px;
    place-items: center;
    padding: 0;
    border: 0;
    border-radius: 4px;
    background: transparent;
    color: #8a94a4;
    cursor: grab;
    font-size: 15px;
    line-height: 1;
  }
  .block-handle:hover,
  .block-handle:focus-visible {
    background: #e8eef7;
    color: #2f5f9f;
    outline: none;
  }
  .block-actions {
    position: absolute;
    z-index: 4;
    display: flex;
    gap: 2px;
    padding: 2px;
    border: 1px solid #d5dce7;
    border-radius: 5px;
    background: #fff;
    box-shadow: 0 4px 12px rgba(38, 50, 66, 0.12);
    transform: translateY(-32px);
  }
  .selection-toolbar {
    position: absolute;
    z-index: 9;
    display: flex;
    gap: 2px;
    padding: 3px;
    border: 1px solid #cfd6e2;
    border-radius: 6px;
    background: #fff;
    box-shadow: 0 6px 18px rgba(32, 45, 64, .18);
  }
  .selection-toolbar button { min-width: 30px; height: 28px; border: 0; border-radius: 3px; background: transparent; color: #263244; cursor: pointer; }
  .selection-toolbar button:hover { background: #edf3fb; }
  .selection-toolbar .selection-ai { min-width: 36px; margin-left: 2px; background: #eaf2ff; color: #1d5fbf; font-weight: 700; }
  .selection-toolbar .selection-ai:hover { background: #dceaff; }
  .find-panel {
    position: absolute;
    z-index: 10;
    top: 10px;
    right: 10px;
    display: grid;
    width: 260px;
    gap: 6px;
    padding: 10px;
    border: 1px solid #cfd6e2;
    border-radius: 6px;
    background: #fff;
    box-shadow: 0 8px 24px rgba(32, 45, 64, .16);
  }
  .find-panel input { box-sizing: border-box; width: 100%; height: 30px; border: 1px solid #cbd2dc; border-radius: 4px; padding: 4px 7px; }
  .find-panel div { display: flex; gap: 4px; flex-wrap: wrap; }
  .find-panel button { height: 27px; border: 1px solid #d5dbe4; border-radius: 4px; background: #fff; cursor: pointer; }
  .find-panel small { color: #667085; }
  .outline-panel {
    position: absolute;
    z-index: 7;
    top: 0;
    right: calc(100% + 14px);
    display: grid;
    width: 210px;
    max-height: 70vh;
    gap: 2px;
    overflow: hidden;
    padding: 10px;
    border: 1px solid #d5dce7;
    border-radius: 6px;
    background: #fff;
    box-shadow: 0 5px 18px rgba(38, 50, 66, .12);
  }
  .outline-panel header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; }
  .outline-panel header button { padding: 0 4px; color: #667085; font-size: 18px; }
  .outline-tabs { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; padding-bottom: 6px; border-bottom: 1px solid #e4e7ec; }
  .outline-tabs button { text-align: center; }
  .outline-tabs button.active { background: #eaf2ff; color: #1d5fbf; font-weight: 600; }
  .outline-search { box-sizing: border-box; width: 100%; height: 30px; margin: 4px 0; padding: 0 8px; border: 1px solid #cfd6e2; border-radius: 4px; outline: none; }
  .outline-search:focus { border-color: #6b9ddd; box-shadow: 0 0 0 2px rgba(37,99,235,.08); }
  .outline-results { display: grid; max-height: calc(70vh - 92px); gap: 2px; overflow: auto; }
  .outline-results small { padding: 10px 6px; color: #7a8494; line-height: 1.5; }
  .outline-panel button { overflow: hidden; padding-block: 6px; border: 0; border-radius: 3px; background: transparent; color: #344054; text-align: left; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; }
  .outline-results.search-results button { white-space: normal; line-height: 1.45; }
  .outline-panel button:hover { background: #edf3fb; }
  .proof-panel {
    position: absolute;
    z-index: 10;
    top: 10px;
    left: calc(100% + 14px);
    display: grid;
    width: 250px;
    max-height: 70vh;
    gap: 6px;
    overflow: auto;
    padding: 10px;
    border: 1px solid #d5dce7;
    border-radius: 6px;
    background: #fff;
    box-shadow: 0 5px 18px rgba(38, 50, 66, .12);
  }
  .review-panel { position: absolute; z-index: 12; top: 10px; left: calc(100% + 14px); box-sizing: border-box; display: grid; width: 300px; max-height: 78vh; gap: 10px; overflow: auto; padding: 12px; border: 1px solid #d5dce7; border-radius: 7px; background: #fff; color: #263244; box-shadow: 0 8px 28px rgba(32,45,64,.16); font-size: 12px; }
  .review-panel > header { display: flex; align-items: center; justify-content: space-between; }
  .review-panel > header button { border: 0; background: transparent; font-size: 19px; cursor: pointer; }
  .track-toggle { display: flex; align-items: center; gap: 6px; color: #334155; }
  .comment-composer { display: grid; gap: 6px; }
  .comment-composer textarea { resize: vertical; }
  .review-panel textarea, .review-panel button { box-sizing: border-box; padding: 6px 8px; border: 1px solid #ccd5e1; border-radius: 4px; background: #fff; color: inherit; font: inherit; }
  .review-panel button { cursor: pointer; }
  .review-panel section { display: grid; gap: 6px; border-top: 1px solid #e5e9ef; padding-top: 8px; }
  .review-panel h3 { margin: 0; font-size: 12px; }
  .review-panel article { display: grid; gap: 5px; padding: 8px; border: 1px solid #dce3ec; border-radius: 5px; background: #f8fafc; }
  .review-panel article.resolved { opacity: .64; }
  .review-panel article p, .review-panel article small { margin: 0; overflow-wrap: anywhere; }
  .review-panel article small, .review-empty { color: #718096; }
  .review-panel article div { display: flex; gap: 5px; }
  .shortcut-panel {
    position: absolute;
    z-index: 10;
    top: 10px;
    right: 10px;
    width: 310px;
    padding: 12px;
    border: 1px solid #d5dce7;
    border-radius: 6px;
    background: #fff;
    box-shadow: 0 8px 24px rgba(32, 45, 64, .16);
  }
  .shortcut-panel header { display: flex; align-items: center; justify-content: space-between; }
  .shortcut-panel header button { border: 0; background: transparent; font-size: 18px; cursor: pointer; }
  .shortcut-panel dl { display: grid; grid-template-columns: 1.35fr 1fr; gap: 7px 12px; margin: 12px 0; font-size: 12px; }
  .shortcut-panel dt { color: #253858; font-family: Consolas, monospace; }
  .shortcut-panel dd { margin: 0; color: #536174; }
  .shortcut-panel p { margin: 0; color: #7a8594; font-size: 11px; }
  .style-manager { position: absolute; z-index: 11; top: 10px; right: 10px; box-sizing: border-box; width: min(560px, calc(100% - 20px)); max-height: calc(100% - 20px); overflow: auto; padding: 13px; border: 1px solid #cfd7e2; border-radius: 7px; background: #fff; box-shadow: 0 10px 30px rgba(30, 43, 62, .18); color: #263244; font-size: 12px; }
  .style-manager header, .style-manager footer, .style-manager-actions { display: flex; align-items: center; gap: 8px; }
  .style-manager header { justify-content: space-between; margin-bottom: 10px; font-size: 15px; }
  .style-manager header button { border: 0; background: transparent; font-size: 19px; cursor: pointer; }
  .style-manager-actions select { flex: 1; }
  .style-manager label { display: grid; gap: 3px; margin-top: 8px; color: #5b6675; }
  .style-manager input, .style-manager select, .style-manager button { box-sizing: border-box; min-height: 29px; border: 1px solid #cfd6e1; border-radius: 4px; background: #fff; color: #263244; }
  .style-manager button { padding: 4px 8px; cursor: pointer; }
  .style-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 9px; }
  .style-preview { box-sizing: border-box; min-height: 58px; margin-top: 10px; padding: 12px; overflow: hidden; border: 1px solid #dbe1e9; border-radius: 4px; background: #fff; }
  .style-preview span { display: block; }
  .style-toggles { margin-top: 6px; padding-top: 3px; border-top: 1px solid #edf0f4; }
  .style-manager p { margin: 8px 0 0; color: #28639e; }
  .style-manager footer { justify-content: flex-end; flex-wrap: wrap; margin-top: 12px; }
  .style-manager-footer span { flex: 1; }
  .style-manager footer .danger { border-color: #d8a6a6; color: #a22323; }
  .style-manager footer .primary { border-color: #2468c8; background: #2468c8; color: #fff; }
  .markdown-dialog-backdrop { position: fixed; z-index: 30; inset: 0; display: grid; place-items: center; background: rgba(20, 29, 43, .28); }
  .reference-dialog-backdrop { position: fixed; z-index: 31; inset: 0; display: grid; place-items: center; background: rgba(20, 29, 43, .28); }
  .reference-dialog { box-sizing: border-box; display: grid; width: min(440px, calc(100vw - 32px)); gap: 11px; padding: 17px; border: 1px solid #ccd4df; border-radius: 8px; background: #fff; box-shadow: 0 18px 55px rgba(22, 34, 51, .22); color: #263244; }
  .reference-dialog header, .reference-dialog footer { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .reference-dialog header button { border: 0; background: transparent; font-size: 20px; cursor: pointer; }
  .reference-dialog label { display: grid; gap: 4px; color: #536174; font-size: 12px; }
  .reference-dialog input, .reference-dialog textarea, .reference-dialog select { box-sizing: border-box; width: 100%; min-height: 32px; padding: 6px 8px; border: 1px solid #cbd3df; border-radius: 5px; background: #fff; color: #263244; font: inherit; }
  .reference-dialog p { margin: 0; color: #687386; font-size: 11px; line-height: 1.5; }
  .reference-dialog footer { justify-content: flex-end; }
  .reference-dialog footer button { padding: 7px 14px; border: 1px solid #cbd3df; border-radius: 5px; background: #fff; cursor: pointer; }
  .reference-dialog footer button.primary { border-color: #2468c8; background: #2468c8; color: #fff; }
  .markdown-dialog { box-sizing: border-box; width: min(540px, calc(100vw - 32px)); padding: 18px; border: 1px solid #ccd4df; border-radius: 8px; background: #fff; box-shadow: 0 18px 55px rgba(22, 34, 51, .22); }
  .markdown-dialog header { display: flex; align-items: center; justify-content: space-between; font-size: 16px; }
  .markdown-dialog header button { border: 0; background: transparent; font-size: 20px; cursor: pointer; }
  .markdown-dialog p, .markdown-dialog li { color: #536174; font-size: 12px; line-height: 1.6; }
  .markdown-dialog > div { display: flex; justify-content: flex-end; gap: 8px; }
  .markdown-dialog > div button { padding: 7px 14px; border: 1px solid #cbd3df; border-radius: 5px; background: #fff; cursor: pointer; }
  .markdown-dialog > div button.primary { border-color: #2468c8; background: #2468c8; color: #fff; }
  .proof-panel header { display: flex; align-items: center; justify-content: space-between; }
  .proof-panel header button { border: 0; background: transparent; font-size: 18px; cursor: pointer; }
  .proof-panel p, .proof-empty { margin: 0; color: #687386; font-size: 11px; line-height: 1.5; }
  .proof-issue { display: grid; gap: 3px; padding: 7px; border: 0; border-radius: 4px; background: #fff8e6; color: #614a13; text-align: left; cursor: pointer; }
  .proof-issue span { overflow: hidden; color: #75632f; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
  .block-actions button {
    display: grid;
    width: 25px;
    height: 25px;
    place-items: center;
    padding: 0;
    border: 0;
    border-radius: 3px;
    background: transparent;
    color: #4d596a;
    cursor: pointer;
  }
  .block-actions select {
    height: 25px;
    border: 0;
    border-radius: 3px;
    background: transparent;
    color: #4d596a;
    font-size: 12px;
  }
  .block-drop-indicator {
    position: absolute;
    z-index: 5;
    right: 0;
    left: 0;
    height: 2px;
    background: #2f6fca;
    pointer-events: none;
  }
  .slash-menu {
    position: absolute;
    z-index: 8;
    display: grid;
    width: 184px;
    max-height: 280px;
    overflow: auto;
    padding: 4px;
    border: 1px solid #d5dce7;
    border-radius: 6px;
    background: #fff;
    box-shadow: 0 10px 28px rgba(38, 50, 66, 0.18);
  }
  .slash-menu button {
    padding: 7px 9px;
    border: 0;
    border-radius: 4px;
    background: transparent;
    color: #263244;
    text-align: left;
  }
  .slash-menu button:hover,
  .slash-menu button.active {
    background: #edf3fb;
  }
  .slash-empty {
    padding: 8px;
    color: #7a8594;
    font-size: 12px;
  }
  .block-actions button:hover,
  .block-actions button:focus-visible {
    background: #edf3fb;
    outline: none;
  }
  .block-actions button.danger:hover,
  .block-actions button.danger:focus-visible {
    background: #fff0f0;
    color: #b42318;
  }
  .block-actions button.ai { width: 30px; color: #205db0; font-size: 10px; font-weight: 700; }
  .structured-editor :global(.tiptap p.is-editor-empty:first-child::before) {
    color: #99a1ad;
    content: '开始输入正文…';
    float: left;
    height: 0;
    pointer-events: none;
  }
  .structured-editor :global(.v3-object) {
    margin: 14px 0;
    padding: 18px;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    background: #f8fafc;
    color: #475569;
    text-align: center;
    user-select: none;
  }
  .structured-editor :global(.v3-inline-object) { display: inline-block; margin: 0 2px; padding: 0 3px; border-radius: 3px; background: #eef4ff; color: #205dab; font-size: .86em; cursor: pointer; user-select: all; }
  .structured-editor :global(.v3-inline-inlineEquation) { background: #f6f3ff; color: #5b3f91; font-family: Cambria Math, serif; }
  .structured-editor :global(a[data-type="link"]), .structured-editor :global(a[href]) { color: #1d5fa7; text-decoration: underline; }
  .structured-editor :global(.v3-object-pageBreak),
  .structured-editor :global(.v3-object-sectionBreak) {
    padding: 0;
    border-width: 1px 0 0;
    border-style: dashed;
    border-radius: 0;
    background: transparent;
    font-size: 11px;
  }
  .structured-editor :global(.v3-object-figure) { padding: 10px; background: #fff; }
  .structured-editor :global(.v3-object-figure[data-wrap="square"][data-alignment="left"]) { float: left; max-width: 52%; margin: 0 18px 12px 0; }
  .structured-editor :global(.v3-object-figure[data-wrap="square"][data-alignment="right"]) { float: right; max-width: 52%; margin: 0 0 12px 18px; }
  .structured-editor :global(.v3-object-figure img) { display: block; max-width: 100%; max-height: 560px; margin: 0 auto; object-fit: contain; }
  .structured-editor :global(.v3-object-figure[data-crop="fill"] img) { width: 100%; height: 320px; object-fit: fill; }
  .structured-editor :global(.v3-object-figure[data-crop="cover"] img) { width: 100%; height: 320px; object-fit: cover; }
  .structured-editor :global(.v3-object-figure figcaption) { margin-top: 8px; color: #586577; font-size: 12px; text-align: center; }
  .structured-editor :global(.v3-figure-placeholder) { padding: 24px; background: #f8fafc; }
  .structured-editor :global(.v3-object-tableOfContents) { display: grid; gap: 7px; padding: 16px 20px; background: #fff; text-align: left; }
  .structured-editor :global(.v3-toc-title) { margin-bottom: 5px; color: #1f2937; font-size: 18px; text-align: center; }
  .structured-editor :global(.v3-toc-entry) { display: flex; align-items: baseline; gap: 5px; color: #344054; font-size: 12px; }
  .structured-editor :global(.v3-toc-entry[data-level="2"]) { padding-left: 1.5em; }
  .structured-editor :global(.v3-toc-entry[data-level="3"]) { padding-left: 3em; }
  .structured-editor :global(.v3-toc-entry[data-level="4"]),
  .structured-editor :global(.v3-toc-entry[data-level="5"]),
  .structured-editor :global(.v3-toc-entry[data-level="6"]) { padding-left: 4.5em; }
  .structured-editor :global(.v3-toc-leader) { flex: 1; border-bottom: 1px dotted #98a2b3; }
  .structured-editor :global(.v3-toc-page) { color: #667085; }
  .structured-editor :global(.tableWrapper) {
    margin: 14px 0;
    overflow-x: auto;
  }
  .structured-editor :global(table) {
    width: 100%;
    table-layout: fixed;
    border-collapse: collapse;
    background: #fff;
  }
  .structured-editor :global(th),
  .structured-editor :global(td) {
    position: relative;
    min-width: 72px;
    padding: 7px 9px;
    border: 1px solid #aeb7c3;
    vertical-align: top;
    text-align: left;
  }
  .structured-editor :global(th) {
    background: #eef3f8;
    font-weight: 600;
  }
  .structured-editor :global(th p),
  .structured-editor :global(td p) {
    margin: 0;
    min-height: 1.4em;
  }
  .structured-editor :global(.selectedCell::after) {
    position: absolute;
    inset: 0;
    content: '';
    pointer-events: none;
    background: rgb(43 111 210 / 12%);
  }
  .structured-editor :global(.column-resize-handle) {
    position: absolute;
    top: 0;
    right: -2px;
    bottom: 0;
    width: 4px;
    background: #2b6fd2;
    pointer-events: none;
  }
  .structured-editor :global(.wa-page-boundary),
  .structured-editor :global(.wa-page-end) {
    position: relative;
    display: grid;
    box-sizing: border-box;
    width: calc(100% + var(--margin-left, 3.18cm) + var(--margin-right, 2.54cm));
    min-height: 44px;
    margin: var(--margin-bottom, 2.54cm) calc(-1 * var(--margin-right, 2.54cm)) var(--margin-top, 2.54cm) calc(-1 * var(--margin-left, 3.18cm));
    padding: 8px var(--margin-right, 2.54cm) 8px var(--margin-left, 3.18cm);
    border-top: 12px solid #e8ebf0;
    color: #7a828d;
    font: 11px/1.4 "Segoe UI", sans-serif;
    pointer-events: none;
  }
  .structured-editor :global(.wa-page-end) {
    min-height: 24px;
    margin-bottom: calc(-1 * var(--margin-bottom, 2.54cm));
    border-top: 1px solid #dfe3e9;
  }
  .structured-editor :global(.wa-page-number) { display: block; width: 100%; }
  .structured-editor :global(.wa-page-footer-text),
  .structured-editor :global(.wa-page-header-text),
  .structured-editor :global(.wa-first-page-header) { display: block; color: #606975; text-align: center; }
  .structured-editor :global(.wa-page-header-text) { margin-top: 20px; }
  .structured-editor :global(.wa-first-page-header) { margin-bottom: 18px; }
  .structured-editor :global([data-page-region]) { pointer-events: auto; cursor: text; }
  .structured-editor :global([data-page-region]:hover) { background: rgba(37,99,235,.08); outline: 1px dashed rgba(37,99,235,.35); }
  .clipboard-error {
    position: sticky;
    bottom: 12px;
    margin: 12px auto 0;
    padding: 8px 12px;
    border: 1px solid #f2c96d;
    border-radius: 4px;
    background: #fff8df;
    color: #6f5310;
    font-size: 12px;
    text-align: center;
  }
  .markdown-notice { position: sticky; z-index: 12; bottom: 12px; display: flex; max-width: 620px; justify-content: space-between; gap: 12px; margin: 12px auto 0; padding: 8px 12px; border: 1px solid #9fc0eb; border-radius: 5px; background: #edf5ff; color: #254d7c; font-size: 12px; }
  .markdown-notice button { border: 0; background: transparent; color: inherit; cursor: pointer; }
</style>
