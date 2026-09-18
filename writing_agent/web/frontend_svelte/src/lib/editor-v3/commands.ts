import type { Editor } from '@tiptap/core'

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
registerDocumentCommand('set_alignment', (editor, command) => {
  const alignment = String(command.params.alignment || '')
  if (!['left', 'center', 'right', 'justify'].includes(alignment)) return false
  return editor.chain().focus().setTextAlign(alignment).run()
})
registerDocumentCommand('apply_style', (editor, command) => {
  const styleId = String(command.params.styleId || 'normal')
  if (styleId === 'normal') return editor.chain().focus().setParagraph().updateAttributes('paragraph', { styleId }).run()
  const match = /^heading-([1-6])$/.exec(styleId)
  if (!match) return editor.chain().focus().updateAttributes('paragraph', { styleId }).run()
  const level = Number(match[1]) as 1 | 2 | 3 | 4 | 5 | 6
  return editor.chain().focus().setHeading({ level }).updateAttributes('heading', { styleId }).run()
})
registerDocumentCommand('undo', (editor) => editor.chain().focus().undo().run())
registerDocumentCommand('redo', (editor) => editor.chain().focus().redo().run())

