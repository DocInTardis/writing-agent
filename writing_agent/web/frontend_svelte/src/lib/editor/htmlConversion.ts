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

  const childrenInline = (el: Element): string => {
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

export function htmlToDocIr(html: string, currentTitle = ''): Record<string, unknown> | null {
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

  const childrenInline = (el: Element): string => {
    const out: string[] = []
    el.childNodes.forEach((child) => out.push(inlineText(child)))
    return out.join('').replace(/\s+/g, ' ').trim()
  }

  const pushParagraph = (text: string, id?: string, preserveEmpty = false) => {
    const t = text.replace(/\s+$/g, '').trim()
    if (t || preserveEmpty) blocks.push({ type: 'paragraph', text: t, id: id || undefined })
  }

  const splitTitleAndRest = (text: string) => {
    const s = String(text || '').trim()
    if (!s) return { title: '', rest: '' }
    return { title: s, rest: '' }
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
    const image = fig?.querySelector('img') as HTMLImageElement | null
    const imageSrc = image?.getAttribute('src') || fig?.dataset.imageSrc || ''
    if (imageSrc) spec = { type: 'image', src: imageSrc }
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
    if (node.classList.contains('wa-page-break')) {
      blocks.push({ type: 'page_break', id: node.dataset.blockId || undefined })
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
        pushParagraph(split.rest)
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
      // Formatting comes from the element type selected by the user. Never
      // infer a heading merely from words such as "摘要" or "1 绪论".
      pushParagraph(text, node.dataset.blockId || undefined, true)
      return
    }
    node.childNodes.forEach((child) => walkBlock(child))
  }

  container.childNodes.forEach((node) => walkBlock(node))
  // The document title is file metadata, not an implicit copy of body text.
  const docTitle = String(currentTitle || title || '未命名文档').trim()
  return buildDocIrFromBlocks(blocks, docTitle)
}

function buildDocIrFromBlocks(blocks: Array<Record<string, unknown>>, title: string): Record<string, unknown> {
  const docTitle = String(title || '').trim() || '自动生成文档'
  const sections: Array<Record<string, unknown>> = []
  const stack: Array<{ level: number; node: Record<string, unknown> }> = []
  const usedBlockIds = new Set<string>()
  let orphan: Array<Record<string, unknown>> = []

  const pushImplicit = () => {
    if (!orphan.length) return
    const implicit = {
      id: makeId(),
      title: '',
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
    let docBlock = toDocIrBlock(b)
    if (!docBlock) continue
    const blockId = String(docBlock.id || '')
    if (!blockId || usedBlockIds.has(blockId)) {
      docBlock = { ...docBlock, id: makeId() }
    }
    usedBlockIds.add(String(docBlock.id || ''))
    if (stack.length) {
      ;(stack[stack.length - 1].node.blocks as Array<Record<string, unknown>>).push(docBlock)
    } else {
      orphan.push(docBlock)
    }
  }

  if (orphan.length && !sections.length) {
    sections.push({ id: makeId(), title: '', level: 1, blocks: orphan, children: [] })
  }
  return { title: docTitle, sections }
}

function toDocIrBlock(block: Record<string, unknown>): Record<string, unknown> | null {
  const t = String(block.type || 'paragraph').toLowerCase()
  const rawId = String(block.id || '').trim()
  const id = rawId || makeId()
  if (t === 'paragraph') {
    const text = String(block.text || '').trim()
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



