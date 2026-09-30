import { cloneJson, type DocumentV3, type InlineNode, type V3BlockNode } from '../editor-v3/model'

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
  loadJson(json: string): void
  syncJson(json: string): void
  importMarkdown(markdown: string): void
  replaceMarkdown(markdown: string, checkpoint: boolean): void
  exportMarkdown(): string
  undo(): void
  redo(): void
  layoutMetrics(width: number): LayoutMetrics | Map<string, number>
  layoutProtocol(requestJson: string): string
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

export type LayoutLine = {
  index: number
  text: string
  x: number
  y: number
  width: number
  height: number
  startOffset: number
  endOffset: number
}

export type LayoutBlock = {
  blockId: string
  rustId: string
  sectionId: string
  kind: string
  pageNumber: number
  x: number
  y: number
  width: number
  height: number
  overflow: boolean
  startOffset: number
  endOffset: number
  lines: LayoutLine[]
}

export type LayoutPage = {
  pageNumber: number
  width: number
  height: number
  contentX: number
  contentY: number
  contentWidth: number
  contentHeight: number
  usedHeight: number
  blocks: LayoutBlock[]
  sectionId?: string
  headerText?: string
  footerText?: string
  pageNumberText?: string
  pageNumberPosition?: 'header' | 'footer'
  pageNumberAlignment?: 'left' | 'center' | 'right'
}

export type DocumentLayout = {
  protocolVersion: number
  layoutVersion: number
  documentVersion: number
  pageCount: number
  pages: LayoutPage[]
  blockPage: Record<string, number>
}

type CoreInline = { type: 'text'; value: string }
type CoreBlock = Record<string, unknown> & { id: string; type: string; dirty: boolean }

function textOf(content: Array<V3BlockNode | InlineNode> | undefined): string {
  return (content || []).map((node) => {
    if (node.type === 'text') return node.text || ''
    if (node.type === 'hardBreak') return '\n'
    return 'content' in node ? textOf(node.content) : ''
  }).join('')
}

// Rust core uses UUIDs while Document V3 intentionally allows readable IDs.
// This deterministic mapping keeps layout-cache keys stable without changing
// the source document identifiers exposed to users and AI commands.
function stableUuid(value: string): string {
  let a = 0x811c9dc5
  let b = 0x9e3779b9
  for (let index = 0; index < value.length; index += 1) {
    const code = value.charCodeAt(index)
    a = Math.imul(a ^ code, 0x01000193) >>> 0
    b = Math.imul(b ^ code, 0x85ebca6b) >>> 0
  }
  const c = Math.imul(a ^ (b >>> 16), 0xc2b2ae35) >>> 0
  const d = Math.imul(b ^ (a >>> 13), 0x27d4eb2f) >>> 0
  const hex = [a, b, c, d].map((part) => part.toString(16).padStart(8, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-4${hex.slice(13, 16)}-a${hex.slice(17, 20)}-${hex.slice(20, 32)}`
}

function coreInline(value: string): CoreInline[] {
  return [{ type: 'text', value }]
}

function coreBlock(block: V3BlockNode, rustId: string): CoreBlock | null {
  const text = textOf(block.content)
  if (block.type === 'pageBreak' || block.type === 'sectionBreak' || block.type === 'horizontalRule') return null
  if (block.type === 'heading') {
    return { id: rustId, type: 'heading', level: Number(block.attrs?.level || 1), content: coreInline(text), dirty: false }
  }
  if (block.type === 'bulletList' || block.type === 'orderedList') {
    const items = (block.content || []).filter((item): item is V3BlockNode => 'id' in item).map((item) => ({
      id: stableUuid(item.id),
      content: coreInline(textOf(item.content))
    }))
    return { id: rustId, type: 'list', ordered: block.type === 'orderedList', items, dirty: false }
  }
  if (block.type === 'blockquote') {
    const nestedId = stableUuid(`${block.id}:quote`)
    return { id: rustId, type: 'quote', content: [{ id: nestedId, type: 'paragraph', content: coreInline(text), dirty: false }], dirty: false }
  }
  if (block.type === 'codeBlock' || block.type === 'equationBlock') {
    const equationSource = String(block.attrs?.latex || block.attrs?.source || '')
    return { id: rustId, type: 'code', lang: block.type === 'equationBlock' ? 'math' : String(block.attrs?.language || ''), code: text || equationSource, dirty: false }
  }
  if (block.type === 'table') {
    const table = block.attrs?.table && typeof block.attrs.table === 'object' && !Array.isArray(block.attrs.table)
      ? block.attrs.table as Record<string, unknown>
      : block.attrs || {}
    const richCells = Array.isArray(table.cells) ? table.cells : []
    const rawRows = Array.isArray(table.rows) ? table.rows : []
    const columns = Array.isArray(table.columns) ? table.columns : []
    const rows = richCells.length
      ? richCells.map((row) => Array.isArray(row)
        ? row.map((cell) => ({ content: coreInline(String(cell && typeof cell === 'object' && !Array.isArray(cell) ? (cell as Record<string, unknown>).text ?? '' : cell ?? '')) }))
        : [])
      : [
          ...(columns.length ? [columns.map((cell) => ({ content: coreInline(String(cell ?? '')) }))] : []),
          ...rawRows.map((row) => Array.isArray(row)
            ? row.map((cell) => ({ content: coreInline(String(cell ?? '')) }))
            : [])
        ]
    return { id: rustId, type: 'table', rows: rows.length ? rows : [[{ content: coreInline('表格') }]], dirty: false }
  }
  if (block.type === 'figure') {
    const figure = (block.attrs?.figure && typeof block.attrs.figure === 'object' ? block.attrs.figure : block.attrs) || {}
    return {
      id: rustId,
      type: 'figure',
      url: String((figure as Record<string, unknown>).src || (figure as Record<string, unknown>).url || ''),
      caption: String((figure as Record<string, unknown>).caption || ''),
      size: null,
      dirty: false
    }
  }
  return { id: rustId, type: 'paragraph', content: coreInline(text), dirty: false }
}

function documentV3LayoutInput(document: DocumentV3, layoutVersion: number) {
  const blocks: CoreBlock[] = []
  const sourceIds: Record<string, string> = {}
  const sectionIds: Record<string, string> = {}
  const forcePageBreakBefore: string[] = []
  const keepLinesTogether: string[] = []
  const keepWithNext: string[] = []
  let forceNext = false
  for (const [sectionIndex, section] of document.sections.entries()) {
    if (sectionIndex > 0 && section.breakType !== 'continuous') forceNext = true
    for (const block of section.content) {
      if (block.type === 'pageBreak' || block.type === 'sectionBreak') {
        forceNext = true
        continue
      }
      const rustId = stableUuid(block.id)
      const converted = coreBlock(block, rustId)
      if (!converted) continue
      sourceIds[rustId] = block.id
      sectionIds[rustId] = section.id
      if (forceNext || Boolean(block.attrs?.pageBreakBefore)) forcePageBreakBefore.push(rustId)
      if (Boolean(block.attrs?.keepLinesTogether)) keepLinesTogether.push(rustId)
      if (Boolean(block.attrs?.keepWithNext)) keepWithNext.push(rustId)
      forceNext = false
      blocks.push(converted)
    }
  }
  const section = document.sections[0]
  const layout = section?.layout
  let widthMm = layout?.widthMm || (layout?.pageSize === 'A3' ? 297 : layout?.pageSize === 'A5' ? 148 : layout?.pageSize === 'Letter' ? 215.9 : 210)
  let heightMm = layout?.heightMm || (layout?.pageSize === 'A3' ? 420 : layout?.pageSize === 'A5' ? 210 : layout?.pageSize === 'Letter' ? 279.4 : 297)
  if (layout?.orientation === 'landscape') [widthMm, heightMm] = [heightMm, widthMm]
  const px = (mm: number) => mm * 96 / 25.4
  return {
    coreDocument: {
      id: stableUuid(document.id),
      version: Math.max(1, layoutVersion),
      blocks,
      metadata: { title: document.title || '', author: '', created_at: 0, updated_at: 0 }
    },
    request: {
      pageWidth: px(widthMm),
      pageHeight: px(heightMm),
      marginTop: px(layout?.marginTopMm ?? 25.4),
      marginRight: px(layout?.marginRightMm ?? 25.4),
      marginBottom: px(layout?.marginBottomMm ?? 25.4),
      marginLeft: px(layout?.marginLeftMm ?? 31.8),
      fontSize: 16,
      lineHeight: 1.5,
      layoutVersion,
      forcePageBreakBefore,
      keepLinesTogether,
      keepWithNext,
      widowOrphanLines: 2,
      sourceIds,
      sectionIds
    }
  }
}

export function initDocumentEngine(markdown = ''): Promise<boolean> {
  if (editor) return Promise.resolve(true)
  if (loading) return loading
  loading = (async () => {
    try {
      const moduleUrl = '/static/v2_svelte/wasm/wa_bridge.js?v=layout-protocol-4'
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

export async function paginateDocumentV3(document: DocumentV3, layoutVersion: number): Promise<DocumentLayout | null> {
  if (!editor && !(await initDocumentEngine())) return null
  if (!editor) return null
  const partials: DocumentLayout[] = []
  for (const section of document.sections) {
    const scoped: DocumentV3 = { ...document, sections: [section] }
    const input = documentV3LayoutInput(scoped, layoutVersion)
    editor.syncJson(JSON.stringify(input.coreDocument))
    partials.push(JSON.parse(editor.layoutProtocol(JSON.stringify(input.request))) as DocumentLayout)
  }
  let pageOffset = 0
  const result: DocumentLayout = {
    protocolVersion: partials[0]?.protocolVersion || 1,
    layoutVersion,
    documentVersion: partials[partials.length - 1]?.documentVersion || 0,
    pageCount: 0,
    pages: [],
    blockPage: {}
  }
  for (const [sectionIndex, partial] of partials.entries()) {
    const breakType = document.sections[sectionIndex]?.breakType
    const nextPageNumber = pageOffset + 1
    const needsParityPage = sectionIndex > 0 && (
      (breakType === 'oddPage' && nextPageNumber % 2 === 0) ||
      (breakType === 'evenPage' && nextPageNumber % 2 === 1)
    )
    if (needsParityPage) {
      const basis = partial.pages[0]
      result.pages.push({
        pageNumber: nextPageNumber,
        width: basis?.width || 794,
        height: basis?.height || 1123,
        contentX: basis?.contentX || 0,
        contentY: basis?.contentY || 0,
        contentWidth: basis?.contentWidth || 794,
        contentHeight: basis?.contentHeight || 1123,
        usedHeight: 0,
        blocks: [],
        sectionId: document.sections[sectionIndex]?.id
      })
      pageOffset += 1
    }
    for (const page of partial.pages) {
      page.pageNumber += pageOffset
      for (const block of page.blocks) block.pageNumber = page.pageNumber
      result.pages.push(page)
    }
    for (const [blockId, pageNumber] of Object.entries(partial.blockPage)) result.blockPage[blockId] = pageNumber + pageOffset
    pageOffset += partial.pageCount
  }
  result.pageCount = result.pages.length
  const sections = new Map(document.sections.map((section) => [section.id, section]))
  const sectionIndexes = new Map(document.sections.map((section, index) => [section.id, index]))
  const pageInSection = new Map<string, number>()
  const plain = (blocks: V3BlockNode[]) => blocks.map((block) => textOf(block.content)).filter(Boolean).join(' · ')
  const formatPage = (value: number, format: string) => {
    if (format === 'lowerLetter' || format === 'upperLetter') {
      let number = Math.max(1, value)
      let label = ''
      while (number > 0) {
        number -= 1
        label = String.fromCharCode(65 + (number % 26)) + label
        number = Math.floor(number / 26)
      }
      return format === 'lowerLetter' ? label.toLowerCase() : label
    }
    if (format === 'lowerRoman' || format === 'upperRoman') {
      const table: Array<[number, string]> = [[1000, 'M'], [900, 'CM'], [500, 'D'], [400, 'CD'], [100, 'C'], [90, 'XC'], [50, 'L'], [40, 'XL'], [10, 'X'], [9, 'IX'], [5, 'V'], [4, 'IV'], [1, 'I']]
      let number = Math.max(1, value)
      let label = ''
      for (const [unit, token] of table) while (number >= unit) { label += token; number -= unit }
      return format === 'lowerRoman' ? label.toLowerCase() : label
    }
    return String(value)
  }
  for (const page of result.pages) {
    const section = sections.get(page.blocks[0]?.sectionId || page.sectionId || '') || document.sections[0]
    if (!section) continue
    const sectionIndex = sectionIndexes.get(section.id) || 0
    const definition = cloneJson(section.headerFooter)
    if (sectionIndex > 0) {
      const previous = document.sections[sectionIndex - 1]?.headerFooter
      if (previous && definition.linkHeaderToPrevious) {
        definition.header = cloneJson(previous.header)
        definition.firstPageHeader = cloneJson(previous.firstPageHeader)
        definition.evenPageHeader = cloneJson(previous.evenPageHeader)
      }
      if (previous && definition.linkFooterToPrevious) {
        definition.footer = cloneJson(previous.footer)
        definition.firstPageFooter = cloneJson(previous.firstPageFooter)
        definition.evenPageFooter = cloneJson(previous.evenPageFooter)
      }
    }
    const localPage = (pageInSection.get(section.id) || 0) + 1
    pageInSection.set(section.id, localPage)
    const first = localPage === 1
    const even = localPage % 2 === 0
    const headerBlocks = first && definition.differentFirstPage
      ? definition.firstPageHeader
      : even && definition.differentOddEven ? definition.evenPageHeader : definition.header
    const footerBlocks = first && definition.differentFirstPage
      ? definition.firstPageFooter
      : even && definition.differentOddEven ? definition.evenPageFooter : definition.footer
    page.sectionId = section.id
    page.headerText = plain(headerBlocks)
    page.footerText = plain(footerBlocks)
    page.pageNumberPosition = definition.pageNumber.position
    page.pageNumberAlignment = definition.pageNumber.alignment
    if (definition.pageNumber.enabled) {
      const value = (definition.pageNumber.startAt || 1) + localPage - 1
      page.pageNumberText = formatPage(value, definition.pageNumber.format)
    }
  }
  return result
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
