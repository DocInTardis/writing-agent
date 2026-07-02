export const SECTION_TARGET_PREFIX = 'sec:'
export const DOC_TITLE_TARGET_ID = 'doc:title'

export function isSectionTargetId(id: string): boolean {
  return String(id || '').startsWith(SECTION_TARGET_PREFIX)
}

export function isDocTitleTargetId(id: string): boolean {
  return String(id || '') === DOC_TITLE_TARGET_ID
}

export function sectionIdFromTarget(id: string): string {
  if (!isSectionTargetId(id)) return ''
  return String(id || '').slice(SECTION_TARGET_PREFIX.length).trim()
}

export function blockIdFromTarget(id: string): string {
  const value = String(id || '').trim()
  if (!value) return ''
  if (isSectionTargetId(value) || isDocTitleTargetId(value)) return ''
  return value
}

export function blockTargetIds(ids: string[]): string[] {
  return (ids || []).map((id) => blockIdFromTarget(id)).filter(Boolean)
}

export function sectionTargetIds(ids: string[]): string[] {
  return (ids || []).map((id) => sectionIdFromTarget(id)).filter(Boolean)
}

export function targetIdForElement(el: HTMLElement | null): string {
  if (!el) return ''
  const blockId = String(el.dataset.blockId || '').trim()
  if (blockId) return blockId
  const sectionId = String(el.dataset.sectionId || '').trim()
  if (sectionId) return `${SECTION_TARGET_PREFIX}${sectionId}`
  if (String(el.dataset.docTitle || '').trim()) return DOC_TITLE_TARGET_ID
  return ''
}

export function normalizeBlockIds(ids: string[]): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of ids || []) {
    const id = String(raw || '').trim()
    if (!id || seen.has(id)) continue
    seen.add(id)
    out.push(id)
  }
  return out
}

export function realBlockTargetIds(ids: string[]): string[] {
  return (ids || [])
    .map((id) => String(id || '').trim())
    .filter((id) => id && id !== DOC_TITLE_TARGET_ID && !isSectionTargetId(id))
}

export function normalizeColorHex(raw: string): string {
  const value = String(raw || '').trim().toLowerCase()
  if (!value) return ''
  if (/^#([0-9a-f]{3})$/.test(value)) {
    const v = value.slice(1)
    return `#${v[0]}${v[0]}${v[1]}${v[1]}${v[2]}${v[2]}`
  }
  if (/^#([0-9a-f]{6})$/.test(value)) return value
  const rgb = /^rgba?\(([^)]+)\)$/.exec(value)
  if (!rgb) return ''
  const parts = rgb[1]
    .split(',')
    .map((item) => Number(item.trim()))
    .filter((num) => Number.isFinite(num))
  if (parts.length < 3) return ''
  const hex = parts.slice(0, 3).map((num) => Math.max(0, Math.min(255, Math.round(num))).toString(16).padStart(2, '0'))
  return `#${hex.join('')}`
}

export function buildBlockSessionKey(ids: string[]): string {
  return (ids || [])
    .map((id) => String(id || '').trim())
    .filter(Boolean)
    .sort()
    .join('|')
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}
