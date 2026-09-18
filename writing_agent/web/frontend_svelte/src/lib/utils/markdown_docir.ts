import {
  escapeHtml,
  renderHeadingHtml,
  styleAttrFromBlock,
  type UnknownRecord
} from './markdown_common'
import { blockToHtml, blockToLines } from './markdown_blocks'

function pushSectionLines(section: UnknownRecord, lines: string[]): void {
  const title = String(section.title || '').trim()
  if (title) {
    const level = Math.min(6, Math.max(1, Number(section.level || 2)))
    lines.push(`${'#'.repeat(level)} ${title}`)
  }

  const blocks = Array.isArray(section.blocks) ? (section.blocks as UnknownRecord[]) : []
  for (const block of blocks) {
    lines.push(...blockToLines(block))
  }

  const children = Array.isArray(section.children) ? (section.children as UnknownRecord[]) : []
  for (const child of children) {
    pushSectionLines(child, lines)
  }
}

function renderSectionHtml(section: UnknownRecord): string {
  const title = String(section.title || '').trim()
  const level = Math.min(6, Math.max(1, Number(section.level || 2)))
  const sectionId = String(section.id || '').trim()
  const sectionAttr = sectionId ? ` data-section-id="${escapeHtml(sectionId)}" data-section-level="${level}"` : ''
  const sectionStyle = styleAttrFromBlock({ style: section.style })
  const sectionAttrs = `${sectionAttr}${sectionStyle}`

  const parts: string[] = []
  if (title) {
    parts.push(renderHeadingHtml(level, title, sectionAttrs))
  }

  const blocks = Array.isArray(section.blocks) ? (section.blocks as UnknownRecord[]) : []
  for (const block of blocks) {
    const html = blockToHtml(block)
    if (html) parts.push(html)
  }

  const children = Array.isArray(section.children) ? (section.children as UnknownRecord[]) : []
  for (const child of children) {
    parts.push(renderSectionHtml(child))
  }

  return parts.join('')
}

export function simpleSectionsToMarkdown(doc: UnknownRecord): string | null {
  const title = String(doc.title || '').trim()
  const sections = Array.isArray(doc.sections) ? (doc.sections as UnknownRecord[]) : []
  const lines: string[] = []
  if (title) lines.push(`# ${title}`)

  for (const sec of sections) {
    const secTitle = String(sec.title || sec.name || sec.section || '').trim()
    if (!secTitle) continue
    lines.push(`## ${secTitle}`)

    let content: unknown = sec.content ?? sec.text ?? sec.body
    if (Array.isArray(content)) {
      content = content
        .map((v) => String(v || '').trim())
        .filter(Boolean)
        .join('\n\n')
    }
    const text = String(content || '').trim()
    if (text) lines.push(text)
  }

  return lines.length ? lines.join('\n\n').trim() : null
}

export function docIrToMarkdown(doc: UnknownRecord): string | null {
  const sections = Array.isArray(doc.sections) ? (doc.sections as UnknownRecord[]) : []
  const lines: string[] = []
  for (const sec of sections) {
    pushSectionLines(sec, lines)
  }
  return lines.length ? lines.join('\n\n').trim() : null
}

export function docIrToHtml(doc: UnknownRecord): string | null {
  const sections = Array.isArray(doc.sections) ? (doc.sections as UnknownRecord[]) : []
  if (sections.length === 0) return null

  const parts: string[] = ['<div class="wa-doc">']
  parts.push('<div class="wa-header" contenteditable="false"></div>')
  parts.push('<div class="wa-body">')
  for (const sec of sections) {
    parts.push(renderSectionHtml(sec))
  }
  parts.push('</div>')
  parts.push('<div class="wa-footer" contenteditable="false"></div>')
  parts.push('</div>')
  return parts.join('')
}
