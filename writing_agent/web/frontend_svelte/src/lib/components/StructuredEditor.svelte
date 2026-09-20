<script lang="ts">
  import { get } from 'svelte/store'
  import { onDestroy, onMount } from 'svelte'
  import type { Editor, JSONContent } from '@tiptap/core'
  import { NodeSelection } from '@tiptap/pm/state'

  import {
    docIr,
    docIrDirty,
    documentV3,
    editorCommand,
    sourceText
  } from '../stores'
  import { createNodeCommand, createShortcutCommand, createUserCommand, executeDocumentCommand } from '../editor-v3/commands'
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
  import { isDocumentV3, migrateLegacyDocIr, type DocumentV3, type StyleDefinition, type StyleProperties } from '../editor-v3/model'
  import { documentV3ToMarkdown, replaceDocumentContentFromMarkdown } from '../editor-v3/markdown'
  import { paginateDocumentV3 } from '../engine/documentEngine'
  import type { EditorCommand } from '../types'

  let {
    paper = true,
    lockEditing = false,
    onblockedit,
    onblockselect,
    ontoolbarstate
  }: {
    showToolbar?: boolean
    paper?: boolean
    lockEditing?: boolean
    onblockedit?: (payload: any) => void
    onblockselect?: (payload: any) => void
    ontoolbarstate?: (state: any) => void
  } = $props()

  let host: HTMLDivElement
  let editor: Editor | null = null
  let activeDocument: DocumentV3 | null = null
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
  let dragTargetId = $state('')
  let dragPlacement = $state<'before' | 'after'>('before')
  let dragIndicatorTop = $state(0)
  let blockPointerId: number | null = null
  let blockPointerStartY = 0
  let blockPointerDragging = false
  let suppressHandleClick = false
  let nativeBlockDrag = false
  let slashQuery = $state('')
  let slashMenuVisible = $state(false)
  let slashMenuTop = $state(0)
  let slashMenuLeft = $state(0)
  let slashMenuIndex = $state(0)
  let paginationTimer: ReturnType<typeof setTimeout> | null = null
  let paginationRevision = 0
  let pageCount = $state(1)
  let paginationState = $state<'loading' | 'ready' | 'unavailable' | 'error'>('loading')
  let resizeObserver: ResizeObserver | null = null
  let observedShellWidth = 0
  let findPanelVisible = $state(false)
  let findQuery = $state('')
  let replaceText = $state('')
  let findStatus = $state('')
  let outlineVisible = $state(false)
  let zoomPercent = $state(100)
  let selectionToolbarVisible = $state(false)
  let selectionToolbarTop = $state(0)
  let selectionToolbarLeft = $state(0)
  let proofPanelVisible = $state(false)
  let proofIssues = $state<Array<{ id: string; message: string; excerpt: string; from: number; to: number }>>([])
  let markdownInput: HTMLInputElement
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
  let managedBold = $state(false)
  let managedItalic = $state(false)
  let managedAlignment = $state<'left' | 'center' | 'right' | 'justify'>('left')
  let managedLineSpacing: number | '' = $state('')
  let managedSpaceBeforePt: number | '' = $state('')
  let managedSpaceAfterPt: number | '' = $state('')
  let creatingStyle = $state(false)
  let styleManagerNotice = $state('')
  let styleRevision = $state(0)

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
    managedBold = Boolean(properties.bold)
    managedItalic = Boolean(properties.italic)
    managedAlignment = properties.alignment || 'left'
    managedLineSpacing = properties.lineSpacing ?? ''
    managedSpaceBeforePt = properties.spaceBeforePt ?? ''
    managedSpaceAfterPt = properties.spaceAfterPt ?? ''
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
    managedBold = editor.isActive('bold')
    managedItalic = editor.isActive('italic')
    managedAlignment = (paragraphAttrs.textAlign || 'left') as typeof managedAlignment
    managedLineSpacing = paragraphAttrs.lineSpacing ?? ''
    managedSpaceBeforePt = paragraphAttrs.spaceBeforePt ?? ''
    managedSpaceAfterPt = paragraphAttrs.spaceAfterPt ?? ''
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
    const properties: StyleProperties = {
      fontFamily: managedFontFamily || undefined,
      fontSizePt: managedFontSizePt === '' ? undefined : Number(managedFontSizePt),
      bold: managedBold || undefined,
      italic: managedItalic || undefined,
      alignment: managedAlignment,
      lineSpacing: managedLineSpacing === '' ? undefined : Number(managedLineSpacing),
      spaceBeforePt: managedSpaceBeforePt === '' ? undefined : Number(managedSpaceBeforePt),
      spaceAfterPt: managedSpaceAfterPt === '' ? undefined : Number(managedSpaceAfterPt)
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
    const next = structuredClone(activeDocument)
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

  function applyManagedStyle() {
    if (!editor) return
    executeDocumentCommand(editor, createUserCommand('apply_style', { styleId: managedStyleId }))
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

  function handlePageSettingsChanged() {
    const next = get(documentV3)
    if (next && isDocumentV3(next)) loadDocument(structuredClone(next))
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
    if (paginationTimer) clearTimeout(paginationTimer)
    const revision = ++paginationRevision
    paginationTimer = setTimeout(async () => {
      if (!editor || !activeDocument || revision !== paginationRevision) return
      paginationState = 'loading'
      try {
        const layout = await paginateDocumentV3(activeDocument, revision)
        if (!editor || revision !== paginationRevision) return
        pageCount = Math.max(1, layout?.pageCount || 1)
        paginationState = layout ? 'ready' : 'unavailable'
        applyPaginationLayout(editor, layout)
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
      if (Math.abs(event.clientY - blockPointerStartY) >= 4) blockPointerDragging = true
      if (blockPointerDragging) {
        event.preventDefault()
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
      positionBlockHandleById(activeBlockId)
    }
  }

  function runBlockCommand(type: 'move_block_up' | 'move_block_down' | 'duplicate_block' | 'delete_block' | 'insert_block_before' | 'insert_block_after') {
    if (!editor) return
    executeDocumentCommand(editor, createUserCommand(type))
    emitSelection()
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
    blockPointerDragging = false
    ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
  }

  function handleBlockDragStart(event: DragEvent) {
    if (!editor || !activeBlockId || !event.dataTransfer) return
    nativeBlockDrag = true
    blockPointerId = null
    blockPointerDragging = false
    if (!selectedBlockIds.includes(activeBlockId)) selectBlock(editor, activeBlockId)
    selectedBlockIds = selectedBlocks(editor).map((block) => block.id)
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('application/x-writing-agent-blocks', JSON.stringify(selectedBlockIds))
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
  }

  function handleNativeDragOver(event: DragEvent) {
    if (!nativeBlockDrag) return
    event.preventDefault()
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
    updateBlockDropTarget(event.clientY, event.target instanceof Element ? event.target : null)
  }

  function handleNativeDrop(event: DragEvent) {
    if (!nativeBlockDrag) return
    event.preventDefault()
    if (editor && dragTargetId) {
      executeDocumentCommand(editor, createNodeCommand('move_blocks', selectedBlockIds, { targetId: dragTargetId, placement: dragPlacement }))
      emitSelection()
    }
    nativeBlockDrag = false
    clearBlockDrag()
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
    ontoolbarstate?.({
      focused: editor.isFocused,
      readonly: !editor.isEditable,
      bold: editor.isActive('bold'),
      italic: editor.isActive('italic'),
      underline: editor.isActive('underline'),
      strike: editor.isActive('strike'),
      hasSelection: !selection.empty,
      canUndo: editor.can().undo(),
      canRedo: editor.can().redo(),
      canCopy: !selection.empty,
      canCut: !selection.empty && editor.isEditable,
      canPaste: editor.isEditable,
      blockType: editor.isActive('heading') ? 'heading' : 'paragraph',
      headingLevel: editor.getAttributes('heading').level || null,
      styleId: editor.getAttributes('heading').styleId || editor.getAttributes('paragraph').styleId || 'normal',
      fontFamily: editor.getAttributes('textStyle').fontFamily || '',
      fontSize: editor.getAttributes('textStyle').fontSize || '',
      alignment: editor.getAttributes('heading').textAlign || editor.getAttributes('paragraph').textAlign || 'left',
      lineSpacing: editor.getAttributes('heading').lineSpacing || editor.getAttributes('paragraph').lineSpacing || null,
      letterSpacing: editor.getAttributes('textStyle').letterSpacing || '',
      textTransform: editor.getAttributes('textStyle').textTransform || 'none',
      firstLineIndentEm: editor.getAttributes('heading').firstLineIndentEm ?? editor.getAttributes('paragraph').firstLineIndentEm ?? null,
      leftIndentEm: editor.getAttributes('heading').leftIndentEm ?? editor.getAttributes('paragraph').leftIndentEm ?? null,
      rightIndentEm: editor.getAttributes('heading').rightIndentEm ?? editor.getAttributes('paragraph').rightIndentEm ?? null,
      spaceBeforePt: editor.getAttributes('heading').spaceBeforePt ?? editor.getAttributes('paragraph').spaceBeforePt ?? null,
      spaceAfterPt: editor.getAttributes('heading').spaceAfterPt ?? editor.getAttributes('paragraph').spaceAfterPt ?? null,
      styles: visibleStyles().map((style) => ({ id: style.id, name: style.name }))
    })
  }

  function emitSelection() {
    if (!editor) return
    const { from, to, empty } = editor.state.selection
    const blocks = selectedBlocks(editor)
    const blockIds = blocks.map((block) => block.id)
    selectedBlockIds = blockIds
    if (editor.state.selection instanceof NodeSelection) blockSelectionActive = true
    else if (editor.state.selection.empty) blockSelectionActive = false
    if (blockIds.length === 1) positionBlockHandleById(blockIds[0])
    const text = empty ? '' : editor.state.doc.textBetween(from, to, '\n')
    selectionToolbarVisible = !empty && !(editor.state.selection instanceof NodeSelection)
    const contextKind = editor.state.selection instanceof NodeSelection ? 'block' : selectionToolbarVisible ? 'text' : 'editor'
    window.dispatchEvent(new CustomEvent('wa-editor-context', { detail: { kind: contextKind } }))
    if (selectionToolbarVisible && shell) {
      const start = editor.view.coordsAtPos(from)
      const end = editor.view.coordsAtPos(to)
      const shellRect = shell.getBoundingClientRect()
      selectionToolbarTop = Math.max(4, Math.min(start.top, end.top) - shellRect.top - 38)
      selectionToolbarLeft = Math.max(4, Math.min((start.left + end.right) / 2 - shellRect.left - 92, shellRect.width - 190))
    }
    onblockselect?.({
      blockId: blockIds[0] || '',
      blockIds,
      blocks: blocks.map((block) => ({ ...block, kind: 'block' })),
      text,
      rect: null,
      style: {}
    })
    emitToolbarState()
  }

  function updateDocument(json: JSONContent) {
    if (!activeDocument) return
    activeDocument = tiptapToDocumentV3(activeDocument, json)
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

  function runLegacyCommand(command: EditorCommand) {
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
    if (command === 'view-outline') {
      outlineVisible = !outlineVisible
      return
    }
    if (command === 'markdown-import') {
      markdownInput?.click()
      return
    }
    if (command === 'markdown-export') {
      prepareMarkdownExport()
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
      'page-break': 'insert_page_break',
      'math-block': 'insert_equation',
      hr: 'insert_horizontal_rule',
      caption: 'apply_style'
    }
    let type = simple[command]
    let params: Record<string, unknown> = {}
    if (command === 'paragraph') params = { styleId: 'normal' }
    if (command === 'caption') params = { styleId: 'caption' }
    if (/^heading[1-6]$/.test(command)) params = { styleId: `heading-${command.slice(-1)}` }
    if (command.startsWith('style:')) {
      type = 'apply_style'
      params = { styleId: command.slice(6) }
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
      const attrs = editor.getAttributes(editor.isActive('heading') ? 'heading' : 'paragraph')
      const current = Number(attrs.leftIndentEm || 0)
      type = 'set_paragraph_format'
      params = { leftIndentEm: Math.max(0, current + (command === 'indent' ? 1 : -1)) }
    } else if (command.startsWith('margin:')) {
      type = 'set_paragraph_format'
      params = { spaceBeforePt: 6, spaceAfterPt: 6 }
    } else if (command.startsWith('letter-spacing:')) {
      type = 'set_character_format'
      params = { letterSpacing: command.slice(15) }
    } else if (command.startsWith('text-transform:')) {
      type = 'set_character_format'
      params = { textTransform: command.slice(15) }
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
    } else if (command.startsWith('border-color:')) {
      type = 'set_paragraph_format'
      params = { borderColor: command.slice(13), borderWidthPt: 0.75, borderStyle: 'solid' }
    } else if (command.startsWith('shading-color:')) {
      type = 'set_paragraph_format'
      params = { shadingColor: command.slice(14) }
    }
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
    activeDocument = stored && isDocumentV3(stored) ? structuredClone(stored) : migrateLegacyDocIr(get(docIr))
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
      onSelectionUpdate: emitSelection,
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
    unsubscribeCommand = editorCommand.subscribe((command) => {
      if (!command || !editor) return
      runLegacyCommand(command)
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
    editor?.setEditable(!lockEditing)
    emitToolbarState()
  })

  onDestroy(() => {
    unsubscribeCommand()
    unsubscribeDocIr()
    editor?.destroy()
    styleElement?.remove()
    if (clipboardErrorTimer) clearTimeout(clipboardErrorTimer)
    if (paginationTimer) clearTimeout(paginationTimer)
    resizeObserver?.disconnect()
    window.removeEventListener('wa-page-settings-changed', handlePageSettingsChanged)
    window.removeEventListener('wa-editor-context', handleEditorContext)
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
  onpointerleave={() => { if (!blockSelectionActive) blockHandleVisible = false }}
  onpointerup={handleBlockPointerUp}
  onpointercancel={handleBlockPointerUp}
  ondragover={handleNativeDragOver}
  ondrop={handleNativeDrop}
>
  <input class="hidden-file-input" bind:this={markdownInput} type="file" accept=".md,.markdown,text/markdown,text/plain" onchange={importMarkdownFile} />
  {#if blockHandleVisible}
    <button
      class="block-handle"
      style:top={`${blockHandleTop}px`}
      style:left={`${blockHandleLeft}px`}
      aria-label="选择当前块"
      title="选择块；Shift 点击选择连续块"
      draggable="true"
      onpointerdown={handleBlockPointerDown}
      onclick={handleBlockHandleClick}
      ondragstart={handleBlockDragStart}
      ondragend={() => { nativeBlockDrag = false; clearBlockDrag() }}
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
      <strong>导航</strong>
      {#each outlineHeadings() as heading (heading.id)}
        <button style:padding-left={`${8 + (heading.level - 1) * 12}px`} onclick={() => jumpToOutline(heading.position)}>{heading.text}</button>
      {:else}<small>应用标题样式后将在这里显示。</small>{/each}
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
      <div class="style-grid">
        <label>基于<select bind:value={managedBasedOn}><option value="">无</option>{#each visibleStyles().filter((style) => style.id !== managedStyleId) as style}<option value={style.id}>{style.name}</option>{/each}</select></label>
        <label>后续段落<select bind:value={managedNextStyle}>{#each visibleStyles() as style}<option value={style.id}>{style.name}</option>{/each}</select></label>
        <label>字体<input bind:value={managedFontFamily} placeholder="继承" /></label>
        <label>字号 pt<input type="number" min="6" max="96" step="0.5" bind:value={managedFontSizePt} /></label>
        <label>对齐<select bind:value={managedAlignment}><option value="left">左对齐</option><option value="center">居中</option><option value="right">右对齐</option><option value="justify">两端对齐</option></select></label>
        <label>行距<input type="number" min="0.8" max="4" step="0.05" bind:value={managedLineSpacing} /></label>
        <label>段前 pt<input type="number" min="0" max="144" bind:value={managedSpaceBeforePt} /></label>
        <label>段后 pt<input type="number" min="0" max="144" bind:value={managedSpaceAfterPt} /></label>
      </div>
      <div class="style-flags"><label><input type="checkbox" bind:checked={managedBold} /> 加粗</label><label><input type="checkbox" bind:checked={managedItalic} /> 斜体</label></div>
      {#if styleManagerNotice}<p>{styleManagerNotice}</p>{/if}
      <footer><button onclick={applyManagedStyle}>应用到当前段落</button><button class="primary" onclick={saveManagedStyle}>保存并全局更新</button></footer>
    </aside>
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
      <button title="复制块" aria-label="复制块" onmousedown={(event) => event.preventDefault()} onclick={() => runBlockCommand('duplicate_block')}>⧉</button>
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
    overflow: auto;
    padding: 10px;
    border: 1px solid #d5dce7;
    border-radius: 6px;
    background: #fff;
    box-shadow: 0 5px 18px rgba(38, 50, 66, .12);
  }
  .outline-panel button { overflow: hidden; padding-block: 6px; border: 0; border-radius: 3px; background: transparent; color: #344054; text-align: left; text-overflow: ellipsis; white-space: nowrap; cursor: pointer; }
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
  .style-manager { position: absolute; z-index: 11; top: 10px; right: 10px; box-sizing: border-box; width: 390px; padding: 13px; border: 1px solid #cfd7e2; border-radius: 7px; background: #fff; box-shadow: 0 10px 30px rgba(30, 43, 62, .18); color: #263244; font-size: 12px; }
  .style-manager header, .style-manager footer, .style-manager-actions, .style-flags { display: flex; align-items: center; gap: 8px; }
  .style-manager header { justify-content: space-between; margin-bottom: 10px; font-size: 15px; }
  .style-manager header button { border: 0; background: transparent; font-size: 19px; cursor: pointer; }
  .style-manager-actions select { flex: 1; }
  .style-manager label { display: grid; gap: 3px; margin-top: 8px; color: #5b6675; }
  .style-manager input, .style-manager select, .style-manager button { box-sizing: border-box; min-height: 29px; border: 1px solid #cfd6e1; border-radius: 4px; background: #fff; color: #263244; }
  .style-manager button { padding: 4px 8px; cursor: pointer; }
  .style-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 9px; }
  .style-flags label { display: flex; align-items: center; gap: 5px; }
  .style-flags input { min-height: auto; }
  .style-manager p { margin: 8px 0 0; color: #28639e; }
  .style-manager footer { justify-content: flex-end; margin-top: 12px; }
  .style-manager footer .primary { border-color: #2468c8; background: #2468c8; color: #fff; }
  .markdown-dialog-backdrop { position: fixed; z-index: 30; inset: 0; display: grid; place-items: center; background: rgba(20, 29, 43, .28); }
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
  .structured-editor :global(.v3-object-pageBreak) {
    padding: 0;
    border-width: 1px 0 0;
    border-style: dashed;
    border-radius: 0;
    background: transparent;
    font-size: 11px;
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
  .structured-editor :global(.wa-first-page-header) { margin-bottom: 18px; pointer-events: none; }
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
