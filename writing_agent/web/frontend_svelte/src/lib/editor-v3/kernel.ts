import { Editor, Extension, Node, mergeAttributes, type JSONContent } from '@tiptap/core'
import Color from '@tiptap/extension-color'
import FontFamily from '@tiptap/extension-font-family'
import Highlight from '@tiptap/extension-highlight'
import Subscript from '@tiptap/extension-subscript'
import Superscript from '@tiptap/extension-superscript'
import TextAlign from '@tiptap/extension-text-align'
import { TextStyle } from '@tiptap/extension-text-style'
import StarterKit from '@tiptap/starter-kit'
import { Fragment, Slice, type Node as ProseMirrorNode } from '@tiptap/pm/model'
import { NodeSelection, Plugin, PluginKey, TextSelection } from '@tiptap/pm/state'

import { resolvedStyleProperties, type DocumentV3, type InlineNode, type SectionV3, type StyleDefinition, type V3BlockNode } from './model'

const StableNodeAttributes = Extension.create({
  name: 'stableNodeAttributes',
  addGlobalAttributes() {
    return [
      {
        types: ['paragraph', 'heading', 'blockquote', 'codeBlock', 'bulletList', 'orderedList', 'listItem'],
        attributes: {
          nodeId: {
            default: null,
            parseHTML: (element) => element.getAttribute('data-node-id'),
            renderHTML: (attributes) => attributes.nodeId ? { 'data-node-id': attributes.nodeId } : {}
          },
          styleId: {
            default: null,
            parseHTML: (element) => element.getAttribute('data-style-id'),
            renderHTML: (attributes) => attributes.styleId ? { 'data-style-id': attributes.styleId } : {}
          },
          sectionId: {
            default: null,
            parseHTML: (element) => element.getAttribute('data-section-id'),
            renderHTML: (attributes) => attributes.sectionId ? { 'data-section-id': attributes.sectionId } : {}
          }
        }
      }
    ]
  }
})

const ParagraphFormatting = Extension.create({
  name: 'paragraphFormatting',
  addGlobalAttributes() {
    const attributes = {
      lineSpacing: {
        default: null,
        parseHTML: (element: HTMLElement) => element.style.lineHeight || null,
        renderHTML: (attrs: Record<string, unknown>) => attrs.lineSpacing ? { style: `line-height:${attrs.lineSpacing}` } : {}
      },
      firstLineIndentEm: {
        default: null,
        parseHTML: (element: HTMLElement) => Number.parseFloat(element.style.textIndent) || null,
        renderHTML: (attrs: Record<string, unknown>) => attrs.firstLineIndentEm !== null ? { style: `text-indent:${attrs.firstLineIndentEm}em` } : {}
      },
      leftIndentEm: {
        default: null,
        parseHTML: (element: HTMLElement) => Number.parseFloat(element.style.marginLeft) || null,
        renderHTML: (attrs: Record<string, unknown>) => attrs.leftIndentEm ? { style: `margin-left:${attrs.leftIndentEm}em` } : {}
      },
      rightIndentEm: {
        default: null,
        parseHTML: (element: HTMLElement) => Number.parseFloat(element.style.marginRight) || null,
        renderHTML: (attrs: Record<string, unknown>) => attrs.rightIndentEm ? { style: `margin-right:${attrs.rightIndentEm}em` } : {}
      },
      spaceBeforePt: {
        default: null,
        parseHTML: (element: HTMLElement) => Number.parseFloat(element.style.marginTop) || null,
        renderHTML: (attrs: Record<string, unknown>) => attrs.spaceBeforePt !== null ? { style: `margin-top:${attrs.spaceBeforePt}pt` } : {}
      },
      spaceAfterPt: {
        default: null,
        parseHTML: (element: HTMLElement) => Number.parseFloat(element.style.marginBottom) || null,
        renderHTML: (attrs: Record<string, unknown>) => attrs.spaceAfterPt !== null ? { style: `margin-bottom:${attrs.spaceAfterPt}pt` } : {}
      },
      keepWithNext: { default: null },
      keepLinesTogether: { default: null },
      pageBreakBefore: { default: null },
      borderColor: {
        default: null,
        parseHTML: (element: HTMLElement) => element.style.borderColor || null,
        renderHTML: (attrs: Record<string, unknown>) => attrs.borderColor ? { style: `border-color:${attrs.borderColor}` } : {}
      },
      borderWidthPt: {
        default: null,
        parseHTML: (element: HTMLElement) => Number.parseFloat(element.style.borderWidth) || null,
        renderHTML: (attrs: Record<string, unknown>) => attrs.borderWidthPt ? { style: `border-width:${attrs.borderWidthPt}pt` } : {}
      },
      borderStyle: {
        default: null,
        parseHTML: (element: HTMLElement) => element.style.borderStyle || null,
        renderHTML: (attrs: Record<string, unknown>) => attrs.borderStyle ? { style: `border-style:${attrs.borderStyle}` } : {}
      },
      shadingColor: {
        default: null,
        parseHTML: (element: HTMLElement) => element.style.backgroundColor || null,
        renderHTML: (attrs: Record<string, unknown>) => attrs.shadingColor ? { style: `background-color:${attrs.shadingColor}` } : {}
      },
      tabStops: { default: null }
    }
    return [{ types: ['paragraph', 'heading'], attributes }]
  }
})

const ReliableBlockIdentity = Extension.create({
  name: 'reliableBlockIdentity',
  addProseMirrorPlugins() {
    return [new Plugin({
      key: new PluginKey('reliableBlockIdentity'),
      appendTransaction(transactions, _oldState, newState) {
        if (!transactions.some((transaction) => transaction.docChanged)) return null
        const seen = new Set<string>()
        const transaction = newState.tr
        let changed = false
        newState.doc.descendants((node, position) => {
          if (!['paragraph', 'heading', 'blockquote', 'codeBlock', 'bulletList', 'orderedList', 'listItem'].includes(node.type.name)) return
          const attrs = { ...node.attrs }
          let nodeChanged = false
          const currentId = String(attrs.nodeId || '')
          if (!currentId || seen.has(currentId)) {
            attrs.nodeId = newNodeId(node.type.name)
            nodeChanged = true
          }
          seen.add(String(attrs.nodeId))
          if (node.type.name === 'paragraph' && /^heading-[1-6]$/.test(String(attrs.styleId || ''))) {
            attrs.styleId = 'normal'
            nodeChanged = true
          }
          if (node.type.name === 'heading') {
            const expectedStyle = `heading-${Number(attrs.level || 1)}`
            if (attrs.styleId !== expectedStyle) {
              attrs.styleId = expectedStyle
              nodeChanged = true
            }
          }
          if (nodeChanged) {
            changed = true
            transaction.setNodeMarkup(position, undefined, attrs)
          }
        })
        return changed ? transaction : null
      }
    })]
  }
})

const BLOCK_NODE_TYPES = new Set([
  'paragraph',
  'heading',
  'blockquote',
  'codeBlock',
  'bulletList',
  'orderedList',
  'listItem'
])

function currentSectionId(editorNode: ProseMirrorNode, position: number): string | null {
  const resolved = editorNode.resolve(Math.max(0, Math.min(position, editorNode.content.size)))
  for (let depth = resolved.depth; depth >= 0; depth -= 1) {
    const value = resolved.node(depth).attrs?.sectionId
    if (value) return String(value)
  }
  return null
}

function normalizePastedNode(node: ProseMirrorNode, sectionId: string | null): ProseMirrorNode {
  if (node.isText) return node
  const children: ProseMirrorNode[] = []
  node.content.forEach((child) => children.push(normalizePastedNode(child, sectionId)))
  let attrs: Record<string, unknown> = { ...node.attrs }
  if (BLOCK_NODE_TYPES.has(node.type.name)) {
    attrs = { ...attrs, nodeId: null, sectionId: sectionId || attrs.sectionId || null }
    if (node.type.name === 'paragraph') attrs.styleId = 'normal'
    if (node.type.name === 'heading') attrs.styleId = `heading-${Number(attrs.level || 1)}`
  }
  const content = Fragment.fromArray(children)
  return BLOCK_NODE_TYPES.has(node.type.name)
    ? node.type.create(attrs, content, node.marks)
    : node.copy(content)
}

const ReliableClipboard = Extension.create({
  name: 'reliableClipboard',
  addProseMirrorPlugins() {
    return [new Plugin({
      key: new PluginKey('reliableClipboard'),
      props: {
        transformPasted(slice, view) {
          const sectionId = currentSectionId(view.state.doc, view.state.selection.from)
          const content: ProseMirrorNode[] = []
          slice.content.forEach((node) => content.push(normalizePastedNode(node, sectionId)))
          return new Slice(Fragment.fromArray(content), slice.openStart, slice.openEnd)
        },
        transformPastedText(text) {
          return text.replace(/\r\n?/g, '\n').replace(/\u00a0/g, ' ')
        }
      }
    })]
  }
})

const ReliableBlockKeyboard = Extension.create({
  name: 'reliableBlockKeyboard',
  addProseMirrorPlugins() {
    return [new Plugin({
      key: new PluginKey('reliableBlockKeyboard'),
      props: {
        handleKeyDown(view, event) {
          const { selection, doc } = view.state
          if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.code === 'Space') {
            const position = selection.$from.depth > 0 ? selection.$from.before(1) : selection.from
            const node = doc.nodeAt(position)
            if (!node) return false
            event.preventDefault()
            view.dispatch(view.state.tr.setSelection(NodeSelection.create(doc, position)).scrollIntoView())
            return true
          }
          if (!(selection instanceof NodeSelection) || selection.$from.depth !== 0) return false
          if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
            const target = event.key === 'ArrowUp'
              ? doc.childBefore(selection.from)
              : doc.childAfter(selection.to)
            if (!target.node) return false
            const position = event.key === 'ArrowUp'
              ? selection.from - target.node.nodeSize
              : selection.to
            event.preventDefault()
            view.dispatch(view.state.tr.setSelection(NodeSelection.create(doc, position)).scrollIntoView())
            return true
          }
          if (event.key === 'Escape' || event.key === 'Enter' || event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
            const preferEnd = event.key === 'ArrowLeft'
            const node = selection.node
            const inside = preferEnd ? selection.to - 1 : selection.from + 1
            const position = node.isTextblock
              ? Math.max(selection.from + 1, Math.min(inside, selection.to - 1))
              : (preferEnd ? selection.from : selection.to)
            event.preventDefault()
            view.dispatch(view.state.tr.setSelection(TextSelection.near(doc.resolve(position), preferEnd ? -1 : 1)).scrollIntoView())
            return true
          }
          return false
        }
      }
    })]
  }
})

const FontSize = Extension.create({
  name: 'fontSize',
  addGlobalAttributes() {
    return [{
      types: ['textStyle'],
      attributes: {
        fontSize: {
          default: null,
          parseHTML: (element) => element.style.fontSize || null,
          renderHTML: (attributes) => attributes.fontSize ? { style: `font-size:${attributes.fontSize}` } : {}
        }
      }
    }]
  }
})

const CharacterFormatting = Extension.create({
  name: 'characterFormatting',
  addGlobalAttributes() {
    return [{
      types: ['textStyle'],
      attributes: {
        letterSpacing: {
          default: null,
          parseHTML: (element) => element.style.letterSpacing || null,
          renderHTML: (attributes) => attributes.letterSpacing ? { style: `letter-spacing:${attributes.letterSpacing}` } : {}
        },
        textTransform: {
          default: null,
          parseHTML: (element) => element.style.textTransform || null,
          renderHTML: (attributes) => attributes.textTransform ? { style: `text-transform:${attributes.textTransform}` } : {}
        }
      }
    }]
  }
})

function atomNode(name: 'figure' | 'table' | 'pageBreak' | 'equationBlock') {
  return Node.create({
    name,
    group: 'block',
    atom: true,
    selectable: true,
    addAttributes() {
      return {
        nodeId: { default: null },
        sectionId: { default: null },
        payload: { default: {} }
      }
    },
    parseHTML() {
      return [{ tag: `[data-v3-node="${name}"]` }]
    },
    renderHTML({ HTMLAttributes }) {
      const payload = HTMLAttributes.payload && typeof HTMLAttributes.payload === 'object' ? HTMLAttributes.payload : {}
      const caption = String((payload as Record<string, unknown>).caption || '')
      const label = name === 'pageBreak' ? '分页符' : name === 'table' ? '表格' : name === 'figure' ? '图片/图表' : '公式'
      const { payload: _payload, ...domAttributes } = HTMLAttributes
      return [
        'div',
        mergeAttributes(domAttributes, {
          'data-v3-node': name,
          'data-node-id': HTMLAttributes.nodeId || '',
          class: `v3-object v3-object-${name}`
        }),
        name === 'pageBreak' ? '分页符' : `${label}${caption ? ` · ${caption}` : ''}`
      ]
    }
  })
}

const FigureNode = atomNode('figure')
const TableNode = atomNode('table')
const PageBreakNode = atomNode('pageBreak')
const EquationBlockNode = atomNode('equationBlock')

function textNodes(content: Array<V3BlockNode | InlineNode> | undefined): JSONContent[] {
  if (!content) return []
  return content.flatMap((node) => {
    if (node.type === 'text') {
      return [{ type: 'text', text: node.text || '', marks: node.marks as JSONContent['marks'] }]
    }
    if (node.type === 'hardBreak') return [{ type: 'hardBreak' }]
    return []
  })
}

function blockToJson(block: V3BlockNode, sectionId: string): JSONContent[] {
  const attrs = { ...(block.attrs || {}), nodeId: block.id, styleId: block.styleId || null, sectionId }
  if (block.type === 'heading') {
    return [{ type: 'heading', attrs: { ...attrs, level: Number(block.attrs?.level || 1) }, content: textNodes(block.content) }]
  }
  if (block.type === 'blockquote') {
    return [{ type: 'blockquote', attrs, content: [{ type: 'paragraph', attrs, content: textNodes(block.content) }] }]
  }
  if (block.type === 'codeBlock') return [{ type: 'codeBlock', attrs, content: textNodes(block.content) }]
  if (block.type === 'horizontalRule') return [{ type: 'horizontalRule' }]
  if (block.type === 'figure') return [{ type: 'figure', attrs: { nodeId: block.id, sectionId, payload: block.attrs?.figure || block.attrs || {} } }]
  if (block.type === 'table') return [{ type: 'table', attrs: { nodeId: block.id, sectionId, payload: block.attrs?.table || block.attrs || {} } }]
  if (block.type === 'pageBreak') return [{ type: 'pageBreak', attrs: { nodeId: block.id, sectionId } }]
  if (block.type === 'equationBlock') return [{ type: 'equationBlock', attrs: { nodeId: block.id, sectionId, payload: block.attrs || {} } }]
  if (block.type === 'bulletList' || block.type === 'orderedList') {
    const items = (block.content || []).filter((item): item is V3BlockNode => 'id' in item)
    return [{
      type: block.type,
      attrs,
      content: items.map((item) => ({
        type: 'listItem',
        attrs: { nodeId: item.id, sectionId },
        content: (item.content || []).filter((child): child is V3BlockNode => 'id' in child).flatMap((child) => blockToJson(child, sectionId))
      }))
    }]
  }
  if (block.type !== 'paragraph') {
    return [{ type: 'paragraph', attrs, content: [{ type: 'text', text: `[暂未迁移的 ${block.type} 对象]` }] }]
  }
  return [{ type: 'paragraph', attrs, content: textNodes(block.content) }]
}

const newNodeId = (prefix: string) => `${prefix}_${crypto.randomUUID().replace(/-/g, '')}`

function inlineFromJson(nodes: JSONContent[] | undefined): InlineNode[] {
  return (nodes || []).flatMap((node) => {
    if (node.type === 'text') return [{ type: 'text', text: node.text || '', marks: (node.marks || []) as InlineNode['marks'] } as InlineNode]
    if (node.type === 'hardBreak') return [{ type: 'hardBreak' } as InlineNode]
    return []
  })
}

function blockFromJson(node: JSONContent): V3BlockNode | null {
  const attrs = (node.attrs || {}) as Record<string, unknown>
  const id = String(attrs.nodeId || newNodeId(node.type || 'block'))
  const styleId = String(attrs.styleId || (node.type === 'heading' ? `heading-${Number(attrs.level || 1)}` : 'normal'))
  const paragraphAttrs = { ...attrs }
  delete paragraphAttrs.nodeId
  delete paragraphAttrs.sectionId
  delete paragraphAttrs.styleId
  if (node.type === 'paragraph') return { id, type: 'paragraph', styleId, attrs: paragraphAttrs, content: inlineFromJson(node.content) }
  if (node.type === 'heading') return { id, type: 'heading', styleId, attrs: paragraphAttrs, content: inlineFromJson(node.content) }
  if (node.type === 'blockquote' || node.type === 'codeBlock') {
    return { id, type: node.type, styleId, attrs: paragraphAttrs, content: inlineFromJson(node.content?.[0]?.content || node.content) }
  }
  if (node.type === 'bulletList' || node.type === 'orderedList') {
    return {
      id,
      type: node.type,
      attrs: paragraphAttrs,
      content: (node.content || []).map((item) => ({
        id: String(item.attrs?.nodeId || newNodeId('listItem')),
        type: 'listItem',
        content: (item.content || []).map(blockFromJson).filter((child): child is V3BlockNode => Boolean(child))
      }))
    }
  }
  if (node.type === 'horizontalRule') return { id, type: 'horizontalRule' }
  if (node.type === 'figure') return { id, type: 'figure', attrs: { figure: attrs.payload || {} } }
  if (node.type === 'table') return { id, type: 'table', attrs: { table: attrs.payload || {} } }
  if (node.type === 'pageBreak') return { id, type: 'pageBreak' }
  if (node.type === 'equationBlock') return { id, type: 'equationBlock', attrs: (attrs.payload || {}) as Record<string, unknown> }
  return null
}

export function tiptapToDocumentV3(base: DocumentV3, json: JSONContent): DocumentV3 {
  const next = structuredClone(base)
  const sectionMap = new Map(next.sections.map((section) => [section.id, section]))
  for (const section of next.sections) section.content = []
  for (const node of json.content || []) {
    const sectionId = String(node.attrs?.sectionId || next.sections[0]?.id || '')
    let section = sectionMap.get(sectionId)
    if (!section) {
      section = {
        id: sectionId || newNodeId('section'),
        breakType: 'nextPage',
        layout: structuredClone(next.sections[0]?.layout),
        headerFooter: structuredClone(next.sections[0]?.headerFooter),
        content: []
      }
      next.sections.push(section)
      sectionMap.set(section.id, section)
    }
    const block = blockFromJson(node)
    if (block) section.content.push(block)
  }
  return next
}

export function documentV3ToText(doc: DocumentV3): string {
  const inlineText = (content: Array<V3BlockNode | InlineNode> | undefined): string =>
    (content || []).map((node) => {
      if ('text' in node && node.type === 'text') return node.text || ''
      if (!('id' in node) && node.type === 'hardBreak') return '\n'
      return 'id' in node ? inlineText(node.content) : ''
    }).join('')
  const lines: string[] = []
  for (const section of doc.sections) {
    for (const block of section.content) {
      const text = inlineText(block.content)
      if (!text.trim()) continue
      if (block.type === 'heading') lines.push(`${'#'.repeat(Math.max(1, Math.min(6, Number(block.attrs?.level || 1))))} ${text}`)
      else lines.push(text)
    }
  }
  return lines.join('\n\n')
}

export function documentV3ToTiptap(doc: DocumentV3): JSONContent {
  const json: JSONContent = {
    type: 'doc',
    content: doc.sections.flatMap((section) => section.content.flatMap((block) => blockToJson(block, section.id)))
  }
  const seen = new Set<string>()
  const normalize = (node: JSONContent) => {
    if (node.attrs?.nodeId) {
      const currentId = String(node.attrs.nodeId)
      if (seen.has(currentId)) node.attrs.nodeId = newNodeId(node.type || 'block')
      seen.add(String(node.attrs.nodeId))
    }
    if (node.type === 'paragraph' && /^heading-[1-6]$/.test(String(node.attrs?.styleId || ''))) {
      node.attrs = { ...(node.attrs || {}), styleId: 'normal' }
    }
    if (node.type === 'heading') {
      node.attrs = { ...(node.attrs || {}), styleId: `heading-${Number(node.attrs?.level || 1)}` }
    }
    for (const child of node.content || []) normalize(child)
  }
  normalize(json)
  return json
}

export function plainTextToTiptapContent(value: string): JSONContent[] {
  const normalized = value.replace(/\r\n?/g, '\n').replace(/\u00a0/g, ' ')
  return normalized.split(/\n{2,}/).map((paragraph) => {
    const content: JSONContent[] = []
    paragraph.split('\n').forEach((line, index) => {
      if (index) content.push({ type: 'hardBreak' })
      if (line) content.push({ type: 'text', text: line })
    })
    return { type: 'paragraph', attrs: { nodeId: null, styleId: 'normal' }, content }
  })
}

function cssForStyle(doc: DocumentV3, style: StyleDefinition): string {
  const p = resolvedStyleProperties(doc, style.id)
  return [
    p.fontFamily ? `font-family:${JSON.stringify(p.fontFamily)}` : '',
    p.fontSizePt ? `font-size:${p.fontSizePt}pt` : '',
    p.bold ? 'font-weight:700' : '',
    p.italic ? 'font-style:italic' : '',
    p.underline ? 'text-decoration:underline' : '',
    p.color ? `color:${p.color}` : '',
    p.backgroundColor ? `background-color:${p.backgroundColor}` : '',
    p.letterSpacingPt !== undefined ? `letter-spacing:${p.letterSpacingPt}pt` : '',
    p.textTransform ? `text-transform:${p.textTransform}` : '',
    p.alignment ? `text-align:${p.alignment}` : '',
    p.lineSpacing ? `line-height:${p.lineSpacing}` : '',
    p.firstLineIndentEm !== undefined ? `text-indent:${p.firstLineIndentEm}em` : '',
    p.leftIndentEm ? `margin-left:${p.leftIndentEm}em` : '',
    p.rightIndentEm ? `margin-right:${p.rightIndentEm}em` : '',
    p.spaceBeforePt !== undefined ? `margin-top:${p.spaceBeforePt}pt` : '',
    p.spaceAfterPt !== undefined ? `margin-bottom:${p.spaceAfterPt}pt` : '',
    p.borderColor ? `border-color:${p.borderColor}` : '',
    p.borderWidthPt !== undefined ? `border-width:${p.borderWidthPt}pt` : '',
    p.borderStyle ? `border-style:${p.borderStyle}` : '',
    p.shadingColor ? `background-color:${p.shadingColor}` : ''
  ].filter(Boolean).join(';')
}

export function styleSheetForDocument(doc: DocumentV3): string {
  return doc.styles.map((style) => `[data-style-id="${style.id}"]{${cssForStyle(doc, style)}}`).join('\n')
}

export function createEditorKernel(options: {
  element: HTMLElement
  document: DocumentV3
  editable?: boolean
  onUpdate?: (json: JSONContent) => void
  onSelectionUpdate?: (editor: Editor) => void
  onSlashQuery?: (query: string | null, position: number, editor: Editor) => void
}): Editor {
  const reportSlashQuery = (editor: Editor) => {
    const selection = editor.state.selection
    if (!selection.empty || !selection.$from.parent.isTextblock) {
      options.onSlashQuery?.(null, selection.from, editor)
      return
    }
    const prefix = selection.$from.parent.textBetween(0, selection.$from.parentOffset, '\n', '\n')
    const match = /^\/([^\s/]*)$/.exec(prefix)
    options.onSlashQuery?.(match ? match[1] : null, selection.from, editor)
  }
  return new Editor({
    element: options.element,
    editable: options.editable !== false,
    content: documentV3ToTiptap(options.document),
    extensions: [
      StarterKit.configure({ heading: { levels: [1, 2, 3, 4, 5, 6] } }),
      TextStyle,
      FontSize,
      CharacterFormatting,
      Color,
      FontFamily,
      Highlight.configure({ multicolor: true }),
      Subscript,
      Superscript,
      TextAlign.configure({ types: ['heading', 'paragraph'] }),
      StableNodeAttributes,
      ParagraphFormatting,
      ReliableBlockIdentity,
      ReliableClipboard,
      ReliableBlockKeyboard,
      FigureNode,
      TableNode,
      PageBreakNode,
      EquationBlockNode
    ],
    onUpdate: ({ editor }) => {
      options.onUpdate?.(editor.getJSON())
      reportSlashQuery(editor)
    },
    onSelectionUpdate: ({ editor }) => {
      options.onSelectionUpdate?.(editor)
      reportSlashQuery(editor)
    },
    onFocus: ({ editor }) => options.onSelectionUpdate?.(editor),
    onBlur: ({ editor }) => options.onSelectionUpdate?.(editor)
  })
}

export function selectedBlocks(editor: Editor): Array<{ id: string; type: string; text: string }> {
  const { from, to, empty, $from } = editor.state.selection
  const blocks: Array<{ id: string; type: string; text: string }> = []
  const seen = new Set<string>()
  const append = (node: ProseMirrorNode) => {
    const id = String(node.attrs?.nodeId || '')
    if (!id || seen.has(id) || !node.isTextblock) return
    seen.add(id)
    blocks.push({ id, type: node.type.name, text: node.textContent })
  }
  if (empty) {
    for (let depth = $from.depth; depth >= 0; depth -= 1) {
      const node = $from.node(depth)
      if (node.isTextblock && node.attrs?.nodeId) {
        append(node)
        break
      }
    }
    return blocks
  }
  editor.state.doc.nodesBetween(from, to, (node) => append(node))
  return blocks
}

export function findBlockById(editor: Editor, nodeId: string): { node: ProseMirrorNode; position: number } | null {
  let match: { node: ProseMirrorNode; position: number } | null = null
  editor.state.doc.descendants((node, position) => {
    if (!match && String(node.attrs?.nodeId || '') === nodeId) {
      match = { node, position }
      return false
    }
    return !match
  })
  return match
}

export function selectBlock(editor: Editor, nodeId: string, anchorNodeId = ''): boolean {
  const target = findBlockById(editor, nodeId)
  if (!target) return false
  let selection
  if (anchorNodeId && anchorNodeId !== nodeId) {
    const anchor = findBlockById(editor, anchorNodeId)
    if (anchor) {
      const start = anchor.position <= target.position ? anchor : target
      const end = anchor.position <= target.position ? target : anchor
      const from = Math.min(editor.state.doc.content.size, start.position + 1)
      const to = Math.min(editor.state.doc.content.size, end.position + end.node.nodeSize - 1)
      selection = TextSelection.create(editor.state.doc, from, to)
    }
  }
  selection ||= NodeSelection.create(editor.state.doc, target.position)
  editor.view.dispatch(editor.state.tr.setSelection(selection).scrollIntoView())
  editor.view.focus()
  return true
}

export function sectionForPosition(doc: DocumentV3, sectionId: string): SectionV3 | undefined {
  return doc.sections.find((section) => section.id === sectionId)
}
