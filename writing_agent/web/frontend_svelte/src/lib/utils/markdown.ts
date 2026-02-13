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



      } catch {}



      if (kind === 'figure') {



        out.push(



          `<figure class="wa-figure" data-wa-figure="1"><div class="wa-figure-box">图</div><figcaption>${escapeHtml(



            caption



          )}</figcaption></figure>`



        )



      } else {



        out.push(



          `<div class="wa-table" data-wa-table="1"><div class="wa-table-box">表</div><div class="wa-table-caption">${escapeHtml(



            caption



          )}</div></div>`



        )



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



      const item = (liBullet || liNum)[1]



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



  const src = String(text || '')



  const jsonHtml = renderJsonText(src)



  if (jsonHtml) {



    return jsonHtml



  }



  if (!preferText) {



    const htmlFromDoc = renderFromUnknown(docIr)



    if (htmlFromDoc) return htmlFromDoc



  }



  return renderMarkdown(src)



}

export function textToDocIr(text: string): Record<string, unknown> | null {
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
  const blocks: Array<Record<string, unknown>> = []
  let title = ''
  let para: string[] = []
  let listItems: string[] = []
  let listOrdered: boolean | null = null

  const flushPara = () => {
    if (!para.length) return
    const joined = para.join(' ').replace(/\s+/g, ' ').trim()
    if (joined) blocks.push({ type: 'paragraph', text: joined })
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
    if (/^#{1,6}$/.test(trimmed)) {
      continue
    }

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
      if (rest) {
        blocks.push({ type: 'paragraph', text: rest })
      }
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
      const canHeading = prevBlank || (!para.length && !listItems.length) || split || shortHeading || prefixMatch
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
        if (rest) blocks.push({ type: 'paragraph', text: rest })
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
      const item = String((orderedMatch?.[1] || bulletMatch?.[1] || '')).trim()
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











function convertJsonToMarkdown(src: string): string | null {



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







function extractJsonBlock(text: string): string | null {



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







function safeJsonParse(raw: string): unknown | null {



  try {



    return JSON.parse(raw)



  } catch {



    return null



  }



}







function parseNdjsonBlocks(text: string): Array<Record<string, unknown>> {



  const blocks: Array<Record<string, unknown>> = []



  const lines = String(text || '').split('\n')



  for (const line of lines) {



    const t = line.trim()



    if (!t) continue



    const obj = safeJsonParse(t)



    if (obj && typeof obj === 'object' && !Array.isArray(obj)) {



      blocks.push(obj as Record<string, unknown>)



    }



  }



  return blocks



}







function jsonToMarkdown(data: unknown): string | null {



  if (!data || typeof data !== 'object') return null



  const root = data as Record<string, unknown>



  if (root.doc_ir && typeof root.doc_ir === 'object') {



    return docIrToMarkdown(root.doc_ir as Record<string, unknown>)



  }



  if (Array.isArray(data)) {



    return blocksToMarkdown(data as Array<Record<string, unknown>>)



  }



  if (Array.isArray(root.blocks)) {



    return blocksToMarkdown(root.blocks as Array<Record<string, unknown>>)



  }



  if (Array.isArray(root.sections)) {



    const sections = root.sections as Array<Record<string, unknown>>



    const hasDocIr = sections.some((s) => s && (((s as Record<string, unknown>).blocks as unknown) || (s as Record<string, unknown>).children))



    if (hasDocIr) {



      return docIrToMarkdown(root)



    }



    return simpleSectionsToMarkdown(root)



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







function jsonToHtml(data: unknown): string | null {



  if (!data || typeof data !== 'object') return null



  const root = data as Record<string, unknown>



  if (root.doc_ir && typeof root.doc_ir === 'object') {



    return docIrToHtml(root.doc_ir as Record<string, unknown>)



  }



  if (Array.isArray(data)) {



    return blocksToHtml(data as Array<Record<string, unknown>>)



  }



  if (Array.isArray(root.blocks)) {



    return blocksToHtml(root.blocks as Array<Record<string, unknown>>, String(root.title || '').trim())



  }



  if (Array.isArray(root.sections)) {



    return docIrToHtml(root)



  }



  return null



}











export function docIrToMarkdown(doc: Record<string, unknown>): string | null {
  const title = resolveDocTitle(doc)
  const sections = Array.isArray(doc.sections) ? (doc.sections as Array<Record<string, unknown>>) : []
  const lines: string[] = []
  if (title) lines.push(`# ${title}`)



  for (const sec of sections) {



    pushSectionLines(sec, lines)



  }



  return lines.length ? lines.join('\n\n').trim() : null



}







function docIrToHtml(doc: Record<string, unknown>): string | null {
  const title = resolveDocTitle(doc)
  const sections = Array.isArray(doc.sections) ? (doc.sections as Array<Record<string, unknown>>) : []
  if (!title && sections.length === 0) return null
  const parts: string[] = ['<div class="wa-doc">']
  const headerTitle = title
  parts.push(`<div class="wa-header" contenteditable="false">${escapeHtml(headerTitle)}</div>`)
  parts.push('<div class="wa-body">')
  const titleNorm = normalizeTitle(title)
  if (title) {
    parts.push(`<div class="wa-title">${formatInline(title)}</div>`)
  }

  for (const sec of sections) {
    parts.push(renderSectionHtml(sec, titleNorm))
  }

  parts.push('</div>')
  parts.push('<div class="wa-footer" contenteditable="false">Page 1</div>')
  parts.push('</div>')

  return parts.join('')



}







function renderSectionHtml(section: Record<string, unknown>, docTitleNorm: string): string {



  const title = String(section.title || '').trim()



  const level = Math.min(6, Math.max(1, Number(section.level || 2)))
  const sectionId = String(section.id || '').trim()
  const sectionAttr = sectionId ? ` data-section-id="${escapeHtml(sectionId)}" data-section-level="${level}"` : ''
  const sectionStyle = styleAttrFromBlock({ style: (section as Record<string, unknown>).style } as Record<string, unknown>)
  const sectionAttrs = `${sectionAttr}${sectionStyle}`



  const parts: string[] = []



  if (title) {



    const skip = level === 1 && docTitleNorm && normalizeTitle(title) === docTitleNorm



    if (!skip) {



      parts.push(renderHeadingHtml(level, title, sectionAttrs))



    }



  }



  const blocks = Array.isArray(section.blocks) ? (section.blocks as Array<Record<string, unknown>>) : []



  for (const block of blocks) {



    const html = blockToHtml(block)



    if (html) parts.push(html)



  }



  const children = Array.isArray(section.children) ? (section.children as Array<Record<string, unknown>>) : []



  for (const child of children) {



    parts.push(renderSectionHtml(child, docTitleNorm))



  }



  return parts.join('')



}











function pushSectionLines(section: Record<string, unknown>, lines: string[]): void {



  const title = String(section.title || '').trim()



  if (title) {



    const level = Math.min(6, Math.max(1, Number(section.level || 2)))



    lines.push(`${'#'.repeat(level)} ${title}`)



  }



  const blocks = Array.isArray(section.blocks) ? (section.blocks as Array<Record<string, unknown>>) : []



  for (const block of blocks) {



    lines.push(...blockToLines(block))



  }



  const children = Array.isArray(section.children) ? (section.children as Array<Record<string, unknown>>) : []



  for (const child of children) {



    pushSectionLines(child, lines)



  }



}







function simpleSectionsToMarkdown(doc: Record<string, unknown>): string | null {



  const title = String(doc.title || '').trim()



  const sections = Array.isArray(doc.sections) ? (doc.sections as Array<Record<string, unknown>>) : []



  const lines: string[] = []



  if (title) lines.push(`# ${title}`)



  for (const sec of sections) {



    const secTitle = String(sec.title || sec.name || sec.section || '').trim()



    if (!secTitle) continue



    lines.push(`## ${secTitle}`)



    let content: unknown = (sec as Record<string, unknown>).content ?? (sec as Record<string, unknown>).text ?? (sec as Record<string, unknown>).body



    if (Array.isArray(content)) {



      content = (content as Array<unknown>)



        .map((v) => String(v || '').trim())



        .filter(Boolean)



        .join('\n\n')



    }



    const text = String(content || '').trim()



    if (text) lines.push(text)



  }



  return lines.length ? lines.join('\n\n').trim() : null



}







function blocksToMarkdown(blocks: Array<Record<string, unknown>>): string | null {



  const lines: string[] = []



  let lastSection = ''



  for (const block of blocks) {



    const sec = String((block as Record<string, unknown>).section_id || (block as Record<string, unknown>).section_title || '').trim()



    if (sec && sec !== lastSection) {



      const heading = headingFromSectionId(sec)



      if (heading) lines.push(heading)



      lastSection = sec



    }



    lines.push(...blockToLines(block))



  }



  return lines.length ? lines.join('\n\n').trim() : null



}







function blocksToHtml(blocks: Array<Record<string, unknown>>, title?: string): string | null {
  const parts: string[] = ['<div class="wa-doc">']
  const docTitle = String(title || '').trim() || inferTitleFromBlocks(blocks)
  const headerTitle = docTitle
  parts.push(`<div class="wa-header" contenteditable="false">${escapeHtml(headerTitle)}</div>`)
  parts.push('<div class="wa-body">')
  if (docTitle) {
    parts.push(`<div class="wa-title">${formatInline(docTitle)}</div>`)
  }
  let lastSection = ''
  let skippedTitle = false
  for (const block of blocks) {
    const sec = String((block as Record<string, unknown>).section_id || (block as Record<string, unknown>).section_title || '').trim()
    if (sec && sec !== lastSection) {
      const heading = headingFromSectionIdHtml(sec)
      if (heading) parts.push(heading)
      lastSection = sec
    }
    const t = String((block as Record<string, unknown>).type || '').toLowerCase()
    if (!skippedTitle && docTitle && t === 'heading' && Number((block as Record<string, unknown>).level || 0) === 1) {
      const text = String((block as Record<string, unknown>).text || '').trim()
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











function headingFromSectionId(sectionId: string): string {



  const m = /^H([1-6])::(.+)$/.exec(sectionId)



  if (m) {



    const level = Math.min(6, Math.max(1, Number(m[1] || 2)))



    const title = String(m[2] || '').trim()



    if (title) return `${'#'.repeat(level)} ${title}`



  }



  return `## ${sectionId}`



}







function headingFromSectionIdHtml(sectionId: string): string {



  const m = /^H([1-6])::(.+)$/.exec(sectionId)



  if (m) {



    const level = Math.min(6, Math.max(1, Number(m[1] || 2)))



    const title = String(m[2] || '').trim()



    if (title) return renderHeadingHtml(level, title)



  }



  return renderHeadingHtml(2, sectionId)



}


function blockIdAttr(block: Record<string, unknown>): string {
  const raw = String((block as Record<string, unknown>).id || '').trim()
  return raw ? ` data-block-id="${escapeHtml(raw)}"` : ''
}

function styleAttrFromBlock(block: Record<string, unknown>): string {
  const style = (block as Record<string, unknown>).style
  if (!style || typeof style !== 'object') return ''
  const css: string[] = []
  const align = String((style as Record<string, unknown>).align || (style as Record<string, unknown>).textAlign || '').trim()
  if (['left', 'center', 'right', 'justify'].includes(align)) css.push(`text-align:${align}`)
  const lineHeight = String((style as Record<string, unknown>).lineHeight || '').trim()
  if (/^\d+(\.\d+)?$/.test(lineHeight)) css.push(`line-height:${lineHeight}`)
  const indent = String((style as Record<string, unknown>).indent || (style as Record<string, unknown>).textIndent || '').trim()
  if (/^\d+(\.\d+)?(px|pt|em|rem)?$/.test(indent)) css.push(`text-indent:${indent}`)
  const marginTop = String((style as Record<string, unknown>).marginTop || '').trim()
  if (/^\d+(\.\d+)?(px|pt|em|rem)?$/.test(marginTop)) css.push(`margin-top:${marginTop}`)
  const marginBottom = String((style as Record<string, unknown>).marginBottom || '').trim()
  if (/^\d+(\.\d+)?(px|pt|em|rem)?$/.test(marginBottom)) css.push(`margin-bottom:${marginBottom}`)
  const fontFamily = String((style as Record<string, unknown>).fontFamily || '').trim()
  if (fontFamily && fontFamily.length < 80) css.push(`font-family:${escapeHtml(fontFamily)}`)
  const fontSize = String((style as Record<string, unknown>).fontSize || '').trim()
  if (/^\d+(\.\d+)?(px|pt|em|rem)?$/.test(fontSize)) css.push(`font-size:${fontSize}`)
  const color = String((style as Record<string, unknown>).color || '').trim()
  if (/^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(color) || color.startsWith('rgb(')) {
    css.push(`color:${escapeHtml(color)}`)
  }
  const background = String((style as Record<string, unknown>).background || (style as Record<string, unknown>).backgroundColor || '').trim()
  if (/^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(background) || background.startsWith('rgb(')) {
    css.push(`background-color:${escapeHtml(background)}`)
  }
  return css.length ? ` style="${css.join(';')}"` : ''
}












function blockToLines(block: Record<string, unknown>): string[] {



  const t = String((block as Record<string, unknown>).type || 'paragraph').toLowerCase()



  if (t === 'paragraph' || t === 'text' || t === 'p') {



    const runs = Array.isArray((block as Record<string, unknown>).runs)
      ? ((block as Record<string, unknown>).runs as Array<Record<string, unknown>>)
      : null
    const raw = runs && runs.length
      ? runs.map((r) => String((r as Record<string, unknown>).text || '')).join('')
      : String((block as Record<string, unknown>).text || '')
    const text = raw.trim()
    return text ? [text] : []



  }



  if (t === 'list' || t === 'bullets' || t === 'bullet') {
    const ordered = Boolean((block as Record<string, unknown>).ordered)
    const items = Array.isArray((block as Record<string, unknown>).items) ? ((block as Record<string, unknown>).items as Array<unknown>) : []
    if (items.length) {
      const cleaned = items.map((v) => String(v || '').trim()).filter(Boolean)
      if (ordered) {
        return cleaned.map((v, idx) => `${idx + 1}. ${v}`)
      }
      return cleaned.map((v) => `- ${v}`)
    }
    const raw = String((block as Record<string, unknown>).text || '').trim()
    if (!raw) return []
    const parts = raw.split(/\n+/).map((v) => v.trim()).filter(Boolean)
    if (ordered) {
      return parts.map((v, idx) => {
        const stripped = v.replace(/^\d+[\.\)]\s+/, '')
        return `${idx + 1}. ${stripped}`
      })
    }
    return parts.map((v) => (v.startsWith('-') ? v : `- ${v}`))
  }



  if (t === 'table' || t === 'figure') {



    const payload: Record<string, unknown> = {}



    if (typeof (block as Record<string, unknown>).caption === 'string') payload.caption = (block as Record<string, unknown>).caption



    if (Array.isArray((block as Record<string, unknown>).columns)) payload.columns = (block as Record<string, unknown>).columns



    if (Array.isArray((block as Record<string, unknown>).rows)) payload.rows = (block as Record<string, unknown>).rows



    if ((block as Record<string, unknown>).data && typeof (block as Record<string, unknown>).data === 'object') payload.data = (block as Record<string, unknown>).data



    const marker = t === 'table' ? 'TABLE' : 'FIGURE'



    return [`[[${marker}:${JSON.stringify(payload)}]]`]



  }



  if (t === 'reference' || t === 'ref') {



    const text = String((block as Record<string, unknown>).text || '').trim()



    if (text) return [text]



    const items = Array.isArray((block as Record<string, unknown>).items) ? ((block as Record<string, unknown>).items as Array<unknown>) : []



    return items.map((v) => String(v || '').trim()).filter(Boolean)



  }



  const fallback = String((block as Record<string, unknown>).text || '').trim()



  return fallback ? [fallback] : []



}







function blockToHtml(block: Record<string, unknown>): string {
  const idAttr = blockIdAttr(block)
  const styleAttr = styleAttrFromBlock(block)



  const t = String((block as Record<string, unknown>).type || 'paragraph').toLowerCase()



  if (t === 'heading') {



    const level = Math.min(6, Math.max(1, Number((block as Record<string, unknown>).level || 1)))



    const raw = String((block as Record<string, unknown>).text || '')
    const runs = Array.isArray((block as Record<string, unknown>).runs)
      ? ((block as Record<string, unknown>).runs as Array<Record<string, unknown>>)
      : null
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



    const raw = String((block as Record<string, unknown>).text || '')
    const runs = Array.isArray((block as Record<string, unknown>).runs)
      ? ((block as Record<string, unknown>).runs as Array<Record<string, unknown>>)
      : null
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



    let ordered = Boolean((block as Record<string, unknown>).ordered)
    const itemsRaw = Array.isArray((block as Record<string, unknown>).items) ? ((block as Record<string, unknown>).items as Array<unknown>) : []
    const hasRawItems = itemsRaw.length > 0
    let items = itemsRaw.length
      ? itemsRaw.map((v) => String(v ?? ''))
      : String((block as Record<string, unknown>).text || '')
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
    const caption = payload.caption || '??'
    const attrs = `${idAttr}${styleAttr}`
    const spec = payload.spec && typeof payload.spec === 'object' ? payload.spec : null
    const encoded = spec ? encodeURIComponent(JSON.stringify(spec)) : ''
    const dataAttr = encoded ? ` data-figure-spec="${escapeHtml(encoded)}"` : ''
    return `<figure class="wa-figure"${attrs}${dataAttr}><div class="wa-figure-box">?</div><figcaption>${escapeHtml(caption)}</figcaption></figure>`
  }


  if (t === 'quote') {



    const text = String((block as Record<string, unknown>).text || '').trim()



    return text ? `<blockquote>${formatInline(text)}</blockquote>` : ''



  }



  const fallback = String((block as Record<string, unknown>).text || '').trim()



  return fallback ? renderParagraphHtml(fallback) : ''



}







function renderHeadingHtml(level: number, text: string, attrs: string = ''): string {



  const safe = formatInline(text)



  const lvl = Math.min(6, Math.max(1, Number(level || 1)))



  return `<h${lvl}${attrs}>${safe}</h${lvl}>`



}







function renderParagraphHtml(text: string): string {



  const safe = formatInline(text).replace(/\n/g, '<br/>')



  return `<p>${safe}</p>`



}







function normalizeTablePayload(block: Record<string, unknown>) {



  const out = { caption: '', columns: [] as string[], rows: [] as Array<unknown> }



  const table = (block as Record<string, unknown>).table



  const data = typeof table === 'object' && table ? (table as Record<string, unknown>) : (block as Record<string, unknown>).data



  const raw = typeof data === 'object' && data ? (data as Record<string, unknown>) : block



  const caption = String((raw as Record<string, unknown>).caption || '').trim()



  out.caption = caption



  const cols = (raw as Record<string, unknown>).columns



  if (Array.isArray(cols)) out.columns = cols.map((c) => String(c))



  const rows = (raw as Record<string, unknown>).rows



  if (Array.isArray(rows)) out.rows = rows as Array<unknown>



  return out



}







function normalizeFigurePayload(block: Record<string, unknown>) {
  const fig = (block as Record<string, unknown>).figure
  const dataObj = typeof fig === 'object' && fig ? (fig as Record<string, unknown>) : null
  const raw = dataObj || block
  const caption = String((raw as Record<string, unknown>).caption || '').trim()
  const spec: Record<string, unknown> = dataObj ? { ...dataObj } : {}
  if (caption) spec.caption = caption
  return { caption, spec }
}







function normalizeTitle(text: string): string {



  return String(text || '').trim().toLowerCase()



}

function findFirstSectionTitle(sections: Array<Record<string, unknown>>): string {
  for (const sec of sections) {
    const title = String((sec as Record<string, unknown>).title || '').trim()
    const level = Number((sec as Record<string, unknown>).level || 0)
    if (title && level <= 1) return title
    const children = Array.isArray((sec as Record<string, unknown>).children)
      ? ((sec as Record<string, unknown>).children as Array<Record<string, unknown>>)
      : []
    const child = findFirstSectionTitle(children)
    if (child) return child
  }
  return ''
}

function inferTitleFromBlocks(blocks: Array<Record<string, unknown>>): string {
  for (const b of blocks) {
    const t = String((b as Record<string, unknown>).type || '').toLowerCase()
    if (t === 'heading' && Number((b as Record<string, unknown>).level || 0) === 1) {
      const text = String((b as Record<string, unknown>).text || '').trim()
      if (text) return text
    }
  }
  for (const b of blocks) {
    if (String((b as Record<string, unknown>).type || '') === 'paragraph') {
      const raw = String((b as Record<string, unknown>).text || '').trim()
      if (raw) return raw.slice(0, 24)
    }
  }
  return ''
}

const HEADING_GLUE_PREFIXES = [
  '摘要',
  '引言',
  '绪论',
  '背景',
  '研究背景',
  '目标',
  '范围',
  '术语',
  '定义',
  '需求',
  '需求分析',
  '总体设计',
  '系统设计',
  '架构设计',
  '详细设计',
  '模块设计',
  '实现',
  '关键技术',
  '应用',
  '方法',
  '数据',
  '分析',
  '讨论',
  '评估',
  '结果',
  '结论',
  '总结',
  '展望',
  '风险',
  '问题',
  '计划',
  '本周工作',
  '下周计划',
  '问题与风险',
  '需协助事项',
  '参考文献',
  '附录',
  '致谢'
]

const HEADING_GLUE_PUNCT = /[。！？!?；;，、]/
const HEADING_GLUE_BODY_STARTERS = [
  '本文',
  '本研究',
  '本项目',
  '随着',
  '本周',
  '本次',
  '本节',
  '我们',
  '由于',
  '因此',
  '此外',
  '同时',
  '首先',
  '其次',
  '最后'
]

function splitHeadingGlue(text: string): { heading: string; rest: string } | null {
  const raw = String(text || '').trim()
  if (!raw) return null
  if (raw.length <= 12 && !HEADING_GLUE_PUNCT.test(raw)) return null
  const colon = /^(.{1,12})[:：](.+)$/.exec(raw)
  if (colon) {
    const left = String(colon[1] || '').trim()
    const right = String(colon[2] || '').trim()
    if (left && right && (HEADING_GLUE_PUNCT.test(right) || right.length >= 12)) {
      return { heading: left.replace(/[：:、\-—\s]+$/g, ''), rest: right.replace(/^[：:、\-—\s]+/g, '') }
    }
  }
  const repeated = /^(.{2,10})\s*\1(.+)$/.exec(raw)
  if (repeated) {
    const left = String(repeated[1] || '').trim()
    const right = String(repeated[2] || '').trim()
    if (left && right && (HEADING_GLUE_PUNCT.test(right) || right.length >= 6)) {
      return { heading: left.replace(/[：:、\-—\s]+$/g, ''), rest: right.replace(/^[：:、\-—\s]+/g, '') }
    }
  }
  const prefixes = HEADING_GLUE_PREFIXES.slice().sort((a, b) => b.length - a.length)
  for (const prefix of prefixes) {
    if (raw.startsWith(prefix) && raw.length > prefix.length + 1) {
      const rest = raw.slice(prefix.length).trim().replace(/^[：:、\-—\s]+/g, '')
      if (rest && (HEADING_GLUE_PUNCT.test(rest) || rest.length >= 12)) {
        return { heading: prefix, rest }
      }
    }
  }
  for (const kw of prefixes) {
    const idx = raw.indexOf(kw)
    if (idx <= 0) continue
    const headEnd = idx + kw.length
    if (headEnd > 10) continue
    const left = raw.slice(0, headEnd).trim()
    const rest = raw.slice(headEnd).trim().replace(/^[：:、\-—\s]+/g, '')
    if (left && rest && (HEADING_GLUE_PUNCT.test(rest) || rest.length >= 12)) {
      return { heading: left.replace(/[：:、\-—\s]+$/g, ''), rest }
    }
  }
  const numIdx = raw.search(/\b\d+(?:\.\d+)+\b/)
  if (numIdx > 0 && numIdx <= 12) {
    const left = raw.slice(0, numIdx).trim()
    const rest = raw.slice(numIdx).trim().replace(/^[：:、\-—\s]+/g, '')
    if (left && rest && (HEADING_GLUE_PUNCT.test(rest) || rest.length >= 12)) {
      return { heading: left.replace(/[：:、\-—\s]+$/g, ''), rest }
    }
  }
  for (const starter of HEADING_GLUE_BODY_STARTERS) {
    const idx = raw.indexOf(starter)
    if (idx > 0 && idx <= 10) {
      const left = raw.slice(0, idx).trim()
      const right = raw.slice(idx).trim().replace(/^[：:、\-—\s]+/g, '')
      if (left && right && right.length >= 6 && !HEADING_GLUE_PUNCT.test(left)) {
        return { heading: left.replace(/[：:、\-—\s]+$/g, ''), rest: right }
      }
    }
  }
  return null
}

function buildDocIrFromBlocks(blocks: Array<Record<string, unknown>>, title: string): Record<string, unknown> {
  const docTitle = String(title || '').trim() || '自动生成文档'
  const sections: Array<Record<string, unknown>> = []
  const stack: Array<{ level: number; node: Record<string, unknown> }> = []
  let orphan: Array<Record<string, unknown>> = []

  const pushImplicit = () => {
    if (!orphan.length) return
    const implicit = { id: makeId(), title: docTitle, level: 1, blocks: orphan, children: [] }
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

function makeId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return (crypto as Crypto).randomUUID().replace(/-/g, '')
  }
  return `b${Math.random().toString(16).slice(2)}${Date.now().toString(16)}`
}

function resolveDocTitle(doc: Record<string, unknown>): string {
  const raw = String(doc.title || '').trim()
  if (raw) return raw
  const sections = Array.isArray(doc.sections) ? (doc.sections as Array<Record<string, unknown>>) : []
  const fromSections = findFirstSectionTitle(sections)
  if (fromSections) return fromSections
  if (sections.length === 1) {
    const sole = sections[0] as Record<string, unknown>
    const level = Number(sole.level || 0)
    const soleTitle = String(sole.title || '').trim()
    if (soleTitle && level <= 1) return soleTitle
  }
  const blocks = Array.isArray((doc as Record<string, unknown>).blocks)
    ? ((doc as Record<string, unknown>).blocks as Array<Record<string, unknown>>)
    : []
  return inferTitleFromBlocks(blocks)
}











function normalizeLines(lines: string[]): string[] {
  const out: string[] = []
  let run: string[] = []
  let blankSeen = false
  const flush = () => {
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







function formatInline(text: string): string {



  let safe = escapeHtml(text)



  safe = safe.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')



  safe = safe.replace(/\*(.+?)\*/g, '<em>$1</em>')



  safe = safe.replace(/~~(.+?)~~/g, '<del>$1</del>')



  safe = safe.replace(/==(.+?)==/g, '<mark>$1</mark>')



  safe = safe.replace(/\+\+(.+?)\+\+/g, '<u>$1</u>')



  safe = safe.replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')



  return safe



}

function runStyleAttr(run: Record<string, unknown>): string {
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

function renderRuns(runs: Array<Record<string, unknown>>): string {
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







function escapeHtml(s: string): string {



  return String(s || '')



    .replace(/&/g, '&amp;')



    .replace(/</g, '&lt;')



    .replace(/>/g, '&gt;')



    .replace(/"/g, '&quot;')



    .replace(/'/g, '&#39;')



}



