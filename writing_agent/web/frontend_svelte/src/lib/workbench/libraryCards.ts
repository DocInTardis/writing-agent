import type { LibraryCard } from './types'

export type LibraryApiItem = {
  doc_id?: string
  title?: string
  status?: string
  source?: string
  source_name?: string
  char_count?: number
  created_at?: string
  updated_at?: string
}

const STATUS_LABELS: Record<LibraryCard['status'], string> = {
  pending: '待启用',
  approved: '已用于 AI',
  trashed: '回收站'
}

export function normalizeLibraryStatus(value: unknown): LibraryCard['status'] {
  const status = String(value || '').trim().toLowerCase()
  if (status === 'approved' || status === 'trashed') return status
  return 'pending'
}

export function libraryCardFromApi(item: LibraryApiItem): LibraryCard {
  const sourceName = String(item.source_name || '').trim()
  const title = String(item.title || '').trim() || sourceName.replace(/\.[^.]+$/, '') || '未命名资料'
  const status = normalizeLibraryStatus(item.status)
  const charCount = Math.max(0, Number(item.char_count || 0))
  const updated = Date.parse(String(item.updated_at || item.created_at || ''))
  const extension = sourceName.includes('.') ? sourceName.split('.').pop()?.toUpperCase() || '文本' : '文本'
  return {
    id: String(item.doc_id || ''),
    title,
    summary: sourceName || `${charCount.toLocaleString()} 字符的文本资料`,
    status,
    status_label: STATUS_LABELS[status],
    kind_label: extension,
    tags: [String(item.source || 'upload') === 'upload' ? '本地上传' : '生成内容'],
    updated_at: Number.isFinite(updated) ? updated : Date.now(),
    size_label: charCount > 0 ? `${charCount.toLocaleString()} 字符` : '未提取文字',
    source_name: sourceName,
    char_count: charCount
  }
}

export function formatLibraryCardTime(ts: number) {
  const diff = Math.max(0, Date.now() - Number(ts || 0))
  const minute = 60 * 1000
  const hour = 60 * minute
  const day = 24 * hour
  if (diff < minute) return '刚刚'
  if (diff < hour) return `${Math.floor(diff / minute)} 分钟前`
  if (diff < day) return `${Math.floor(diff / hour)} 小时前`
  if (diff < 30 * day) return `${Math.floor(diff / day)} 天前`
  return new Date(ts).toLocaleDateString('zh-CN')
}

export function cardMatchesSearch(card: LibraryCard, query: string) {
  const q = String(query || '').trim().toLowerCase()
  if (!q) return true
  return `${card.title} ${card.summary} ${card.kind_label} ${card.tags.join(' ')}`.toLowerCase().includes(q)
}

export function guessDocTitle(text: string) {
  const match = String(text || '').match(/^\s*#\s+(.+)$/m)
  return match?.[1]?.trim() || '未命名文档'
}

export function estimateKb(text: string) {
  return Math.max(1, Math.round(String(text || '').length * 2 / 1024))
}
