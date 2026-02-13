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
  | 'heading1'
  | 'heading2'
  | 'list-bullet'
  | 'list-number'
  | 'quote'
  | 'code'
  | 'image'
  | 'table'
  | 'undo'
  | 'redo'
  | 'clear-format'
