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
  | 'heading4'
  | 'heading5'
  | 'heading6'
  | 'paragraph'
  | 'list-bullet'
  | 'list-number'
  | 'quote'
  | 'code'
  | 'image'
  | 'diagram'
  | 'table'
  | 'table-row-before'
  | 'table-row-after'
  | 'table-row-delete'
  | 'table-column-before'
  | 'table-column-after'
  | 'table-column-delete'
  | 'table-merge-cells'
  | 'table-split-cell'
  | 'table-toggle-header-row'
  | 'table-toggle-header-column'
  | 'table-toggle-header-cell'
  | 'table-distribute-columns'
  | 'table-distribute-rows'
  | 'table-toggle-repeat-header'
  | 'table-delete'
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
  | 'section-break-next'
  | 'section-break-continuous'
  | 'link'
  | 'hr'
  | 'superscript'
  | 'subscript'
  | 'math-inline'
  | 'math-block'
  | 'footnote'
  | 'endnote'
  | 'citation'
  | 'bibliography'
  | 'toc'
  | 'caption'
  | 'cross-reference'
  | 'thesis-structure'
  | 'view-outline'
  | 'zoom-in'
  | 'zoom-out'
  | 'zoom-100'
  | 'find-replace'
  | 'proofread'
  | 'add-comment'
  | 'track-changes'
  | 'review-revisions'
  | 'markdown-import'
  | 'word-import'
  | 'markdown-export'
  | 'view-shortcuts'
  | 'style-manager'
  | `style:${string}`
  | `font:${string}`
  | `size:${string}`
  | `color:${string}`
  | `bgcolor:${string}`
  | `line-height:${string}`
  | `margin:${string}`
  | `letter-spacing:${string}`
  | `text-transform:${string}`
  | `font-weight:${string}`
  | `font-style:${string}`
  | `font-variant:${string}`
  | `text-shadow:${string}`
  | `space-before:${string}`
  | `space-after:${string}`
  | `left-indent:${string}`
  | `right-indent:${string}`
  | `first-indent:${string}`
  | `keep-with-next:${string}`
  | `keep-lines:${string}`
  | `page-break-before:${string}`
  | `tab-stop:${string}`
  | `border-color:${string}`
  | `shading-color:${string}`
  | `table-cell-bg:${string}`
  | `table-cell-valign:${string}`
  | `table-cell-border:${string}`
  | `table-row-height:${string}`
  | `table-caption:${string}`
  | `table-align:${string}`
  | `table-width:${string}`

export interface EditorCommandRequest {
  command: EditorCommand
  params?: Record<string, unknown>
}
