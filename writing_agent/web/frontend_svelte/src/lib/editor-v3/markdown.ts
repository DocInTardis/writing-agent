import type { DocumentV3, InlineNode, TextMark, V3BlockNode } from './model'

export interface MarkdownExportResult {
  markdown: string
  warnings: string[]
}

const makeId = (prefix: string) => `${prefix}_${crypto.randomUUID().replace(/-/g, '')}`

function textContent(value: string): InlineNode[] {
  return value ? [{ type: 'text', text: value }] : []
}

function inlineContent(value: string): InlineNode[] {
  const nodes: InlineNode[] = []
  // Single underscores are intentionally left literal: technical documents are
  // full of identifiers such as WRITING_AGENT_MODEL, which must not be damaged.
  const pattern = /(\[([^\]]+)\]\(([^)\s]+)\)|\*\*([^*]+)\*\*|__([^_]+)__|~~([^~]+)~~|\*([^*\n]+)\*)/g
  let cursor = 0
  for (const match of value.matchAll(pattern)) {
    const start = match.index || 0
    if (start > cursor) nodes.push(...textContent(value.slice(cursor, start)))
    let text = match[0]
    let marks: TextMark[] = []
    if (match[2] !== undefined) {
      text = match[2]
      marks = [{ type: 'link', attrs: { href: match[3] } }]
    } else if (match[4] !== undefined || match[5] !== undefined) {
      text = match[4] ?? match[5]
      marks = [{ type: 'bold' }]
    } else if (match[6] !== undefined) {
      text = match[6]
      marks = [{ type: 'strike' }]
    } else {
      text = match[7]
      marks = [{ type: 'italic' }]
    }
    nodes.push({ type: 'text', text, marks })
    cursor = start + match[0].length
  }
  if (cursor < value.length) nodes.push(...textContent(value.slice(cursor)))
  return nodes
}

function inlineLines(value: string): InlineNode[] {
  const content: InlineNode[] = []
  value.split('\n').forEach((line, index) => {
    if (index) content.push({ type: 'hardBreak' })
    content.push(...inlineContent(line))
  })
  return content
}

function paragraph(value: string): V3BlockNode {
  return { id: makeId('paragraph'), type: 'paragraph', styleId: 'normal', content: inlineLines(value) }
}

function listBlock(type: 'bulletList' | 'orderedList', items: string[]): V3BlockNode {
  return {
    id: makeId(type),
    type,
    content: items.map((item) => ({
      id: makeId('listItem'),
      type: 'listItem',
      content: [paragraph(item)]
    }))
  }
}

/**
 * Deliberately conservative Markdown import. Markdown is an interchange format,
 * never the editor's source of truth, so unsupported syntax remains readable text.
 */
export function markdownToBlocks(markdown: string): V3BlockNode[] {
  const lines = markdown.replace(/^\uFEFF/, '').replace(/\r\n?/g, '\n').split('\n')
  const blocks: V3BlockNode[] = []
  let index = 0

  while (index < lines.length) {
    const line = lines[index]
    if (!line.trim()) {
      index += 1
      continue
    }

    const fence = /^\s*```\s*([^\s`]*)\s*$/.exec(line)
    if (fence) {
      const body: string[] = []
      index += 1
      while (index < lines.length && !/^\s*```\s*$/.test(lines[index])) body.push(lines[index++])
      if (index < lines.length) index += 1
      blocks.push({
        id: makeId('codeBlock'),
        type: 'codeBlock',
        styleId: 'code',
        attrs: fence[1] ? { language: fence[1] } : {},
        content: textContent(body.join('\n'))
      })
      continue
    }

    const heading = /^(#{1,6})\s+(.+)$/.exec(line)
    if (heading) {
      const level = heading[1].length
      blocks.push({
        id: makeId('heading'),
        type: 'heading',
        styleId: `heading-${level}`,
        attrs: { level },
        content: inlineContent(heading[2].trim())
      })
      index += 1
      continue
    }

    if (/^\s*([-*_])(?:\s*\1){2,}\s*$/.test(line)) {
      blocks.push({ id: makeId('horizontalRule'), type: 'horizontalRule' })
      index += 1
      continue
    }

    if (/^\s*>\s?/.test(line)) {
      const quote: string[] = []
      while (index < lines.length && /^\s*>\s?/.test(lines[index])) quote.push(lines[index++].replace(/^\s*>\s?/, ''))
      blocks.push({ id: makeId('blockquote'), type: 'blockquote', styleId: 'quote', content: inlineLines(quote.join('\n')) })
      continue
    }

    if (/^\s*[-+*]\s+/.test(line)) {
      const items: string[] = []
      while (index < lines.length && /^\s*[-+*]\s+/.test(lines[index])) items.push(lines[index++].replace(/^\s*[-+*]\s+/, ''))
      blocks.push(listBlock('bulletList', items))
      continue
    }

    if (/^\s*\d+[.)]\s+/.test(line)) {
      const items: string[] = []
      while (index < lines.length && /^\s*\d+[.)]\s+/.test(lines[index])) items.push(lines[index++].replace(/^\s*\d+[.)]\s+/, ''))
      blocks.push(listBlock('orderedList', items))
      continue
    }

    if (/^\s*<!--\s*pagebreak\s*-->\s*$/i.test(line) || /^\s*\[分页符]\s*$/.test(line)) {
      blocks.push({ id: makeId('pageBreak'), type: 'pageBreak' })
      index += 1
      continue
    }

    const body = [line]
    index += 1
    while (index < lines.length && lines[index].trim()) {
      if (/^(#{1,6})\s+/.test(lines[index]) || /^\s*```/.test(lines[index])) break
      body.push(lines[index++])
    }
    blocks.push(paragraph(body.join('\n')))
  }

  return blocks.length ? blocks : [paragraph('')]
}

export function replaceDocumentContentFromMarkdown(document: DocumentV3, markdown: string, sourceName = ''): DocumentV3 {
  const next = structuredClone(document)
  const first = next.sections[0]
  if (!first) return next
  first.content = markdownToBlocks(markdown)
  next.sections = [first]
  next.metadata = {
    ...next.metadata,
    lastImport: {
      format: 'markdown',
      sourceName,
      importedAt: new Date().toISOString(),
      note: 'Markdown 仅转换结构与文本；Document V3 继续保存页面和样式设置。'
    }
  }
  return next
}

function escapeText(value: string): string {
  return value.replace(/\\/g, '\\\\').replace(/([*_`[\]])/g, '\\$1')
}

function markedText(text: string, marks: TextMark[] | undefined): string {
  let result = escapeText(text)
  for (const mark of marks || []) {
    if (mark.type === 'bold') result = `**${result}**`
    else if (mark.type === 'italic') result = `*${result}*`
    else if (mark.type === 'strike') result = `~~${result}~~`
    else if (mark.type === 'link' && mark.attrs?.href) result = `[${result}](${String(mark.attrs.href)})`
  }
  return result
}

function inlineMarkdown(content: Array<V3BlockNode | InlineNode> | undefined): string {
  return (content || []).map((node) => {
    if (!('id' in node) && node.type === 'text') return markedText(node.text || '', node.marks)
    if (!('id' in node) && node.type === 'hardBreak') return '  \n'
    return 'id' in node ? inlineMarkdown(node.content) : ''
  }).join('')
}

function blockMarkdown(block: V3BlockNode, warnings: Set<string>): string {
  const text = inlineMarkdown(block.content)
  if (block.type === 'heading') return `${'#'.repeat(Math.max(1, Math.min(6, Number(block.attrs?.level || 1))))} ${text}`
  if (block.type === 'paragraph') return text
  if (block.type === 'blockquote') return text.split('\n').map((line) => `> ${line}`).join('\n')
  if (block.type === 'codeBlock') return `\`\`\`${String(block.attrs?.language || '')}\n${text}\n\`\`\``
  if (block.type === 'horizontalRule') return '---'
  if (block.type === 'pageBreak') return '<!-- pagebreak -->'
  if (block.type === 'bulletList' || block.type === 'orderedList') {
    return (block.content || []).filter((node): node is V3BlockNode => 'id' in node).map((item, index) => {
      const prefix = block.type === 'orderedList' ? `${index + 1}.` : '-'
      return `${prefix} ${inlineMarkdown(item.content)}`
    }).join('\n')
  }
  if (block.type === 'table') {
    warnings.add('表格会导出为占位说明，单元格尺寸、边框和合并信息不会进入 Markdown。')
    return '> [表格对象：请在 Document V3 或 Word 导出中查看]'
  }
  if (block.type === 'figure') {
    warnings.add('图片和图形会导出为占位说明，嵌入资源与版式不会进入 Markdown。')
    return `> [图片/图形对象${String(block.attrs?.figure && typeof block.attrs.figure === 'object' && 'caption' in block.attrs.figure ? `：${block.attrs.figure.caption}` : '')}]`
  }
  if (block.type === 'equationBlock') {
    warnings.add('块级公式会尽量导出为 LaTeX 围栏，公式编号与版式不会进入 Markdown。')
    return `$$\n${String(block.attrs?.latex || '')}\n$$`
  }
  warnings.add(`“${block.type}”对象没有等价的 Markdown 表达，已导出为占位说明。`)
  return `> [${block.type} 对象：请在 Document V3 中查看]`
}

export function documentV3ToMarkdown(document: DocumentV3): MarkdownExportResult {
  const warnings = new Set<string>([
    'Markdown 不保存纸张、页边距、分页结果、字体、字号和段落精确样式。',
    '页眉页脚、页码格式和分节设置不会写入 Markdown；当前 Document V3 文档不会被覆盖。'
  ])
  if (document.comments.length || document.revisions.length) warnings.add('批注和修订记录不会写入 Markdown。')
  if (Object.keys(document.citations || {}).length) warnings.add('结构化引文数据不会写入 Markdown，只保留正文中可见文字。')
  if (document.sections.length > 1) warnings.add('多个分节会顺序合并，分节属性不会写入 Markdown。')
  const parts: string[] = []
  for (const section of document.sections) {
    for (const block of section.content) parts.push(blockMarkdown(block, warnings))
  }
  return { markdown: `${parts.join('\n\n').replace(/\n{3,}/g, '\n\n').trim()}\n`, warnings: [...warnings] }
}
