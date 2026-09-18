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
  import { createUserCommand, executeDocumentCommand } from '../editor-v3/commands'
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
    positionBlockHandle(topLevelBlockElement(event.target instanceof Element ? event.target : null))
  }

  function handleBlockHandleClick(event: MouseEvent) {
    if (!editor || !activeBlockId) return
    const extend = event.shiftKey && Boolean(blockSelectionAnchorId)
    if (selectBlock(editor, activeBlockId, extend ? blockSelectionAnchorId : '')) {
      if (!extend) blockSelectionAnchorId = activeBlockId
      positionBlockHandleById(activeBlockId)
    }
  }

  function runBlockCommand(type: 'move_block_up' | 'move_block_down' | 'duplicate_block' | 'delete_block') {
    if (!editor) return
    executeDocumentCommand(editor, createUserCommand(type))
    emitSelection()
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
    blockSelectionActive = editor.state.selection instanceof NodeSelection
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
      onSelectionUpdate: emitSelection
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

<div class:paper class="structured-editor-shell" role="group" aria-label="Document V3 编辑区" bind:this={shell} onpointermove={handleEditorPointerMove}>
  {#if blockHandleVisible}
    <button
      class="block-handle"
      style:top={`${blockHandleTop}px`}
      style:left={`${blockHandleLeft}px`}
      aria-label="选择当前块"
      title="选择块；Shift 点击选择连续块"
      onmousedown={(event) => event.preventDefault()}
      onclick={handleBlockHandleClick}
    >⋮⋮</button>
  {/if}
  {#if blockHandleVisible && blockSelectionActive}
    <div class="block-actions" style:top={`${blockHandleTop}px`} style:left={`${blockHandleLeft + 32}px`} role="toolbar" aria-label="块操作">
      <button title="上移块" aria-label="上移块" onmousedown={(event) => event.preventDefault()} onclick={() => runBlockCommand('move_block_up')}>↑</button>
      <button title="下移块" aria-label="下移块" onmousedown={(event) => event.preventDefault()} onclick={() => runBlockCommand('move_block_down')}>↓</button>
      <button title="复制块" aria-label="复制块" onmousedown={(event) => event.preventDefault()} onclick={() => runBlockCommand('duplicate_block')}>⧉</button>
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
