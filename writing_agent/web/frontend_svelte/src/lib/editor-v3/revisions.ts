import { cloneJson, type DocumentV3, type JsonObject, type V3BlockNode } from './model'

export interface BlockRevisionPatch {
  nodeId: string
  beforeSectionId?: string
  beforeIndex?: number
  before?: V3BlockNode
  afterSectionId?: string
  afterIndex?: number
  after?: V3BlockNode
}

export interface DocumentRevision extends JsonObject {
  id: string
  author: string
  createdAt: number
  status: 'pending' | 'accepted' | 'rejected'
  summary: string
  patches: BlockRevisionPatch[]
}

function indexedBlocks(document: DocumentV3) {
  const result = new Map<string, { sectionId: string; index: number; block: V3BlockNode }>()
  for (const section of document.sections) {
    section.content.forEach((block, index) => result.set(block.id, { sectionId: section.id, index, block }))
  }
  return result
}

export function buildRevision(before: DocumentV3, after: DocumentV3, author = '用户'): DocumentRevision | null {
  const oldBlocks = indexedBlocks(before)
  const newBlocks = indexedBlocks(after)
  const patches: BlockRevisionPatch[] = []
  for (const nodeId of new Set([...oldBlocks.keys(), ...newBlocks.keys()])) {
    const oldEntry = oldBlocks.get(nodeId)
    const newEntry = newBlocks.get(nodeId)
    const same = oldEntry && newEntry && oldEntry.sectionId === newEntry.sectionId && oldEntry.index === newEntry.index &&
      JSON.stringify(oldEntry.block) === JSON.stringify(newEntry.block)
    if (same) continue
    patches.push({
      nodeId,
      beforeSectionId: oldEntry?.sectionId,
      beforeIndex: oldEntry?.index,
      before: oldEntry ? cloneJson(oldEntry.block) : undefined,
      afterSectionId: newEntry?.sectionId,
      afterIndex: newEntry?.index,
      after: newEntry ? cloneJson(newEntry.block) : undefined
    })
  }
  if (!patches.length) return null
  const inserted = patches.filter((patch) => !patch.before && patch.after).length
  const deleted = patches.filter((patch) => patch.before && !patch.after).length
  const changed = patches.length - inserted - deleted
  return {
    id: `revision_${crypto.randomUUID().replace(/-/g, '')}`,
    author,
    createdAt: Date.now(),
    status: 'pending',
    summary: `修改 ${changed}、新增 ${inserted}、删除 ${deleted} 个块`,
    patches
  }
}

function removeNodes(document: DocumentV3, ids: Set<string>) {
  for (const section of document.sections) section.content = section.content.filter((block) => !ids.has(block.id))
}

export function settleRevision(document: DocumentV3, revisionId: string, accept: boolean): DocumentV3 {
  const next = cloneJson(document)
  const revision = next.revisions.find((item) => String(item.id || '') === revisionId) as DocumentRevision | undefined
  if (!revision || revision.status !== 'pending') return next
  if (!accept) {
    removeNodes(next, new Set(revision.patches.map((patch) => patch.nodeId)))
    const restorations = revision.patches.filter((patch) => patch.before && patch.beforeSectionId)
    restorations.sort((left, right) => Number(left.beforeIndex || 0) - Number(right.beforeIndex || 0))
    for (const patch of restorations) {
      const section = next.sections.find((item) => item.id === patch.beforeSectionId)
      if (!section || !patch.before) continue
      const index = Math.max(0, Math.min(section.content.length, Number(patch.beforeIndex || 0)))
      section.content.splice(index, 0, cloneJson(patch.before))
    }
  }
  revision.status = accept ? 'accepted' : 'rejected'
  revision.settledAt = Date.now()
  return next
}

export function addDocumentComment(
  document: DocumentV3,
  nodeIds: string[],
  text: string,
  selection?: { from: number; to: number; quote: string }
): DocumentV3 {
  const next = cloneJson(document)
  next.comments.push({
    id: `comment_${crypto.randomUUID().replace(/-/g, '')}`,
    author: '用户',
    createdAt: Date.now(),
    nodeIds: [...new Set(nodeIds)],
    text: text.trim(),
    selection: selection || null,
    resolved: false
  })
  return next
}

export function resolveDocumentComment(document: DocumentV3, commentId: string, resolved: boolean): DocumentV3 {
  const next = cloneJson(document)
  const comment = next.comments.find((item) => String(item.id || '') === commentId)
  if (comment) comment.resolved = resolved
  return next
}
