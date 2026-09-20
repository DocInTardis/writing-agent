import type { Editor } from '@tiptap/core'
import { Fragment, type Node as ProseMirrorNode } from '@tiptap/pm/model'
import { NodeSelection, TextSelection, type Transaction } from '@tiptap/pm/state'

export type CommandSource = 'user' | 'shortcut' | 'ai' | 'import'
export type ReviewMode = 'direct' | 'suggest'

export type CommandTarget =
  | { kind: 'selection'; from?: number; to?: number }
  | { kind: 'nodes'; nodeIds: string[] }
  | { kind: 'section'; sectionId: string }
  | { kind: 'document' }

export interface DocumentCommand<TParams = Record<string, unknown>> {
  id: string
  type: string
  target: CommandTarget
  params: TParams
  source: CommandSource
  reviewMode: ReviewMode
  timestamp: number
}

export interface CommandResult {
  ok: boolean
  changed: boolean
  commandId: string
  affectedNodeIds: string[]
  warnings: string[]
  error?: string
}

type CommandHandler = (editor: Editor, command: DocumentCommand<any>) => boolean

const registry = new Map<string, CommandHandler>()

function selectionCommand(command: Omit<DocumentCommand, 'id' | 'timestamp'>): DocumentCommand {
  return {
    ...command,
    id: crypto.randomUUID(),
    timestamp: Date.now()
  }
}

export function createUserCommand(type: string, params: Record<string, unknown> = {}): DocumentCommand {
  return selectionCommand({
    type,
    target: { kind: 'selection' },
    params,
    source: 'user',
    reviewMode: 'direct'
  })
}

export function createShortcutCommand(type: string, params: Record<string, unknown> = {}): DocumentCommand {
  return selectionCommand({
    type,
    target: { kind: 'selection' },
    params,
    source: 'shortcut',
    reviewMode: 'direct'
  })
}

export function createNodeCommand(type: string, nodeIds: string[], params: Record<string, unknown> = {}): DocumentCommand {
  return selectionCommand({
    type,
    target: { kind: 'nodes', nodeIds: [...new Set(nodeIds.filter(Boolean))] },
    params,
    source: 'user',
    reviewMode: 'direct'
  })
}

export function registerDocumentCommand(type: string, handler: CommandHandler): void {
  if (registry.has(type)) throw new Error(`Document command already registered: ${type}`)
  registry.set(type, handler)
}

export function registeredDocumentCommands(): string[] {
  return [...registry.keys()].sort()
}

export function executeDocumentCommand(editor: Editor, command: DocumentCommand): CommandResult {
  const handler = registry.get(command.type)
  if (!handler) {
    return {
      ok: false,
      changed: false,
      commandId: command.id,
      affectedNodeIds: [],
      warnings: [],
      error: `Unsupported document command: ${command.type}`
    }
  }
  if (command.reviewMode === 'suggest' && command.source === 'ai') {
    return {
      ok: false,
      changed: false,
      commandId: command.id,
      affectedNodeIds: [],
      warnings: ['AI suggestion transactions are not enabled yet.'],
      error: 'review_mode_not_ready'
    }
  }
  const before = editor.state.doc.content.size
  try {
    const applied = handler(editor, command)
    return {
      ok: applied,
      changed: applied || before !== editor.state.doc.content.size,
      commandId: command.id,
      affectedNodeIds: command.target.kind === 'nodes' ? command.target.nodeIds : [],
      warnings: []
    }
  } catch (error) {
    return {
      ok: false,
      changed: false,
      commandId: command.id,
      affectedNodeIds: [],
      warnings: [],
      error: error instanceof Error ? error.message : String(error)
    }
  }
}

registerDocumentCommand('toggle_bold', (editor) => editor.chain().focus().toggleBold().run())
registerDocumentCommand('toggle_italic', (editor) => editor.chain().focus().toggleItalic().run())
registerDocumentCommand('toggle_underline', (editor) => editor.chain().focus().toggleUnderline().run())
registerDocumentCommand('toggle_strike', (editor) => editor.chain().focus().toggleStrike().run())
registerDocumentCommand('toggle_subscript', (editor) => editor.chain().focus().toggleSubscript().run())
registerDocumentCommand('toggle_superscript', (editor) => editor.chain().focus().toggleSuperscript().run())
registerDocumentCommand('set_text_color', (editor, command) => {
  const color = String(command.params.color || '').trim()
  return color ? editor.chain().focus().setColor(color).run() : false
})
registerDocumentCommand('set_highlight', (editor, command) => {
  const color = String(command.params.color || '').trim()
  return color ? editor.chain().focus().setHighlight({ color }).run() : false
})
registerDocumentCommand('set_font_family', (editor, command) => {
  const fontFamily = String(command.params.fontFamily || '').trim()
  return fontFamily ? editor.chain().focus().setFontFamily(fontFamily).run() : false
})
registerDocumentCommand('set_font_size', (editor, command) => {
  const fontSize = String(command.params.fontSize || '').trim()
  return fontSize ? editor.chain().focus().setMark('textStyle', { fontSize }).run() : false
})
registerDocumentCommand('set_character_format', (editor, command) => {
  const attrs: Record<string, unknown> = {}
  if ('letterSpacing' in command.params) attrs.letterSpacing = String(command.params.letterSpacing || '') || null
  if ('textTransform' in command.params) {
    const transform = String(command.params.textTransform || '')
    if (!['none', 'uppercase', 'lowercase', 'capitalize'].includes(transform)) return false
    attrs.textTransform = transform
  }
  if (!Object.keys(attrs).length) return false
  return editor.chain().focus().setMark('textStyle', attrs).run()
})
registerDocumentCommand('set_alignment', (editor, command) => {
  const alignment = String(command.params.alignment || '')
  if (!['left', 'center', 'right', 'justify'].includes(alignment)) return false
  return editor.chain().focus().setTextAlign(alignment).run()
})
registerDocumentCommand('apply_style', (editor, command) => {
  const styleId = String(command.params.styleId || 'normal')
  if (styleId === 'normal') return editor.chain().focus().setParagraph().updateAttributes('paragraph', { styleId }).run()
  const match = /^heading-([1-6])$/.exec(styleId)
  if (!match) return editor.chain().focus().setParagraph().updateAttributes('paragraph', { styleId }).run()
  const level = Number(match[1]) as 1 | 2 | 3 | 4 | 5 | 6
  return editor.chain().focus().setHeading({ level }).updateAttributes('heading', { styleId }).run()
})
registerDocumentCommand('split_block_with_style', (editor, command) => {
  const styleId = String(command.params.styleId || 'normal')
  return editor.chain().focus().splitBlock().command(({ tr }) => {
    const { $from } = tr.selection
    if (!$from.parent.isTextblock || $from.depth < 1) return false
    const heading = /^heading-([1-6])$/.exec(styleId)
    const type = heading ? editor.state.schema.nodes.heading : editor.state.schema.nodes.paragraph
    if (!type) return false
    const attrs: Record<string, unknown> = { ...$from.parent.attrs, styleId }
    if (heading) attrs.level = Number(heading[1])
    else delete attrs.level
    tr.setNodeMarkup($from.before($from.depth), type, attrs)
    return true
  }).run()
})
registerDocumentCommand('set_paragraph_format', (editor, command) => {
  const attrs: Record<string, unknown> = {}
  for (const key of [
    'lineSpacing',
    'firstLineIndentEm',
    'leftIndentEm',
    'rightIndentEm',
    'spaceBeforePt',
    'spaceAfterPt',
    'keepWithNext',
    'keepLinesTogether',
    'pageBreakBefore',
    'borderColor',
    'borderWidthPt',
    'borderStyle',
    'shadingColor',
    'tabStops'
  ]) {
    if (key in command.params) attrs[key] = command.params[key]
  }
  if (!Object.keys(attrs).length) return false
  return editor.chain().focus().updateAttributes('paragraph', attrs).updateAttributes('heading', attrs).run()
})
registerDocumentCommand('toggle_bullet_list', (editor) => editor.chain().focus().toggleBulletList().run())
registerDocumentCommand('toggle_ordered_list', (editor) => editor.chain().focus().toggleOrderedList().run())
registerDocumentCommand('toggle_blockquote', (editor) => editor.chain().focus().toggleBlockquote().run())
registerDocumentCommand('toggle_code_block', (editor) => editor.chain().focus().toggleCodeBlock().run())
registerDocumentCommand('insert_page_break', (editor) => editor.chain().focus().insertContent({ type: 'pageBreak', attrs: { nodeId: null } }).run())
registerDocumentCommand('insert_figure', (editor, command) => editor.chain().focus().insertContent({
  type: 'figure',
  attrs: { nodeId: null, payload: { caption: String(command.params.caption || ''), source: String(command.params.source || '') } }
}).run())
registerDocumentCommand('insert_table', (editor, command) => editor.chain().focus().insertContent({
  type: 'table',
  attrs: { nodeId: null, payload: { rows: Math.max(1, Number(command.params.rows || 2)), columns: Math.max(1, Number(command.params.columns || 2)), cells: [] } }
}).run())
registerDocumentCommand('insert_equation', (editor, command) => editor.chain().focus().insertContent({
  type: 'equationBlock',
  attrs: { nodeId: null, payload: { latex: String(command.params.latex || '') } }
}).run())
registerDocumentCommand('insert_horizontal_rule', (editor) => editor.chain().focus().setHorizontalRule().run())
registerDocumentCommand('clear_formatting', (editor) => editor.chain().focus().unsetAllMarks().clearNodes().run())
registerDocumentCommand('undo', (editor) => editor.chain().focus().undo().run())
registerDocumentCommand('redo', (editor) => editor.chain().focus().redo().run())
registerDocumentCommand('restore_markdown_trigger', (editor, command) => {
  const from = Number(command.params.from)
  const to = Number(command.params.to)
  const raw = String(command.params.raw || '')
  if (!Number.isInteger(from) || !Number.isInteger(to) || !raw || from < 0 || to <= from || to > editor.state.doc.content.size) return false
  const paragraph = editor.state.schema.nodes.paragraph.create(
    { nodeId: null, styleId: 'normal' },
    editor.state.schema.text(raw)
  )
  const transaction = editor.state.tr.replaceWith(from, to, paragraph)
  transaction.setSelection(TextSelection.create(transaction.doc, from + 1 + raw.length))
  editor.view.dispatch(transaction.scrollIntoView())
  return true
})

interface TopLevelRange {
  from: number
  to: number
  nodes: Array<{ node: ProseMirrorNode; position: number }>
}

function selectedTopLevelRange(editor: Editor): TopLevelRange | null {
  const selection = editor.state.selection
  if (selection instanceof NodeSelection && selection.$from.depth === 0) {
    return {
      from: selection.from,
      to: selection.to,
      nodes: [{ node: selection.node, position: selection.from }]
    }
  }
  const nodes: TopLevelRange['nodes'] = []
  editor.state.doc.forEach((node, position) => {
    const end = position + node.nodeSize
    if (end > selection.from && position < selection.to) nodes.push({ node, position })
  })
  if (!nodes.length) return null
  return {
    from: nodes[0].position,
    to: nodes[nodes.length - 1].position + nodes[nodes.length - 1].node.nodeSize,
    nodes
  }
}

function selectInsertedRange(transaction: Transaction, from: number, to: number) {
  const selection = to - from === transaction.doc.nodeAt(from)?.nodeSize
    ? NodeSelection.create(transaction.doc, from)
    : TextSelection.create(transaction.doc, Math.min(from + 1, transaction.doc.content.size), Math.max(from + 1, to - 1))
  transaction.setSelection(selection)
}

registerDocumentCommand('duplicate_block', (editor) => {
  const selected = selectedTopLevelRange(editor)
  if (!selected) return false
  const insertAt = selected.to
  const content = Fragment.fromArray(selected.nodes.map(({ node }) => node))
  const transaction = editor.state.tr.insert(insertAt, content)
  selectInsertedRange(transaction, insertAt, insertAt + content.size)
  editor.view.dispatch(transaction.scrollIntoView())
  return true
})

registerDocumentCommand('delete_block', (editor) => {
  const selected = selectedTopLevelRange(editor)
  if (!selected) return false
  const transaction = editor.state.tr.delete(selected.from, selected.to)
  editor.view.dispatch(transaction.scrollIntoView())
  return true
})

registerDocumentCommand('move_block_up', (editor) => {
  const selected = selectedTopLevelRange(editor)
  if (!selected) return false
  const before = editor.state.doc.childBefore(selected.from)
  if (!before.node) return false
  const insertAt = selected.from - before.node.nodeSize
  const content = Fragment.fromArray(selected.nodes.map(({ node }) => node))
  const transaction = editor.state.tr
    .delete(selected.from, selected.to)
    .insert(insertAt, content)
  selectInsertedRange(transaction, insertAt, insertAt + content.size)
  editor.view.dispatch(transaction.scrollIntoView())
  return true
})

registerDocumentCommand('move_block_down', (editor) => {
  const selected = selectedTopLevelRange(editor)
  if (!selected) return false
  const after = editor.state.doc.childAfter(selected.to)
  if (!after.node) return false
  const content = Fragment.fromArray(selected.nodes.map(({ node }) => node))
  const insertAt = selected.from + after.node.nodeSize
  const transaction = editor.state.tr
    .delete(selected.from, selected.to)
    .insert(insertAt, content)
  selectInsertedRange(transaction, insertAt, insertAt + content.size)
  editor.view.dispatch(transaction.scrollIntoView())
  return true
})

registerDocumentCommand('insert_block_before', (editor) => {
  const selected = selectedTopLevelRange(editor)
  if (!selected) return false
  const paragraph = editor.state.schema.nodes.paragraph.create({ nodeId: null, styleId: 'normal' })
  const transaction = editor.state.tr.insert(selected.from, paragraph)
  transaction.setSelection(TextSelection.create(transaction.doc, selected.from + 1))
  editor.view.dispatch(transaction.scrollIntoView())
  return true
})

registerDocumentCommand('insert_block_after', (editor) => {
  const selected = selectedTopLevelRange(editor)
  if (!selected) return false
  const paragraph = editor.state.schema.nodes.paragraph.create({ nodeId: null, styleId: 'normal' })
  const transaction = editor.state.tr.insert(selected.to, paragraph)
  transaction.setSelection(TextSelection.create(transaction.doc, selected.to + 1))
  editor.view.dispatch(transaction.scrollIntoView())
  return true
})

registerDocumentCommand('convert_block', (editor, command) => {
  const target = String(command.params.type || 'paragraph')
  if (target === 'paragraph') return editor.chain().focus().setParagraph().run()
  const heading = /^heading-([1-6])$/.exec(target)
  if (heading) return editor.chain().focus().setHeading({ level: Number(heading[1]) as 1 | 2 | 3 | 4 | 5 | 6 }).run()
  if (target === 'blockquote') return editor.chain().focus().toggleBlockquote().run()
  if (target === 'codeBlock') return editor.chain().focus().toggleCodeBlock().run()
  if (target === 'bulletList') return editor.chain().focus().toggleBulletList().run()
  if (target === 'orderedList') return editor.chain().focus().toggleOrderedList().run()
  return false
})

registerDocumentCommand('move_blocks', (editor, command) => {
  const nodeIds = command.target.kind === 'nodes' ? new Set(command.target.nodeIds) : new Set<string>()
  const targetId = String(command.params.targetId || '')
  const placement = command.params.placement === 'after' ? 'after' : 'before'
  if (!nodeIds.size || !targetId || nodeIds.has(targetId)) return false
  const indexed: Array<{ node: ProseMirrorNode; position: number; id: string }> = []
  editor.state.doc.forEach((node, position) => indexed.push({ node, position, id: String(node.attrs?.nodeId || '') }))
  const selected = indexed.filter((entry) => nodeIds.has(entry.id))
  const target = indexed.find((entry) => entry.id === targetId)
  if (!selected.length || !target) return false
  const contiguous = selected.every((entry, index) => index === 0 || selected[index - 1].position + selected[index - 1].node.nodeSize === entry.position)
  if (!contiguous) return false
  const from = selected[0].position
  const to = selected[selected.length - 1].position + selected[selected.length - 1].node.nodeSize
  const content = Fragment.fromArray(selected.map(({ node }) => node))
  let insertAt = target.position + (placement === 'after' ? target.node.nodeSize : 0)
  if (insertAt > to) insertAt -= to - from
  if (insertAt >= from && insertAt <= to) return false
  const transaction = editor.state.tr.delete(from, to).insert(insertAt, content)
  selectInsertedRange(transaction, insertAt, insertAt + content.size)
  editor.view.dispatch(transaction.scrollIntoView())
  return true
})
