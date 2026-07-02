export function htmlToMarkdown(html: string): string {
  const container = document.createElement('div')
  container.innerHTML = html
  const blocks: string[] = []

  const inlineText = (node: Node): string => {
    if (node.nodeType === Node.TEXT_NODE) return (node.textContent || '').replace(/\s+/g, ' ')
    if (!(node instanceof HTMLElement)) return ''
    const tag = node.tagName.toLowerCase()
    if (tag === 'br') return '\n'
    if (tag === 'strong' || tag === 'b') return `**${childrenInline(node)}**`
    if (tag === 'em' || tag === 'i') return `*${childrenInline(node)}*`
    if (tag === 'u') return `++${childrenInline(node)}++`
    if (tag === 'del' || tag === 's') return `~~${childrenInline(node)}~~`
    if (tag === 'mark') return `==${childrenInline(node)}==`
    if (tag === 'code') return '`' + childrenInline(node) + '`'
    if (tag === 'a') {
      const href = node.getAttribute('href') || ''
      const text = childrenInline(node)
      return href ? `[${text}](${href})` : text
    }
    if (tag === 'span') return childrenInline(node)
    return childrenInline(node)
  }

  const childrenInline = (el: HTMLElement): string => {
    const out: string[] = []
    el.childNodes.forEach((child) => out.push(inlineText(child)))
    return out.join('').replace(/\s+/g, ' ').trim()
  }

  const pushParagraph = (text: string) => {
    const t = text.replace(/\s+$/g, '').trim()
    if (t) blocks.push(t)
  }

  const walkBlock = (node: Node) => {
    if (!(node instanceof HTMLElement)) return
    const tag = node.tagName.toLowerCase()

    if (node.dataset.waFigure === '1') {
      const cap = node.querySelector('figcaption')?.textContent?.trim() || '图示'
      blocks.push(`[[FIGURE:{"caption":"${escapeJson(cap)}"}]]`)
      return
    }
    if (node.dataset.waTable === '1') {
      const cap = node.querySelector('.wa-table-caption')?.textContent?.trim() || '表格'
      blocks.push(`[[TABLE:{"caption":"${escapeJson(cap)}"}]]`)
      return
    }

    if (tag === 'h1' || tag === 'h2' || tag === 'h3') {
      const level = tag === 'h1' ? 1 : tag === 'h2' ? 2 : 3
      const text = childrenInline(node)
      if (text) blocks.push(`${'#'.repeat(level)} ${text}`)
      return
    }

    if (tag === 'pre') {
      const text = node.textContent || ''
      blocks.push('```\n' + text.replace(/\n+$/, '') + '\n```')
      return
    }

    if (tag === 'blockquote') {
      const text = childrenInline(node)
      if (text) blocks.push('> ' + text)
      return
    }

    if (tag === 'ul' || tag === 'ol') {
      const items = Array.from(node.querySelectorAll(':scope > li'))
      items.forEach((li, idx) => {
        const t = childrenInline(li)
        if (!t) return
        blocks.push(tag === 'ol' ? `${idx + 1}. ${t}` : `- ${t}`)
      })
      return
    }

    if (tag === 'p' || tag === 'div') {
      const text = childrenInline(node)
      pushParagraph(text)
      return
    }

    if (tag === 'figure') {
      const cap = node.querySelector('figcaption')?.textContent?.trim() || '图示'
      blocks.push(`[[FIGURE:{"caption":"${escapeJson(cap)}"}]]`)
      return
    }

    if (tag === 'table') {
      blocks.push(`[[TABLE:{"caption":"表格"}]]`)
      return
    }

    node.childNodes.forEach((child) => walkBlock(child))
  }

  container.childNodes.forEach((node) => walkBlock(node))
  return blocks.join('\n\n').trim()
}

export function htmlToDocIr(html: string): Record<string, unknown> | null {
  const container = document.createElement('div')
  container.innerHTML = html
  const blocks: Array<Record<string, unknown>> = []
  let title = ''

  const inlineText = (node: Node): string => {
    if (node.nodeType === Node.TEXT_NODE) return (node.textContent || '').replace(/\s+/g, ' ')
    if (!(node instanceof HTMLElement)) return ''
    const tag = node.tagName.toLowerCase()
    if (tag === 'br') return '\n'
    if (tag === 'strong' || tag === 'b') return `**${childrenInline(node)}**`
    if (tag === 'em' || tag === 'i') return `*${childrenInline(node)}*`
    if (tag === 'u') return `++${childrenInline(node)}++`
    if (tag === 'del' || tag === 's') return `~~${childrenInline(node)}~~`
    if (tag === 'mark') return `==${childrenInline(node)}==`
    if (tag === 'code') return '`' + childrenInline(node) + '`'
    if (tag === 'a') {
      const href = node.getAttribute('href') || ''
      const text = childrenInline(node)
      return href ? `[${text}](${href})` : text
    }
    if (tag === 'span') return childrenInline(node)
    return childrenInline(node)
  }

  const childrenInline = (el: HTMLElement): string => {
    const out: string[] = []
    el.childNodes.forEach((child) => out.push(inlineText(child)))
    return out.join('').replace(/\s+/g, ' ').trim()
  }

  const pushParagraph = (text: string, id?: string) => {
    const t = text.replace(/\s+$/g, '').trim()
    if (t) blocks.push({ type: 'paragraph', text: t, id: id || undefined })
  }

  const HEADING_HINTS = [
    '摘要',
    '引言',
    '绪论',
    '前言',
    '背景',
    '相关技术概述',
    '关键技术',
    '研究方法',
    '实验',
    '结果',
    '讨论',
    '结论',
    '总结',
    '展望',
    '参考文献',
    '附录',
    '致谢',
    'Abstract'
  ]

  const NUM_HEADING_RE = /^(\d+(?:\.\d+){0,2})\s*[\.、:：-]?\s*([^\s].{0,24})$/
  const CN_NUM_HEADING_RE = /^([一二三四五六七八九十]+)\s*[、.．:：-]?\s*([^\s].{0,24})$/

  const looksLikeBodySentence = (text: string) => {
    const s = String(text || '').trim()
    if (!s) return false
    if (s.length >= 24) return true
    if (/[。！？!?；;，,]/.test(s)) return true
    const starters = ['本文', '本研究', '随着', '通过', '由于', '因此', '此外', '同时', '首先', '其次', '最后']
    const hit = starters.some((starter) => {
      const idx = s.indexOf(starter)
      return idx >= 1 && idx <= 18
    })
    if (hit) return true
    if (s.length >= 14 && /(是|为|通过|随着|由于|因此|并且|能够|可以|实现|提升|优化)/.test(s)) {
      return true
    }
    return false
  }

  const splitTitleAndRest = (text: string) => {
    const s = String(text || '').trim()
    if (!s) return { title: '', rest: '' }
    const repeated = /^(.{2,18})\s*\1(.+)$/.exec(s)
    if (repeated) {
      return { title: String(repeated[1] || '').trim(), rest: String(repeated[2] || '').trim() }
    }
    for (const kw of HEADING_HINTS) {
      const idx = s.indexOf(kw)
      if (idx > 1 && idx <= 20) {
        const left = s.slice(0, idx).trim()
        const right = s.slice(idx).trim()
        if (left.length >= 2 && right.length >= 2) {
          return { title: left, rest: right }
        }
      }
    }
    const numIdx = s.search(/\b\d+(?:\.\d+){0,2}\b/)
    if (numIdx > 1 && numIdx <= 20) {
      return { title: s.slice(0, numIdx).trim(), rest: s.slice(numIdx).trim() }
    }
    return { title: s, rest: '' }
  }

  const detectHeadingFromText = (text: string) => {
    const s = String(text || '').trim()
    if (!s) return null
    if (s.length <= 12 && HEADING_HINTS.includes(s)) {
      return { level: 2, heading: s, rest: '' }
    }
    const mNum = NUM_HEADING_RE.exec(s)
    if (mNum) {
      const num = String(mNum[1] || '').trim()
      const name = String(mNum[2] || '').trim()
      if (looksLikeBodySentence(name)) return null
      const dots = num.split('.').length - 1
      const level = Math.min(4, 2 + Math.max(0, dots))
      return { level, heading: `${num} ${name}`.trim(), rest: '' }
    }
    const mCn = CN_NUM_HEADING_RE.exec(s)
    if (mCn) {
      const num = String(mCn[1] || '').trim()
      const name = String(mCn[2] || '').trim()
      if (looksLikeBodySentence(name)) return null
      return { level: 2, heading: `${num} ${name}`.trim(), rest: '' }
    }
    if (s.length > 20) {
      for (const kw of HEADING_HINTS) {
        if (s.startsWith(kw) && s.length > kw.length + 8) {
          return { level: 2, heading: kw, rest: s.slice(kw.length).trim() }
        }
      }
    }
    return null
  }

  const emitTextAsBlocks = (text: string, id?: string) => {
    const s = String(text || '').trim()
    if (!s) return
    const heading = detectHeadingFromText(s)
    if (heading) {
      blocks.push({ type: 'heading', level: heading.level, text: heading.heading })
      if (heading.rest) pushParagraph(heading.rest, id)
      return
    }
    pushParagraph(s, id)
  }

  const extractTable = (node: HTMLElement): Record<string, unknown> | null => {
    const tableEl = node.tagName.toLowerCase() === 'table' ? node : (node.querySelector('table') as HTMLElement | null)
    if (!tableEl) return null
    const captionEl =
      node.querySelector('figcaption') ||
      node.querySelector('.wa-table-caption') ||
      tableEl.querySelector('caption')
    const caption = captionEl ? (captionEl.textContent || '').trim() : ''
    const cols: string[] = []
    const rows: Array<Array<string>> = []
    const headCells = Array.from(tableEl.querySelectorAll('thead th'))
    if (headCells.length) {
      headCells.forEach((c) => cols.push((c.textContent || '').trim()))
    }
    const rowEls = Array.from(tableEl.querySelectorAll('tr'))
    rowEls.forEach((row, idx) => {
      const cells = Array.from(row.querySelectorAll('td, th'))
      if (!cells.length) return
      const vals = cells.map((c) => (c.textContent || '').trim())
      if (!cols.length && idx === 0 && row.querySelectorAll('th').length === cells.length) {
        cols.push(...vals)
        return
      }
      rows.push(vals)
    })
    return { caption, columns: cols, rows }
  }

  const extractFigure = (node: HTMLElement): Record<string, unknown> | null => {
    const fig = node.tagName.toLowerCase() === 'figure' ? node : (node.querySelector('figure') as HTMLElement | null)
    const capEl = fig?.querySelector('figcaption') || node.querySelector('figcaption')
    const caption = capEl ? (capEl.textContent || '').trim() : ''
    const rawSpec = fig?.dataset.figureSpec || ''
    let spec: Record<string, unknown> = {}
    if (rawSpec) {
      try {
        const parsed = JSON.parse(decodeURIComponent(rawSpec))
        if (parsed && typeof parsed === 'object') spec = parsed
      } catch {
        spec = {}
      }
    }
    if (caption) spec = { ...spec, caption }
    return Object.keys(spec).length ? spec : { caption }
  }

  const walkBlock = (node: Node) => {
    if (!(node instanceof HTMLElement)) return
    const tag = node.tagName.toLowerCase()
    if (tag === 'div' && node.classList.contains('wa-doc')) {
      node.childNodes.forEach((child) => walkBlock(child))
      return
    }
    if (node.classList.contains('wa-header') || node.classList.contains('wa-footer')) {
      return
    }
    if (node.classList.contains('wa-body')) {
      node.childNodes.forEach((child) => walkBlock(child))
      return
    }
    if (node.classList.contains('wa-title')) {
      const t = childrenInline(node)
      const split = splitTitleAndRest(t)
      if (split.title && !title) title = split.title
      if (split.rest) {
        emitTextAsBlocks(split.rest)
      }
      return
    }
    if (node.dataset.waTable === '1' || node.classList.contains('wa-table') || tag === 'table') {
      const table = extractTable(node)
      if (table) blocks.push({ type: 'table', table, id: node.dataset.blockId || undefined })
      return
    }
    if (node.dataset.waFigure === '1' || node.classList.contains('wa-figure') || tag === 'figure') {
      const fig = extractFigure(node)
      if (fig) blocks.push({ type: 'figure', figure: fig, id: node.dataset.blockId || undefined })
      return
    }
    if (tag === 'h1' || tag === 'h2' || tag === 'h3' || tag === 'h4' || tag === 'h5' || tag === 'h6') {
      const level = Number(tag.slice(1))
      const text = childrenInline(node)
      if (text) {
        if (level === 1 && !title) {
          title = text
          return
        }
        blocks.push({ type: 'heading', level, text })
      }
      return
    }
    if (tag === 'ul' || tag === 'ol') {
      const items = Array.from(node.querySelectorAll(':scope > li'))
        .map((li) => childrenInline(li))
        .filter(Boolean)
      if (items.length) blocks.push({ type: 'list', items, ordered: tag === 'ol', id: node.dataset.blockId || undefined })
      return
    }
    if (tag === 'blockquote') {
      const text = childrenInline(node)
      if (text) blocks.push({ type: 'paragraph', text })
      return
    }
    if (tag === 'pre') {
      const text = node.textContent || ''
      pushParagraph(text.replace(/\n+$/, ''), node.dataset.blockId || undefined)
      return
    }
    if (tag === 'p' || tag === 'div') {
      const text = childrenInline(node)
      emitTextAsBlocks(text, node.dataset.blockId || undefined)
      return
    }
    node.childNodes.forEach((child) => walkBlock(child))
  }

  container.childNodes.forEach((node) => walkBlock(node))
  const docTitle = title || deriveTitleFromBlocks(blocks) || '自动生成文档'
  return buildDocIrFromBlocks(blocks, docTitle)
}

function deriveTitleFromBlocks(blocks: Array<Record<string, unknown>>): string {
  for (const b of blocks) {
    if (String(b.type || '') === 'heading' && Number(b.level || 0) === 1 && b.text) {
      return String(b.text || '').trim()
    }
    if (String(b.type || '') === 'paragraph' && b.text) {
      const raw = String(b.text || '').trim()
      if (raw) return raw.slice(0, 24)
    }
  }
  return ''
}

function buildDocIrFromBlocks(blocks: Array<Record<string, unknown>>, title: string): Record<string, unknown> {
  const docTitle = String(title || '').trim() || '自动生成文档'
  const sections: Array<Record<string, unknown>> = []
  const stack: Array<{ level: number; node: Record<string, unknown> }> = []
  let orphan: Array<Record<string, unknown>> = []

  const pushImplicit = () => {
    if (!orphan.length) return
    const implicit = {
      id: makeId(),
      title: docTitle,
      level: 1,
      blocks: orphan,
      children: []
    }
    sections.push(implicit)
    stack.push({ level: 1, node: implicit })
    orphan = []
  }

  for (const b of blocks) {
    const t = String(b.type || '').toLowerCase()
    if (t === 'heading') {
      const level = Math.min(6, Math.max(1, Number(b.level || 1)))
      const text = String(b.text || '').trim() || '章节'
      const node: Record<string, unknown> = { id: makeId(), title: text, level, blocks: [], children: [] }
      if (orphan.length && stack.length === 0) pushImplicit()
      while (stack.length && stack[stack.length - 1].level >= level) stack.pop()
      if (stack.length) {
        ;(stack[stack.length - 1].node.children as Array<Record<string, unknown>>).push(node)
      } else {
        sections.push(node)
      }
      stack.push({ level, node })
      continue
    }
    const docBlock = toDocIrBlock(b)
    if (!docBlock) continue
    if (stack.length) {
      ;(stack[stack.length - 1].node.blocks as Array<Record<string, unknown>>).push(docBlock)
    } else {
      orphan.push(docBlock)
    }
  }

  if (orphan.length && !sections.length) {
    sections.push({ id: makeId(), title: docTitle, level: 1, blocks: orphan, children: [] })
  }
  return { title: docTitle, sections }
}

function toDocIrBlock(block: Record<string, unknown>): Record<string, unknown> | null {
  const t = String(block.type || 'paragraph').toLowerCase()
  const rawId = String(block.id || '').trim()
  const id = rawId || makeId()
  if (t === 'paragraph') {
    const text = String(block.text || '').trim()
    if (!text) return null
    return { id, type: 'paragraph', text }
  }
  if (t === 'list') {
    const items = Array.isArray(block.items) ? block.items.map((v) => String(v || '').trim()).filter(Boolean) : []
    if (!items.length) return null
    const ordered = Boolean(block.ordered)
    return { id, type: 'list', items, ordered }
  }
  if (t === 'table') {
    return { id, type: 'table', table: block.table || {} }
  }
  if (t === 'figure') {
    return { id, type: 'figure', figure: block.figure || {} }
  }
  const text = String(block.text || '').trim()
  if (!text) return null
  return { id, type: 'paragraph', text }
}

export function makeId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return (crypto as Crypto).randomUUID().replace(/-/g, '')
  }
  return `b${Math.random().toString(16).slice(2)}${Date.now().toString(16)}`
}

function escapeJson(text: string) {
  return text.replace(/\\/g, '\\\\').replace(/"/g, '\\"')
}


