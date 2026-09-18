<script lang="ts">
  import { get } from 'svelte/store'
  import { onDestroy, onMount } from 'svelte'
  import type { Editor, JSONContent } from '@tiptap/core'

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
    const { from, to, empty, $from: resolvedFrom } = editor.state.selection
    let nodeId = ''
    for (let depth = resolvedFrom.depth; depth >= 0; depth -= 1) {
      const candidate = resolvedFrom.node(depth).attrs?.nodeId
      if (candidate) {
        nodeId = String(candidate)
        break
      }
    }
    const text = empty ? '' : editor.state.doc.textBetween(from, to, '\n')
    onblockselect?.({
      blockId: nodeId,
      blockIds: nodeId ? [nodeId] : [],
      blocks: nodeId ? [{ id: nodeId, kind: 'block', text }] : [],
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
  })
</script>

<div class:paper class="structured-editor-shell" aria-label="Document V3 编辑区">
  <div class="structured-editor" bind:this={host}></div>
</div>

<style>
  .structured-editor-shell {
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
</style>
