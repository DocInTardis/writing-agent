function flattenSections(doc: any): any[] {
  const out: any[] = []
  const sections = Array.isArray(doc?.sections) ? doc.sections : []
  const walk = (sec: any) => {
    out.push(sec)
    const children = Array.isArray(sec?.children) ? sec.children : []
    children.forEach((child: any) => walk(child))
  }
  sections.forEach((sec: any) => walk(sec))
  return out
}

function sectionSignature(sec: any): string {
  const level = Math.max(1, Math.min(6, Number(sec?.level || 1)))
  const title = String(sec?.title || '').trim()
  const style = sec?.style && typeof sec.style === 'object' ? JSON.stringify(sec.style) : ''
  return `${level}:${title}:${style}`
}

function blockPayload(block: any): Record<string, unknown> {
  const t = String(block?.type || 'paragraph').toLowerCase()
  const style = block?.style && typeof block.style === 'object' ? block.style : null
  const runs = Array.isArray(block?.runs) ? block.runs : null
  if (t === 'list') {
    const items = Array.isArray(block?.items) ? block.items : []
    const ordered = Boolean(block?.ordered)
    const payload: Record<string, unknown> = { type: 'list', items, ordered }
    if (style) payload.style = style
    if (runs) payload.runs = runs
    return payload
  }
  if (t === 'table') {
    const payload: Record<string, unknown> = { type: 'table', table: block?.table || {} }
    if (style) payload.style = style
    if (runs) payload.runs = runs
    return payload
  }
  if (t === 'figure') {
    const payload: Record<string, unknown> = { type: 'figure', figure: block?.figure || {} }
    if (style) payload.style = style
    if (runs) payload.runs = runs
    return payload
  }
  const text = String(block?.text || '')
  const payload: Record<string, unknown> = { type: 'paragraph', text }
  if (style) payload.style = style
  if (runs) payload.runs = runs
  return payload
}

function blockKey(block: any): string {
  const t = String(block?.type || 'paragraph').toLowerCase()
  const styleSig = block?.style ? `:style=${JSON.stringify(block?.style || {})}` : ''
  const runSig = block?.runs ? `:runs=${JSON.stringify(block?.runs || [])}` : ''
  if (t === 'list') return `list:${JSON.stringify(block?.items || [])}:${Boolean(block?.ordered)}${styleSig}`
  if (t === 'table') return `table:${JSON.stringify(block?.table || {})}${styleSig}`
  if (t === 'figure') return `figure:${JSON.stringify(block?.figure || {})}${styleSig}`
  return `paragraph:${String(block?.text || '')}${styleSig}${runSig}`
}

export function buildDocIrOps(baseDoc: any, nextDoc: any): Array<Record<string, unknown>> | null {
  if (!baseDoc || !nextDoc) return null
  const oldSecs = flattenSections(baseDoc)
  const newSecs = flattenSections(nextDoc)
  if (oldSecs.length !== newSecs.length) return null
  for (let i = 0; i < oldSecs.length; i++) {
    if (sectionSignature(oldSecs[i]) !== sectionSignature(newSecs[i])) return null
    if (!oldSecs[i]?.id) return null
  }
  const ops: Array<Record<string, unknown>> = []
  for (let i = 0; i < oldSecs.length; i++) {
    const oldSec = oldSecs[i]
    const newSec = newSecs[i]
    const oldBlocks = Array.isArray(oldSec?.blocks) ? oldSec.blocks : []
    const newBlocks = Array.isArray(newSec?.blocks) ? newSec.blocks : []
    const oldIds = oldBlocks.map((b: any) => String(b?.id || '')).filter(Boolean)
    const newIds = newBlocks.map((b: any) => String(b?.id || '')).filter(Boolean)
    const oldIdSet = new Set(oldIds)
    const newIdSet = new Set(newIds)
    const oldMap = new Map(oldBlocks.map((b: any) => [String(b?.id || ''), b]))
    for (const id of oldIds) {
      if (!newIdSet.has(id)) ops.push({ op: 'delete', target_id: id })
    }
    const sharedNew = newIds.filter((id) => oldIdSet.has(id))
    const working = oldIds.filter((id) => newIdSet.has(id))
    sharedNew.forEach((id, idx) => {
      const curIndex = working.indexOf(id)
      if (curIndex === -1) return
      if (curIndex !== idx) {
        ops.push({ op: 'move', target_id: id, parent_id: String(oldSec.id), index: idx })
        working.splice(curIndex, 1)
        working.splice(idx, 0, id)
      }
    })
    newBlocks.forEach((b: any, idx: number) => {
      const id = String(b?.id || '')
      if (id && oldIdSet.has(id)) {
        const prev = oldMap.get(id)
        if (prev && blockKey(prev) !== blockKey(b)) {
          ops.push({ op: 'update', target_id: id, payload: blockPayload(b) })
        }
        return
      }
      const payload = blockPayload(b)
      ops.push({ op: 'insert', parent_id: String(oldSec.id), index: idx, payload })
    })
  }
  return ops
}
