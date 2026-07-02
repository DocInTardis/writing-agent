function updateSectionsDeep(
  sections: Array<Record<string, unknown>>,
  updater: (section: Record<string, unknown>) => Record<string, unknown>
): Array<Record<string, unknown>> {
  let changed = false
  const nextSections = sections.map((sec) => {
    let nextSec = updater(sec)
    let touched = nextSec !== sec
    const children = Array.isArray(nextSec.children) ? (nextSec.children as Array<Record<string, unknown>>) : []
    if (children.length) {
      const nextChildren = updateSectionsDeep(children, updater)
      if (nextChildren !== children) {
        nextSec = { ...nextSec, children: nextChildren }
        touched = true
      }
    }
    if (touched) changed = true
    return nextSec
  })
  return changed ? nextSections : sections
}

export function updateDocTitle(doc: Record<string, unknown>, text: string): Record<string, unknown> | null {
  const nextTitle = String(text || '').trim() || '自动生成文档'
  const curTitle = String(doc.title || '').trim()
  let changed = nextTitle !== curTitle
  const sections = Array.isArray(doc.sections) ? (doc.sections as Array<Record<string, unknown>>) : []
  const nextSections = updateSectionsDeep(sections, (sec) => {
    if (String(sec.title || '').trim() !== curTitle) return sec
    changed = true
    return { ...sec, title: nextTitle }
  })
  if (!changed) return null
  return { ...doc, title: nextTitle, sections: nextSections }
}

export function updateSectionTitle(
  doc: Record<string, unknown>,
  sectionId: string,
  text: string,
  style?: Record<string, string> | null
): Record<string, unknown> | null {
  const nextTitle = String(text || '').trim() || '章节'
  let changed = false
  const sections = Array.isArray(doc.sections) ? (doc.sections as Array<Record<string, unknown>>) : []
  const nextSections = updateSectionsDeep(sections, (sec) => {
    if (String(sec.id || '') !== sectionId) return sec
    changed = true
    const nextSec = { ...sec, title: nextTitle }
    if (style && Object.keys(style).length) {
      return { ...nextSec, style }
    }
    return nextSec
  })
  if (!changed) return null
  return { ...doc, sections: nextSections }
}

export function updateBlock(
  doc: Record<string, unknown>,
  blockId: string,
  payload: Record<string, unknown>
): Record<string, unknown> | null {
  let changed = false
  const sections = Array.isArray(doc.sections) ? (doc.sections as Array<Record<string, unknown>>) : []
  const nextSections = updateSectionsDeep(sections, (sec) => {
    const blocks = Array.isArray(sec.blocks) ? (sec.blocks as Array<Record<string, unknown>>) : []
    if (!blocks.length) return sec
    const idx = blocks.findIndex((b) => String(b.id || '') === blockId)
    if (idx < 0) return sec
    const prev = blocks[idx] || {}
    const nextBlocks = blocks.slice()
    nextBlocks[idx] = { ...prev, ...payload, id: prev.id || blockId }
    changed = true
    return { ...sec, blocks: nextBlocks }
  })
  if (!changed) return null
  return { ...doc, sections: nextSections }
}

function insertBlockRelative(
  doc: Record<string, unknown>,
  blockId: string,
  newBlock: Record<string, unknown>,
  offset: 0 | 1
) {
  let changed = false
  const sections = Array.isArray(doc.sections) ? (doc.sections as Array<Record<string, unknown>>) : []
  const nextSections = updateSectionsDeep(sections, (sec) => {
    const blocks = Array.isArray(sec.blocks) ? (sec.blocks as Array<Record<string, unknown>>) : []
    if (!blocks.length) return sec
    const idx = blocks.findIndex((b) => String(b.id || '') === blockId)
    if (idx < 0) return sec
    const nextBlocks = blocks.slice()
    nextBlocks.splice(idx + offset, 0, newBlock)
    changed = true
    return { ...sec, blocks: nextBlocks }
  })
  if (!changed) return null
  return { ...doc, sections: nextSections }
}

export function insertBlockAfter(doc: Record<string, unknown>, blockId: string, newBlock: Record<string, unknown>) {
  return insertBlockRelative(doc, blockId, newBlock, 1)
}

export function insertBlockBefore(doc: Record<string, unknown>, blockId: string, newBlock: Record<string, unknown>) {
  return insertBlockRelative(doc, blockId, newBlock, 0)
}

export function replaceInDocIr(doc: Record<string, unknown>, regex: RegExp, replace: string): Record<string, unknown> | null {
  let changed = false
  const updateBlock = (block: Record<string, unknown>) => {
    const t = String(block.type || 'paragraph').toLowerCase()
    if (t === 'list') {
      const items = Array.isArray(block.items) ? (block.items as Array<unknown>) : []
      const nextItems = items.map((item) => String(item ?? '').replace(regex, replace))
      if (nextItems.join('') !== items.join('')) {
        changed = true
        return { ...block, items: nextItems }
      }
      return block
    }
    if (t === 'table') {
      const table = typeof block.table === 'object' && block.table ? (block.table as Record<string, unknown>) : null
      if (table && typeof table.caption === 'string') {
        const nextCaption = String(table.caption || '').replace(regex, replace)
        if (nextCaption !== table.caption) {
          changed = true
          return { ...block, table: { ...table, caption: nextCaption } }
        }
      }
      return block
    }
    if (t === 'figure') {
      const fig = typeof block.figure === 'object' && block.figure ? (block.figure as Record<string, unknown>) : null
      if (fig && typeof fig.caption === 'string') {
        const nextCaption = String(fig.caption || '').replace(regex, replace)
        if (nextCaption !== fig.caption) {
          changed = true
          return { ...block, figure: { ...fig, caption: nextCaption } }
        }
      }
      return block
    }
    if (typeof block.text === 'string') {
      const nextText = String(block.text || '').replace(regex, replace)
      if (nextText !== block.text) {
        changed = true
        return { ...block, text: nextText }
      }
    }
    return block
  }
  const nextDoc: Record<string, unknown> = { ...doc }
  if (typeof nextDoc.title === 'string') {
    const nextTitle = String(nextDoc.title || '').replace(regex, replace)
    if (nextTitle !== nextDoc.title) {
      nextDoc.title = nextTitle
      changed = true
    }
  }
  const sections = Array.isArray(nextDoc.sections) ? (nextDoc.sections as Array<Record<string, unknown>>) : []
  const nextSections = updateSectionsDeep(sections, (sec) => {
    let nextSec = sec
    let touched = false
    if (typeof sec.title === 'string') {
      const nextTitle = String(sec.title || '').replace(regex, replace)
      if (nextTitle !== sec.title) {
        nextSec = { ...nextSec, title: nextTitle }
        touched = true
        changed = true
      }
    }
    const blocks = Array.isArray(sec.blocks) ? (sec.blocks as Array<Record<string, unknown>>) : []
    if (blocks.length) {
      const nextBlocks = blocks.map((b) => updateBlock(b))
      if (nextBlocks.some((b, idx) => b !== blocks[idx])) {
        nextSec = { ...nextSec, blocks: nextBlocks }
        touched = true
      }
    }
    return touched ? nextSec : sec
  })
  if (nextSections !== sections) {
    nextDoc.sections = nextSections
  }
  return changed ? nextDoc : null
}
