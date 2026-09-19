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
  import { createNodeCommand, createUserCommand, executeDocumentCommand } from '../editor-v3/commands'
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
  import { isDocumentV3, migrateLegacyDocIr, type DocumentV3 } from '../editor-v3/model'
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

  function handlePageSettingsChanged() {
    const next = get(documentV3)
    if (next && isDocumentV3(next)) loadDocument(structuredClone(next))
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
      spaceAfterPt: editor.getAttributes('heading').spaceAfterPt ?? editor.getAttributes('paragraph').spaceAfterPt ?? null
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
    if (command === 'view-outline') {
      outlineVisible = !outlineVisible
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
    if (command.startsWith('font:')) {
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
      onSlashQuery: handleSlashQuery
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
</style>
