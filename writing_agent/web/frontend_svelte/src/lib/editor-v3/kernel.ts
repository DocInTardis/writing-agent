import { Editor, Extension, type JSONContent } from '@tiptap/core'
import Color from '@tiptap/extension-color'
import FontFamily from '@tiptap/extension-font-family'
import Highlight from '@tiptap/extension-highlight'
import Subscript from '@tiptap/extension-subscript'
import Superscript from '@tiptap/extension-superscript'
import TextAlign from '@tiptap/extension-text-align'
import { TextStyle } from '@tiptap/extension-text-style'
import StarterKit from '@tiptap/starter-kit'

import type { DocumentV3, InlineNode, SectionV3, StyleDefinition, V3BlockNode } from './model'

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

export function documentV3ToTiptap(doc: DocumentV3): JSONContent {
  return {
    type: 'doc',
    content: doc.sections.flatMap((section) => section.content.flatMap((block) => blockToJson(block, section.id)))
  }
}

function cssForStyle(style: StyleDefinition): string {
  const p = style.properties
  return [
    p.fontFamily ? `font-family:${JSON.stringify(p.fontFamily)}` : '',
    p.fontSizePt ? `font-size:${p.fontSizePt}pt` : '',
    p.bold ? 'font-weight:700' : '',
    p.italic ? 'font-style:italic' : '',
    p.color ? `color:${p.color}` : '',
    p.alignment ? `text-align:${p.alignment}` : '',
    p.lineSpacing ? `line-height:${p.lineSpacing}` : '',
    p.firstLineIndentEm !== undefined ? `text-indent:${p.firstLineIndentEm}em` : '',
    p.leftIndentEm ? `margin-left:${p.leftIndentEm}em` : '',
    p.rightIndentEm ? `margin-right:${p.rightIndentEm}em` : '',
    p.spaceBeforePt !== undefined ? `margin-top:${p.spaceBeforePt}pt` : '',
    p.spaceAfterPt !== undefined ? `margin-bottom:${p.spaceAfterPt}pt` : ''
  ].filter(Boolean).join(';')
}

export function styleSheetForDocument(doc: DocumentV3): string {
  return doc.styles.map((style) => `[data-style-id="${style.id}"]{${cssForStyle(style)}}`).join('\n')
}

export function createEditorKernel(options: {
  element: HTMLElement
  document: DocumentV3
  editable?: boolean
  onUpdate?: (json: JSONContent) => void
  onSelectionUpdate?: (editor: Editor) => void
}): Editor {
  return new Editor({
    element: options.element,
    editable: options.editable !== false,
    content: documentV3ToTiptap(options.document),
    extensions: [
      StarterKit.configure({ heading: { levels: [1, 2, 3, 4, 5, 6] } }),
      TextStyle,
      Color,
      FontFamily,
      Highlight.configure({ multicolor: true }),
      Subscript,
      Superscript,
      TextAlign.configure({ types: ['heading', 'paragraph'] }),
      StableNodeAttributes
    ],
    onUpdate: ({ editor }) => options.onUpdate?.(editor.getJSON()),
    onSelectionUpdate: ({ editor }) => options.onSelectionUpdate?.(editor)
  })
}

export function sectionForPosition(doc: DocumentV3, sectionId: string): SectionV3 | undefined {
  return doc.sections.find((section) => section.id === sectionId)
}
