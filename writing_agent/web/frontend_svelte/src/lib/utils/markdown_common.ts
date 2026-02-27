export type UnknownRecord = Record<string, unknown>

export function escapeHtml(s: string): string {
  return String(s || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

export function formatInline(text: string): string {
  let safe = escapeHtml(text)
  safe = safe.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  safe = safe.replace(/\*(.+?)\*/g, '<em>$1</em>')
  safe = safe.replace(/~~(.+?)~~/g, '<del>$1</del>')
  safe = safe.replace(/==(.+?)==/g, '<mark>$1</mark>')
  safe = safe.replace(/\+\+(.+?)\+\+/g, '<u>$1</u>')
  safe = safe.replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
  return safe
}

export function normalizeTitle(text: string): string {
  return String(text || '').trim().toLowerCase()
}

export function normalizeLines(lines: string[]): string[] {
  const out: string[] = []
  let run: string[] = []
  let blankSeen = false
  const flush = () => {
    if (!run.length) return
    if (run.length >= 4) {
      out.push(run.join(''))
    } else {
      out.push(...run)
    }
    run = []
  }
  for (const raw of lines) {
    const line = raw.trim()
    if (!line) {
      flush()
      if (!blankSeen) {
        out.push('')
        blankSeen = true
      }
      continue
    }
    blankSeen = false
    const single = line.length <= 1
    const looksLikeChar = /[\u4e00-\u9fa5A-Za-z0-9\.\-\u3000-\u303F]/.test(line)
    if (single && looksLikeChar) {
      run.push(line)
      continue
    }
    flush()
    out.push(raw)
  }
  flush()
  return out
}

export function renderHeadingHtml(level: number, text: string, attrs = ''): string {
  const safe = formatInline(text)
  const lvl = Math.min(6, Math.max(1, Number(level || 1)))
  return `<h${lvl}${attrs}>${safe}</h${lvl}>`
}

export function renderParagraphHtml(text: string): string {
  const safe = formatInline(text).replace(/\n/g, '<br/>')
  return `<p>${safe}</p>`
}

export function blockIdAttr(block: UnknownRecord): string {
  const raw = String(block.id || '').trim()
  return raw ? ` data-block-id="${escapeHtml(raw)}"` : ''
}

export function styleAttrFromBlock(block: UnknownRecord): string {
  const style = block.style
  if (!style || typeof style !== 'object') return ''

  const styleObj = style as UnknownRecord
  const css: string[] = []
  const align = String(styleObj.align || styleObj.textAlign || '').trim()
  if (['left', 'center', 'right', 'justify'].includes(align)) css.push(`text-align:${align}`)

  const lineHeight = String(styleObj.lineHeight || '').trim()
  if (/^\d+(\.\d+)?$/.test(lineHeight)) css.push(`line-height:${lineHeight}`)

  const indent = String(styleObj.indent || styleObj.textIndent || '').trim()
  if (/^\d+(\.\d+)?(px|pt|em|rem)?$/.test(indent)) css.push(`text-indent:${indent}`)

  const marginTop = String(styleObj.marginTop || '').trim()
  if (/^\d+(\.\d+)?(px|pt|em|rem)?$/.test(marginTop)) css.push(`margin-top:${marginTop}`)

  const marginBottom = String(styleObj.marginBottom || '').trim()
  if (/^\d+(\.\d+)?(px|pt|em|rem)?$/.test(marginBottom)) css.push(`margin-bottom:${marginBottom}`)

  const fontFamily = String(styleObj.fontFamily || '').trim()
  if (fontFamily && fontFamily.length < 80) css.push(`font-family:${escapeHtml(fontFamily)}`)

  const fontSize = String(styleObj.fontSize || '').trim()
  if (/^\d+(\.\d+)?(px|pt|em|rem)?$/.test(fontSize)) css.push(`font-size:${fontSize}`)

  const fontWeight = String(styleObj.fontWeight || '').trim()
  if (/^(normal|bold|bolder|lighter|[1-9]00)$/.test(fontWeight)) css.push(`font-weight:${fontWeight}`)

  const fontStyle = String(styleObj.fontStyle || '').trim()
  if (/^(normal|italic|oblique)$/.test(fontStyle)) css.push(`font-style:${fontStyle}`)

  const color = String(styleObj.color || '').trim()
  if (/^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(color) || color.startsWith('rgb(') || color.startsWith('rgba(')) {
    css.push(`color:${escapeHtml(color)}`)
  }

  const background = String(styleObj.background || styleObj.backgroundColor || '').trim()
  if (
    /^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(background) ||
    background.startsWith('rgb(') ||
    background.startsWith('rgba(')
  ) {
    css.push(`background-color:${escapeHtml(background)}`)
  }

  return css.length ? ` style="${css.join(';')}"` : ''
}

export function normalizeTablePayload(block: UnknownRecord): { caption: string; columns: string[]; rows: Array<unknown> } {
  const out = { caption: '', columns: [] as string[], rows: [] as Array<unknown> }
  const table = block.table
  const data = typeof table === 'object' && table ? (table as UnknownRecord) : block.data
  const raw = typeof data === 'object' && data ? (data as UnknownRecord) : block
  out.caption = String(raw.caption || '').trim()

  const cols = raw.columns
  if (Array.isArray(cols)) out.columns = cols.map((c) => String(c))

  const rows = raw.rows
  if (Array.isArray(rows)) out.rows = rows
  return out
}

export function normalizeFigurePayload(block: UnknownRecord): { caption: string; spec: UnknownRecord } {
  const fig = block.figure
  const dataObj = typeof fig === 'object' && fig ? (fig as UnknownRecord) : null
  const raw = dataObj || block
  const caption = String(raw.caption || '').trim()
  const spec: UnknownRecord = dataObj ? { ...dataObj } : {}
  if (caption) spec.caption = caption
  return { caption, spec }
}

export function runStyleAttr(run: UnknownRecord): string {
  const css: string[] = []
  const color = String(run.color || '').trim()
  if (/^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(color) || color.startsWith('rgb(')) {
    css.push(`color:${escapeHtml(color)}`)
  }

  const background = String(run.background || '').trim()
  if (/^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(background) || background.startsWith('rgb(')) {
    css.push(`background-color:${escapeHtml(background)}`)
  }

  const font = String(run.font || '').trim()
  if (font && font.length < 80) {
    css.push(`font-family:${escapeHtml(font)}`)
  }

  const size = String(run.size || '').trim()
  if (/^\d+(\.\d+)?(px|pt|em|rem)?$/.test(size)) {
    css.push(`font-size:${size}`)
  }
  return css.length ? ` style="${css.join(';')}"` : ''
}

export function renderRuns(runs: UnknownRecord[]): string {
  const parts: string[] = []
  runs.forEach((run) => {
    const text = String(run.text || '')
    if (!text) return
    let inner = escapeHtml(text).replace(/\n/g, '<br/>')
    if (run.bold) inner = `<strong>${inner}</strong>`
    if (run.italic) inner = `<em>${inner}</em>`
    if (run.underline) inner = `<u>${inner}</u>`
    if (run.strike) inner = `<del>${inner}</del>`
    const link = String(run.link || '').trim()
    if (link) {
      inner = `<a href="${escapeHtml(link)}" target="_blank" rel="noopener">${inner}</a>`
    }
    const style = runStyleAttr(run)
    if (style) {
      inner = `<span${style}>${inner}</span>`
    }
    parts.push(inner)
  })
  return parts.join('')
}
