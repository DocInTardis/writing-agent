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
    documentV3ToTiptap,
    documentV3ToText,
    plainTextToTiptapContent,
    selectBlock,
    selectedBlocks,
    styleSheetForDocument,
    tiptapToDocumentV3
  } from '../editor-v3/kernel'
  import { isDocumentV3, migrateLegacyDocIr, type DocumentV3 } from '../editor-v3/model'
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
      lineSpacing: editor.getAttributes('heading').lineSpacing || editor.getAttributes('paragraph').lineSpacing || null
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
  }

  function runLegacyCommand(command: EditorCommand) {
    if (!editor) return
    if (command === 'copy' || command === 'cut' || command === 'paste') {
      void runClipboardCommand(command)
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
      redo: 'redo'
    }
    let type = simple[command]
    let params: Record<string, unknown> = {}
    if (command === 'paragraph') params = { styleId: 'normal' }
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
  })
</script>

<!-- svelte-ignore a11y_no_noninteractive_element_interactions: wrapper delegates input to the ProseMirror application below -->
<div
  class:paper
  class="structured-editor-shell"
  role="application"
  tabindex="-1"
  aria-label="Document V3 编辑区"
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
    width: min(100%, 21cm);
    min-height: 29.7cm;
    margin: 0 auto 64px;
    background: #fff;
    color: #1f2328;
  }
  .structured-editor-shell.paper {
    padding: 2.54cm 2.54cm 2.54cm 3.18cm;
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
