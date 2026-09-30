import type { Editor } from '@tiptap/core'
import { Fragment, type Node as ProseMirrorNode } from '@tiptap/pm/model'
import { AllSelection, NodeSelection, TextSelection, type Transaction } from '@tiptap/pm/state'

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
  proposal?: Record<string, unknown>
}

type CommandHandler = (editor: Editor, command: DocumentCommand<any>) => boolean

const registry = new Map<string, CommandHandler>()

function insertInlineContent(editor: Editor, content: Record<string, unknown>): boolean {
  const selection = editor.state.selection
  if (selection instanceof NodeSelection && selection.node.isBlock) {
    const inline = editor.state.schema.nodeFromJSON(content)
    const paragraph = editor.state.schema.nodes.paragraph.create(
      { nodeId: null, styleId: 'normal', sectionId: selection.node.attrs?.sectionId || null },
      inline
    )
    const insertAt = selection.to
    const transaction = editor.state.tr.insert(insertAt, paragraph)
    transaction.setSelection(TextSelection.create(transaction.doc, insertAt + 2))
    editor.view.dispatch(transaction.scrollIntoView())
    return true
  }
  return editor.chain().focus().insertContent(content).run()
}

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

function selectCommandTarget(editor: Editor, target: CommandTarget): boolean {
  if (target.kind === 'selection') {
    if (target.from === undefined || target.to === undefined) return true
    const from = Math.max(0, Math.min(editor.state.doc.content.size, target.from))
    const to = Math.max(from, Math.min(editor.state.doc.content.size, target.to))
    editor.view.dispatch(editor.state.tr.setSelection(TextSelection.create(editor.state.doc, from, to)))
    return true
  }
  if (target.kind === 'document') {
    editor.view.dispatch(editor.state.tr.setSelection(new AllSelection(editor.state.doc)))
    return true
  }
  const matches: Array<{ position: number; size: number }> = []
  const wanted = target.kind === 'nodes' ? new Set(target.nodeIds) : null
  const sectionId = target.kind === 'section' ? target.sectionId : ''
  editor.state.doc.forEach((node, position) => {
    const selected = wanted ? wanted.has(String(node.attrs?.nodeId || '')) : String(node.attrs?.sectionId || '') === sectionId
    if (selected) matches.push({ position, size: node.nodeSize })
  })
  if (!matches.length || (wanted && matches.length !== wanted.size)) return false
  const from = Math.min(...matches.map((item) => item.position))
  const to = Math.max(...matches.map((item) => item.position + item.size))
  editor.view.dispatch(editor.state.tr.setSelection(TextSelection.create(editor.state.doc, Math.min(from + 1, to), Math.max(from + 1, to - 1))))
  return true
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
    const proposal = {
      command,
      selection: { from: editor.state.selection.from, to: editor.state.selection.to },
      documentVersion: Number(editor.state.doc.attrs?.version || 0)
    }
    window.dispatchEvent(new CustomEvent('wa-ai-command-proposal', { detail: proposal }))
    return {
      ok: true,
      changed: false,
      commandId: command.id,
      affectedNodeIds: [],
      warnings: ['pending_user_review'],
      proposal
    }
  }
  const before = editor.state.doc.content.size
  try {
    if (!selectCommandTarget(editor, command.target)) throw new Error('command_target_not_found')
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
registerDocumentCommand('set_link', (editor, command) => {
  const href = String(command.params.href || '').trim()
  if (!href || !/^(https?:\/\/|mailto:|#)/i.test(href)) return false
  return editor.chain().focus().extendMarkRange('link').setMark('link', {
    href,
    title: String(command.params.title || '').trim() || null,
    target: command.params.target === '_self' ? '_self' : '_blank'
  }).run()
})
registerDocumentCommand('unset_link', (editor) => editor.chain().focus().extendMarkRange('link').unsetMark('link').run())
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
  if ('fontWeight' in command.params) {
    const weight = String(command.params.fontWeight || '')
    if (!['400', '500', '600', '700'].includes(weight)) return false
    attrs.fontWeight = weight
  }
  if ('fontStyle' in command.params) {
    const style = String(command.params.fontStyle || '')
    if (!['normal', 'italic'].includes(style)) return false
    attrs.fontStyle = style
  }
  if ('fontVariant' in command.params) {
    const variant = String(command.params.fontVariant || '')
    if (!['normal', 'small-caps'].includes(variant)) return false
    attrs.fontVariant = variant
  }
  if ('textShadow' in command.params) attrs.textShadow = String(command.params.textShadow || '') || null
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
registerDocumentCommand('list_indent', (editor) => editor.chain().focus().sinkListItem('listItem').run())
registerDocumentCommand('list_outdent', (editor) => editor.chain().focus().liftListItem('listItem').run())
registerDocumentCommand('toggle_blockquote', (editor) => editor.chain().focus().toggleBlockquote().run())
registerDocumentCommand('toggle_code_block', (editor) => editor.chain().focus().toggleCodeBlock().run())
registerDocumentCommand('insert_page_break', (editor) => editor.chain().focus().insertContent([
  { type: 'pageBreak', attrs: { nodeId: null } },
  { type: 'paragraph', attrs: { nodeId: null, styleId: 'normal' } }
]).run())
registerDocumentCommand('insert_section_break', (editor, command) => {
  const breakType = ['continuous', 'nextPage', 'oddPage', 'evenPage'].includes(String(command.params.breakType))
    ? String(command.params.breakType)
    : 'nextPage'
  return editor.chain().focus().insertContent([
    {
      type: 'sectionBreak',
      attrs: {
        nodeId: null,
        sectionId: null,
        payload: { nextSectionId: `section_${crypto.randomUUID().replace(/-/g, '')}`, breakType }
      }
    },
    { type: 'paragraph', attrs: { nodeId: null, styleId: 'normal' } }
  ]).run()
})
registerDocumentCommand('insert_figure', (editor, command) => editor.chain().focus().insertContent([
  {
    type: 'figure',
    attrs: {
      nodeId: null,
      payload: {
        ...command.params,
        caption: String(command.params.caption || ''),
        source: String(command.params.source || '')
      }
    }
  },
  { type: 'paragraph', attrs: { nodeId: null, styleId: 'normal' } }
]).run())
registerDocumentCommand('update_figure', (editor, command) => {
  if (!editor.isActive('figure')) return false
  const current = editor.getAttributes('figure').payload
  const payload = current && typeof current === 'object' ? current as Record<string, unknown> : {}
  return editor.chain().focus().updateAttributes('figure', {
    payload: {
      ...payload,
      caption: String(command.params.caption ?? payload.caption ?? ''),
      alt: String(command.params.alt ?? payload.alt ?? ''),
      widthPercent: Math.max(10, Math.min(100, Number(command.params.widthPercent ?? payload.widthPercent ?? 100))),
      alignment: ['left', 'center', 'right'].includes(String(command.params.alignment ?? payload.alignment))
        ? String(command.params.alignment ?? payload.alignment)
        : 'center',
      wrap: ['inline', 'square'].includes(String(command.params.wrap ?? payload.wrap))
        ? String(command.params.wrap ?? payload.wrap)
        : 'inline',
      spec: command.params.spec ?? payload.spec,
      svg: command.params.svg ?? payload.svg,
      src: command.params.src ?? payload.src,
      editableSource: command.params.editableSource ?? payload.editableSource,
      crop: command.params.crop ?? payload.crop
    }
  }).run()
})
registerDocumentCommand('insert_table', (editor, command) => editor.chain().focus().insertTable({
  rows: Math.max(1, Number(command.params.rows || 3)),
  cols: Math.max(1, Number(command.params.columns || command.params.cols || 3)),
  withHeaderRow: command.params.withHeaderRow !== false
}).run())
registerDocumentCommand('table_add_row_before', (editor) => editor.chain().focus().addRowBefore().run())
registerDocumentCommand('table_add_row_after', (editor) => editor.chain().focus().addRowAfter().run())
registerDocumentCommand('table_delete_row', (editor) => editor.chain().focus().deleteRow().run())
registerDocumentCommand('table_add_column_before', (editor) => editor.chain().focus().addColumnBefore().run())
registerDocumentCommand('table_add_column_after', (editor) => editor.chain().focus().addColumnAfter().run())
registerDocumentCommand('table_delete_column', (editor) => editor.chain().focus().deleteColumn().run())
registerDocumentCommand('table_merge_cells', (editor) => editor.chain().focus().mergeCells().run())
registerDocumentCommand('table_split_cell', (editor) => editor.chain().focus().splitCell().run())
registerDocumentCommand('table_toggle_header_row', (editor) => editor.chain().focus().toggleHeaderRow().run())
registerDocumentCommand('table_toggle_header_column', (editor) => editor.chain().focus().toggleHeaderColumn().run())
registerDocumentCommand('table_toggle_header_cell', (editor) => editor.chain().focus().toggleHeaderCell().run())
registerDocumentCommand('table_set_caption', (editor, command) => editor.chain().focus().updateAttributes('table', {
  caption: String(command.params.caption || '').slice(0, 200)
}).run())
registerDocumentCommand('table_set_repeat_header', (editor, command) => editor.chain().focus().updateAttributes('table', {
  repeatHeader: Boolean(command.params.enabled)
}).run())
registerDocumentCommand('table_set_alignment', (editor, command) => editor.chain().focus().updateAttributes('table', {
  tableAlignment: ['left', 'center', 'right'].includes(String(command.params.alignment))
    ? String(command.params.alignment)
    : 'left'
}).run())
registerDocumentCommand('table_set_width', (editor, command) => editor.chain().focus().updateAttributes('table', {
  widthPercent: Math.max(20, Math.min(100, Number(command.params.widthPercent || 100)))
}).run())
registerDocumentCommand('table_set_cell_background', (editor, command) => editor.chain().focus().setCellAttribute(
  'backgroundColor',
  command.params.color ? String(command.params.color) : null
).run())
registerDocumentCommand('table_set_vertical_align', (editor, command) => editor.chain().focus().setCellAttribute(
  'verticalAlign',
  ['top', 'middle', 'bottom'].includes(String(command.params.alignment)) ? String(command.params.alignment) : 'top'
).run())
registerDocumentCommand('table_set_cell_border', (editor, command) => editor.chain().focus()
  .setCellAttribute('borderColor', String(command.params.color || '#64748b'))
  .setCellAttribute('borderWidthPt', Math.max(0, Math.min(6, Number(command.params.widthPt || 0.75))))
  .run())
registerDocumentCommand('table_set_row_height', (editor, command) => {
  const selection = editor.state.selection
  for (let depth = selection.$from.depth; depth > 0; depth -= 1) {
    if (selection.$from.node(depth).type.name !== 'tableRow') continue
    const position = selection.$from.before(depth)
    const node = selection.$from.node(depth)
    editor.view.dispatch(editor.state.tr.setNodeMarkup(position, undefined, { ...node.attrs, heightPx: Math.max(20, Math.min(500, Number(command.params.heightPx || 36))) }))
    return true
  }
  return false
})
registerDocumentCommand('table_distribute_columns', (editor) => {
  const selection = editor.state.selection
  let tableDepth = -1
  for (let depth = selection.$from.depth; depth > 0; depth -= 1) {
    if (selection.$from.node(depth).type.name === 'table') {
      tableDepth = depth
      break
    }
  }
  if (tableDepth < 0) return false
  const table = selection.$from.node(tableDepth)
  const tablePosition = selection.$from.before(tableDepth)
  let transaction = editor.state.tr
  table.descendants((node, position) => {
    if (node.type.name === 'tableCell' || node.type.name === 'tableHeader') {
      transaction = transaction.setNodeMarkup(tablePosition + 1 + position, undefined, { ...node.attrs, colwidth: null })
    }
  })
  editor.view.dispatch(transaction)
  return true
})
registerDocumentCommand('table_distribute_rows', (editor) => {
  const selection = editor.state.selection
  let tableDepth = -1
  for (let depth = selection.$from.depth; depth > 0; depth -= 1) {
    if (selection.$from.node(depth).type.name === 'table') {
      tableDepth = depth
      break
    }
  }
  if (tableDepth < 0) return false
  const table = selection.$from.node(tableDepth)
  const tablePosition = selection.$from.before(tableDepth)
  let heightPx = 36
  table.forEach((row) => { heightPx = Math.max(heightPx, Number(row.attrs.heightPx) || 0) })
  let transaction = editor.state.tr
  table.forEach((row, offset) => {
    transaction = transaction.setNodeMarkup(tablePosition + 1 + offset, undefined, { ...row.attrs, heightPx })
  })
  editor.view.dispatch(transaction)
  return true
})
registerDocumentCommand('table_delete', (editor) => editor.chain().focus().deleteTable().run())
registerDocumentCommand('insert_equation', (editor, command) => editor.chain().focus().insertContent([
  { type: 'equationBlock', attrs: { nodeId: null, payload: { latex: String(command.params.latex || '') } } },
  { type: 'paragraph', attrs: { nodeId: null, styleId: 'normal' } }
]).run())
registerDocumentCommand('insert_inline_equation', (editor, command) => {
  const latex = String(command.params.latex || '').trim()
  if (!latex) return false
  return insertInlineContent(editor, { type: 'inlineEquation', attrs: { payload: { fieldKind: 'equation', latex } } })
})
registerDocumentCommand('insert_footnote_reference', (editor, command) => {
  const noteId = String(command.params.noteId || '').trim()
  const text = String(command.params.text || '').trim()
  if (!noteId || !text) return false
  return insertInlineContent(editor, {
    type: 'footnoteReference',
    attrs: { payload: { noteId, label: String(command.params.label || ''), text } }
  })
})
registerDocumentCommand('insert_endnote_reference', (editor, command) => {
  const noteId = String(command.params.noteId || '').trim()
  const text = String(command.params.text || '').trim()
  if (!noteId || !text) return false
  return insertInlineContent(editor, {
    type: 'endnoteReference',
    attrs: { payload: { noteId, label: String(command.params.label || ''), text } }
  })
})
registerDocumentCommand('insert_citation', (editor, command) => {
  const citationId = String(command.params.citationId || '').trim()
  if (!citationId) return false
  return insertInlineContent(editor, {
    type: 'citationReference',
    attrs: { payload: { ...command.params, citationId, label: String(command.params.label || citationId) } }
  })
})
registerDocumentCommand('insert_cross_reference', (editor, command) => {
  const targetId = String(command.params.targetId || '').trim()
  if (!targetId) return false
  return insertInlineContent(editor, {
    type: 'crossReference',
    attrs: { payload: { fieldKind: 'crossReference', targetId, targetText: String(command.params.targetText || ''), label: String(command.params.label || '') } }
  })
})
registerDocumentCommand('update_table_of_contents', (editor) => {
  const entries: Array<{ id: string; level: number; text: string }> = []
  editor.state.doc.descendants((node) => {
    if (node.type.name === 'heading') entries.push({
      id: String(node.attrs.nodeId || ''),
      level: Math.max(1, Math.min(6, Number(node.attrs.level || 1))),
      text: node.textContent || '未命名标题'
    })
  })
  let tocPosition = -1
  editor.state.doc.forEach((node, position) => {
    if (tocPosition < 0 && node.type.name === 'tableOfContents') tocPosition = position
  })
  if (tocPosition >= 0) {
    const current = editor.state.doc.nodeAt(tocPosition)
    if (!current) return false
    editor.view.dispatch(editor.state.tr.setNodeMarkup(tocPosition, undefined, {
      ...current.attrs,
      payload: { entries, updatedAt: Date.now() }
    }))
registerDocumentCommand('update_equation', (editor, command) => editor.isActive('equationBlock') && editor.chain().focus().updateAttributes('equationBlock', {
  payload: { ...(editor.getAttributes('equationBlock').payload || {}), latex: String(command.params.latex || '') }
}).run())
    return true
  }
  return editor.chain().focus().insertContent([
    { type: 'tableOfContents', attrs: { nodeId: null, sectionId: null, payload: { entries, updatedAt: Date.now() } } },
    { type: 'paragraph', attrs: { nodeId: null, styleId: 'normal' } }
  ]).run()
})
registerDocumentCommand('update_bibliography', (editor, command) => {
  const entries = Array.isArray(command.params.entries) ? command.params.entries : []
  let position = -1
  editor.state.doc.forEach((node, offset) => {
    if (position < 0 && node.type.name === 'bibliography') position = offset
  })
  if (position >= 0) {
    const current = editor.state.doc.nodeAt(position)
    if (!current) return false
    editor.view.dispatch(editor.state.tr.setNodeMarkup(position, undefined, { ...current.attrs, payload: { entries, updatedAt: Date.now() } }))
    return true
  }
  return editor.chain().focus().insertContent([
    { type: 'bibliography', attrs: { nodeId: null, sectionId: null, payload: { entries, updatedAt: Date.now() } } },
    { type: 'paragraph', attrs: { nodeId: null, styleId: 'normal' } }
  ]).run()
})
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

registerDocumentCommand('toggle_block_collapsed', (editor) => {
  const selected = selectedTopLevelRange(editor)
  if (!selected) return false
  const collapse = !selected.nodes.every(({ node }) => Boolean(node.attrs?.collapsed))
  const transaction = editor.state.tr
  for (const { node, position } of selected.nodes) {
    transaction.setNodeMarkup(position, undefined, { ...node.attrs, collapsed: collapse })
  }
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
