type LayoutMetrics = {
  pageCount: number
  blockCount: number
  contentHeight: number
  documentVersion: number
}

export type DocumentHit = {
  blockId: string
  offset: number
}

type WasmEditor = {
  importMarkdown(markdown: string): void
  replaceMarkdown(markdown: string, checkpoint: boolean): void
  exportMarkdown(): string
  undo(): void
  redo(): void
  layoutMetrics(width: number): LayoutMetrics | Map<string, number>
  hitTest(width: number, x: number, y: number, pageGap: number): DocumentHit | Map<string, unknown> | undefined
  free?: () => void
}

type WasmModule = {
  default: (input?: unknown) => Promise<unknown>
  WasmEditor: new () => WasmEditor
}

let editor: WasmEditor | null = null
let loading: Promise<boolean> | null = null
let mirroredMarkdown = ''

export function initDocumentEngine(markdown = ''): Promise<boolean> {
  if (editor) return Promise.resolve(true)
  if (loading) return loading
  loading = (async () => {
    try {
      const moduleUrl = '/static/v2_svelte/wasm/wa_bridge.js'
      const wasm = (await import(/* @vite-ignore */ moduleUrl)) as WasmModule
      await wasm.default()
      editor = new wasm.WasmEditor()
      editor.importMarkdown(markdown)
      mirroredMarkdown = markdown
      return true
    } catch (error) {
      console.warn('Rust document engine is unavailable; editing remains usable.', error)
      editor = null
      return false
    }
  })()
  return loading
}

export function mirrorMarkdown(markdown: string, checkpoint: boolean): boolean {
  if (!editor || markdown === mirroredMarkdown) return Boolean(editor)
  editor.replaceMarkdown(markdown, checkpoint)
  mirroredMarkdown = markdown
  return true
}

export function undoMarkdown(): string | null {
  if (!editor) return null
  editor.undo()
  mirroredMarkdown = editor.exportMarkdown()
  return mirroredMarkdown
}

export function redoMarkdown(): string | null {
  if (!editor) return null
  editor.redo()
  mirroredMarkdown = editor.exportMarkdown()
  return mirroredMarkdown
}

export function measureDocument(width: number): LayoutMetrics | null {
  if (!editor) return null
  const raw = editor.layoutMetrics(Math.max(320, width || 794))
  if (raw instanceof Map) {
    return {
      pageCount: Number(raw.get('pageCount') || 0),
      blockCount: Number(raw.get('blockCount') || 0),
      contentHeight: Number(raw.get('contentHeight') || 0),
      documentVersion: Number(raw.get('documentVersion') || 0)
    }
  }
  return raw
}

export function hitTestDocument(width: number, x: number, y: number, pageGap = 24): DocumentHit | null {
  if (!editor) return null
  const raw = editor.hitTest(Math.max(320, width || 794), x, y, pageGap)
  if (!raw) return null
  if (raw instanceof Map) {
    const blockId = String(raw.get('blockId') || '')
    return blockId ? { blockId, offset: Number(raw.get('offset') || 0) } : null
  }
  return raw.blockId ? raw : null
}

export function documentEngineReady(): boolean {
  return Boolean(editor)
}
