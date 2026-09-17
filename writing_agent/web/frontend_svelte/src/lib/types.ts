export type ChatRole = 'user' | 'system'

export interface ChatMessage {
  role: ChatRole
  text: string
}

export interface ThoughtItem {
  label: string
  detail: string
  time: string
}

export interface ToastItem {
  id: number
  message: string
  type: 'ok' | 'bad' | 'info'
}

export type EditorCommand =
  | 'bold'
  | 'italic'
  | 'underline'
  | 'copy'
  | 'cut'
  | 'paste'
  | 'heading1'
  | 'heading2'
  | 'heading3'
  | 'paragraph'
  | 'list-bullet'
  | 'list-number'
  | 'quote'
  | 'code'
  | 'image'
  | 'table'
  | 'undo'
  | 'redo'
  | 'clear-format'
  | 'commit'
  | 'strikethrough'
  | 'align-left'
  | 'align-center'
  | 'align-right'
  | 'align-justify'
  | 'indent-first'
  | 'indent'
  | 'outdent'
  | 'page-break'
  | 'link'
  | 'hr'
  | 'superscript'
  | 'subscript'
  | 'math-inline'
  | 'math-block'
  | 'footnote'
  | 'toc'
  | 'caption'
  | 'cross-reference'
  | 'thesis-structure'
  | 'view-outline'
  | 'zoom-in'
  | 'zoom-out'
  | 'zoom-100'
  | 'find-replace'
  | `font:${string}`
  | `size:${string}`
  | `color:${string}`
  | `bgcolor:${string}`
  | `line-height:${string}`
  | `margin:${string}`
