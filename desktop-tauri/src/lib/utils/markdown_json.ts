import { blocksToHtml, blocksToMarkdown, inferTitleFromBlocks } from './markdown_blocks'
import { buildDocIrFromBlocks } from './markdown_builder'
import {
  HEADING_GLUE_PREFIXES,
  HEADING_GLUE_PUNCT,
  looksLikeBodySentence,
  splitHeadingGlue,
  splitParagraphForBlocks
} from './markdown_heading_glue'
import { docIrToHtml, docIrToMarkdown, simpleSectionsToMarkdown } from './markdown_docir'
import { normalizeLines, type UnknownRecord } from './markdown_common'

export function extractJsonBlock(text: string): string | null {
  let s = String(text || '').trim()
  if (!s) return null

  if (s.startsWith('```')) {
    s = s.replace(/^```json/i, '').replace(/^```/, '')
    if (s.endsWith('```')) s = s.slice(0, -3)
    s = s.trim()
  }
  if (s.startsWith('{') || s.startsWith('[')) return s
  return null
}

export function safeJsonParse(raw: string): unknown | null {
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

export function parseNdjsonBlocks(text: string): UnknownRecord[] {
  const blocks: UnknownRecord[] = []
  const lines = String(text || '').split('\n')
  for (const line of lines) {
    const t = line.trim()
    if (!t) continue
    const obj = safeJsonParse(t)
    if (obj && typeof obj === 'object' && !Array.isArray(obj)) {
      blocks.push(obj as UnknownRecord)
    }
  }
  return blocks
}

function jsonToMarkdown(data: unknown): string | null {
  if (!data || typeof data !== 'object') return null
  const root = data as UnknownRecord

  if (root.doc_ir && typeof root.doc_ir === 'object') {
    return docIrToMarkdown(root.doc_ir as UnknownRecord)
  }
  if (Array.isArray(data)) {
    return blocksToMarkdown(data as UnknownRecord[])
  }
  if (Array.isArray(root.blocks)) {
    return blocksToMarkdown(root.blocks as UnknownRecord[])
  }
  if (Array.isArray(root.sections)) {
    const sections = root.sections as UnknownRecord[]
    const hasDocIr = sections.some((s) => s && (s.blocks || s.children))
    if (hasDocIr) return docIrToMarkdown(root)
    return simpleSectionsToMarkdown(root)
  }
  return null
}

function jsonToHtml(data: unknown): string | null {
  if (!data || typeof data !== 'object') return null
  const root = data as UnknownRecord

  if (root.doc_ir && typeof root.doc_ir === 'object') {
    return docIrToHtml(root.doc_ir as UnknownRecord)
  }
  if (Array.isArray(data)) {
    return blocksToHtml(data as UnknownRecord[])
  }
  if (Array.isArray(root.blocks)) {
    return blocksToHtml(root.blocks as UnknownRecord[], String(root.title || '').trim())
  }
  if (Array.isArray(root.sections)) {
    return docIrToHtml(root)
  }
  return null
}

export function convertJsonToMarkdown(src: string): string | null {
  const trimmed = String(src || '').trim()
  if (!trimmed) return null
  if (/^#{1,3}\s+/m.test(trimmed)) return null

  const jsonBlock = extractJsonBlock(trimmed)
  if (jsonBlock) {
    const parsed = safeJsonParse(jsonBlock)
    if (parsed !== null) {
      const md = jsonToMarkdown(parsed)
      if (md) return md
    }
  }

  const ndjsonBlocks = parseNdjsonBlocks(trimmed)
  if (ndjsonBlocks.length > 0) {
    return blocksToMarkdown(ndjsonBlocks)
  }
  return null
}

function renderJsonText(src: string): string | null {
  const trimmed = String(src || '').trim()
  if (!trimmed) return null

  const jsonBlock = extractJsonBlock(trimmed)
  if (jsonBlock) {
    const parsed = safeJsonParse(jsonBlock)
    if (parsed !== null) {
      const html = jsonToHtml(parsed)
      if (html) return html
    }
  }

  const ndjsonBlocks = parseNdjsonBlocks(trimmed)
  if (ndjsonBlocks.length > 0) {
    const html = blocksToHtml(ndjsonBlocks)
    if (html) return html
  }
  return null
}

function renderFromUnknown(docIr: unknown): string | null {
  if (!docIr) return null
  if (typeof docIr === 'string') {
    const parsed = safeJsonParse(docIr)
    return parsed ? jsonToHtml(parsed) : null
  }
  if (typeof docIr !== 'object') return null
  return jsonToHtml(docIr)
}

export function renderDocument(text: string, docIr?: unknown, preferText?: boolean): string {
  const src = String(text || '')
  const jsonHtml = renderJsonText(src)
  if (jsonHtml) return jsonHtml

  if (!preferText) {
    const htmlFromDoc = renderFromUnknown(docIr)
    if (htmlFromDoc) return htmlFromDoc
  }
  return ''
}

export function textToDocIr(text: string): UnknownRecord | null {
  let src = String(text || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  if (!src.endsWith('\n')) {
    const lastBreak = src.lastIndexOf('\n')
    const lastLine = lastBreak >= 0 ? src.slice(lastBreak + 1) : src
    const short = lastLine.trim().length <= 4
    if (short && (/^#{1,6}\s*\S*$/.test(lastLine) || /^[-*•·]\s*\S*$/.test(lastLine))) {
      src = lastBreak >= 0 ? src.slice(0, lastBreak + 1) : ''
    }
  }
  if (!src.trim()) return null

  const lines = normalizeLines(src.split('\n'))
  const blocks: UnknownRecord[] = []
  let title = ''
  let para: string[] = []
  let listItems: string[] = []
  let listOrdered: boolean | null = null

  const pushParagraphBlocks = (inputText: string) => {
    const pieces = splitParagraphForBlocks(String(inputText || ''))
    for (const piece of pieces) {
      const clean = String(piece || '').trim()
      if (clean) blocks.push({ type: 'paragraph', text: clean })
    }
  }

  const flushPara = () => {
    if (!para.length) return
    const joined = para.join(' ').replace(/\s+/g, ' ').trim()
    if (joined) pushParagraphBlocks(joined)
    para = []
  }

  const flushList = () => {
    if (!listItems.length) return
    blocks.push({ type: 'list', items: listItems.slice(), ordered: Boolean(listOrdered) })
    listItems = []
    listOrdered = null
  }

  let prevBlank = true
  for (const raw of lines) {
    const line = String(raw || '')
    const trimmed = line.trim()
    if (!trimmed) {
      flushPara()
      flushList()
      prevBlank = true
      continue
    }
    if (/^#{1,6}$/.test(trimmed)) continue

    const headingMatch = /^(#{1,3})\s*(.+)$/.exec(trimmed)
    if (headingMatch) {
      flushPara()
      flushList()
      const level = Math.min(3, Math.max(1, headingMatch[1].length))
      let headingText = String(headingMatch[2] || '').trim()
      let rest = ''
      const split = splitHeadingGlue(headingText)
      if (split) {
        headingText = split.heading
        rest = split.rest
      }
      if (level === 1 && !title && headingText) title = headingText
      blocks.push({ type: 'heading', level, text: headingText || '章节' })
      if (rest) pushParagraphBlocks(rest)
      prevBlank = false
      continue
    }

    const numMatch = /^(\d+(?:\.\d+){0,3})[\.、\)]?\s+(.+)$/.exec(trimmed)
    if (numMatch) {
      const num = String(numMatch[1] || '')
      let headingText = String(numMatch[2] || '').trim()
      const dotCount = (num.match(/\./g) || []).length
      const level = Math.min(6, 2 + dotCount)
      const split = splitHeadingGlue(headingText)
      const shortHeading = headingText.length <= 16 && !HEADING_GLUE_PUNCT.test(headingText)
      const prefixMatch = HEADING_GLUE_PREFIXES.some((p) => headingText.startsWith(p))
      const bodyLike = looksLikeBodySentence(headingText)
      const canHeading = split || shortHeading || prefixMatch || ((prevBlank || (!para.length && !listItems.length)) && !bodyLike)
      if (headingText && canHeading) {
        flushPara()
        flushList()
        let rest = ''
        if (split) {
          headingText = split.heading
          rest = split.rest
        }
        if (level === 1 && !title && headingText) title = headingText
        blocks.push({ type: 'heading', level, text: headingText || '章节' })
        if (rest) pushParagraphBlocks(rest)
        prevBlank = false
        continue
      }
    }

    const marker = trimmed.match(/^\[\[(FIGURE|TABLE)\s*:\s*(\{[\s\S]*\})\s*\]\]$/i)
    if (marker) {
      flushPara()
      flushList()
      const kind = String(marker[1] || '').toLowerCase()
      const payload = safeJsonParse(marker[2]) || { raw: marker[2] }
      if (kind === 'table') {
        blocks.push({ type: 'table', table: payload })
      } else {
        blocks.push({ type: 'figure', figure: payload })
      }
      continue
    }

    const bulletMatch = trimmed.match(/^[-*•·]\s+(.*)$/)
    const orderedMatch = trimmed.match(/^\d+[\.\)]\s+(.*)$/)
    if (bulletMatch || orderedMatch) {
      flushPara()
      const ordered = Boolean(orderedMatch)
      if (listOrdered === null) listOrdered = ordered
      if (listOrdered !== ordered) {
        flushList()
        listOrdered = ordered
      }
      const item = String(orderedMatch?.[1] || bulletMatch?.[1] || '').trim()
      if (item) listItems.push(item)
      prevBlank = false
      continue
    }

    flushList()
    para.push(trimmed)
    prevBlank = false
  }

  flushPara()
  flushList()

  const docTitle = title || inferTitleFromBlocks(blocks) || '自动生成文档'
  return buildDocIrFromBlocks(blocks, docTitle)
}
