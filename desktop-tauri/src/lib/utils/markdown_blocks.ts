import {
  blockIdAttr,
  escapeHtml,
  formatInline,
  normalizeFigurePayload,
  normalizeTablePayload,
  normalizeTitle,
  renderHeadingHtml,
  renderParagraphHtml,
  renderRuns,
  styleAttrFromBlock,
  type UnknownRecord
} from './markdown_common'

export function headingFromSectionId(sectionId: string): string {
  const m = /^H([1-6])::(.+)$/.exec(sectionId)
  if (m) {
    const level = Math.min(6, Math.max(1, Number(m[1] || 2)))
    const title = String(m[2] || '').trim()
    if (title) return `${'#'.repeat(level)} ${title}`
  }
  return `## ${sectionId}`
}

export function headingFromSectionIdHtml(sectionId: string): string {
  const m = /^H([1-6])::(.+)$/.exec(sectionId)
  if (m) {
    const level = Math.min(6, Math.max(1, Number(m[1] || 2)))
    const title = String(m[2] || '').trim()
    if (title) return renderHeadingHtml(level, title)
  }
  return renderHeadingHtml(2, sectionId)
}

export function blockToLines(block: UnknownRecord): string[] {
  const t = String(block.type || 'paragraph').toLowerCase()

  if (t === 'paragraph' || t === 'text' || t === 'p') {
    const runs = Array.isArray(block.runs) ? (block.runs as UnknownRecord[]) : null
    const raw = runs && runs.length ? runs.map((r) => String(r.text || '')).join('') : String(block.text || '')
    const text = raw.trim()
    return text ? [text] : []
  }

  if (t === 'list' || t === 'bullets' || t === 'bullet') {
    const ordered = Boolean(block.ordered)
    const items = Array.isArray(block.items) ? (block.items as Array<unknown>) : []
    if (items.length) {
      const cleaned = items.map((v) => String(v || '').trim()).filter(Boolean)
      if (ordered) return cleaned.map((v, idx) => `${idx + 1}. ${v}`)
      return cleaned.map((v) => `- ${v}`)
    }
    const raw = String(block.text || '').trim()
    if (!raw) return []
    const parts = raw.split(/\n+/).map((v) => v.trim()).filter(Boolean)
    if (ordered) {
      return parts.map((v, idx) => `${idx + 1}. ${v.replace(/^\d+[\.\)]\s+/, '')}`)
    }
    return parts.map((v) => (v.startsWith('-') ? v : `- ${v}`))
  }

  if (t === 'table' || t === 'figure') {
    const payload: UnknownRecord = {}
    if (typeof block.caption === 'string') payload.caption = block.caption
    if (Array.isArray(block.columns)) payload.columns = block.columns
    if (Array.isArray(block.rows)) payload.rows = block.rows
    if (block.data && typeof block.data === 'object') payload.data = block.data
    const marker = t === 'table' ? 'TABLE' : 'FIGURE'
    return [`[[${marker}:${JSON.stringify(payload)}]]`]
  }

  if (t === 'reference' || t === 'ref') {
    const text = String(block.text || '').trim()
    if (text) return [text]
    const items = Array.isArray(block.items) ? (block.items as Array<unknown>) : []
    return items.map((v) => String(v || '').trim()).filter(Boolean)
  }

  const fallback = String(block.text || '').trim()
  return fallback ? [fallback] : []
}

export function blockToHtml(block: UnknownRecord): string {
  const idAttr = blockIdAttr(block)
  const styleAttr = styleAttrFromBlock(block)
  const t = String(block.type || 'paragraph').toLowerCase()

  if (t === 'heading') {
    const level = Math.min(6, Math.max(1, Number(block.level || 1)))
    const raw = String(block.text || '')
    const runs = Array.isArray(block.runs) ? (block.runs as UnknownRecord[]) : null
    const text = raw.trim()
    const attrs = `${idAttr}${styleAttr}`
    if (runs && runs.length) {
      const inner = renderRuns(runs)
      return `<h${level}${attrs}>${inner || '<br/>'}</h${level}>`
    }
    if (text) return renderHeadingHtml(level, raw, attrs)
    return attrs ? `<h${level}${attrs}><br/></h${level}>` : ''
  }

  if (t === 'paragraph' || t === 'text' || t === 'p') {
    const raw = String(block.text || '')
    const runs = Array.isArray(block.runs) ? (block.runs as UnknownRecord[]) : null
    const text = raw.trim()
    const attrs = `${idAttr}${styleAttr}`
    if (runs && runs.length) {
      const inner = renderRuns(runs)
      return `<p${attrs}>${inner || '<br/>'}</p>`
    }
    if (text) return `<p${attrs}>${formatInline(raw).replace(/\n/g, '<br/>')}</p>`
    return attrs ? `<p${attrs}><br/></p>` : ''
  }

  if (t === 'list' || t === 'bullets' || t === 'bullet') {
    let ordered = Boolean(block.ordered)
    const itemsRaw = Array.isArray(block.items) ? (block.items as Array<unknown>) : []
    const hasRawItems = itemsRaw.length > 0
    let items = itemsRaw.length
      ? itemsRaw.map((v) => String(v ?? ''))
      : String(block.text || '')
          .split(/\n+/)
          .map((v) => v.trim())
          .filter(Boolean)

    if (!items.length && !hasRawItems) return ''
    if (!ordered) {
      const numRe = /^\d+[\.\)]\s+/
      const numHits = items.filter((v) => numRe.test(v)).length
      if (numHits === items.length) {
        ordered = true
        items = items.map((v) => v.replace(numRe, ''))
      }
    }
    const li = items
      .map((v) => {
        const text = String(v ?? '')
        const trimmed = text.trim()
        if (!trimmed) return '<li><br/></li>'
        return `<li>${formatInline(text)}</li>`
      })
      .join('')
    const attrs = `${idAttr}${styleAttr}`
    return ordered ? `<ol${attrs}>${li}</ol>` : `<ul${attrs}>${li}</ul>`
  }

  if (t === 'table') {
    const payload = normalizeTablePayload(block)
    const caption = payload.caption || 'Table'
    const cols = payload.columns.length ? payload.columns : ['Col 1', 'Col 2']
    const rows = payload.rows.length ? payload.rows : [['', '']]
    const head = cols.map((c) => `<th>${escapeHtml(c)}</th>`).join('')
    const body = rows
      .map((row) => {
        const cells = Array.isArray(row) ? row : [row]
        const full = cols.map((_, idx) => `<td>${escapeHtml(String(cells[idx] ?? ''))}</td>`).join('')
        return `<tr>${full}</tr>`
      })
      .join('')
    const attrs = `${idAttr}${styleAttr}`
    return `<figure class="wa-table"${attrs}><figcaption>${escapeHtml(caption)}</figcaption><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></figure>`
  }

  if (t === 'figure') {
    const payload = normalizeFigurePayload(block)
    const caption = payload.caption || '图示'
    const attrs = `${idAttr}${styleAttr}`
    const encoded = payload.spec && typeof payload.spec === 'object' ? encodeURIComponent(JSON.stringify(payload.spec)) : ''
    const dataAttr = encoded ? ` data-figure-spec="${escapeHtml(encoded)}"` : ''
    return `<figure class="wa-figure"${attrs}${dataAttr}><div class="wa-figure-box">图</div><figcaption>${escapeHtml(caption)}</figcaption></figure>`
  }

  if (t === 'quote') {
    const text = String(block.text || '').trim()
    return text ? `<blockquote>${formatInline(text)}</blockquote>` : ''
  }

  const fallback = String(block.text || '').trim()
  return fallback ? renderParagraphHtml(fallback) : ''
}

export function inferTitleFromBlocks(blocks: UnknownRecord[]): string {
  for (const b of blocks) {
    const t = String(b.type || '').toLowerCase()
    if (t === 'heading' && Number(b.level || 0) === 1) {
      const text = String(b.text || '').trim()
      if (text) return text
    }
  }
  for (const b of blocks) {
    if (String(b.type || '') === 'paragraph') {
      const raw = String(b.text || '').trim()
      if (raw) return raw.slice(0, 24)
    }
  }
  return ''
}

export function blocksToMarkdown(blocks: UnknownRecord[]): string | null {
  const lines: string[] = []
  let lastSection = ''
  for (const block of blocks) {
    const sec = String(block.section_id || block.section_title || '').trim()
    if (sec && sec !== lastSection) {
      const heading = headingFromSectionId(sec)
      if (heading) lines.push(heading)
      lastSection = sec
    }
    lines.push(...blockToLines(block))
  }
  return lines.length ? lines.join('\n\n').trim() : null
}

export function blocksToHtml(blocks: UnknownRecord[], title?: string): string | null {
  const parts: string[] = ['<div class="wa-doc">']
  const docTitle = String(title || '').trim() || inferTitleFromBlocks(blocks)
  parts.push(`<div class="wa-header" contenteditable="false">${escapeHtml(docTitle)}</div>`)
  parts.push('<div class="wa-body">')
  if (docTitle) {
    parts.push(`<div class="wa-title">${formatInline(docTitle)}</div>`)
  }

  let lastSection = ''
  let skippedTitle = false
  for (const block of blocks) {
    const sec = String(block.section_id || block.section_title || '').trim()
    if (sec && sec !== lastSection) {
      const heading = headingFromSectionIdHtml(sec)
      if (heading) parts.push(heading)
      lastSection = sec
    }

    const t = String(block.type || '').toLowerCase()
    if (!skippedTitle && docTitle && t === 'heading' && Number(block.level || 0) === 1) {
      const text = String(block.text || '').trim()
      if (normalizeTitle(text) === normalizeTitle(docTitle)) {
        skippedTitle = true
        continue
      }
    }

    const html = blockToHtml(block)
    if (html) parts.push(html)
  }

  parts.push('</div>')
  parts.push('<div class="wa-footer" contenteditable="false">Page 1</div>')
  parts.push('</div>')
  return parts.length > 2 ? parts.join('') : null
}
