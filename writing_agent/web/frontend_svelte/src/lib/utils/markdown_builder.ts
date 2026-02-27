import type { UnknownRecord } from './markdown_common'

function toDocIrBlock(block: UnknownRecord): UnknownRecord | null {
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
    return { id, type: 'list', items, ordered: Boolean(block.ordered) }
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

export function buildDocIrFromBlocks(blocks: UnknownRecord[], title: string): UnknownRecord {
  const docTitle = String(title || '').trim() || '自动生成文档'
  const sections: UnknownRecord[] = []
  const stack: Array<{ level: number; node: UnknownRecord }> = []
  let orphan: UnknownRecord[] = []

  const pushImplicit = () => {
    if (!orphan.length) return
    const implicit = { id: makeId(), title: docTitle, level: 1, blocks: orphan, children: [] as UnknownRecord[] }
    sections.push(implicit)
    stack.push({ level: 1, node: implicit })
    orphan = []
  }

  for (const b of blocks) {
    const t = String(b.type || '').toLowerCase()
    if (t === 'heading') {
      const level = Math.min(6, Math.max(1, Number(b.level || 1)))
      const text = String(b.text || '').trim() || '章节'
      const node: UnknownRecord = { id: makeId(), title: text, level, blocks: [] as UnknownRecord[], children: [] as UnknownRecord[] }
      if (orphan.length && stack.length === 0) pushImplicit()
      while (stack.length && stack[stack.length - 1].level >= level) stack.pop()
      if (stack.length) {
        ;(stack[stack.length - 1].node.children as UnknownRecord[]).push(node)
      } else {
        sections.push(node)
      }
      stack.push({ level, node })
      continue
    }

    const docBlock = toDocIrBlock(b)
    if (!docBlock) continue
    if (stack.length) {
      ;(stack[stack.length - 1].node.blocks as UnknownRecord[]).push(docBlock)
    } else {
      orphan.push(docBlock)
    }
  }

  if (orphan.length && !sections.length) {
    sections.push({ id: makeId(), title: docTitle, level: 1, blocks: orphan, children: [] as UnknownRecord[] })
  }
  return { title: docTitle, sections }
}
