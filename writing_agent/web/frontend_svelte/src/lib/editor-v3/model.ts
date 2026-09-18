export type JsonObject = Record<string, unknown>

export type StyleKind = 'paragraph' | 'character' | 'table'

export interface StyleProperties {
  fontFamily?: string
  fontSizePt?: number
  bold?: boolean
  italic?: boolean
  underline?: boolean
  color?: string
  backgroundColor?: string
  alignment?: 'left' | 'center' | 'right' | 'justify'
  lineSpacing?: number
  firstLineIndentEm?: number
  leftIndentEm?: number
  rightIndentEm?: number
  spaceBeforePt?: number
  spaceAfterPt?: number
  outlineLevel?: number
  keepWithNext?: boolean
  keepLinesTogether?: boolean
  pageBreakBefore?: boolean
}

export interface StyleDefinition {
  id: string
  name: string
  kind: StyleKind
  basedOn?: string
  nextStyle?: string
  visible: boolean
  properties: StyleProperties
}

export interface PageLayout {
  pageSize: 'A4' | 'A3' | 'Letter' | 'custom'
  widthMm?: number
  heightMm?: number
  orientation: 'portrait' | 'landscape'
  marginTopMm: number
  marginRightMm: number
  marginBottomMm: number
  marginLeftMm: number
  columns: number
}

export interface HeaderFooterDefinition {
  linkHeaderToPrevious: boolean
  linkFooterToPrevious: boolean
  differentFirstPage: boolean
  differentOddEven: boolean
  header: V3BlockNode[]
  footer: V3BlockNode[]
  firstPageHeader: V3BlockNode[]
  firstPageFooter: V3BlockNode[]
  evenPageHeader: V3BlockNode[]
  evenPageFooter: V3BlockNode[]
  pageNumber: {
    enabled: boolean
    format: 'arabic' | 'lowerRoman' | 'upperRoman' | 'lowerLetter' | 'upperLetter'
    startAt?: number
    position: 'header' | 'footer'
    alignment: 'left' | 'center' | 'right'
  }
}

export interface TextMark {
  type: 'bold' | 'italic' | 'underline' | 'strike' | 'subscript' | 'superscript' | 'textStyle' | 'link'
  attrs?: JsonObject
}

export interface InlineNode {
  type: 'text' | 'hardBreak' | 'field' | 'footnoteReference' | 'citation' | 'bookmark'
  text?: string
  marks?: TextMark[]
  attrs?: JsonObject
}

export interface V3BlockNode {
  id: string
  type:
    | 'paragraph'
    | 'heading'
    | 'bulletList'
    | 'orderedList'
    | 'listItem'
    | 'blockquote'
    | 'codeBlock'
    | 'table'
    | 'figure'
    | 'equationBlock'
    | 'horizontalRule'
    | 'pageBreak'
    | 'sectionBreak'
    | 'tableOfContents'
    | 'bibliography'
  styleId?: string
  attrs?: JsonObject
  content?: Array<V3BlockNode | InlineNode>
}

export interface SectionV3 {
  id: string
  breakType: 'nextPage' | 'continuous' | 'oddPage' | 'evenPage'
  layout: PageLayout
  headerFooter: HeaderFooterDefinition
  content: V3BlockNode[]
}

export interface DocumentV3 {
  schemaVersion: 3
  id: string
  title: string
  metadata: JsonObject
  styles: StyleDefinition[]
  numbering: JsonObject[]
  sections: SectionV3[]
  notes: JsonObject
  citations: JsonObject
  comments: JsonObject[]
  revisions: JsonObject[]
  resources: JsonObject
}

const makeId = (prefix: string) => `${prefix}_${crypto.randomUUID().replace(/-/g, '')}`

export const DEFAULT_PAGE_LAYOUT: PageLayout = {
  pageSize: 'A4',
  orientation: 'portrait',
  marginTopMm: 25.4,
  marginRightMm: 25.4,
  marginBottomMm: 25.4,
  marginLeftMm: 31.8,
  columns: 1
}

export function createDefaultHeaderFooter(): HeaderFooterDefinition {
  return {
    linkHeaderToPrevious: true,
    linkFooterToPrevious: true,
    differentFirstPage: false,
    differentOddEven: false,
    header: [],
    footer: [],
    firstPageHeader: [],
    firstPageFooter: [],
    evenPageHeader: [],
    evenPageFooter: [],
    pageNumber: {
      enabled: true,
      format: 'arabic',
      position: 'footer',
      alignment: 'center'
    }
  }
}

export const DEFAULT_STYLES: StyleDefinition[] = [
  {
    id: 'normal',
    name: '正文',
    kind: 'paragraph',
    nextStyle: 'normal',
    visible: true,
    properties: {
      fontFamily: 'SimSun',
      fontSizePt: 12,
      alignment: 'justify',
      lineSpacing: 1.5,
      firstLineIndentEm: 2,
      spaceAfterPt: 0
    }
  },
  {
    id: 'title',
    name: '文档标题',
    kind: 'paragraph',
    basedOn: 'normal',
    nextStyle: 'normal',
    visible: true,
    properties: {
      fontFamily: 'SimHei',
      fontSizePt: 22,
      bold: true,
      alignment: 'center',
      firstLineIndentEm: 0,
      spaceBeforePt: 12,
      spaceAfterPt: 18,
      outlineLevel: 0
    }
  },
  ...[1, 2, 3, 4, 5, 6].map<StyleDefinition>((level) => ({
    id: `heading-${level}`,
    name: `标题 ${level}`,
    kind: 'paragraph',
    basedOn: 'normal',
    nextStyle: 'normal',
    visible: true,
    properties: {
      fontFamily: level <= 2 ? 'SimHei' : 'SimSun',
      fontSizePt: Math.max(12, 18 - (level - 1) * 1.5),
      bold: true,
      alignment: 'left',
      firstLineIndentEm: 0,
      spaceBeforePt: Math.max(6, 14 - level),
      spaceAfterPt: Math.max(4, 9 - level),
      outlineLevel: level,
      keepWithNext: true,
      pageBreakBefore: level === 1
    }
  })),
  {
    id: 'quote',
    name: '引用',
    kind: 'paragraph',
    basedOn: 'normal',
    nextStyle: 'normal',
    visible: true,
    properties: { leftIndentEm: 2, rightIndentEm: 2, firstLineIndentEm: 0, italic: true }
  },
  {
    id: 'caption',
    name: '题注',
    kind: 'paragraph',
    basedOn: 'normal',
    nextStyle: 'normal',
    visible: true,
    properties: { fontSizePt: 10.5, alignment: 'center', firstLineIndentEm: 0, keepWithNext: true }
  }
]

export function createDocumentV3(title = '未命名文档'): DocumentV3 {
  return {
    schemaVersion: 3,
    id: makeId('doc'),
    title,
    metadata: {},
    styles: structuredClone(DEFAULT_STYLES),
    numbering: [],
    sections: [
      {
        id: makeId('section'),
        breakType: 'nextPage',
        layout: { ...DEFAULT_PAGE_LAYOUT },
        headerFooter: createDefaultHeaderFooter(),
        content: [
          {
            id: makeId('paragraph'),
            type: 'paragraph',
            styleId: 'normal',
            content: []
          }
        ]
      }
    ],
    notes: {},
    citations: {},
    comments: [],
    revisions: [],
    resources: {}
  }
}

export function isDocumentV3(value: unknown): value is DocumentV3 {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<DocumentV3>
  return candidate.schemaVersion === 3 && Array.isArray(candidate.styles) && Array.isArray(candidate.sections)
}

function textContent(text: unknown): InlineNode[] {
  const value = String(text ?? '')
  return value ? [{ type: 'text', text: value }] : []
}

function legacyBlockToV3(raw: JsonObject): V3BlockNode {
  const type = String(raw.type || 'paragraph').toLowerCase()
  const id = String(raw.id || makeId('block'))
  const style = raw.style && typeof raw.style === 'object' ? (raw.style as JsonObject) : {}
  if (type === 'heading') {
    const level = Math.max(1, Math.min(6, Number(raw.level || 1)))
    return { id, type: 'heading', styleId: `heading-${level}`, attrs: { level, directFormatting: style }, content: textContent(raw.text) }
  }
  if (type === 'list') {
    const items = Array.isArray(raw.items) ? raw.items : []
    return {
      id,
      type: raw.ordered ? 'orderedList' : 'bulletList',
      attrs: { directFormatting: style },
      content: items.map((item) => ({
        id: makeId('listItem'),
        type: 'listItem',
        content: [{ id: makeId('paragraph'), type: 'paragraph', styleId: 'normal', content: textContent(item) }]
      }))
    }
  }
  if (type === 'table') return { id, type: 'table', attrs: { table: raw.table || {}, directFormatting: style } }
  if (type === 'figure') return { id, type: 'figure', attrs: { figure: raw.figure || {}, directFormatting: style } }
  if (type === 'page_break') return { id, type: 'pageBreak' }
  return { id, type: 'paragraph', styleId: 'normal', attrs: { directFormatting: style }, content: textContent(raw.text) }
}

export function migrateLegacyDocIr(value: unknown): DocumentV3 {
  if (isDocumentV3(value)) return structuredClone(value)
  const legacy = value && typeof value === 'object' ? (value as JsonObject) : {}
  const doc = createDocumentV3(String(legacy.title || '未命名文档'))
  const sections = Array.isArray(legacy.sections) ? legacy.sections : []
  const content: V3BlockNode[] = []

  const walk = (items: unknown[]) => {
    for (const item of items) {
      if (!item || typeof item !== 'object') continue
      const section = item as JsonObject
      const title = String(section.title || '').trim()
      if (title) {
        const level = Math.max(1, Math.min(6, Number(section.level || 1)))
        content.push({
          id: String(section.id || makeId('heading')),
          type: 'heading',
          styleId: `heading-${level}`,
          attrs: { level, legacySection: true, directFormatting: section.style || {} },
          content: textContent(title)
        })
      }
      const blocks = Array.isArray(section.blocks) ? section.blocks : []
      for (const block of blocks) {
        if (block && typeof block === 'object') content.push(legacyBlockToV3(block as JsonObject))
      }
      if (Array.isArray(section.children)) walk(section.children)
    }
  }

  walk(sections)
  if (content.length) doc.sections[0].content = content
  doc.metadata = { ...doc.metadata, migratedFrom: 'DocIR-v2' }
  return doc
}

export function styleById(doc: DocumentV3, styleId: string): StyleDefinition | undefined {
  return doc.styles.find((style) => style.id === styleId)
}
