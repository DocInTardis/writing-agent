import type { FeedbackItem, GraphMeta, LibraryCard } from './types'
import { summarizeGraphMeta } from './metadata'

export type BuildLibraryCardsInput = {
  sourceText: string
  wordCount: number
  previewSnippet: string
  lastGraphMeta: GraphMeta | null
  feedbackItems: FeedbackItem[]
  versionGroupCount: number
}

export function guessDocTitle(text: string) {
  const src = String(text || '')
  const m = src.match(/^\s*#\s+(.+)$/m)
  if (m && m[1]) return m[1].trim()
  return '未命名文档'
}

export function estimateKb(text: string) {
  const chars = String(text || '').length
  const bytes = chars * 2
  return Math.max(1, Math.round(bytes / 1024))
}

export function formatLibraryCardTime(ts: number) {
  const now = Date.now()
  const diff = Math.max(0, now - Number(ts || 0))
  const minute = 60 * 1000
  const hour = 60 * minute
  const day = 24 * hour
  if (diff < minute) return '刚刚更新'
  if (diff < hour) return `${Math.floor(diff / minute)} 分钟前`
  if (diff < day) return `${Math.floor(diff / hour)} 小时前`
  return `${Math.floor(diff / day)} 天前`
}

export function buildLibraryCards(input: BuildLibraryCardsInput): LibraryCard[] {
  const now = Date.now()
  const docTitle = guessDocTitle(input.sourceText)
  const wordLabel = `${Math.max(1, Number(input.wordCount || 0))} 词`
  const routeLabel = input.lastGraphMeta?.route_id ? `路由:${input.lastGraphMeta.route_id}` : '路由:default'
  const feedbackLabel =
    input.feedbackItems.length > 0 ? `满意度 ${input.feedbackItems[0].rating}/5` : '待收集反馈'
  return [
    {
      id: 'doc-main',
      title: docTitle,
      summary: input.previewSnippet || '当前文档正文摘要',
      status: 'draft',
      status_label: '草稿',
      kind_label: '正文',
      tone: 'azure',
      tags: ['当前文档', routeLabel, feedbackLabel],
      updated_at: now - 2 * 60 * 1000,
      size_label: wordLabel,
      action: 'editor'
    },
    {
      id: 'route-context',
      title: '路由与上下文策略',
      summary: input.lastGraphMeta ? summarizeGraphMeta(input.lastGraphMeta) : '默认图路由生效，可用于追踪生成链路。',
      status: 'synced',
      status_label: '已同步',
      kind_label: '策略',
      tone: 'teal',
      tags: ['图路由', '上下文窗口', '可追踪'],
      updated_at: now - 17 * 60 * 1000,
      size_label: '策略卡',
      action: 'metrics'
    },
    {
      id: 'citation-kit',
      title: '引用与证据包',
      summary: '维护引用、脚注与来源一致性，导出前建议先核验。',
      status: 'review',
      status_label: '待核验',
      kind_label: '引用',
      tone: 'gold',
      tags: ['引用', '脚注', '导出检查'],
      updated_at: now - 48 * 60 * 1000,
      size_label: '证据集',
      action: 'citation'
    },
    {
      id: 'version-archive',
      title: '版本归档',
      summary:
        input.versionGroupCount > 0
          ? `已记录 ${input.versionGroupCount} 组版本，可随时回退。`
          : '尚未创建版本，建议在关键阶段手动归档。',
      status: input.versionGroupCount > 0 ? 'synced' : 'draft',
      status_label: input.versionGroupCount > 0 ? '已同步' : '草稿',
      kind_label: '版本',
      tone: 'violet',
      tags: ['回滚', '对比', '里程碑'],
      updated_at: now - 2 * 60 * 60 * 1000,
      size_label: `${input.versionGroupCount} 组`,
      action: 'version'
    },
    {
      id: 'asset-upload',
      title: '上传新素材',
      summary: '支持图片、文档、模板上传，自动纳入资料库并可插入正文。',
      status: 'draft',
      status_label: '待上传',
      kind_label: '素材',
      tone: 'azure',
      tags: ['图片', '文档', '模板'],
      updated_at: now - 8 * 60 * 60 * 1000,
      size_label: '上传入口',
      action: 'upload'
    }
  ]
}

export function cardMatchesSearch(card: LibraryCard, query: string) {
  if (!query) return true
  const q = query.toLowerCase()
  const haystack = `${card.title} ${card.summary} ${card.tags.join(' ')}`.toLowerCase()
  return haystack.includes(q)
}
