import { docIrToMarkdown } from './markdown_docir'
import { escapeHtml, formatInline, normalizeLines } from './markdown_common'
import { convertJsonToMarkdown, renderDocument as renderDocumentFromJson, textToDocIr } from './markdown_json'

export { docIrToMarkdown, textToDocIr }

export function renderMarkdown(text: string): string {
  const src = String(text || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  if (!src.trim()) {
    return ''
  }

  const normalized = convertJsonToMarkdown(src) || src
  const lines = normalizeLines(normalized.split('\n'))

  let alignMode = ''
  let inCode = false
  let listMode = ''
  const out: string[] = []

  const flushList = () => {
    if (!listMode) return
    out.push(listMode === 'ol' ? '</ol>' : '</ul>')
    listMode = ''
  }

  for (const line of lines) {
    const trimmed = line.trim()

    if (trimmed.startsWith('```')) {
      if (inCode) {
        out.push('</code></pre>')
        inCode = false
      } else {
        flushList()
        out.push('<pre class="code"><code>')
        inCode = true
      }
      continue
    }

    if (inCode) {
      out.push(`${escapeHtml(line)}\n`)
      continue
    }

    if (/^#{1,6}$/.test(trimmed)) {
      continue
    }

    if (trimmed === ':::left') {
      flushList()
      alignMode = 'left'
      continue
    }

    if (trimmed === ':::center') {
      flushList()
      alignMode = 'center'
      continue
    }

    if (trimmed === ':::right') {
      flushList()
      alignMode = 'right'
      continue
    }

    if (trimmed === ':::') {
      flushList()
      alignMode = ''
      continue
    }

    const marker = trimmed.match(/^\[\[(FIGURE|TABLE)\s*:\s*(\{[\s\S]*\})\s*\]\]$/i)
    if (marker) {
      flushList()
      const kind = String(marker[1] || '').toLowerCase()
      let caption = kind === 'figure' ? '图示' : '表格'
      try {
        const data = JSON.parse(marker[2])
        if (data && typeof data.caption === 'string' && data.caption.trim()) {
          caption = data.caption.trim()
        }
      } catch {
        // keep fallback caption
      }
      if (kind === 'figure') {
        out.push(`<figure class="wa-figure" data-wa-figure="1"><div class="wa-figure-box">图</div><figcaption>${escapeHtml(caption)}</figcaption></figure>`)
      } else {
        out.push(`<div class="wa-table" data-wa-table="1"><div class="wa-table-box">表</div><div class="wa-table-caption">${escapeHtml(caption)}</div></div>`)
      }
      continue
    }

    const h = trimmed.match(/^(#{1,3})\s*(.+?)\s*$/)
    if (h) {
      flushList()
      const level = Math.min(3, h[1].length)
      out.push(`<h${level}>${formatInline(h[2])}</h${level}>`)
      continue
    }

    if (!trimmed) {
      if (listMode) {
        continue
      }
      flushList()
      out.push('<p><br/></p>')
      continue
    }

    const liBullet = trimmed.match(/^-\s+(.+)/)
    const liNum = trimmed.match(/^\d+\.\s+(.+)/)
    if (liBullet || liNum) {
      const kind = liBullet ? 'ul' : 'ol'
      if (!listMode) {
        listMode = kind
        out.push(kind === 'ol' ? '<ol>' : '<ul>')
      } else if (listMode !== kind) {
        flushList()
        listMode = kind
        out.push(kind === 'ol' ? '<ol>' : '<ul>')
      }
      const item = (liBullet || liNum)![1]
      out.push(`<li>${formatInline(item)}</li>`)
      continue
    }

    flushList()
    const style = alignMode ? ` style="text-align:${alignMode};"` : ''
    out.push(`<p${style}>${formatInline(line)}</p>`)
  }

  flushList()
  return out.join('')
}

export function renderDocument(text: string, docIr?: unknown, preferText?: boolean): string {
  const html = renderDocumentFromJson(text, docIr, preferText)
  if (html) return html
  return renderMarkdown(String(text || ''))
}
