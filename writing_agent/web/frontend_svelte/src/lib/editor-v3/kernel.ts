import { Editor, Extension, Mark, Node, mergeAttributes, type JSONContent } from '@tiptap/core'
import Color from '@tiptap/extension-color'
import FontFamily from '@tiptap/extension-font-family'
import Highlight from '@tiptap/extension-highlight'
import Subscript from '@tiptap/extension-subscript'
import Superscript from '@tiptap/extension-superscript'
import TextAlign from '@tiptap/extension-text-align'
import { TextStyle } from '@tiptap/extension-text-style'
import { Table, TableCell, TableHeader, TableRow, TableView } from '@tiptap/extension-table'
import StarterKit from '@tiptap/starter-kit'
import { Fragment, Slice, type Node as ProseMirrorNode } from '@tiptap/pm/model'
import { NodeSelection, Plugin, PluginKey, TextSelection } from '@tiptap/pm/state'
import { Decoration, DecorationSet, type EditorView } from '@tiptap/pm/view'

import { cloneJson, resolvedStyleProperties, type DocumentV3, type InlineNode, type SectionV3, type StyleDefinition, type V3BlockNode } from './model'
import type { DocumentLayout, LayoutPage } from '../engine/documentEngine'

const paginationPluginKey = new PluginKey<DecorationSet>('rustPagination')
const focusBlockPluginKey = new PluginKey<DecorationSet>('focusBlock')

function makePageRegionInteractive(element: HTMLElement, page: LayoutPage, region: 'header' | 'footer') {
  element.dataset.pageRegion = region
  element.dataset.sectionId = page.sectionId || ''
  element.title = `双击编辑${region === 'header' ? '页眉' : '页脚'}`
  element.addEventListener('dblclick', (event) => {
    event.preventDefault()
    event.stopPropagation()
    window.dispatchEvent(new CustomEvent('wa-edit-page-region', { detail: { region, sectionId: page.sectionId || '', pageNumber: page.pageNumber } }))
  })
}

function pageBoundary(page: LayoutPage, pageCount: number, nextPage?: LayoutPage, final = false) {
  const element = document.createElement('span')
  element.className = final ? 'wa-page-end' : 'wa-page-boundary'
  element.contentEditable = 'false'
  element.dataset.pageNumber = String(page.pageNumber)
  element.setAttribute('aria-label', final ? `第 ${page.pageNumber} 页结束` : `第 ${page.pageNumber + 1} 页开始`)
  if (page.footerText) {
    const footerText = document.createElement('span')
    footerText.className = 'wa-page-footer-text'
    footerText.textContent = page.footerText
    makePageRegionInteractive(footerText, page, 'footer')
    element.appendChild(footerText)
  }
  const footer = document.createElement('span')
  footer.className = 'wa-page-number'
  footer.style.textAlign = page.pageNumberAlignment || 'center'
  footer.textContent = page.pageNumberText ? `第 ${page.pageNumberText} 页，共 ${pageCount} 页` : ''
  makePageRegionInteractive(footer, page, page.pageNumberPosition === 'header' ? 'header' : 'footer')
  element.appendChild(footer)
  if (nextPage?.headerText) {
    const headerText = document.createElement('span')
    headerText.className = 'wa-page-header-text'
    headerText.textContent = nextPage.headerText
    makePageRegionInteractive(headerText, nextPage, 'header')
    element.appendChild(headerText)
  }
  return element
}

const RustPagination = Extension.create({
  name: 'rustPagination',
  addProseMirrorPlugins() {
    return [new Plugin<DecorationSet>({
      key: paginationPluginKey,
      state: {
        init: (_, state) => DecorationSet.empty,
        apply(transaction, previous, _oldState, newState) {
          const layout = transaction.getMeta(paginationPluginKey) as DocumentLayout | null | undefined
          if (layout === undefined) return transaction.docChanged ? previous.map(transaction.mapping, transaction.doc) : previous
          if (!layout?.pages?.length) return DecorationSet.empty
          const positions = new Map<string, { position: number; size: number }>()
          newState.doc.forEach((node, position) => {
            const id = String(node.attrs?.nodeId || '')
            if (id) positions.set(id, { position, size: node.nodeSize })
          })
          const decorations: Decoration[] = []
          const firstPage = layout.pages[0]!
          if (firstPage?.headerText) {
            decorations.push(Decoration.widget(0, () => {
              const header = document.createElement('div')
              header.className = 'wa-first-page-header'
              header.contentEditable = 'false'
              header.textContent = firstPage.headerText || ''
              makePageRegionInteractive(header, firstPage, 'header')
              return header
            }, { side: -1, key: 'page-first-header' }))
          }
          for (const page of layout.pages) {
            const first = page.blocks[0]
            const target = first ? positions.get(first.blockId) : null
            if (target && first.startOffset === 0) {
              decorations.push(Decoration.node(target.position, target.position + target.size, {
                'data-layout-page': String(page.pageNumber)
              }))
            }
            if (target && page.pageNumber > 1) {
              const pagePosition = first.startOffset > 0
                ? Math.min(target.position + target.size - 1, target.position + 1 + first.startOffset)
                : target.position
              decorations.push(Decoration.widget(
                pagePosition,
                () => pageBoundary(layout.pages[page.pageNumber - 2] || page, layout.pageCount, page),
                { side: -1, key: `page-${layout.layoutVersion}-${page.pageNumber}` }
              ))
            }
          }
          decorations.push(Decoration.widget(
            newState.doc.content.size,
            () => pageBoundary(layout.pages[layout.pages.length - 1] || firstPage, layout.pageCount, undefined, true),
            { side: 1, key: `page-final-${layout.layoutVersion}` }
          ))
          return DecorationSet.create(newState.doc, decorations)
        }
      },
      props: {
        decorations(state) {
          return paginationPluginKey.getState(state) || DecorationSet.empty
        }
      }
    })]
  }
})

const FocusBlockDecoration = Extension.create({
  name: 'focusBlockDecoration',
  addProseMirrorPlugins() {
    return [new Plugin<DecorationSet>({
      key: focusBlockPluginKey,
      state: {
        init: () => DecorationSet.empty,
        apply(transaction, previous, _oldState, newState) {
          const blockId = transaction.getMeta(focusBlockPluginKey) as string | null | undefined
          if (blockId === undefined) {
            return transaction.docChanged ? previous.map(transaction.mapping, transaction.doc) : previous
          }
          if (!blockId) return DecorationSet.empty
          let decoration: Decoration | null = null
          newState.doc.forEach((node, position) => {
            if (!decoration && String(node.attrs?.nodeId || '') === blockId) {
              decoration = Decoration.node(position, position + node.nodeSize, {
                class: 'wa-focus-active',
                'data-focus-active': 'true'
              })
            }
          })
          return decoration ? DecorationSet.create(newState.doc, [decoration]) : DecorationSet.empty
        }
      },
      props: {
        decorations(state) {
          return focusBlockPluginKey.getState(state) || DecorationSet.empty
        }
      }
    })]
  }
})

export function applyFocusBlock(editor: Editor, blockId: string | null) {
  editor.view.dispatch(editor.state.tr.setMeta(focusBlockPluginKey, blockId))
}

export function applyPaginationLayout(editor: Editor, layout: DocumentLayout | null) {
  editor.view.dispatch(editor.state.tr.setMeta(paginationPluginKey, layout))
}

const StableNodeAttributes = Extension.create({
  name: 'stableNodeAttributes',
  addGlobalAttributes() {
    return [
      {
        types: ['paragraph', 'heading', 'blockquote', 'codeBlock', 'bulletList', 'orderedList', 'listItem', 'table'],
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
          },
          collapsed: {
            default: false,
            parseHTML: (element) => element.getAttribute('data-collapsed') === 'true',
            renderHTML: (attributes) => attributes.collapsed ? { 'data-collapsed': 'true' } : {}
          }
        }
      },
      {
        types: ['table'],
        attributes: {
          caption: {
            default: '',
            parseHTML: (element) => element.getAttribute('data-caption') || '',
            renderHTML: (attributes) => attributes.caption ? { 'data-caption': attributes.caption } : {}
          },
          repeatHeader: {
            default: false,
            parseHTML: (element) => element.getAttribute('data-repeat-header') === 'true',
            renderHTML: (attributes) => attributes.repeatHeader ? { 'data-repeat-header': 'true' } : {}
          },
          tableAlignment: {
            default: 'left',
            parseHTML: (element) => element.getAttribute('data-table-alignment') || 'left',
            renderHTML: (attributes) => ({
              'data-table-alignment': attributes.tableAlignment || 'left',
              style: attributes.tableAlignment === 'center'
                ? 'margin-left:auto;margin-right:auto'
                : attributes.tableAlignment === 'right'
                  ? 'margin-left:auto;margin-right:0'
                  : 'margin-left:0;margin-right:auto'
            })
          },
          widthPercent: {
            default: 100,
            parseHTML: (element) => Number(element.getAttribute('data-width-percent') || 100),
            renderHTML: (attributes) => {
              const width = Math.max(20, Math.min(100, Number(attributes.widthPercent || 100)))
              return { 'data-width-percent': String(width), style: `width:${width}%` }
            }
          }
        }
      },
      {
        types: ['bulletList', 'orderedList'],
        attributes: {
          numberingId: {
            default: null,
            parseHTML: (element) => element.getAttribute('data-numbering-id'),
            renderHTML: (attributes) => attributes.numberingId ? { 'data-numbering-id': attributes.numberingId } : {}
          },
          numberingLevel: {
            default: 0,
            parseHTML: (element) => Number(element.getAttribute('data-numbering-level') || 0),
            renderHTML: (attributes) => ({ 'data-numbering-level': String(Math.max(0, Math.min(8, Number(attributes.numberingLevel || 0)))) })
          },
          restartNumbering: {
            default: false,
            parseHTML: (element) => element.getAttribute('data-restart-numbering') === 'true',
            renderHTML: (attributes) => attributes.restartNumbering ? { 'data-restart-numbering': 'true' } : {}
          }
        }
      }
    ]
  }
})

const tableCellStyleAttributes = {
  backgroundColor: {
    default: null,
    parseHTML: (element: HTMLElement) => element.style.backgroundColor || null,
    renderHTML: (attributes: Record<string, unknown>) => attributes.backgroundColor
      ? { style: `background-color:${attributes.backgroundColor}` }
      : {}
  },
  verticalAlign: {
    default: null,
    parseHTML: (element: HTMLElement) => element.style.verticalAlign || null,
    renderHTML: (attributes: Record<string, unknown>) => attributes.verticalAlign
      ? { style: `vertical-align:${attributes.verticalAlign}` }
      : {}
  },
  borderColor: {
    default: null,
    parseHTML: (element: HTMLElement) => element.style.borderColor || null,
    renderHTML: (attributes: Record<string, unknown>) => attributes.borderColor ? { style: `border-color:${attributes.borderColor}` } : {}
  },
  borderWidthPt: {
    default: null,
    parseHTML: (element: HTMLElement) => Number.parseFloat(element.style.borderWidth) || null,
    renderHTML: (attributes: Record<string, unknown>) => attributes.borderWidthPt ? { style: `border-width:${attributes.borderWidthPt}pt;border-style:solid` } : {}
  }
}

const StyledTableCell = TableCell.extend({
  addAttributes() {
    return { ...(this.parent?.() || {}), ...tableCellStyleAttributes }
  }
})

const StyledTableHeader = TableHeader.extend({
  addAttributes() {
    return { ...(this.parent?.() || {}), ...tableCellStyleAttributes }
  }
})

const SizedTableRow = TableRow.extend({
  addAttributes() {
    return {
      ...(this.parent?.() || {}),
      heightPx: {
        default: null,
        parseHTML: (element: HTMLElement) => Number.parseFloat(element.style.height) || null,
        renderHTML: (attributes: Record<string, unknown>) => attributes.heightPx
          ? { style: `height:${attributes.heightPx}px` }
          : {}
      }
    }
  }
})

class DocumentTableView extends TableView {
  constructor(node: ProseMirrorNode, cellMinWidth: number, view?: EditorView, HTMLAttributes: Record<string, unknown> = {}) {
    super(node, cellMinWidth, view, HTMLAttributes)
    this.applyDocumentAttributes(node)
  }

  update(node: ProseMirrorNode): boolean {
    const updated = super.update(node)
    if (updated) this.applyDocumentAttributes(node)
    return updated
  }

  private applyDocumentAttributes(node: ProseMirrorNode) {
    const alignment = ['left', 'center', 'right'].includes(String(node.attrs.tableAlignment))
      ? String(node.attrs.tableAlignment)
      : 'left'
    const width = Math.max(20, Math.min(100, Number(node.attrs.widthPercent || 100)))
    this.table.dataset.caption = String(node.attrs.caption || '')
    this.table.dataset.repeatHeader = node.attrs.repeatHeader ? 'true' : 'false'
    this.table.dataset.tableAlignment = alignment
    this.table.dataset.widthPercent = String(width)
    this.table.style.width = `${width}%`
    this.table.style.minWidth = ''
    this.table.style.marginLeft = alignment === 'left' ? '0' : 'auto'
    this.table.style.marginRight = alignment === 'right' ? '0' : 'auto'
  }
}

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
      tabStops: {
        default: null,
        renderHTML: (attrs: Record<string, unknown>) => {
          const stops = Array.isArray(attrs.tabStops) ? attrs.tabStops : []
          const size = Number((stops[0] as Record<string, unknown> | undefined)?.positionEm || 8)
          return { style: `tab-size:${Math.max(1, Math.min(32, size))}` }
        }
      }
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
          if (!['paragraph', 'heading', 'blockquote', 'codeBlock', 'bulletList', 'orderedList', 'listItem', 'table'].includes(node.type.name)) return
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

const ReliableBlockKeyboard = Extension.create<{
  onCommand?: (type: string, params?: Record<string, unknown>) => boolean
}>({
  name: 'reliableBlockKeyboard',
  priority: 1000,
  addOptions() {
    return { onCommand: undefined }
  },
  addProseMirrorPlugins() {
    const onCommand = this.options.onCommand
    type RecentMarkdownRule = { from: number; to: number; raw: string; blockType: string } | null
    const markdownRuleKey = new PluginKey<RecentMarkdownRule>('reliableMarkdownRuleUndo')
    return [new Plugin({
      key: markdownRuleKey,
      state: {
        init: () => null,
        apply(transaction, recent, oldState, newState): RecentMarkdownRule {
          if (!transaction.docChanged) return recent
          const oldParent = oldState.selection.$from.parent
          const oldText = oldParent.isTextblock ? oldParent.textContent : ''
          const marker = /^(#{1,6}|[-+*]|\d+[.)]|>|```)$/.exec(oldText)
          const $cursor = newState.selection.$from
          const topDepth = Math.min(1, $cursor.depth)
          const topNode = $cursor.node(topDepth)
          const topFrom = topDepth ? $cursor.before(topDepth) : 0
          const converted = Boolean(marker) && (
            topNode.type.name === 'heading' ||
            topNode.type.name === 'bulletList' ||
            topNode.type.name === 'orderedList' ||
            topNode.type.name === 'blockquote' ||
            topNode.type.name === 'codeBlock'
          )
          if (converted) return { from: topFrom, to: topFrom + topNode.nodeSize, raw: `${marker?.[1]} `, blockType: topNode.type.name }
          if (recent && topFrom === recent.from && topNode.type.name === recent.blockType && !topNode.textContent) {
            return { ...recent, to: topFrom + topNode.nodeSize }
          }
          return null
        }
      },
      props: {
        handleKeyDown(view, event) {
          const { selection, doc } = view.state
          if (event.isComposing || event.keyCode === 229) return false
          if ((event.ctrlKey || event.metaKey) && !event.altKey && !event.shiftKey && event.key.toLocaleLowerCase() === 'z') {
            const recent = markdownRuleKey.getState(view.state)
            if (recent) {
              const applied = onCommand?.('restore_markdown_trigger', recent) || false
              if (applied) event.preventDefault()
              return applied
            }
          }
          if (event.altKey && event.shiftKey && !event.ctrlKey && !event.metaKey && (event.key === 'ArrowUp' || event.key === 'ArrowDown')) {
            const applied = onCommand?.(event.key === 'ArrowUp' ? 'move_block_up' : 'move_block_down') || false
            if (applied) event.preventDefault()
            return applied
          }
          if ((event.ctrlKey || event.metaKey) && event.altKey && !event.shiftKey && /^[0-3]$/.test(event.key)) {
            const styleId = event.key === '0' ? 'normal' : `heading-${event.key}`
            const applied = onCommand?.('apply_style', { styleId }) || false
            if (applied) event.preventDefault()
            return applied
          }
          const ancestorNames = Array.from({ length: selection.$from.depth }, (_, index) => selection.$from.node(index + 1).type.name)
          if (event.key === 'Tab' && !event.ctrlKey && !event.metaKey && !event.altKey && !ancestorNames.some((name) => name === 'tableCell' || name === 'tableHeader')) {
            const inList = ancestorNames.includes('listItem')
            if (inList) {
              const applied = onCommand?.(event.shiftKey ? 'list_outdent' : 'list_indent') || false
              if (applied) event.preventDefault()
              return applied
            }
            event.preventDefault()
            view.dispatch(view.state.tr.insertText('\t').scrollIntoView())
            return true
          }
          if (event.key === 'Enter' && !event.shiftKey && !event.altKey && !event.ctrlKey && !event.metaKey && selection.empty && selection.$from.parent.isTextblock) {
            const styleId = String(selection.$from.parent.attrs?.styleId || '')
            const applied = styleId ? onCommand?.('split_with_next_style', { styleId }) || false : false
            if (applied) event.preventDefault()
            if (applied) return true
          }
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
        },
        fontWeight: {
          default: null,
          parseHTML: (element) => element.style.fontWeight || null,
          renderHTML: (attributes) => attributes.fontWeight ? { style: `font-weight:${attributes.fontWeight}` } : {}
        },
        fontStyle: {
          default: null,
          parseHTML: (element) => element.style.fontStyle || null,
          renderHTML: (attributes) => attributes.fontStyle ? { style: `font-style:${attributes.fontStyle}` } : {}
        },
        fontVariant: {
          default: null,
          parseHTML: (element) => element.style.fontVariant || null,
          renderHTML: (attributes) => attributes.fontVariant ? { style: `font-variant:${attributes.fontVariant}` } : {}
        },
        textShadow: {
          default: null,
          parseHTML: (element) => element.style.textShadow || null,
          renderHTML: (attributes) => attributes.textShadow ? { style: `text-shadow:${attributes.textShadow}` } : {}
        }
      }
    }]
  }
})

const LinkMark = Mark.create({
  name: 'link',
  inclusive: false,
  addAttributes() {
    return {
      href: { default: '' },
      title: { default: null },
      target: { default: '_blank' }
    }
  },
  parseHTML() {
    return [{ tag: 'a[href]' }]
  },
  renderHTML({ HTMLAttributes }) {
    const href = String(HTMLAttributes.href || '').trim()
    return ['a', mergeAttributes(HTMLAttributes, {
      href,
      rel: 'noopener noreferrer',
      target: HTMLAttributes.target || '_blank'
    }), 0]
  }
})

function inlineObjectNode(name: 'footnoteReference' | 'endnoteReference' | 'citationReference' | 'inlineEquation' | 'crossReference') {
  return Node.create({
    name,
    group: 'inline',
    inline: true,
    atom: true,
    selectable: true,
    addAttributes() {
      return { payload: { default: {} } }
    },
    parseHTML() {
      return [{ tag: `[data-v3-inline="${name}"]` }]
    },
    renderHTML({ HTMLAttributes }) {
      const payload = HTMLAttributes.payload && typeof HTMLAttributes.payload === 'object'
        ? HTMLAttributes.payload as Record<string, unknown>
        : {}
      const label = name === 'inlineEquation'
        ? String(payload.latex || '公式')
        : name === 'footnoteReference' || name === 'endnoteReference'
          ? String(payload.label || payload.number || '注')
          : String(payload.label || payload.targetText || '引用')
      const { payload: _payload, ...domAttributes } = HTMLAttributes
      return [name === 'inlineEquation' ? 'span' : 'sup', mergeAttributes(domAttributes, {
        'data-v3-inline': name,
        class: `v3-inline-object v3-inline-${name}`,
        title: String(payload.title || payload.text || label)
      }), name === 'inlineEquation' ? `$${label}$` : `[${label}]`]
    }
  })
}

function atomNode(name: 'figure' | 'pageBreak' | 'sectionBreak' | 'equationBlock' | 'tableOfContents' | 'bibliography') {
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
      const caption = String((payload as Record<string, unknown>).displayCaption || (payload as Record<string, unknown>).caption || '')
      const label = name === 'pageBreak' ? '分页符' : name === 'sectionBreak' ? '分节符' : name === 'figure' ? '图片/图表' : name === 'tableOfContents' ? '自动目录' : name === 'bibliography' ? '参考文献' : '公式'
      const { payload: _payload, ...domAttributes } = HTMLAttributes
      const attributes = mergeAttributes(domAttributes, {
        'data-v3-node': name,
        'data-node-id': HTMLAttributes.nodeId || '',
        class: `v3-object v3-object-${name}`
      })
      if (name === 'tableOfContents') {
        const entries = Array.isArray((payload as Record<string, unknown>).entries)
          ? (payload as Record<string, unknown>).entries as Array<Record<string, unknown>>
          : []
        return ['div', attributes,
          ['strong', { class: 'v3-toc-title' }, '目录'],
          ['div', { class: 'v3-toc-entries' }, ...entries.map((entry) => [
            'div',
            { class: 'v3-toc-entry', 'data-level': String(entry.level || 1) },
            ['span', {}, String(entry.text || '未命名标题')],
            ['span', { class: 'v3-toc-leader' }, ''],
            ['span', { class: 'v3-toc-page' }, '自动']
          ])]
        ]
      }
      if (name === 'bibliography') {
        const entries = Array.isArray((payload as Record<string, unknown>).entries)
          ? (payload as Record<string, unknown>).entries as Array<Record<string, unknown>>
          : []
        return ['section', attributes,
          ['strong', { class: 'v3-bibliography-title' }, '参考文献'],
          ['ol', { class: 'v3-bibliography-entries' }, ...entries.map((entry) => ['li', { 'data-citation-id': String(entry.id || '') }, String(entry.text || entry.label || entry.id || '')])]
        ]
      }
      if (name === 'figure') {
        const source = String((payload as Record<string, unknown>).src || (payload as Record<string, unknown>).url || '')
        const widthPercent = Math.max(10, Math.min(100, Number((payload as Record<string, unknown>).widthPercent || 100)))
        const alignment = ['left', 'center', 'right'].includes(String((payload as Record<string, unknown>).alignment))
          ? String((payload as Record<string, unknown>).alignment)
          : 'center'
        const figureAttributes = mergeAttributes(attributes, {
          'data-wrap': String((payload as Record<string, unknown>).wrap || 'inline'),
          'data-alignment': alignment,
          'data-crop': String((payload as Record<string, unknown>).crop || 'none'),
          style: `width:${widthPercent}%;margin-left:${alignment === 'left' ? '0' : 'auto'};margin-right:${alignment === 'right' ? '0' : 'auto'}`
        })
        return ['figure', figureAttributes,
          ...(source ? [['img', { src: source, alt: String((payload as Record<string, unknown>).alt || caption || '文档图片') }]] : [['div', { class: 'v3-figure-placeholder' }, '图片/图表源数据已保留']]),
          ...(caption ? [['figcaption', {}, caption]] : [])
        ]
      }
      if (name === 'equationBlock') {
        const latex = String((payload as Record<string, unknown>).latex || (payload as Record<string, unknown>).source || '')
        return ['div', attributes, latex ? `$$${latex}$$` : '公式']
      }
      return [
        'div',
        attributes,
        name === 'pageBreak' ? '分页符' : name === 'sectionBreak' ? `分节符 · ${String((payload as Record<string, unknown>).breakType || 'nextPage')}` : `${label}${caption ? ` · ${caption}` : ''}`
      ]
    }
  })
}

const FigureNode = atomNode('figure')
const PageBreakNode = atomNode('pageBreak')
const SectionBreakNode = atomNode('sectionBreak')
const EquationBlockNode = atomNode('equationBlock')
const TableOfContentsNode = atomNode('tableOfContents')
const BibliographyNode = atomNode('bibliography')
const FootnoteReferenceNode = inlineObjectNode('footnoteReference')
const EndnoteReferenceNode = inlineObjectNode('endnoteReference')
const CitationReferenceNode = inlineObjectNode('citationReference')
const InlineEquationNode = inlineObjectNode('inlineEquation')
const CrossReferenceNode = inlineObjectNode('crossReference')

function textNodes(content: Array<V3BlockNode | InlineNode> | undefined): JSONContent[] {
  if (!content) return []
  return content.flatMap((node) => {
    if (node.type === 'text') {
      return [{ type: 'text', text: node.text || '', marks: node.marks as JSONContent['marks'] }]
    }
    if (node.type === 'hardBreak') return [{ type: 'hardBreak' }]
    if (node.type === 'footnoteReference') return [{ type: 'footnoteReference', attrs: { payload: node.attrs || {} } }]
    if (node.type === 'field' && node.attrs?.fieldKind === 'endnote') return [{ type: 'endnoteReference', attrs: { payload: node.attrs } }]
    if (node.type === 'field' && node.attrs?.fieldKind === 'equation') return [{ type: 'inlineEquation', attrs: { payload: node.attrs } }]
    if (node.type === 'field' && node.attrs?.fieldKind === 'crossReference') return [{ type: 'crossReference', attrs: { payload: node.attrs } }]
    if (node.type === 'citation') return [{ type: 'citationReference', attrs: { payload: node.attrs || {} } }]
    return []
  })
}

function tableBlockToJson(block: V3BlockNode, sectionId: string): JSONContent {
  const table = ((block.attrs?.table || block.attrs || {}) as Record<string, unknown>)
  const columns = Array.isArray(table.columns) ? table.columns.map((value) => String(value ?? '')) : []
  const sourceRows = Array.isArray(table.rows) ? table.rows : []
  const bodyRows = sourceRows.map((row) => Array.isArray(row) ? row.map((value) => String(value ?? '')) : [])
  const storedCells = Array.isArray(table.cells) ? table.cells : []
  const storedRowHeights = Array.isArray(table.rowHeights) ? table.rowHeights : []
  const columnCount = Math.max(1, columns.length, ...bodyRows.map((row) => row.length))
  const cell = (type: 'tableHeader' | 'tableCell', text: string, attrs: Record<string, unknown> = {}): JSONContent => ({
    type,
    attrs,
    content: [{ type: 'paragraph', content: text ? [{ type: 'text', text }] : [] }]
  })
  const rows: JSONContent[] = []
  if (storedCells.length) {
    for (const [rowIndex, rawRow] of storedCells.entries()) {
      if (!Array.isArray(rawRow)) continue
      const cells = rawRow.flatMap((rawCell): JSONContent[] => {
        if (!rawCell || typeof rawCell !== 'object' || Array.isArray(rawCell)) return []
        const value = rawCell as Record<string, unknown>
        const type = value.type === 'header' ? 'tableHeader' : 'tableCell'
        const colspan = Math.max(1, Number(value.colspan || 1))
        const rowspan = Math.max(1, Number(value.rowspan || 1))
        const colwidth = Array.isArray(value.colwidth)
          ? value.colwidth.map((width) => Number(width)).filter((width) => Number.isFinite(width) && width > 0)
          : null
        return [cell(type, String(value.text ?? ''), {
          colspan,
          rowspan,
          colwidth: colwidth?.length ? colwidth : null,
          backgroundColor: value.backgroundColor ? String(value.backgroundColor) : null,
          verticalAlign: value.verticalAlign ? String(value.verticalAlign) : null,
          borderColor: value.borderColor ? String(value.borderColor) : null,
          borderWidthPt: value.borderWidthPt ? Number(value.borderWidthPt) : null
        })]
      })
      if (cells.length) {
        const heightPx = Number(storedRowHeights[rowIndex])
        rows.push({ type: 'tableRow', attrs: { heightPx: Number.isFinite(heightPx) && heightPx > 0 ? heightPx : null }, content: cells })
      }
    }
  } else {
    if (columns.length) {
      rows.push({
        type: 'tableRow',
        content: Array.from({ length: columnCount }, (_, index) => cell('tableHeader', columns[index] || ''))
      })
    }
    for (const row of bodyRows) {
      rows.push({
        type: 'tableRow',
        content: Array.from({ length: columnCount }, (_, index) => cell('tableCell', row[index] || ''))
      })
    }
  }
  if (!rows.length) {
    rows.push({ type: 'tableRow', content: Array.from({ length: columnCount }, () => cell('tableCell', '')) })
  }
  return {
    type: 'table',
    attrs: {
      nodeId: block.id,
      sectionId,
      caption: String(table.caption || ''),
      repeatHeader: Boolean(table.repeatHeader),
      tableAlignment: ['left', 'center', 'right'].includes(String(table.alignment)) ? String(table.alignment) : 'left',
      widthPercent: Math.max(20, Math.min(100, Number(table.widthPercent || 100)))
    },
    content: rows
  }
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
  if (block.type === 'table') return [tableBlockToJson(block, sectionId)]
  if (block.type === 'pageBreak') return [{ type: 'pageBreak', attrs: { nodeId: block.id, sectionId } }]
  if (block.type === 'sectionBreak') return [{ type: 'sectionBreak', attrs: { nodeId: block.id, sectionId, payload: block.attrs || {} } }]
  if (block.type === 'equationBlock') return [{ type: 'equationBlock', attrs: { nodeId: block.id, sectionId, payload: block.attrs || {} } }]
  if (block.type === 'tableOfContents') return [{ type: 'tableOfContents', attrs: { nodeId: block.id, sectionId, payload: block.attrs || {} } }]
  if (block.type === 'bibliography') return [{ type: 'bibliography', attrs: { nodeId: block.id, sectionId, payload: block.attrs || {} } }]
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
    if (node.type === 'footnoteReference') return [{ type: 'footnoteReference', attrs: (node.attrs?.payload || {}) as Record<string, unknown> } as InlineNode]
    if (node.type === 'endnoteReference') return [{ type: 'field', attrs: { ...((node.attrs?.payload || {}) as Record<string, unknown>), fieldKind: 'endnote' } } as InlineNode]
    if (node.type === 'inlineEquation') return [{ type: 'field', attrs: { ...((node.attrs?.payload || {}) as Record<string, unknown>), fieldKind: 'equation' } } as InlineNode]
    if (node.type === 'crossReference') {
      const payload = (node.attrs?.payload || {}) as Record<string, unknown>
      return [{ type: payload.referenceKind === 'citation' ? 'citation' : 'field', attrs: { ...payload, fieldKind: payload.referenceKind === 'citation' ? undefined : 'crossReference' } } as InlineNode]
    }
    if (node.type === 'citationReference') return [{ type: 'citation', attrs: (node.attrs?.payload || {}) as Record<string, unknown> } as InlineNode]
    return []
  })
}

function jsonText(node: JSONContent): string {
  if (node.type === 'text') return node.text || ''
  if (node.type === 'hardBreak') return '\n'
  return (node.content || []).map(jsonText).join('')
}

function tableFromJson(node: JSONContent, id: string): V3BlockNode {
  const rows = (node.content || []).filter((row) => row.type === 'tableRow')
  const firstCells = rows[0]?.content || []
  const hasHeader = firstCells.length > 0 && firstCells.every((cell) => cell.type === 'tableHeader')
  const columns = hasHeader ? firstCells.map((cell) => jsonText(cell)) : []
  const bodyRows = (hasHeader ? rows.slice(1) : rows).map((row) => (row.content || []).map((cell) => jsonText(cell)))
  const cells = rows.map((row) => (row.content || []).map((cell) => ({
    text: jsonText(cell),
    type: cell.type === 'tableHeader' ? 'header' : 'cell',
    colspan: Math.max(1, Number(cell.attrs?.colspan || 1)),
    rowspan: Math.max(1, Number(cell.attrs?.rowspan || 1)),
    colwidth: Array.isArray(cell.attrs?.colwidth) ? cell.attrs?.colwidth : null,
    backgroundColor: cell.attrs?.backgroundColor || null,
    verticalAlign: cell.attrs?.verticalAlign || null,
    borderColor: cell.attrs?.borderColor || null,
    borderWidthPt: cell.attrs?.borderWidthPt || null
  })))
  const rowHeights = rows.map((row) => Number(row.attrs?.heightPx) || null)
  return {
    id,
    type: 'table',
    attrs: {
      table: {
        caption: String(node.attrs?.caption || ''),
        columns,
        rows: bodyRows,
        cells,
        rowHeights,
        repeatHeader: Boolean(node.attrs?.repeatHeader),
        alignment: String(node.attrs?.tableAlignment || 'left'),
        widthPercent: Math.max(20, Math.min(100, Number(node.attrs?.widthPercent || 100)))
      }
    }
  }
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
  if (node.type === 'table') return tableFromJson(node, id)
  if (node.type === 'pageBreak') return { id, type: 'pageBreak' }
  if (node.type === 'sectionBreak') return { id, type: 'sectionBreak', attrs: (attrs.payload || {}) as Record<string, unknown> }
  if (node.type === 'equationBlock') return { id, type: 'equationBlock', attrs: (attrs.payload || {}) as Record<string, unknown> }
  if (node.type === 'tableOfContents') return { id, type: 'tableOfContents', attrs: (attrs.payload || {}) as Record<string, unknown> }
  if (node.type === 'bibliography') return { id, type: 'bibliography', attrs: (attrs.payload || {}) as Record<string, unknown> }
  return null
}

export function tiptapToDocumentV3(base: DocumentV3, json: JSONContent): DocumentV3 {
  const next = cloneJson(base)
  const templates = new Map(next.sections.map((section) => [section.id, section]))
  const firstTemplate = next.sections[0]
  const firstSection: SectionV3 = firstTemplate
    ? { ...cloneJson(firstTemplate), content: [] }
    : {
        id: newNodeId('section'),
        breakType: 'nextPage',
        layout: { pageSize: 'A4', orientation: 'portrait', marginTopMm: 25.4, marginRightMm: 25.4, marginBottomMm: 25.4, marginLeftMm: 31.8, columns: 1 },
        headerFooter: { linkHeaderToPrevious: true, linkFooterToPrevious: true, differentFirstPage: false, differentOddEven: false, header: [], footer: [], firstPageHeader: [], firstPageFooter: [], evenPageHeader: [], evenPageFooter: [], pageNumber: { enabled: true, format: 'arabic', position: 'footer', alignment: 'center' } },
        content: []
      }
  const rebuilt: SectionV3[] = [firstSection]
  let section = firstSection
  let markerControlledSection = false
  for (const node of json.content || []) {
    if (node.type === 'sectionBreak') {
      const payload = (node.attrs?.payload || {}) as Record<string, unknown>
      const id = String(payload.nextSectionId || newNodeId('section'))
      const existing = templates.get(id)
      section = existing
        ? { ...cloneJson(existing), breakType: (payload.breakType || existing.breakType) as SectionV3['breakType'], content: [] }
        : {
            ...cloneJson(section),
            id,
            breakType: (['continuous', 'nextPage', 'oddPage', 'evenPage'].includes(String(payload.breakType)) ? payload.breakType : 'nextPage') as SectionV3['breakType'],
            content: []
          }
      rebuilt.push(section)
      markerControlledSection = true
      continue
    }
    const requestedSectionId = String(node.attrs?.sectionId || '')
    if (!markerControlledSection && requestedSectionId && requestedSectionId !== section.id) {
      const existing = templates.get(requestedSectionId)
      section = existing
        ? { ...cloneJson(existing), content: [] }
        : { ...cloneJson(section), id: requestedSectionId, content: [] }
      rebuilt.push(section)
    }
    const block = blockFromJson(node)
    if (block) section.content.push(block)
  }
  next.sections = rebuilt
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
    content: doc.sections.flatMap((section, index) => [
      ...(index ? [{
        type: 'sectionBreak',
        attrs: {
          nodeId: newNodeId('sectionBreak'),
          sectionId: doc.sections[index - 1]?.id || null,
          payload: { nextSectionId: section.id, breakType: section.breakType }
        }
      } as JSONContent] : []),
      ...section.content.flatMap((block) => blockToJson(block, section.id))
    ])
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
    p.bold !== undefined ? `font-weight:${p.bold ? 700 : 400}` : '',
    p.italic !== undefined ? `font-style:${p.italic ? 'italic' : 'normal'}` : '',
    p.underline !== undefined ? `text-decoration:${p.underline ? 'underline' : 'none'}` : '',
    p.color ? `color:${p.color}` : '',
    p.backgroundColor ? `background-color:${p.backgroundColor}` : '',
    p.letterSpacingPt !== undefined ? `letter-spacing:${p.letterSpacingPt}pt` : '',
    p.textTransform ? `text-transform:${p.textTransform}` : '',
    p.alignment ? `text-align:${p.alignment}` : '',
    p.lineSpacing ? `line-height:${p.lineSpacing}` : '',
    p.firstLineIndentEm !== undefined ? `text-indent:${p.firstLineIndentEm}em` : '',
    p.leftIndentEm !== undefined ? `margin-left:${p.leftIndentEm}em` : '',
    p.rightIndentEm !== undefined ? `margin-right:${p.rightIndentEm}em` : '',
    p.spaceBeforePt !== undefined ? `margin-top:${p.spaceBeforePt}pt` : '',
    p.spaceAfterPt !== undefined ? `margin-bottom:${p.spaceAfterPt}pt` : '',
    p.borderColor ? `border-color:${p.borderColor}` : '',
    p.borderWidthPt !== undefined ? `border-width:${p.borderWidthPt}pt` : '',
    p.borderStyle ? `border-style:${p.borderStyle}` : '',
    p.shadingColor ? `background-color:${p.shadingColor}` : ''
  ].filter(Boolean).join(';')
}

export function styleSheetForDocument(doc: DocumentV3): string {
  const styles = doc.styles.map((style) => `[data-style-id="${style.id}"]{${cssForStyle(doc, style)}}`)
  const numbering = (doc.numbering || []).flatMap((definition) => definition.levels.map((level) => {
    const selector = `[data-numbering-id="${definition.id}"][data-numbering-level="${level.level}"]`
    const listStyle = level.format === 'bullet'
      ? 'none'
      : ({ decimal: 'decimal', lowerLetter: 'lower-alpha', upperLetter: 'upper-alpha', lowerRoman: 'lower-roman', upperRoman: 'upper-roman' } as Record<string, string>)[level.format] || 'decimal'
    const rules = `${selector}{list-style-type:${listStyle};padding-left:${Math.max(0, level.leftIndentEm)}em}`
    const marker = level.format === 'bullet' ? `${selector}>li::marker{content:"${String(level.bulletChar || level.text || '•').replace(/"/g, '\\"')}  "}` : ''
    return [rules, marker].filter(Boolean)
  }))
  const styleNumbering: string[] = []
  for (const definition of doc.numbering || []) {
    const counterBase = `wa-${String(definition.id).replace(/[^a-zA-Z0-9_-]/g, '-')}`
    const linked = doc.styles
      .map((style) => ({ style, properties: resolvedStyleProperties(doc, style.id) }))
      .filter((item) => item.properties.numberingId === definition.id)
    if (!linked.length) continue
    styleNumbering.push(`.ProseMirror{counter-reset:${definition.levels.map((level) => `${counterBase}-${level.level}`).join(' ')}}`)
    for (const { style, properties } of linked) {
      const levelIndex = Math.max(0, Math.min(8, Number(properties.numberingLevel || 0)))
      const level = definition.levels.find((candidate) => candidate.level === levelIndex) || definition.levels[0]
      if (!level) continue
      const selector = `[data-style-id="${style.id}"]`
      const deeper = definition.levels.filter((candidate) => candidate.level > levelIndex).map((candidate) => `${counterBase}-${candidate.level}`).join(' ')
      styleNumbering.push(`${selector}{counter-increment:${counterBase}-${levelIndex}${deeper ? `;counter-reset:${deeper}` : ''}}`)
      if (level.format === 'bullet') {
        const bullet = String(level.bulletChar || level.text || '•').replace(/(["\\])/g, '\\$1')
        styleNumbering.push(`${selector}::before{content:"${bullet} ";display:inline-block;margin-right:.35em;text-indent:0}`)
        continue
      }
      const counterFormat = ({ decimal: 'decimal', lowerLetter: 'lower-alpha', upperLetter: 'upper-alpha', lowerRoman: 'lower-roman', upperRoman: 'upper-roman' } as Record<string, string>)[level.format] || 'decimal'
      const prefix = definition.levels
        .filter((candidate) => candidate.level <= levelIndex)
        .map((candidate) => `counter(${counterBase}-${candidate.level},${candidate.level === levelIndex ? counterFormat : 'decimal'})`)
        .join(' "." ')
      styleNumbering.push(`${selector}::before{content:${prefix} ". ";display:inline-block;margin-right:.35em;text-indent:0}`)
    }
  }
  return [...styles, ...numbering, ...styleNumbering].join('\n')
}

export function createEditorKernel(options: {
  element: HTMLElement
  document: DocumentV3
  editable?: boolean
  onUpdate?: (json: JSONContent) => void
  onSelectionUpdate?: (editor: Editor) => void
  onSlashQuery?: (query: string | null, position: number, editor: Editor) => void
  onShortcutCommand?: (type: string, params?: Record<string, unknown>) => boolean
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
    editorProps: { attributes: { spellcheck: 'true', autocapitalize: 'sentences' } },
    extensions: [
      StarterKit.configure({ heading: { levels: [1, 2, 3, 4, 5, 6] }, link: false }),
      TextStyle,
      LinkMark,
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
      ReliableBlockKeyboard.configure({ onCommand: options.onShortcutCommand }),
      RustPagination,
      FocusBlockDecoration,
      FigureNode,
      Table.configure({ resizable: true, View: DocumentTableView }),
      SizedTableRow,
      StyledTableHeader,
      StyledTableCell,
      PageBreakNode,
      SectionBreakNode,
      EquationBlockNode,
      TableOfContentsNode,
      BibliographyNode,
      FootnoteReferenceNode,
      EndnoteReferenceNode,
      CitationReferenceNode,
      InlineEquationNode,
      CrossReferenceNode
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

export function selectedBlocks(editor: Editor): Array<{ id: string; type: string; text: string; collapsed: boolean }> {
  const { from, to, empty, $from } = editor.state.selection
  const blocks: Array<{ id: string; type: string; text: string; collapsed: boolean }> = []
  const seen = new Set<string>()
  const append = (node: ProseMirrorNode) => {
    const id = String(node.attrs?.nodeId || '')
    if (!id || seen.has(id)) return
    seen.add(id)
    blocks.push({ id, type: node.type.name, text: node.textContent, collapsed: Boolean(node.attrs?.collapsed) })
  }
  if (empty) {
    if ($from.depth >= 1) append($from.node(1))
    return blocks
  }
  editor.state.doc.forEach((node, position) => {
    const end = position + node.nodeSize
    if (end > from && position < to) append(node)
  })
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
