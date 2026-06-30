export interface PatchChunk {
  id: string
  offset: number
  deleteCount: number
  insertText: string
}

export function applyPatch(base: string, patch: PatchChunk): string {
  const source = String(base ?? '')
  const start = Math.max(0, Math.min(source.length, Number(patch.offset || 0)))
  const del = Math.max(0, Number(patch.deleteCount || 0))
  return source.slice(0, start) + String(patch.insertText || '') + source.slice(start + del)
}

export function applyPatchBatch(base: string, patches: PatchChunk[]): string {
  let out = String(base ?? '')
  for (const p of patches || []) {
    out = applyPatch(out, p)
  }
  return out
}
