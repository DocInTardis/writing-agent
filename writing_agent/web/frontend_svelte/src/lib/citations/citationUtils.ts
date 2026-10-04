import type { Citation } from './citationTypes'

export function normalizeItems(items: unknown): Citation[] {
  if (!Array.isArray(items)) return []
  return items
    .filter((raw) => raw && typeof raw === 'object')
    .map((raw) => {
      const row = raw as Record<string, unknown>
      return {
        id: String(row.id || '').trim(),
        author: String(row.author || '').trim(),
        title: String(row.title || '').trim(),
        year: String(row.year || '').trim(),
        source: String(row.source || '').trim()
      }
    })
    .filter((c) => c.id && c.title)
}

export function normalizeResolveItem(item: unknown): Citation | null {
  if (!item || typeof item !== 'object') return null
  const row = item as Record<string, unknown>
  const next = {
    id: String(row.id || '').trim(),
    author: String(row.author || '').trim(),
    title: String(row.title || '').trim(),
    year: String(row.year || '').trim(),
    source: String(row.source || row.url || '').trim()
  }
  if (!next.title) return null
  return next
}

export function formatCitation(cite: Citation, style: 'apa' | 'mla' | 'gb'): string {
  if (style === 'apa') {
    return `${cite.author} (${cite.year}). ${cite.title}. ${cite.source}.`
  }
  if (style === 'mla') {
    return `${cite.author}. "${cite.title}." ${cite.source}, ${cite.year}.`
  }
  return `${cite.author}. ${cite.title}[J]. ${cite.source}, ${cite.year}.`
}

export function statusClass(status: string): string {
  if (status === 'verified') return 'ok'
  if (status === 'possible') return 'warn'
  if (status === 'error') return 'err'
  return 'miss'
}

export function statusLabel(status: string): string {
  if (status === 'verified') return '已核验'
  if (status === 'possible') return '疑似匹配'
  if (status === 'error') return '核验失败'
  return '未命中'
}
