<script lang="ts">
  import { onMount, createEventDispatcher } from 'svelte'
  import { editorCommand, sourceText, docIr, docIrDirty, pushHistory, undoHistory, redoHistory, generating, wordCount, docId } from '../stores'
  import { renderDocument, docIrToMarkdown, textToDocIr } from '../utils/markdown'

  let editor: HTMLDivElement | null = null
  let lastMarkdown = ''
  let lastRenderSig = ''
  let renderMode: 'text' | 'doc' = 'text'
  let historyTimer: ReturnType<typeof setTimeout> | null = null
  let syncTimer: ReturnType<typeof setTimeout> | null = null
  let docTextTimer: ReturnType<typeof setTimeout> | null = null
  let sourceUnsub: (() => void) | null = null
  let docIrUnsub: (() => void) | null = null
  export let showToolbar = true
  export let paper = true
  const dispatch = createEventDispatcher()
  let editingEl: HTMLElement | null = null
  let editingKey = ''
  let composing = false
  let pendingRenderSig: string | null = null
  let pendingFocusBlockId = ''
  let editCommitTimer: ReturnType<typeof setTimeout> | null = null
  let selectedBlockIds: string[] = []
  let selectedBlockEls: HTMLElement[] = []
  let selectedAnchorId = ''
  let dragSelectSeed: { x: number; y: number } | null = null
  let dragSelecting = false
  let dragRect = { left: 0, top: 0, width: 0, height: 0 }
  let suppressClickOnce = false

  function setEmptyFlag(text: string) {
    if (!editor) return
    const empty = !String(text || '').trim()
    editor.dataset.empty = empty ? '1' : '0'
  }

  function syncFromStore() {
    if (!editor) return
    const next = String($sourceText || '')
    const doc = $docIr
    const hasDocIr = Boolean(doc && typeof doc === 'object')
    const preferText = !hasDocIr
    const sig = hasDocIr ? `doc:${docIrSignature(doc)}` : `text:${next}`
    if (editingEl && editor.contains(editingEl) && sig !== lastRenderSig) {
      pendingRenderSig = sig
      return
    }
    if (sig !== lastRenderSig) {
      if (syncTimer) clearTimeout(syncTimer)
      syncTimer = setTimeout(() => {
        editor!.innerHTML = renderDocument(next, doc, preferText)
        renderMode = preferText ? 'text' : 'doc'
        lastMarkdown = next
        lastRenderSig = sig
        pendingRenderSig = null
        setEmptyFlag(next)
        markEditableBlocks()
        refreshSelectedBlock()
        if (pendingFocusBlockId) {
          const target = editor!.querySelector(
            `[data-block-id="${CSS.escape(pendingFocusBlockId)}"]`
          ) as HTMLElement | null
          pendingFocusBlockId = ''
          if (target) target.focus()
        }
        renderMathInEditor()
        highlightCodeBlocks()
        renderFiguresInEditor()
      }, 100)
    }
  }

  function docIrSignature(doc: unknown): string {
    try {
      return JSON.stringify(doc) || ''
    } catch {
      return ''
    }
  }

  function setEditableAttrs(el: HTMLElement) {
    el.setAttribute('contenteditable', 'true')
    el.setAttribute('spellcheck', 'false')
    el.dataset.waEdit = '1'
  }

  function markEditableBlocks() {
    if (!editor) return
    const titleEl = editor.querySelector('.wa-title') as HTMLElement | null
    if (titleEl) {
      titleEl.dataset.docTitle = '1'
      setEditableAttrs(titleEl)
    }
    editor.querySelectorAll('[data-section-id]').forEach((node) => {
      const el = node as HTMLElement
      setEditableAttrs(el)
    })
    editor.querySelectorAll('[data-block-id]').forEach((node) => {
      const el = node as HTMLElement
      const tag = el.tagName.toLowerCase()
      if (tag === 'figure' || tag === 'table') {
        el.setAttribute('contenteditable', 'false')
        return
      }
      setEditableAttrs(el)
    })
  }

  function findEditableRoot(target: EventTarget | null): HTMLElement | null {
    if (!target || !(target instanceof HTMLElement) || !editor) return null
    const el = target.closest('[data-wa-edit="1"]') as HTMLElement | null
    if (!el || !editor.contains(el)) return null
    return el
  }

  function normalizeInlineText(text: string): string {
    let out = String(text || '').replace(/\r/g, '')
    out = out.replace(/[ \t]+/g, ' ')
    out = out.replace(/[ \t]*\n[ \t]*/g, '\n')
    out = out.replace(/\n{3,}/g, '\n\n')
    return out.trim()
  }

  function inlineFromNode(node: Node): string {
    if (node.nodeType === Node.TEXT_NODE) return node.textContent || ''
    if (!(node instanceof HTMLElement)) return ''
    const tag = node.tagName.toLowerCase()
    if (tag === 'br') return '\n'
    if (tag === 'strong' || tag === 'b') return `**${inlineFromElement(node)}**`
    if (tag === 'em' || tag === 'i') return `*${inlineFromElement(node)}*`
    if (tag === 'u') return `++${inlineFromElement(node)}++`
    if (tag === 'del' || tag === 's') return `~~${inlineFromElement(node)}~~`
    if (tag === 'mark') return `==${inlineFromElement(node)}==`
    if (tag === 'code') return '`' + (node.textContent || '') + '`'
    if (tag === 'a') {
      const href = node.getAttribute('href') || ''
      const text = inlineFromElement(node)
      return href ? `[${text}](${href})` : text
    }
    return inlineFromElement(node)
  }

  function inlineFromElement(el: HTMLElement): string {
    const out: string[] = []
    el.childNodes.forEach((child) => out.push(inlineFromNode(child)))
    return normalizeInlineText(out.join(''))
  }

  function plainTextFromNode(node: Node): string {
    if (node.nodeType === Node.TEXT_NODE) return node.textContent || ''
    if (!(node instanceof HTMLElement)) return ''
    const tag = node.tagName.toLowerCase()
    if (tag === 'br') return '\n'
    const out: string[] = []
    node.childNodes.forEach((child) => out.push(plainTextFromNode(child)))
    return out.join('')
  }

  function plainTextFromElement(el: HTMLElement): string {
    const out: string[] = []
    el.childNodes.forEach((child) => out.push(plainTextFromNode(child)))
    return out.join('')
  }

  function inlineFromFragment(fragment: DocumentFragment): string {
    const wrapper = document.createElement('div')
    wrapper.appendChild(fragment)
    return inlineFromElement(wrapper)
  }

  function splitInlineAtSelection(li: HTMLElement): { before: string; after: string } | null {
    const sel = window.getSelection()
    if (!sel || sel.rangeCount === 0) return null
    const range = sel.getRangeAt(0)
    if (!li.contains(range.startContainer)) return null
    const beforeRange = range.cloneRange()
    beforeRange.selectNodeContents(li)
    beforeRange.setEnd(range.startContainer, range.startOffset)
    const afterRange = range.cloneRange()
    afterRange.selectNodeContents(li)
    afterRange.setStart(range.startContainer, range.startOffset)
    const before = inlineFromFragment(beforeRange.cloneContents())
    const after = inlineFromFragment(afterRange.cloneContents())
    return { before, after }
  }

  function nodeTextLength(node: Node): number {
    if (node.nodeType === Node.TEXT_NODE) return (node.textContent || '').length
    if (!(node instanceof HTMLElement)) return 0
    const tag = node.tagName.toLowerCase()
    if (tag === 'br') return 1
    let total = 0
    node.childNodes.forEach((child) => {
      total += nodeTextLength(child)
    })
    return total
  }

  function getCaretOffset(root: HTMLElement): number | null {
    const sel = window.getSelection()
    if (!sel || sel.rangeCount === 0) return null
    const range = sel.getRangeAt(0)
    const start = range.startContainer
    if (!root.contains(start)) return null
    let offset = 0
    let found = false
    const walk = (node: Node) => {
      if (found) return
      if (node === start) {
        if (node.nodeType === Node.TEXT_NODE) {
          offset += range.startOffset
        } else if (node instanceof HTMLElement) {
          const children = Array.from(node.childNodes)
          for (let i = 0; i < range.startOffset; i++) {
            offset += nodeTextLength(children[i])
          }
        }
        found = true
        return
      }
      if (node.nodeType === Node.TEXT_NODE || (node instanceof HTMLElement && node.tagName.toLowerCase() === 'br')) {
        offset += nodeTextLength(node)
        return
      }
      node.childNodes.forEach((child) => walk(child))
    }
    walk(root)
    return offset
  }

  function extractBlockStyle(el: HTMLElement): Record<string, string> | null {
    const style = el.style
    const out: Record<string, string> = {}
    const align = style.textAlign || el.getAttribute('align') || ''
    if (align) out.align = align
    const lineHeight = style.lineHeight
    if (lineHeight) out.lineHeight = lineHeight
    const indent = style.textIndent
    if (indent) out.indent = indent
    const marginTop = style.marginTop
    if (marginTop) out.marginTop = marginTop
    const marginBottom = style.marginBottom
    if (marginBottom) out.marginBottom = marginBottom
    const fontFamily = style.fontFamily
    if (fontFamily) out.fontFamily = fontFamily
    const fontSize = style.fontSize
    if (fontSize) out.fontSize = fontSize
    const color = style.color
    if (color) out.color = color
    const background = style.backgroundColor
    if (background) out.background = background
    return Object.keys(out).length ? out : null
  }

  function extractRunsFromElement(el: HTMLElement) {
    type Run = {
      text: string
      bold?: boolean
      italic?: boolean
      underline?: boolean
      strike?: boolean
      color?: string
      background?: string
      font?: string
      size?: string
      link?: string
    }
    const runs: Run[] = []
    const pushRun = (text: string, ctx: Run) => {
      if (!text) return
      runs.push({
        text,
        bold: ctx.bold,
        italic: ctx.italic,
        underline: ctx.underline,
        strike: ctx.strike,
        color: ctx.color,
        background: ctx.background,
        font: ctx.font,
        size: ctx.size,
        link: ctx.link
      })
    }
    const normalizeFont = (value: string) => {
      const v = String(value || '').trim()
      if (!v) return ''
      return v.split(',')[0].replace(/["']/g, '').trim()
    }
    const walk = (node: Node, ctx: Run) => {
      if (node.nodeType === Node.TEXT_NODE) {
        pushRun(node.textContent || '', ctx)
        return
      }
      if (!(node instanceof HTMLElement)) return
      const tag = node.tagName.toLowerCase()
      if (tag === 'br') {
        pushRun('\n', ctx)
        return
      }
      const next: Run = { ...ctx }
      if (tag === 'strong' || tag === 'b') next.bold = true
      if (tag === 'em' || tag === 'i') next.italic = true
      if (tag === 'u') next.underline = true
      if (tag === 's' || tag === 'del' || tag === 'strike') next.strike = true
      if (tag === 'a') {
        const href = node.getAttribute('href') || ''
        if (href) next.link = href
      }
      if (tag === 'font') {
        const color = node.getAttribute('color')
        if (color) next.color = color
        const face = node.getAttribute('face')
        if (face) next.font = normalizeFont(face)
        const size = node.getAttribute('size')
        if (size) next.size = String(size)
      }
      const style = node.style
      if (style) {
        if (style.color) next.color = style.color
        if (style.backgroundColor) next.background = style.backgroundColor
        if (style.fontFamily) next.font = normalizeFont(style.fontFamily)
        if (style.fontSize) next.size = style.fontSize
        const deco = style.textDecoration
        if (deco && deco.includes('underline')) next.underline = true
        if (deco && deco.includes('line-through')) next.strike = true
      }
      node.childNodes.forEach((child) => walk(child, next))
    }
    walk(el, {})
    const merged: Run[] = []
    const keyFor = (r: Run) =>
      [
        r.bold ? 'b' : '',
        r.italic ? 'i' : '',
        r.underline ? 'u' : '',
        r.strike ? 's' : '',
        r.color || '',
        r.background || '',
        r.font || '',
        r.size || '',
        r.link || ''
      ].join('|')
    runs.forEach((run) => {
      const last = merged[merged.length - 1]
      if (last && keyFor(last) === keyFor(run)) {
        last.text += run.text
      } else {
        merged.push({ ...run })
      }
    })
    const text = normalizeInlineText(merged.map((r) => r.text).join(''))
    const styled = merged.some((r) =>
      Object.keys(r).some((k) => k !== 'text' && (r as Record<string, unknown>)[k])
    )
    return { text, runs: styled ? merged : null }
  }

  function extractEditablePayload(el: HTMLElement) {
    if (el.dataset.docTitle === '1') {
      return { kind: 'title', text: inlineFromElement(el) }
    }
    const sectionId = String(el.dataset.sectionId || '').trim()
    if (sectionId) {
      return { kind: 'section', id: sectionId, text: inlineFromElement(el), style: extractBlockStyle(el) }
    }
    const blockId = String(el.dataset.blockId || '').trim()
    if (!blockId) return null
    const tag = el.tagName.toLowerCase()
    if (tag === 'ul' || tag === 'ol') {
      const items = Array.from(el.querySelectorAll(':scope > li')).map((li) =>
        normalizeInlineText(inlineFromElement(li as HTMLElement))
      )
      const payload: Record<string, unknown> = { type: 'list', items, ordered: tag === 'ol' }
      const style = extractBlockStyle(el)
      if (style) payload.style = style
      return { kind: 'block', id: blockId, payload }
    }
    if (/^h[1-6]$/.test(tag)) {
      const level = Number(tag.slice(1))
      const inline = extractRunsFromElement(el)
      const text = inline.text.replace(/\n+/g, ' ').trim()
      const payload: Record<string, unknown> = { type: 'heading', level, text }
      if (inline.runs) payload.runs = inline.runs
      const style = extractBlockStyle(el)
      if (style) payload.style = style
      return { kind: 'block', id: blockId, payload }
    }
    const inline = extractRunsFromElement(el)
    const text = inline.text
    const payload: Record<string, unknown> = { type: 'paragraph', text }
    if (inline.runs) payload.runs = inline.runs
    const style = extractBlockStyle(el)
    if (style) payload.style = style
    return { kind: 'block', id: blockId, payload }
  }

  function scheduleDocTextSync(nextDoc: Record<string, unknown>) {
    if (docTextTimer) clearTimeout(docTextTimer)
    docTextTimer = setTimeout(() => {
      const text = docIrToMarkdown(nextDoc) || ''
      sourceText.set(text)
      lastMarkdown = text
      setEmptyFlag(text)
      pushHistory(text)
    }, 180)
  }

  function applyDocIrUpdate(nextDoc: Record<string, unknown>) {
    docIr.set(nextDoc)
    docIrDirty.set(false)
    lastRenderSig = `doc:${docIrSignature(nextDoc)}`
    scheduleDocTextSync(nextDoc)
  }

  function updateDocTitle(doc: Record<string, unknown>, text: string): Record<string, unknown> | null {
    const nextTitle = String(text || '').trim() || '自动生成文档'
    const curTitle = String(doc.title || '').trim()
    let changed = false
    if (nextTitle !== curTitle) changed = true
    const updateSections = (sections: Array<Record<string, unknown>>) => {
      let localChanged = false
      const nextSections = sections.map((sec) => {
        let touched = false
        let nextSec = sec
        if (String(sec.title || '').trim() === curTitle) {
          nextSec = { ...sec, title: nextTitle }
          touched = true
        }
        const children = Array.isArray(sec.children) ? (sec.children as Array<Record<string, unknown>>) : []
        if (children.length) {
          const nextChildren = updateSections(children)
          if (nextChildren !== children) {
            nextSec = { ...nextSec, children: nextChildren }
            touched = true
          }
        }
        if (touched) localChanged = true
        return nextSec
      })
      if (localChanged) changed = true
      return localChanged ? nextSections : sections
    }
    const sections = Array.isArray(doc.sections) ? (doc.sections as Array<Record<string, unknown>>) : []
    const nextSections = updateSections(sections)
    if (!changed) return null
    return { ...doc, title: nextTitle, sections: nextSections }
  }

  function updateSectionTitle(
    doc: Record<string, unknown>,
    sectionId: string,
    text: string,
    style?: Record<string, string> | null
  ): Record<string, unknown> | null {
    const nextTitle = String(text || '').trim() || '章节'
    let changed = false
    const updateSections = (sections: Array<Record<string, unknown>>) => {
      let localChanged = false
      const nextSections = sections.map((sec) => {
        let touched = false
        let nextSec = sec
        if (String(sec.id || '') === sectionId) {
          nextSec = { ...sec, title: nextTitle }
          if (style && Object.keys(style).length) {
            nextSec = { ...nextSec, style: style }
          }
          touched = true
        }
        const children = Array.isArray(sec.children) ? (sec.children as Array<Record<string, unknown>>) : []
        if (children.length) {
          const nextChildren = updateSections(children)
          if (nextChildren !== children) {
            nextSec = { ...nextSec, children: nextChildren }
            touched = true
          }
        }
        if (touched) {
          localChanged = true
        }
        return nextSec
      })
      if (localChanged) changed = true
      return localChanged ? nextSections : sections
    }
    const sections = Array.isArray(doc.sections) ? (doc.sections as Array<Record<string, unknown>>) : []
    const nextSections = updateSections(sections)
    if (!changed) return null
    return { ...doc, sections: nextSections }
  }

  function updateBlock(
    doc: Record<string, unknown>,
    blockId: string,
    payload: Record<string, unknown>
  ): Record<string, unknown> | null {
    let changed = false
    const updateSections = (sections: Array<Record<string, unknown>>) => {
      let localChanged = false
      const nextSections = sections.map((sec) => {
        let touched = false
        let nextSec = sec
        const blocks = Array.isArray(sec.blocks) ? (sec.blocks as Array<Record<string, unknown>>) : []
        if (blocks.length) {
          const idx = blocks.findIndex((b) => String(b.id || '') === blockId)
          if (idx >= 0) {
            const prev = blocks[idx] || {}
            const updated = { ...prev, ...payload, id: prev.id || blockId }
            const nextBlocks = blocks.slice()
            nextBlocks[idx] = updated
            nextSec = { ...nextSec, blocks: nextBlocks }
            touched = true
          }
        }
        const children = Array.isArray(sec.children) ? (sec.children as Array<Record<string, unknown>>) : []
        if (children.length) {
          const nextChildren = updateSections(children)
          if (nextChildren !== children) {
            nextSec = { ...nextSec, children: nextChildren }
            touched = true
          }
        }
        if (touched) localChanged = true
        return nextSec
      })
      if (localChanged) changed = true
      return localChanged ? nextSections : sections
    }
    const sections = Array.isArray(doc.sections) ? (doc.sections as Array<Record<string, unknown>>) : []
    const nextSections = updateSections(sections)
    if (!changed) return null
    return { ...doc, sections: nextSections }
  }

  function insertBlockAfter(doc: Record<string, unknown>, blockId: string, newBlock: Record<string, unknown>) {
    let changed = false
    const updateSections = (sections: Array<Record<string, unknown>>) => {
      let localChanged = false
      const nextSections = sections.map((sec) => {
        let touched = false
        let nextSec = sec
        const blocks = Array.isArray(sec.blocks) ? (sec.blocks as Array<Record<string, unknown>>) : []
        if (blocks.length) {
          const idx = blocks.findIndex((b) => String(b.id || '') === blockId)
          if (idx >= 0) {
            const nextBlocks = blocks.slice()
            nextBlocks.splice(idx + 1, 0, newBlock)
            nextSec = { ...nextSec, blocks: nextBlocks }
            touched = true
          }
        }
        const children = Array.isArray(sec.children) ? (sec.children as Array<Record<string, unknown>>) : []
        if (children.length) {
          const nextChildren = updateSections(children)
          if (nextChildren !== children) {
            nextSec = { ...nextSec, children: nextChildren }
            touched = true
          }
        }
        if (touched) localChanged = true
        return nextSec
      })
      if (localChanged) changed = true
      return localChanged ? nextSections : sections
    }
    const sections = Array.isArray(doc.sections) ? (doc.sections as Array<Record<string, unknown>>) : []
    const nextSections = updateSections(sections)
    if (!changed) return null
    return { ...doc, sections: nextSections }
  }

  function insertBlockBefore(doc: Record<string, unknown>, blockId: string, newBlock: Record<string, unknown>) {
    let changed = false
    const updateSections = (sections: Array<Record<string, unknown>>) => {
      let localChanged = false
      const nextSections = sections.map((sec) => {
        let touched = false
        let nextSec = sec
        const blocks = Array.isArray(sec.blocks) ? (sec.blocks as Array<Record<string, unknown>>) : []
        if (blocks.length) {
          const idx = blocks.findIndex((b) => String(b.id || '') === blockId)
          if (idx >= 0) {
            const nextBlocks = blocks.slice()
            nextBlocks.splice(idx, 0, newBlock)
            nextSec = { ...nextSec, blocks: nextBlocks }
            touched = true
          }
        }
        const children = Array.isArray(sec.children) ? (sec.children as Array<Record<string, unknown>>) : []
        if (children.length) {
          const nextChildren = updateSections(children)
          if (nextChildren !== children) {
            nextSec = { ...nextSec, children: nextChildren }
            touched = true
          }
        }
        if (touched) localChanged = true
        return nextSec
      })
      if (localChanged) changed = true
      return localChanged ? nextSections : sections
    }
    const sections = Array.isArray(doc.sections) ? (doc.sections as Array<Record<string, unknown>>) : []
    const nextSections = updateSections(sections)
    if (!changed) return null
    return { ...doc, sections: nextSections }
  }

  function replaceInDocIr(doc: Record<string, unknown>, regex: RegExp, replace: string): Record<string, unknown> | null {
    let changed = false
    const updateBlock = (block: Record<string, unknown>) => {
      const t = String(block.type || 'paragraph').toLowerCase()
      if (t === 'list') {
        const items = Array.isArray(block.items) ? (block.items as Array<unknown>) : []
        const nextItems = items.map((item) => String(item ?? '').replace(regex, replace))
        if (nextItems.join('') !== items.join('')) {
          changed = true
          return { ...block, items: nextItems }
        }
        return block
      }
      if (t === 'table') {
        const table = typeof block.table === 'object' && block.table ? (block.table as Record<string, unknown>) : null
        if (table && typeof table.caption === 'string') {
          const nextCaption = String(table.caption || '').replace(regex, replace)
          if (nextCaption !== table.caption) {
            changed = true
            return { ...block, table: { ...table, caption: nextCaption } }
          }
        }
        return block
      }
      if (t === 'figure') {
        const fig = typeof block.figure === 'object' && block.figure ? (block.figure as Record<string, unknown>) : null
        if (fig && typeof fig.caption === 'string') {
          const nextCaption = String(fig.caption || '').replace(regex, replace)
          if (nextCaption !== fig.caption) {
            changed = true
            return { ...block, figure: { ...fig, caption: nextCaption } }
          }
        }
        return block
      }
      if (typeof block.text === 'string') {
        const nextText = String(block.text || '').replace(regex, replace)
        if (nextText !== block.text) {
          changed = true
          return { ...block, text: nextText }
        }
      }
      return block
    }
    const updateSections = (sections: Array<Record<string, unknown>>) => {
      let localChanged = false
      const nextSections = sections.map((sec) => {
        let touched = false
        let nextSec = sec
        if (typeof sec.title === 'string') {
          const nextTitle = String(sec.title || '').replace(regex, replace)
          if (nextTitle !== sec.title) {
            nextSec = { ...nextSec, title: nextTitle }
            touched = true
            changed = true
          }
        }
        const blocks = Array.isArray(sec.blocks) ? (sec.blocks as Array<Record<string, unknown>>) : []
        if (blocks.length) {
          const nextBlocks = blocks.map((b) => updateBlock(b))
          if (nextBlocks.some((b, idx) => b !== blocks[idx])) {
            nextSec = { ...nextSec, blocks: nextBlocks }
            touched = true
          }
        }
        const children = Array.isArray(sec.children) ? (sec.children as Array<Record<string, unknown>>) : []
        if (children.length) {
          const nextChildren = updateSections(children)
          if (nextChildren !== children) {
            nextSec = { ...nextSec, children: nextChildren }
            touched = true
          }
        }
        if (touched) localChanged = true
        return touched ? nextSec : sec
      })
      return localChanged ? nextSections : sections
    }
    const nextDoc: Record<string, unknown> = { ...doc }
    if (typeof nextDoc.title === 'string') {
      const nextTitle = String(nextDoc.title || '').replace(regex, replace)
      if (nextTitle !== nextDoc.title) {
        nextDoc.title = nextTitle
        changed = true
      }
    }
    const sections = Array.isArray(nextDoc.sections) ? (nextDoc.sections as Array<Record<string, unknown>>) : []
    const nextSections = updateSections(sections)
    if (nextSections !== sections) {
      nextDoc.sections = nextSections
    }
    return changed ? nextDoc : null
  }

  function scheduleCommit(el: HTMLElement, delayMs = 160) {
    if (editCommitTimer) clearTimeout(editCommitTimer)
    editCommitTimer = setTimeout(() => {
      commitEditableElement(el)
    }, delayMs)
  }

  function commitEditableElement(el: HTMLElement) {
    const doc = $docIr
    if (!doc || typeof doc !== 'object') return
    const payload = extractEditablePayload(el)
    if (!payload) return
    let nextDoc: Record<string, unknown> | null = null
    if (payload.kind === 'title') {
      nextDoc = updateDocTitle(doc, String(payload.text || ''))
    } else if (payload.kind === 'section') {
      nextDoc = updateSectionTitle(doc, String(payload.id || ''), String(payload.text || ''), payload.style || null)
    } else if (payload.kind === 'block') {
      nextDoc = updateBlock(doc, String(payload.id || ''), payload.payload || {})
    }
    if (!nextDoc) return
    applyDocIrUpdate(nextDoc)
  }

  function allBlockElements(): HTMLElement[] {
    if (!editor) return []
    return Array.from(editor.querySelectorAll('[data-block-id]')) as HTMLElement[]
  }

  function blockIdOf(el: HTMLElement | null): string {
    return String(el?.dataset.blockId || '').trim()
  }

  function blockById(id: string): HTMLElement | null {
    if (!editor || !id) return null
    return editor.querySelector(`[data-block-id="${CSS.escape(id)}"]`) as HTMLElement | null
  }

  function normalizeBlockIds(ids: string[]): string[] {
    const seen = new Set<string>()
    const out: string[] = []
    for (const raw of ids) {
      const id = String(raw || '').trim()
      if (!id || seen.has(id)) continue
      seen.add(id)
      out.push(id)
    }
    return out
  }

  function sortIdsByDocumentOrder(ids: string[]): string[] {
    const wanted = new Set(normalizeBlockIds(ids))
    const out: string[] = []
    for (const el of allBlockElements()) {
      const id = blockIdOf(el)
      if (id && wanted.has(id)) out.push(id)
    }
    return out
  }

  function dispatchBlockSelection() {
    const blocks = selectedBlockEls.map((el) => {
      const id = blockIdOf(el)
      const text = plainTextFromElement(el)
      return {
        id,
        text,
        style: extractBlockStyle(el) || {}
      }
    })
    if (!blocks.length) {
      dispatch('blockselect', { blockId: '', blockIds: [], blocks: [], text: '', rect: null, style: {} })
      return
    }
    const primaryEl = selectedBlockEls[0]
    const primaryId = blockIdOf(primaryEl)
    const primaryText = plainTextFromElement(primaryEl)
    const rect = primaryEl.getBoundingClientRect()
    dispatch('blockselect', {
      blockId: primaryId,
      blockIds: selectedBlockIds.slice(),
      blocks,
      text: primaryText,
      rect: {
        top: rect.top,
        left: rect.left,
        width: rect.width,
        height: rect.height
      },
      style: extractBlockStyle(primaryEl) || {}
    })
  }

  function setSelectedBlocksByIds(ids: string[], anchorId?: string) {
    for (const el of selectedBlockEls) el.classList.remove('wa-block-selected')
    selectedBlockIds = sortIdsByDocumentOrder(ids)
    selectedBlockEls = selectedBlockIds
      .map((id) => blockById(id))
      .filter((el): el is HTMLElement => Boolean(el))
    for (const el of selectedBlockEls) el.classList.add('wa-block-selected')
    if (anchorId && selectedBlockIds.includes(anchorId)) {
      selectedAnchorId = anchorId
    } else if (selectedBlockIds.length === 1) {
      selectedAnchorId = selectedBlockIds[0]
    } else if (!selectedBlockIds.length) {
      selectedAnchorId = ''
    }
    dispatchBlockSelection()
  }

  function clearSelectedBlock() {
    setSelectedBlocksByIds([])
  }

  function refreshSelectedBlock() {
    if (!editor || !selectedBlockIds.length) return
    setSelectedBlocksByIds(selectedBlockIds, selectedAnchorId)
  }

  function selectRangeTo(targetId: string) {
    const all = allBlockElements()
    const ids = all.map((el) => blockIdOf(el)).filter(Boolean)
    const anchor = selectedAnchorId && ids.includes(selectedAnchorId) ? selectedAnchorId : ids[0] || ''
    const from = ids.indexOf(anchor)
    const to = ids.indexOf(targetId)
    if (from < 0 || to < 0) {
      setSelectedBlocksByIds([targetId], targetId)
      return
    }
    const [start, end] = from <= to ? [from, to] : [to, from]
    setSelectedBlocksByIds(ids.slice(start, end + 1), anchor)
  }

  function toggleSelectedBlock(targetId: string) {
    const has = selectedBlockIds.includes(targetId)
    const next = has
      ? selectedBlockIds.filter((id) => id !== targetId)
      : [...selectedBlockIds, targetId]
    setSelectedBlocksByIds(next, has ? selectedAnchorId : targetId)
  }

  function rectFromPoints(a: { x: number; y: number }, b: { x: number; y: number }) {
    const left = Math.min(a.x, b.x)
    const top = Math.min(a.y, b.y)
    const width = Math.abs(a.x - b.x)
    const height = Math.abs(a.y - b.y)
    return { left, top, width, height }
  }

  function intersectsViewportRect(a: { left: number; top: number; width: number; height: number }, b: DOMRect) {
    const aRight = a.left + a.width
    const aBottom = a.top + a.height
    const bRight = b.left + b.width
    const bBottom = b.top + b.height
    return !(aRight < b.left || bRight < a.left || aBottom < b.top || bBottom < a.top)
  }

  function blockIdsInMarquee(rect: { left: number; top: number; width: number; height: number }) {
    const ids: string[] = []
    for (const el of allBlockElements()) {
      const id = blockIdOf(el)
      if (!id) continue
      if (intersectsViewportRect(rect, el.getBoundingClientRect())) {
        ids.push(id)
      }
    }
    return ids
  }

  function handleMarqueeMouseMove(event: MouseEvent) {
    if (!dragSelectSeed) return
    const current = { x: event.clientX, y: event.clientY }
    const rect = rectFromPoints(dragSelectSeed, current)
    if (!dragSelecting) {
      if (rect.width < 10 && rect.height < 10) return
      dragSelecting = true
      suppressClickOnce = true
      window.getSelection()?.removeAllRanges()
    }
    event.preventDefault()
    dragRect = rect
    const ids = blockIdsInMarquee(rect)
    if (ids.length) {
      setSelectedBlocksByIds(ids, ids[0])
    } else {
      setSelectedBlocksByIds([])
    }
  }

  function finishMarqueeSelection() {
    dragSelectSeed = null
    dragSelecting = false
    dragRect = { left: 0, top: 0, width: 0, height: 0 }
    window.removeEventListener('mousemove', handleMarqueeMouseMove)
    window.removeEventListener('mouseup', handleMarqueeMouseUp)
  }

  function handleMarqueeMouseUp() {
    finishMarqueeSelection()
  }

  function handleEditorMouseDown(event: MouseEvent) {
    if (!editor) return
    if (event.button !== 0) return
    const target = event.target as HTMLElement | null
    if (!target || !editor.contains(target)) return
    if (target.closest('a,button,input,textarea,select,[data-wa-no-marquee="1"]')) return
    dragSelectSeed = { x: event.clientX, y: event.clientY }
    dragSelecting = false
    dragRect = { left: event.clientX, top: event.clientY, width: 0, height: 0 }
    window.addEventListener('mousemove', handleMarqueeMouseMove)
    window.addEventListener('mouseup', handleMarqueeMouseUp)
  }

  function handleEditorClick(event: MouseEvent) {
    if (suppressClickOnce) {
      suppressClickOnce = false
      return
    }
    const target = event.target as HTMLElement | null
    if (!target || !editor) return
    const block = target.closest('[data-block-id]') as HTMLElement | null
    if (!block || !editor.contains(block)) {
      clearSelectedBlock()
      return
    }
    const id = blockIdOf(block)
    if (!id) {
      clearSelectedBlock()
      return
    }
    const appendMode = event.ctrlKey || event.metaKey
    if (event.shiftKey) {
      selectRangeTo(id)
      return
    }
    if (appendMode) {
      toggleSelectedBlock(id)
      return
    }
    setSelectedBlocksByIds([id], id)
  }

  function handleEditableFocus(event: FocusEvent) {
    const el = findEditableRoot(event.target)
    if (!el) return
    editingEl = el
    editingKey = String(el.dataset.blockId || el.dataset.sectionId || el.dataset.docTitle || '')
  }

  function handleEditableBlur(event: FocusEvent) {
    const el = findEditableRoot(event.target)
    if (!el) return
    commitEditableElement(el)
    if (editingEl === el) {
      editingEl = null
      editingKey = ''
    }
    if (pendingRenderSig && pendingRenderSig !== lastRenderSig) {
      syncFromStore()
    }
  }

  function handleEditableInput(event: Event) {
    if (composing) return
    const el = findEditableRoot(event.target)
    if (!el) return
    scheduleCommit(el)
  }

  function handleCompositionStart() {
    composing = true
  }

  function handleCompositionEnd(event: CompositionEvent) {
    composing = false
    handleEditableInput(event)
  }


  function htmlToMarkdown(html: string): string {
    const container = document.createElement('div')
    container.innerHTML = html
    const blocks: string[] = []

    const inlineText = (node: Node): string => {
      if (node.nodeType === Node.TEXT_NODE) return (node.textContent || '').replace(/\s+/g, ' ')
      if (!(node instanceof HTMLElement)) return ''
      const tag = node.tagName.toLowerCase()
      if (tag === 'br') return '\n'
      if (tag === 'strong' || tag === 'b') return `**${childrenInline(node)}**`
      if (tag === 'em' || tag === 'i') return `*${childrenInline(node)}*`
      if (tag === 'u') return `++${childrenInline(node)}++`
      if (tag === 'del' || tag === 's') return `~~${childrenInline(node)}~~`
      if (tag === 'mark') return `==${childrenInline(node)}==`
      if (tag === 'code') return '`' + childrenInline(node) + '`'
      if (tag === 'a') {
        const href = node.getAttribute('href') || ''
        const text = childrenInline(node)
        return href ? `[${text}](${href})` : text
      }
      if (tag === 'span') return childrenInline(node)
      return childrenInline(node)
    }

    const childrenInline = (el: HTMLElement): string => {
      const out: string[] = []
      el.childNodes.forEach((child) => out.push(inlineText(child)))
      return out.join('').replace(/\s+/g, ' ').trim()
    }

    const pushParagraph = (text: string) => {
      const t = text.replace(/\s+$/g, '').trim()
      if (t) blocks.push(t)
    }

    const walkBlock = (node: Node) => {
      if (!(node instanceof HTMLElement)) return
      const tag = node.tagName.toLowerCase()

      if (node.dataset.waFigure === '1') {
        const cap = node.querySelector('figcaption')?.textContent?.trim() || '图示'
        blocks.push(`[[FIGURE:{"caption":"${escapeJson(cap)}"}]]`)
        return
      }
      if (node.dataset.waTable === '1') {
        const cap = node.querySelector('.wa-table-caption')?.textContent?.trim() || '表格'
        blocks.push(`[[TABLE:{"caption":"${escapeJson(cap)}"}]]`)
        return
      }

      if (tag === 'h1' || tag === 'h2' || tag === 'h3') {
        const level = tag === 'h1' ? 1 : tag === 'h2' ? 2 : 3
        const text = childrenInline(node)
        if (text) blocks.push(`${'#'.repeat(level)} ${text}`)
        return
      }

      if (tag === 'pre') {
        const text = node.textContent || ''
        blocks.push('```\n' + text.replace(/\n+$/, '') + '\n```')
        return
      }

      if (tag === 'blockquote') {
        const text = childrenInline(node)
        if (text) blocks.push('> ' + text)
        return
      }

      if (tag === 'ul' || tag === 'ol') {
        const items = Array.from(node.querySelectorAll(':scope > li'))
        items.forEach((li, idx) => {
          const t = childrenInline(li)
          if (!t) return
          blocks.push(tag === 'ol' ? `${idx + 1}. ${t}` : `- ${t}`)
        })
        return
      }

      if (tag === 'p' || tag === 'div') {
        const text = childrenInline(node)
        pushParagraph(text)
        return
      }

      if (tag === 'figure') {
        const cap = node.querySelector('figcaption')?.textContent?.trim() || '图示'
        blocks.push(`[[FIGURE:{"caption":"${escapeJson(cap)}"}]]`)
        return
      }

      if (tag === 'table') {
        blocks.push(`[[TABLE:{"caption":"表格"}]]`)
        return
      }

      node.childNodes.forEach((child) => walkBlock(child))
    }

    container.childNodes.forEach((node) => walkBlock(node))
    return blocks.join('\n\n').trim()
  }

  function htmlToDocIr(html: string): Record<string, unknown> | null {
    const container = document.createElement('div')
    container.innerHTML = html
    const blocks: Array<Record<string, unknown>> = []
    let title = ''

    const inlineText = (node: Node): string => {
      if (node.nodeType === Node.TEXT_NODE) return (node.textContent || '').replace(/\s+/g, ' ')
      if (!(node instanceof HTMLElement)) return ''
      const tag = node.tagName.toLowerCase()
      if (tag === 'br') return '\n'
      if (tag === 'strong' || tag === 'b') return `**${childrenInline(node)}**`
      if (tag === 'em' || tag === 'i') return `*${childrenInline(node)}*`
      if (tag === 'u') return `++${childrenInline(node)}++`
      if (tag === 'del' || tag === 's') return `~~${childrenInline(node)}~~`
      if (tag === 'mark') return `==${childrenInline(node)}==`
      if (tag === 'code') return '`' + childrenInline(node) + '`'
      if (tag === 'a') {
        const href = node.getAttribute('href') || ''
        const text = childrenInline(node)
        return href ? `[${text}](${href})` : text
      }
      if (tag === 'span') return childrenInline(node)
      return childrenInline(node)
    }

    const childrenInline = (el: HTMLElement): string => {
      const out: string[] = []
      el.childNodes.forEach((child) => out.push(inlineText(child)))
      return out.join('').replace(/\s+/g, ' ').trim()
    }

    const pushParagraph = (text: string, id?: string) => {
      const t = text.replace(/\s+$/g, '').trim()
      if (t) blocks.push({ type: 'paragraph', text: t, id: id || undefined })
    }

    const HEADING_HINTS = [
      '摘要',
      '引言',
      '绪论',
      '前言',
      '背景',
      '相关技术概述',
      '关键技术',
      '研究方法',
      '实验',
      '结果',
      '讨论',
      '结论',
      '总结',
      '展望',
      '参考文献',
      '附录',
      '致谢',
      'Abstract'
    ]

    const NUM_HEADING_RE = /^(\d+(?:\.\d+){0,2})\s*[\.、:：-]?\s*([^\s].{0,24})$/
    const CN_NUM_HEADING_RE = /^([一二三四五六七八九十]+)\s*[、.．:：-]?\s*([^\s].{0,24})$/

    const splitTitleAndRest = (text: string) => {
      const s = String(text || '').trim()
      if (!s) return { title: '', rest: '' }
      const repeated = /^(.{2,18})\s*\1(.+)$/.exec(s)
      if (repeated) {
        return { title: String(repeated[1] || '').trim(), rest: String(repeated[2] || '').trim() }
      }
      for (const kw of HEADING_HINTS) {
        const idx = s.indexOf(kw)
        if (idx > 1 && idx <= 20) {
          const left = s.slice(0, idx).trim()
          const right = s.slice(idx).trim()
          if (left.length >= 2 && right.length >= 2) {
            return { title: left, rest: right }
          }
        }
      }
      const numIdx = s.search(/\b\d+(?:\.\d+){0,2}\b/)
      if (numIdx > 1 && numIdx <= 20) {
        return { title: s.slice(0, numIdx).trim(), rest: s.slice(numIdx).trim() }
      }
      return { title: s, rest: '' }
    }

    const detectHeadingFromText = (text: string) => {
      const s = String(text || '').trim()
      if (!s) return null
      if (s.length <= 12 && HEADING_HINTS.includes(s)) {
        return { level: 2, heading: s, rest: '' }
      }
      const mNum = NUM_HEADING_RE.exec(s)
      if (mNum) {
        const num = String(mNum[1] || '').trim()
        const name = String(mNum[2] || '').trim()
        const dots = num.split('.').length - 1
        const level = Math.min(4, 2 + Math.max(0, dots))
        return { level, heading: `${num} ${name}`.trim(), rest: '' }
      }
      const mCn = CN_NUM_HEADING_RE.exec(s)
      if (mCn) {
        const num = String(mCn[1] || '').trim()
        const name = String(mCn[2] || '').trim()
        return { level: 2, heading: `${num} ${name}`.trim(), rest: '' }
      }
      if (s.length > 20) {
        for (const kw of HEADING_HINTS) {
          if (s.startsWith(kw) && s.length > kw.length + 8) {
            return { level: 2, heading: kw, rest: s.slice(kw.length).trim() }
          }
        }
      }
      return null
    }

    const emitTextAsBlocks = (text: string, id?: string) => {
      const s = String(text || '').trim()
      if (!s) return
      const heading = detectHeadingFromText(s)
      if (heading) {
        blocks.push({ type: 'heading', level: heading.level, text: heading.heading })
        if (heading.rest) pushParagraph(heading.rest, id)
        return
      }
      pushParagraph(s, id)
    }

    const extractTable = (node: HTMLElement): Record<string, unknown> | null => {
      const tableEl = node.tagName.toLowerCase() === 'table' ? node : (node.querySelector('table') as HTMLElement | null)
      if (!tableEl) return null
      const captionEl =
        node.querySelector('figcaption') ||
        node.querySelector('.wa-table-caption') ||
        tableEl.querySelector('caption')
      const caption = captionEl ? (captionEl.textContent || '').trim() : ''
      const cols: string[] = []
      const rows: Array<Array<string>> = []
      const headCells = Array.from(tableEl.querySelectorAll('thead th'))
      if (headCells.length) {
        headCells.forEach((c) => cols.push((c.textContent || '').trim()))
      }
      const rowEls = Array.from(tableEl.querySelectorAll('tr'))
      rowEls.forEach((row, idx) => {
        const cells = Array.from(row.querySelectorAll('td, th'))
        if (!cells.length) return
        const vals = cells.map((c) => (c.textContent || '').trim())
        if (!cols.length && idx === 0 && row.querySelectorAll('th').length === cells.length) {
          cols.push(...vals)
          return
        }
        rows.push(vals)
      })
      return { caption, columns: cols, rows }
    }

    const extractFigure = (node: HTMLElement): Record<string, unknown> | null => {
      const fig = node.tagName.toLowerCase() === 'figure' ? node : (node.querySelector('figure') as HTMLElement | null)
      const capEl = fig?.querySelector('figcaption') || node.querySelector('figcaption')
      const caption = capEl ? (capEl.textContent || '').trim() : ''
      const rawSpec = fig?.dataset.figureSpec || ''
      let spec: Record<string, unknown> = {}
      if (rawSpec) {
        try {
          const parsed = JSON.parse(decodeURIComponent(rawSpec))
          if (parsed && typeof parsed === 'object') spec = parsed
        } catch {
          spec = {}
        }
      }
      if (caption) spec = { ...spec, caption }
      return Object.keys(spec).length ? spec : { caption }
    }

    const walkBlock = (node: Node) => {
      if (!(node instanceof HTMLElement)) return
      const tag = node.tagName.toLowerCase()
      if (tag === 'div' && node.classList.contains('wa-doc')) {
        node.childNodes.forEach((child) => walkBlock(child))
        return
      }
      if (node.classList.contains('wa-header') || node.classList.contains('wa-footer')) {
        return
      }
      if (node.classList.contains('wa-body')) {
        node.childNodes.forEach((child) => walkBlock(child))
        return
      }
      if (node.classList.contains('wa-title')) {
        const t = childrenInline(node)
        const split = splitTitleAndRest(t)
        if (split.title && !title) title = split.title
        if (split.rest) {
          emitTextAsBlocks(split.rest)
        }
        return
      }
      if (node.dataset.waTable === '1' || node.classList.contains('wa-table') || tag === 'table') {
        const table = extractTable(node)
        if (table) blocks.push({ type: 'table', table, id: node.dataset.blockId || undefined })
        return
      }
      if (node.dataset.waFigure === '1' || node.classList.contains('wa-figure') || tag === 'figure') {
        const fig = extractFigure(node)
        if (fig) blocks.push({ type: 'figure', figure: fig, id: node.dataset.blockId || undefined })
        return
      }
      if (tag === 'h1' || tag === 'h2' || tag === 'h3' || tag === 'h4' || tag === 'h5' || tag === 'h6') {
        const level = Number(tag.slice(1))
        const text = childrenInline(node)
        if (text) {
          if (level === 1 && !title) {
            title = text
            return
          }
          blocks.push({ type: 'heading', level, text })
        }
        return
      }
      if (tag === 'ul' || tag === 'ol') {
        const items = Array.from(node.querySelectorAll(':scope > li'))
          .map((li) => childrenInline(li))
          .filter(Boolean)
        if (items.length) blocks.push({ type: 'list', items, ordered: tag === 'ol', id: node.dataset.blockId || undefined })
        return
      }
      if (tag === 'blockquote') {
        const text = childrenInline(node)
        if (text) blocks.push({ type: 'paragraph', text })
        return
      }
      if (tag === 'pre') {
        const text = node.textContent || ''
        pushParagraph(text.replace(/\n+$/, ''), node.dataset.blockId || undefined)
        return
      }
      if (tag === 'p' || tag === 'div') {
        const text = childrenInline(node)
        emitTextAsBlocks(text, node.dataset.blockId || undefined)
        return
      }
      node.childNodes.forEach((child) => walkBlock(child))
    }

    container.childNodes.forEach((node) => walkBlock(node))
    const docTitle = title || deriveTitleFromBlocks(blocks) || '自动生成文档'
    return buildDocIrFromBlocks(blocks, docTitle)
  }

  function deriveTitleFromBlocks(blocks: Array<Record<string, unknown>>): string {
    for (const b of blocks) {
      if (String(b.type || '') === 'heading' && Number(b.level || 0) === 1 && b.text) {
        return String(b.text || '').trim()
      }
      if (String(b.type || '') === 'paragraph' && b.text) {
        const raw = String(b.text || '').trim()
        if (raw) return raw.slice(0, 24)
      }
    }
    return ''
  }

  function buildDocIrFromBlocks(blocks: Array<Record<string, unknown>>, title: string): Record<string, unknown> {
    const docTitle = String(title || '').trim() || '自动生成文档'
    const sections: Array<Record<string, unknown>> = []
    const stack: Array<{ level: number; node: Record<string, unknown> }> = []
    let orphan: Array<Record<string, unknown>> = []

    const pushImplicit = () => {
      if (!orphan.length) return
      const implicit = {
        id: makeId(),
        title: docTitle,
        level: 1,
        blocks: orphan,
        children: []
      }
      sections.push(implicit)
      stack.push({ level: 1, node: implicit })
      orphan = []
    }

    for (const b of blocks) {
      const t = String(b.type || '').toLowerCase()
      if (t === 'heading') {
        const level = Math.min(6, Math.max(1, Number(b.level || 1)))
        const text = String(b.text || '').trim() || '章节'
        const node: Record<string, unknown> = { id: makeId(), title: text, level, blocks: [], children: [] }
        if (orphan.length && stack.length === 0) pushImplicit()
        while (stack.length && stack[stack.length - 1].level >= level) stack.pop()
        if (stack.length) {
          ;(stack[stack.length - 1].node.children as Array<Record<string, unknown>>).push(node)
        } else {
          sections.push(node)
        }
        stack.push({ level, node })
        continue
      }
      const docBlock = toDocIrBlock(b)
      if (!docBlock) continue
      if (stack.length) {
        ;(stack[stack.length - 1].node.blocks as Array<Record<string, unknown>>).push(docBlock)
      } else {
        orphan.push(docBlock)
      }
    }

    if (orphan.length && !sections.length) {
      sections.push({ id: makeId(), title: docTitle, level: 1, blocks: orphan, children: [] })
    }
    return { title: docTitle, sections }
  }

  function toDocIrBlock(block: Record<string, unknown>): Record<string, unknown> | null {
    const t = String(block.type || 'paragraph').toLowerCase()
    const rawId = String(block.id || '').trim()
    const id = rawId || makeId()
    if (t === 'paragraph') {
      const text = String(block.text || '').trim()
      if (!text) return null
      return { id, type: 'paragraph', text }
    }
    if (t === 'list') {
      const items = Array.isArray(block.items) ? block.items.map((v) => String(v || '').trim()).filter(Boolean) : []
      if (!items.length) return null
      const ordered = Boolean(block.ordered)
      return { id, type: 'list', items, ordered }
    }
    if (t === 'table') {
      return { id, type: 'table', table: block.table || {} }
    }
    if (t === 'figure') {
      return { id, type: 'figure', figure: block.figure || {} }
    }
    const text = String(block.text || '').trim()
    if (!text) return null
    return { id, type: 'paragraph', text }
  }

  function makeId(): string {
    if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
      return (crypto as Crypto).randomUUID().replace(/-/g, '')
    }
    return `b${Math.random().toString(16).slice(2)}${Date.now().toString(16)}`
  }

  function escapeJson(text: string) {
    return text.replace(/\\/g, '\\\\').replace(/"/g, '\\"')
  }

  function ensureEditableFocus(): HTMLElement | null {
    if (!editor) return null
    const active = document.activeElement as HTMLElement | null
    if (active && editor.contains(active) && active.isContentEditable) return active
    const selected = selectedBlockEls[0] || null
    if (selected && selected.isContentEditable) {
      selected.focus()
      return selected
    }
    const first = editor.querySelector('[data-wa-edit="1"]') as HTMLElement | null
    if (first) {
      first.focus()
      return first
    }
    return null
  }

  function applyCommand(cmd: string) {
    if (!ensureEditableFocus()) return
    
    // 基础格式
    if (cmd === 'bold') return document.execCommand('bold')
    if (cmd === 'italic') return document.execCommand('italic')
    if (cmd === 'underline') return document.execCommand('underline')
    if (cmd === 'strikethrough') return document.execCommand('strikeThrough')
    if (cmd === 'superscript') return document.execCommand('superscript')
    if (cmd === 'subscript') return document.execCommand('subscript')
    
    // 标题
    if (cmd === 'heading1') return document.execCommand('formatBlock', false, 'H1')
    if (cmd === 'heading2') return document.execCommand('formatBlock', false, 'H2')
    if (cmd === 'heading3') return document.execCommand('formatBlock', false, 'H3')
    if (cmd === 'paragraph') return document.execCommand('formatBlock', false, 'P')
    
    // 列表与缩进
    if (cmd === 'list-bullet') return document.execCommand('insertUnorderedList')
    if (cmd === 'list-number') return document.execCommand('insertOrderedList')
    if (cmd === 'indent') return document.execCommand('indent')
    if (cmd === 'outdent') return document.execCommand('outdent')
    if (cmd === 'quote') return document.execCommand('formatBlock', false, 'BLOCKQUOTE')
    
    // 对齐
    if (cmd === 'align-left') return document.execCommand('justifyLeft')
    if (cmd === 'align-center') return document.execCommand('justifyCenter')
    if (cmd === 'align-right') return document.execCommand('justifyRight')
    if (cmd === 'align-justify') return document.execCommand('justifyFull')
    
    // 行距
    if (cmd.startsWith('line-height:')) {
      const height = cmd.slice(12)
      const sel = window.getSelection()
      if (sel && sel.rangeCount) {
        const range = sel.getRangeAt(0)
        let node = range.commonAncestorContainer
        if (node.nodeType === Node.TEXT_NODE) node = node.parentElement
        if (node instanceof HTMLElement) {
          let block = node.closest('p, div, h1, h2, h3, blockquote')
          if (block instanceof HTMLElement) block.style.lineHeight = height
        }
      }
      return
    }
    
    // 段间距
    if (cmd.startsWith('margin:')) {
      const margin = cmd.slice(7)
      const sel = window.getSelection()
      if (sel && sel.rangeCount) {
        const range = sel.getRangeAt(0)
        let node = range.commonAncestorContainer
        if (node.nodeType === Node.TEXT_NODE) node = node.parentElement
        if (node instanceof HTMLElement) {
          let block = node.closest('p, div, h1, h2, h3')
          if (block instanceof HTMLElement) block.style.margin = margin
        }
      }
      return
    }
    
    // 首行缩进
    if (cmd === 'indent-first') {
      const sel = window.getSelection()
      if (sel && sel.rangeCount) {
        const range = sel.getRangeAt(0)
        let node = range.commonAncestorContainer
        if (node.nodeType === Node.TEXT_NODE) node = node.parentElement
        if (node instanceof HTMLElement) {
          let block = node.closest('p, div')
          if (block instanceof HTMLElement) block.style.textIndent = '2em'
        }
      }
      return
    }
    
    // 颜色
    if (cmd.startsWith('color:')) {
      const color = cmd.slice(6)
      return document.execCommand('foreColor', false, color)
    }
    if (cmd.startsWith('bgcolor:')) {
      const color = cmd.slice(8)
      return document.execCommand('hiliteColor', false, color)
    }
    
    // 字体
    if (cmd.startsWith('font:')) {
      const font = cmd.slice(5)
      return document.execCommand('fontName', false, font)
    }
    
    // 字号
    if (cmd.startsWith('size:')) {
      const size = cmd.slice(5)
      const sel = window.getSelection()
      if (sel && sel.rangeCount) {
        const range = sel.getRangeAt(0)
        const span = document.createElement('span')
        span.style.fontSize = size + 'px'
        range.surroundContents(span)
      }
      return
    }
    
    // 代码块
    if (cmd === 'code') {
      const sel = window.getSelection()
      const text = sel && sel.rangeCount ? sel.getRangeAt(0).toString() : ''
      return document.execCommand('insertHTML', false, `<pre><code>${escapeHtml(text || '')}</code></pre>`)
    }
    
    // 图片
    if (cmd === 'image') {
      const input = document.createElement('input')
      input.type = 'file'
      input.accept = 'image/*'
      input.onchange = async (e) => {
        const file = (e.target as HTMLInputElement).files?.[0]
        if (!file) return
        const reader = new FileReader()
        reader.onload = (ev) => {
          const dataUrl = ev.target?.result as string
          document.execCommand('insertHTML', false, `<img src="${dataUrl}" alt="图片" style="max-width:100%;height:auto;" />`)
        }
        reader.readAsDataURL(file)
      }
      input.click()
      return
    }
    
    // 表格
    if (cmd === 'table') {
      const rows = prompt('行数：', '3')
      const cols = prompt('列数：', '3')
      if (!rows || !cols) return
      let html = '<table style="border-collapse:collapse;width:100%;margin:10px 0;">'
      for (let i = 0; i < parseInt(rows); i++) {
        html += '<tr>'
        for (let j = 0; j < parseInt(cols); j++) {
          html += '<td style="border:1px solid #ccc;padding:8px;min-width:80px;">　</td>'
        }
        html += '</tr>'
      }
      html += '</table>'
      return document.execCommand('insertHTML', false, html)
    }
    
    // 链接
    if (cmd === 'link') {
      const url = prompt('请输入链接地址：', 'https://')
      if (url) document.execCommand('createLink', false, url)
      return
    }
    
    // 水平线
    if (cmd === 'hr') {
      return document.execCommand('insertHTML', false, '<hr style="border:none;border-top:1px solid #ddd;margin:16px 0;" />')
    }
    
    // 数学公式
    if (cmd === 'math-inline') {
      const latex = prompt('输入行内公式（LaTeX）：', 'x^2 + y^2 = r^2')
      if (latex) {
        document.execCommand('insertHTML', false, `<span class="math-inline" data-latex="${escapeHtml(latex)}">$${latex}$</span>`)
      }
      return
    }
    
    if (cmd === 'math-block') {
      const latex = prompt('输入公式块（LaTeX）：', '\\int_{-\\infty}^{\\infty} e^{-x^2} dx = \\sqrt{\\pi}')
      if (latex) {
        document.execCommand('insertHTML', false, `<div class="math-block" data-latex="${escapeHtml(latex)}">$$${latex}$$</div>`)
      }
      return
    }
    
    // 脚注
    if (cmd === 'footnote') {
      const text = prompt('脚注内容：')
      if (!text) return
      const footnoteId = 'fn-' + Date.now()
      const footnoteHtml = `<sup><a href="#${footnoteId}" id="ref-${footnoteId}" style="color:#a5722a;text-decoration:none;">[${getFootnoteNumber()}]</a></sup>`
      document.execCommand('insertHTML', false, footnoteHtml)
      addFootnoteToEnd(footnoteId, text, getFootnoteNumber())
      return
    }
    
    // 生成目录
    if (cmd === 'toc') {
      const toc = generateTableOfContents()
      document.execCommand('insertHTML', false, toc)
      return
    }
    
    // 撤销重做
    if (cmd === 'undo') return undoHistory()
    if (cmd === 'redo') return redoHistory()
    if (cmd === 'clear-format') return document.execCommand('removeFormat')
  }

  function handleKeydown(e: KeyboardEvent) {
    const ctrl = e.ctrlKey || e.metaKey
    if (ctrl && e.key === 'b') {
      e.preventDefault()
      applyCommand('bold')
    }
    if (ctrl && e.key === 'i') {
      e.preventDefault()
      applyCommand('italic')
    }
    if (ctrl && e.key === 'u') {
      e.preventDefault()
      applyCommand('underline')
    }
    if (ctrl && e.shiftKey && e.key === 'X') {
      e.preventDefault()
      applyCommand('strikethrough')
    }
    if (ctrl && e.key === 'z') {
      e.preventDefault()
      applyCommand('undo')
    }
    if (ctrl && e.key === 'y') {
      e.preventDefault()
      applyCommand('redo')
    }
    if (ctrl && e.key === 'k') {
      e.preventDefault()
      applyCommand('link')
    }
    if (ctrl && e.key === 'f') {
      e.preventDefault()
      showFindReplace = true
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      const el = findEditableRoot(e.target)
      if (el && el.dataset.blockId) {
        const tag = el.tagName.toLowerCase()
        if (tag === 'ul' || tag === 'ol') {
          e.preventDefault()
          const doc = $docIr
          if (!doc || typeof doc !== 'object') return
          const blockId = String(el.dataset.blockId)
          const sel = window.getSelection()
          const anchor = sel?.anchorNode
          const anchorEl = anchor instanceof HTMLElement ? anchor : anchor?.parentElement
          const li = anchorEl ? (anchorEl.closest('li') as HTMLElement | null) : null
          if (!li || !el.contains(li)) return
          const listItems = Array.from(el.querySelectorAll(':scope > li')) as HTMLElement[]
          const idx = listItems.indexOf(li)
          if (idx < 0) return

          let beforeText = ''
          let afterText = ''
          const split = splitInlineAtSelection(li)
          if (split) {
            beforeText = split.before
            afterText = split.after
          } else {
            const rawText = plainTextFromElement(li)
            const caret = getCaretOffset(li)
            const offset = caret == null ? rawText.length : Math.max(0, Math.min(rawText.length, caret))
            beforeText = rawText.slice(0, offset)
            afterText = rawText.slice(offset)
          }
          const before = normalizeInlineText(beforeText)
          const after = normalizeInlineText(afterText)

          if (!before && !after) {
            const remaining = listItems
              .map((item, i) => (i === idx ? null : normalizeInlineText(inlineFromElement(item))))
              .filter((v) => v !== null) as string[]
            if (remaining.length) {
              const nextDoc = updateBlock(doc, blockId, { type: 'list', items: remaining, ordered: tag === 'ol' })
              if (nextDoc) {
                const newBlock: Record<string, unknown> = { id: makeId(), type: 'paragraph', text: '' }
                const finalDoc = insertBlockAfter(nextDoc, blockId, newBlock)
                if (finalDoc) {
                  pendingFocusBlockId = String(newBlock.id || '')
                  applyDocIrUpdate(finalDoc)
                  return
                }
                applyDocIrUpdate(nextDoc)
              }
            } else {
              const nextDoc = updateBlock(doc, blockId, { type: 'paragraph', text: '', items: [], ordered: false })
              if (nextDoc) {
                pendingFocusBlockId = blockId
                applyDocIrUpdate(nextDoc)
              }
            }
            return
          }

          const items = listItems.map((item, i) =>
            i === idx ? before : normalizeInlineText(inlineFromElement(item))
          )
          items.splice(idx + 1, 0, after)
          const nextDoc = updateBlock(doc, blockId, { type: 'list', items, ordered: tag === 'ol' })
          if (nextDoc) {
            pendingFocusBlockId = blockId
            applyDocIrUpdate(nextDoc)
          }
          return
        }
        if (tag === 'p' || /^h[1-6]$/.test(tag)) {
          e.preventDefault()
          const doc = $docIr
          if (!doc || typeof doc !== 'object') return
          const blockId = String(el.dataset.blockId)
          const rawText = plainTextFromElement(el)
          const caret = getCaretOffset(el)
          const offset = caret == null ? rawText.length : Math.max(0, Math.min(rawText.length, caret))
          const beforeRaw = rawText.slice(0, offset)
          const afterRaw = rawText.slice(offset)
          const beforeText = normalizeInlineText(beforeRaw)
          const afterText = normalizeInlineText(afterRaw)
          const blockStyle = extractBlockStyle(el)
          const isHeading = /^h[1-6]$/.test(tag)

          if (offset === 0) {
            const newBlock: Record<string, unknown> = { id: makeId(), type: 'paragraph', text: '' }
            if (blockStyle && tag === 'p') newBlock.style = blockStyle
            const nextDoc = insertBlockBefore(doc, blockId, newBlock)
            if (nextDoc) {
              pendingFocusBlockId = String(newBlock.id || '')
              applyDocIrUpdate(nextDoc)
            }
            return
          }

          if (offset >= rawText.length) {
            const newBlock: Record<string, unknown> = { id: makeId(), type: 'paragraph', text: '' }
            if (blockStyle && tag === 'p') newBlock.style = blockStyle
            const nextDoc = insertBlockAfter(doc, blockId, newBlock)
            if (nextDoc) {
              pendingFocusBlockId = String(newBlock.id || '')
              applyDocIrUpdate(nextDoc)
            }
            return
          }

          let nextDoc: Record<string, unknown> | null = null
          if (isHeading) {
            const level = Number(tag.slice(1))
            const payload: Record<string, unknown> = { type: 'heading', level, text: beforeText.replace(/\n+/g, ' ').trim() }
            if (blockStyle) payload.style = blockStyle
            nextDoc = updateBlock(doc, blockId, payload)
          } else {
            const payload: Record<string, unknown> = { type: 'paragraph', text: beforeText }
            if (blockStyle) payload.style = blockStyle
            nextDoc = updateBlock(doc, blockId, payload)
          }

          const newBlock: Record<string, unknown> = { id: makeId(), type: 'paragraph', text: afterText }
          if (!isHeading && blockStyle) newBlock.style = blockStyle
          const baseDoc = nextDoc || doc
          const finalDoc = insertBlockAfter(baseDoc, blockId, newBlock)
          if (finalDoc) {
            pendingFocusBlockId = String(newBlock.id || '')
            applyDocIrUpdate(finalDoc)
          }
        }
      }
    }
  }

  let showFindReplace = false
  let findText = ''
  let replaceText = ''
  let showFontPanel = false
  let showColorPanel = false
  let showBgColorPanel = false
  let showLineHeightPanel = false
  let showTableMenu = false
  const figureCache = new Map<string, string>()
  
  const fontList = ['宋体', '黑体', '微软雅黑', '楷体', 'Arial', 'Times New Roman', 'Courier New', 'Georgia', 'Verdana']
  const fontSizes = [12, 14, 16, 18, 20, 22, 24, 28, 32, 36, 42, 48, 56, 64, 72]
  const colors = ['#000000', '#333333', '#666666', '#999999', '#CCCCCC', '#FFFFFF', 
                  '#FF0000', '#FF6600', '#FFCC00', '#00FF00', '#00CCFF', '#0000FF', '#9900FF', '#FF00FF']
  const lineHeights = [1.0, 1.15, 1.5, 2.0, 2.5, 3.0]

  function findNext() {
    if (!findText) return
    window.find(findText, false, false, true, false, true, false)
  }

  function replaceNext() {
    if (!findText) return
    const sel = window.getSelection()
    if (sel && sel.toString().toLowerCase() === findText.toLowerCase()) {
      document.execCommand('insertHTML', false, replaceText)
    }
    findNext()
  }

  function replaceAll() {
    const regex = new RegExp(escapeRegex(findText), 'gi')
    if (!findText) return
    if ($docIr && typeof $docIr === 'object') {
      const nextDoc = replaceInDocIr($docIr as Record<string, unknown>, regex, replaceText)
      if (nextDoc) applyDocIrUpdate(nextDoc)
      showFindReplace = false
      return
    }
    if (!editor) return
    let html = editor.innerHTML
    html = html.replace(regex, replaceText)
    editor.innerHTML = html
    markEditableBlocks()
    showFindReplace = false
  }

  function escapeRegex(text: string) {
    return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  }

  function mergeTableCells() {
    const sel = window.getSelection()
    if (!sel || !sel.rangeCount) return
    const cell = sel.anchorNode?.parentElement?.closest('td, th')
    if (!cell) return alert('请先选中表格单元格')
    const nextCell = cell.nextElementSibling
    if (!nextCell || (nextCell.tagName !== 'TD' && nextCell.tagName !== 'TH')) {
      return alert('无法合并：需要选中相邻单元格')
    }
    const colspan = parseInt(cell.getAttribute('colspan') || '1')
    cell.setAttribute('colspan', String(colspan + 1))
    nextCell.remove()
  }

  function insertTableRow() {
    const sel = window.getSelection()
    if (!sel || !sel.rangeCount) return
    const cell = sel.anchorNode?.parentElement?.closest('td, th')
    if (!cell) return alert('请先选中表格单元格')
    const row = cell.parentElement as HTMLTableRowElement
    const newRow = row.cloneNode(true) as HTMLTableRowElement
    newRow.querySelectorAll('td, th').forEach(c => (c.textContent = '　'))
    row.parentElement?.insertBefore(newRow, row.nextSibling)
  }

  function insertTableCol() {
    const sel = window.getSelection()
    if (!sel || !sel.rangeCount) return
    const cell = sel.anchorNode?.parentElement?.closest('td, th')
    if (!cell) return alert('请先选中表格单元格')
    const cellIndex = Array.from(cell.parentElement?.children || []).indexOf(cell)
    const table = cell.closest('table')
    if (!table) return
    table.querySelectorAll('tr').forEach(row => {
      const newCell = document.createElement(cell.tagName.toLowerCase())
      newCell.textContent = '　'
      newCell.style.cssText = cell.style.cssText
      row.insertBefore(newCell, row.children[cellIndex + 1])
    })
  }

  function deleteTableRow() {
    const sel = window.getSelection()
    if (!sel || !sel.rangeCount) return
    const cell = sel.anchorNode?.parentElement?.closest('td, th')
    if (!cell) return alert('请先选中表格单元格')
    const row = cell.parentElement
    if (!row) return
    const table = row.parentElement
    if (table && table.children.length <= 1) return alert('无法删除：表格至少需要一行')
    row.remove()
  }

  function deleteTableCol() {
    const sel = window.getSelection()
    if (!sel || !sel.rangeCount) return
    const cell = sel.anchorNode?.parentElement?.closest('td, th')
    if (!cell) return alert('请先选中表格单元格')
    const cellIndex = Array.from(cell.parentElement?.children || []).indexOf(cell)
    const table = cell.closest('table')
    if (!table) return
    const firstRow = table.querySelector('tr')
    if (firstRow && firstRow.children.length <= 1) return alert('无法删除：表格至少需要一列')
    table.querySelectorAll('tr').forEach(row => {
      row.children[cellIndex]?.remove()
    })
  }

  function getFootnoteNumber(): number {
    if (!editor) return 1
    const existingNotes = editor.querySelectorAll('[id^="ref-fn-"]')
    return existingNotes.length + 1
  }

  function addFootnoteToEnd(id: string, text: string, num: number) {
    if (!editor) return
    let footnotesSection = editor.querySelector('.footnotes-section')
    if (!footnotesSection) {
      footnotesSection = document.createElement('div')
      footnotesSection.className = 'footnotes-section'
      footnotesSection.innerHTML = '<hr style="margin-top:40px;border:none;border-top:1px solid #ddd;" /><h3>脚注</h3>'
      editor.appendChild(footnotesSection)
    }
    const footnoteItem = document.createElement('div')
    footnoteItem.className = 'footnote-item'
    footnoteItem.id = id
    footnoteItem.innerHTML = `<sup>[${num}]</sup> ${text}`
    footnotesSection.appendChild(footnoteItem)
  }

  function generateTableOfContents(): string {
    if (!editor) return ''
    const headings = editor.querySelectorAll('h1, h2, h3')
    if (headings.length === 0) return '<p>未找到标题</p>'
    
    let toc = '<div class="toc-section" style="border:1px solid #ddd;padding:16px;border-radius:8px;background:rgba(255,255,255,0.5);margin:20px 0;"><h3>目录</h3><ul style="list-style:none;padding-left:0;">'
    
    headings.forEach((heading, index) => {
      const level = parseInt(heading.tagName[1])
      const text = heading.textContent || ''
      const id = 'heading-' + index
      heading.id = id
      const indent = (level - 1) * 20
      toc += `<li style="margin-left:${indent}px;margin-top:8px;"><a href="#${id}" style="color:#a5722a;text-decoration:none;">${text}</a></li>`
    })
    
    toc += '</ul></div>'
    return toc
  }

  function escapeHtml(text: string): string {
    return String(text || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;')
  }

  function renderMathInEditor() {
    if (!editor || !(window as any).renderMathInElement) return
    try {
      (window as any).renderMathInElement(editor, {
        delimiters: [
          {left: '$$', right: '$$', display: true},
          {left: '$', right: '$', display: false}
        ],
        throwOnError: false
      })
    } catch (e) {
      console.error('Math rendering error:', e)
    }
  }

  function highlightCodeBlocks() {
    if (!editor || !(window as any).Prism) return
    editor.querySelectorAll('pre code').forEach((block) => {
      (window as any).Prism.highlightElement(block)
    })
  }

  async function renderFiguresInEditor() {
    if (!editor) return
    const figures = Array.from(editor.querySelectorAll('.wa-figure[data-figure-spec]')) as HTMLElement[]
    for (const fig of figures) {
      if (fig.dataset.figureRendered === '1') continue
      const raw = fig.dataset.figureSpec || ''
      if (!raw) continue
      fig.dataset.figureRendered = '1'
      let spec: Record<string, unknown> | null = null
      try {
        spec = JSON.parse(decodeURIComponent(raw))
      } catch {
        spec = null
      }
      if (!spec) continue
      const cacheKey = JSON.stringify(spec)
      let svg = figureCache.get(cacheKey)
      const box = fig.querySelector('.wa-figure-box') as HTMLElement | null
      if (box) box.innerHTML = '<div class="wa-figure-loading">渲染中...</div>'
      if (!svg) {
        try {
          const resp = await fetch('/api/figure/render', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ spec })
          })
          if (!resp.ok) throw new Error(await resp.text())
          const data = await resp.json()
          svg = String(data.svg || '')
          if (svg) figureCache.set(cacheKey, svg)
        } catch {
          svg = ''
        }
      }
      if (box) {
        box.innerHTML = svg || '<div class="wa-figure-loading">渲染失败</div>'
      }
    }
  }

  function handleInput() {
    if (!editor) return
    const html = editor.innerHTML || ''
    const markdown = htmlToMarkdown(html)
    lastMarkdown = markdown
    if (historyTimer) clearTimeout(historyTimer)
    historyTimer = setTimeout(() => {
      const doc = htmlToDocIr(html)
      if (doc) {
        docIr.set(doc)
        docIrDirty.set(false)
        lastRenderSig = `doc:${docIrSignature(doc)}`
        renderMode = 'doc'
      } else {
        docIr.set(null)
        docIrDirty.set(true)
        lastRenderSig = `text:${markdown}`
        renderMode = 'text'
      }
      sourceText.set(markdown)
      setEmptyFlag(markdown)
      pushHistory(markdown)
      renderMathInEditor()
      highlightCodeBlocks()
      renderFiguresInEditor()
    }, 300)
  }

  const unsubscribe = editorCommand.subscribe((cmd) => {
    if (cmd) {
      applyCommand(cmd)
      editorCommand.set(null)
    }
  })

  onMount(() => {
    syncFromStore()
    if (!$docIr) {
      const fromText = String($sourceText || '').trim()
      const doc = fromText ? textToDocIr(fromText) : null
      if (doc) {
        docIr.set(doc)
        docIrDirty.set(false)
      } else {
        const baseTitle = '自动生成文档'
        docIr.set({
          title: baseTitle,
          sections: [
            {
              id: makeId(),
              title: baseTitle,
              level: 1,
              blocks: [{ id: makeId(), type: 'paragraph', text: '' }],
              children: []
            }
          ]
        })
        docIrDirty.set(false)
      }
    }
    sourceUnsub = sourceText.subscribe(() => syncFromStore())
    docIrUnsub = docIr.subscribe(() => syncFromStore())
    
    // 加载KaTeX样式
    const katexCSS = document.createElement('link')
    katexCSS.rel = 'stylesheet'
    katexCSS.href = 'https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css'
    document.head.appendChild(katexCSS)
    
    // 加载KaTeX脚本
    const katexScript = document.createElement('script')
    katexScript.src = 'https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js'
    katexScript.onload = () => {
      const autoRenderScript = document.createElement('script')
      autoRenderScript.src = 'https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js'
      autoRenderScript.onload = () => {
        renderMathInEditor()
      }
      document.head.appendChild(autoRenderScript)
    }
    document.head.appendChild(katexScript)
    
    // 加载Prism样式
    const prismCSS = document.createElement('link')
    prismCSS.rel = 'stylesheet'
    prismCSS.href = 'https://cdn.jsdelivr.net/npm/prismjs@1.29.0/themes/prism-tomorrow.min.css'
    document.head.appendChild(prismCSS)
    
    // 加载Prism脚本
    const prismScript = document.createElement('script')
    prismScript.src = 'https://cdn.jsdelivr.net/npm/prismjs@1.29.0/prism.min.js'
    prismScript.onload = () => {
      const langScripts = [
        'https://cdn.jsdelivr.net/npm/prismjs@1.29.0/components/prism-clike.min.js',
        'https://cdn.jsdelivr.net/npm/prismjs@1.29.0/components/prism-c.min.js',
        'https://cdn.jsdelivr.net/npm/prismjs@1.29.0/components/prism-cpp.min.js',
        'https://cdn.jsdelivr.net/npm/prismjs@1.29.0/components/prism-java.min.js',
        'https://cdn.jsdelivr.net/npm/prismjs@1.29.0/components/prism-javascript.min.js',
        'https://cdn.jsdelivr.net/npm/prismjs@1.29.0/components/prism-python.min.js',
        'https://cdn.jsdelivr.net/npm/prismjs@1.29.0/components/prism-sql.min.js'
      ]
      const loadScript = (src: string) =>
        new Promise<void>((resolve) => {
          const script = document.createElement('script')
          script.src = src
          script.async = false
          script.onload = () => resolve()
          script.onerror = () => resolve()
          document.head.appendChild(script)
        })
      void (async () => {
        for (const src of langScripts) {
          await loadScript(src)
        }
        setTimeout(() => highlightCodeBlocks(), 500)
      })()
    }
    document.head.appendChild(prismScript)
    
    // 图片懒加载
    const imgObserver = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting && entry.target instanceof HTMLImageElement) {
          const img = entry.target
          if (img.dataset.src) {
            img.src = img.dataset.src
            img.removeAttribute('data-src')
          }
        }
      })
    })
    
    const observer = new MutationObserver(() => {
      editor?.querySelectorAll('img[data-src]').forEach(img => imgObserver.observe(img))
    })
    
    if (editor) observer.observe(editor, { childList: true, subtree: true })
    
    return () => {
      finishMarqueeSelection()
      unsubscribe()
      if (sourceUnsub) sourceUnsub()
      imgObserver.disconnect()
      observer.disconnect()
      if (syncTimer) clearTimeout(syncTimer)
      if (historyTimer) clearTimeout(historyTimer)
    }
  })

  $: syncFromStore()
</script>

<div class={`panel editor ${paper ? 'paper' : ''}`}>
  {#if showToolbar}
    <div class="panel-header">
      <div class="panel-title">正文编辑</div>
      <div class="editor-stats">
        <span>{$wordCount} 字</span>
        <span>·</span>
        <span>{Math.ceil($wordCount / 400)} 分钟阅读</span>
      </div>
    </div>

    <!-- 扩展工具栏 -->
    <div class="extended-toolbar">
    <div class="toolbar-group">
      <button class="tool-btn" on:click={() => (showFontPanel = !showFontPanel)} title="字体">
        <span style="font-family: serif;">A</span>
      </button>
      {#if showFontPanel}
        <div class="dropdown-panel">
          {#each fontList as font}
            <button class="dropdown-item" on:click={() => { applyCommand('font:' + font); showFontPanel = false }} style="font-family: {font}">
              {font}
            </button>
          {/each}
        </div>
      {/if}
    </div>
    
    <div class="toolbar-group">
      <select class="tool-select" on:change={(e) => applyCommand('size:' + e.currentTarget.value)}>
        <option value="">字号</option>
        {#each fontSizes as size}
          <option value={size}>{size}pt</option>
        {/each}
      </select>
    </div>
    
    <div class="toolbar-group">
      <button class="tool-btn" on:click={() => (showColorPanel = !showColorPanel)} title="文字颜色">
        <span style="color: #FF0000;">A</span>
      </button>
      {#if showColorPanel}
        <div class="dropdown-panel color-grid">
          {#each colors as color}
            <button 
              class="color-item" 
              style="background: {color};" 
              aria-label={`文字颜色 ${color}`}
              on:click={() => { applyCommand('color:' + color); showColorPanel = false }}
            ></button>
          {/each}
        </div>
      {/if}
    </div>
    
    <div class="toolbar-group">
      <button class="tool-btn" on:click={() => (showBgColorPanel = !showBgColorPanel)} title="背景颜色">
        <span style="background: #FFFF00;">█</span>
      </button>
      {#if showBgColorPanel}
        <div class="dropdown-panel color-grid">
          {#each colors as color}
            <button 
              class="color-item" 
              style="background: {color};" 
              aria-label={`背景颜色 ${color}`}
              on:click={() => { applyCommand('bgcolor:' + color); showBgColorPanel = false }}
            ></button>
          {/each}
        </div>
      {/if}
    </div>
    
    <span class="separator"></span>
    
    <button class="tool-btn" on:click={() => applyCommand('align-left')} title="左对齐">≡</button>
    <button class="tool-btn" on:click={() => applyCommand('align-center')} title="居中">≡</button>
    <button class="tool-btn" on:click={() => applyCommand('align-right')} title="右对齐">≡</button>
    <button class="tool-btn" on:click={() => applyCommand('align-justify')} title="两端对齐">≡</button>
    
    <span class="separator"></span>
    
    <button class="tool-btn" on:click={() => applyCommand('superscript')} title="上标">x²</button>
    <button class="tool-btn" on:click={() => applyCommand('subscript')} title="下标">x₂</button>
    <button class="tool-btn" on:click={() => applyCommand('hr')} title="水平线">—</button>
    
    <span class="separator"></span>
    
    <div class="toolbar-group">
      <button class="tool-btn" on:click={() => (showLineHeightPanel = !showLineHeightPanel)} title="行距">
        ≣
      </button>
      {#if showLineHeightPanel}
        <div class="dropdown-panel">
          {#each lineHeights as height}
            <button class="dropdown-item" on:click={() => { applyCommand('line-height:' + height); showLineHeightPanel = false }}>
              {height}倍行距
            </button>
          {/each}
        </div>
      {/if}
    </div>
    
    <button class="tool-btn" on:click={() => applyCommand('indent-first')} title="首行缩进">¶</button>
    <button class="tool-btn" on:click={() => applyCommand('margin:10px 0')} title="段间距">⇕</button>
    
    <span class="separator"></span>
    
    <button class="tool-btn" on:click={() => applyCommand('math-inline')} title="行内公式">𝑓(𝑥)</button>
    <button class="tool-btn" on:click={() => applyCommand('math-block')} title="公式块">∫</button>
    
    <span class="separator"></span>
    
    <button class="tool-btn" on:click={() => applyCommand('footnote')} title="插入脚注">※</button>
    <button class="tool-btn" on:click={() => applyCommand('toc')} title="生成目录">☰</button>
    
    <span class="separator"></span>
    
    <div class="toolbar-group">
      <button class="tool-btn" on:click={() => (showTableMenu = !showTableMenu)} title="表格">
        ⊞
      </button>
      {#if showTableMenu}
        <div class="dropdown-panel">
          <button class="dropdown-item" on:click={() => { applyCommand('table'); showTableMenu = false }}>插入表格</button>
          <button class="dropdown-item" on:click={() => { mergeTableCells(); showTableMenu = false }}>合并单元格</button>
          <button class="dropdown-item" on:click={() => { insertTableRow(); showTableMenu = false }}>插入行</button>
          <button class="dropdown-item" on:click={() => { insertTableCol(); showTableMenu = false }}>插入列</button>
          <button class="dropdown-item" on:click={() => { deleteTableRow(); showTableMenu = false }}>删除行</button>
          <button class="dropdown-item" on:click={() => { deleteTableCol(); showTableMenu = false }}>删除列</button>
        </div>
      {/if}
    </div>
    </div>
  {/if}

  <div
    class="editable"
    data-render-mode={renderMode}
    bind:this={editor}
    contenteditable="false"
    role="region"
    aria-label="文档编辑区"
    on:mousedown={handleEditorMouseDown}
    on:input={handleEditableInput}
    on:focusin={handleEditableFocus}
    on:focusout={handleEditableBlur}
    on:compositionstart={handleCompositionStart}
    on:compositionend={handleCompositionEnd}
    on:click={handleEditorClick}
    on:keydown={handleKeydown}
  ></div>

  {#if dragSelecting}
    <div
      class="block-marquee"
      style={`left:${dragRect.left}px;top:${dragRect.top}px;width:${dragRect.width}px;height:${dragRect.height}px;`}
      aria-hidden="true"
    ></div>
  {/if}

  {#if showFindReplace}
    <div class="find-replace-panel">
      <div class="find-replace-row">
        <input type="text" bind:value={findText} placeholder="查找..." />
        <button class="btn-small" on:click={findNext}>下一个</button>
        <button class="btn-small" on:click={() => (showFindReplace = false)}>✕</button>
      </div>
      <div class="find-replace-row">
        <input type="text" bind:value={replaceText} placeholder="替换为..." />
        <button class="btn-small" on:click={replaceNext}>替换</button>
        <button class="btn-small" on:click={replaceAll}>全部替换</button>
      </div>
    </div>
  {/if}
</div>

<style>
  .editor {
    display: grid;
    gap: 12px;
  }

  .block-marquee {
    position: fixed;
    z-index: 22;
    border: 1.5px solid rgba(37, 99, 235, 0.78);
    background: rgba(37, 99, 235, 0.14);
    border-radius: 8px;
    pointer-events: none;
    box-shadow: 0 10px 24px rgba(37, 99, 235, 0.16);
  }

  :global(.editable .wa-block-selected) {
    outline: 2px solid rgba(37, 99, 235, 0.6);
    background: rgba(37, 99, 235, 0.08);
    border-radius: 8px;
  }

  :global(.editable [data-wa-edit='1']:focus) {
    outline: 2px solid rgba(90, 140, 255, 0.35);
    border-radius: 6px;
  }

  .panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .editor-stats {
    display: flex;
    gap: 8px;
    font-size: 12px;
    color: #8b7d65;
  }

  .editable {
    width: 100%;
    min-height: 560px;
    border: 1px solid rgba(90, 70, 45, 0.18);
    border-radius: 16px;
    padding: 24px 28px;
    font-size: 14px;
    line-height: 1.8;
    outline: none;
    background: #fffdf8;
    white-space: pre-wrap;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.6), 0 18px 40px rgba(70, 50, 20, 0.12);
    transition: box-shadow 0.15s ease, border-color 0.15s ease;
  }

  .editable[data-render-mode='doc'] {
    border: none;
    border-radius: 0;
    padding: 20px 0 32px;
    background: #f0f2f5;
    box-shadow: none;
    white-space: normal;
  }

  :global(.editable[data-render-mode='doc'] .wa-doc) {
    max-width: 820px;
    margin: 0 auto;
    padding: 56px 64px;
    background: #fff;
    box-shadow: 0 18px 40px rgba(15, 23, 42, 0.12);
    border: 1px solid #e2e8f0;
    font-family: "Times New Roman", "Noto Serif SC", "Source Han Serif SC", "Songti SC", serif;
    color: #1f2933;
  }

  :global(.editable[data-render-mode='doc'] .wa-doc .wa-header),
  :global(.editable[data-render-mode='doc'] .wa-doc .wa-footer) {
    font-size: 12px;
    color: #94a3b8;
    text-align: center;
    letter-spacing: 0.04em;
  }

  :global(.editable[data-render-mode='doc'] .wa-doc .wa-header) {
    border-bottom: 1px solid #e2e8f0;
    padding-bottom: 6px;
    margin-bottom: 18px;
    min-height: 14px;
  }

  :global(.editable[data-render-mode='doc'] .wa-doc .wa-header:empty) {
    border-bottom: none;
    padding-bottom: 0;
    margin-bottom: 0;
    min-height: 0;
  }

  :global(.editable[data-render-mode='doc'] .wa-doc .wa-footer) {
    border-top: 1px solid #e2e8f0;
    padding-top: 6px;
    margin-top: 24px;
  }

  :global(.editable[data-render-mode='doc'] .wa-doc .wa-title) {
    text-align: center;
    margin-bottom: 22px;
    font-size: 26px;
    font-weight: 600;
    letter-spacing: 0.02em;
  }

  :global(.editable[data-render-mode='doc'] .wa-doc h1),
  :global(.editable[data-render-mode='doc'] .wa-doc h2),
  :global(.editable[data-render-mode='doc'] .wa-doc h3) {
    margin: 18px 0 10px;
    font-weight: 600;
  }

  :global(.editable[data-render-mode='doc'] .wa-doc p) {
    margin: 6px 0;
    line-height: 1.8;
    text-align: justify;
  }

  :global(.editable[data-render-mode='doc'] .wa-doc ul),
  :global(.editable[data-render-mode='doc'] .wa-doc ol) {
    padding-left: 22px;
    margin: 6px 0;
  }

  :global(.editable[data-render-mode='doc'] .wa-doc li) {
    line-height: 1.7;
    margin: 2px 0;
  }

  :global(.editable[data-render-mode='doc'] .wa-doc figure) {
    margin: 14px 0;
    text-align: center;
  }

  :global(.editable[data-render-mode='doc'] .wa-doc .wa-figure-box),
  :global(.editable[data-render-mode='doc'] .wa-doc .wa-table-box) {
    height: 140px;
    border: 1px dashed #94a3b8;
    color: #64748b;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 14px;
  }

  :global(.editable[data-render-mode='doc'] .wa-doc table) {
    width: 100%;
    border-collapse: collapse;
    margin-top: 8px;
    font-size: 14px;
  }

  :global(.editable[data-render-mode='doc'] .wa-doc th),
  :global(.editable[data-render-mode='doc'] .wa-doc td) {
    border: 1px solid #cbd5e1;
    padding: 6px 8px;
  }

  :global(.editable[data-render-mode='doc'] .wa-doc figcaption) {
    margin-top: 6px;
    font-size: 12px;
    color: #64748b;
  }

  .editor.paper .editable {
    width: min(100%, 210mm);
    min-height: 297mm;
    margin: 8px auto 32px;
    padding: 37mm 26mm 35mm 28mm;
    border-radius: 10px;
    background: #ffffff;
    box-shadow:
      0 2px 0 rgba(0, 0, 0, 0.02),
      0 20px 60px rgba(50, 30, 10, 0.12);
    font-family: "SimSun", "Songti SC", "Noto Serif SC", serif;
    font-size: 12pt;
    line-height: 28pt;
    color: #1f1a12;
  }

  .editable:focus {
    border-color: rgba(140, 100, 50, 0.4);
    box-shadow: 0 0 0 3px rgba(140, 100, 50, 0.15), 0 18px 40px rgba(70, 50, 20, 0.12);
  }

  :global(.editable[data-empty='1'])::before {
    content: '在这里直接编辑或等待生成内容…';
    color: rgba(100, 90, 70, 0.5);
  }

  :global(.editable h1),
  :global(.editable h2),
  :global(.editable h3) {
    margin: 16px 0 10px;
    font-weight: 700;
  }

  :global(.editor.paper .editable h1),
  :global(.editor.paper .editable h2),
  :global(.editor.paper .editable h3) {
    text-indent: 0;
    margin: 0 0 16pt;
    font-weight: 700;
  }

  :global(.editable h1) {
    font-size: 20px;
  }

  :global(.editor.paper .editable h1) {
    font-size: 22pt;
    text-align: center;
    letter-spacing: 0.5pt;
    margin-top: 0;
  }

  :global(.editable h2) {
    font-size: 17px;
  }

  :global(.editor.paper .editable h2) {
    font-size: 16pt;
    margin-top: 18pt;
  }

  :global(.editable h3) {
    font-size: 15px;
  }

  :global(.editor.paper .editable h3) {
    font-size: 14pt;
    margin-top: 14pt;
  }

  :global(.editable p) {
    margin: 8px 0;
  }

  :global(.editor.paper .editable p) {
    margin: 0 0 12pt;
    text-indent: 2em;
    text-align: justify;
  }

  :global(.editable ul),
  :global(.editable ol) {
    padding-left: 24px;
  }

  :global(.editor.paper .editable ul),
  :global(.editor.paper .editable ol) {
    margin: 0 0 12pt 0;
    padding-left: 2.2em;
  }

  :global(.editor.paper .editable li) {
    text-indent: 0;
    margin: 0 0 8pt;
  }

  :global(.editor.paper .editable blockquote) {
    margin: 0 0 12pt;
    padding: 0.4em 0 0.4em 1.2em;
    border-left: 3px solid rgba(120, 90, 50, 0.3);
    text-indent: 0;
    color: #4b3d2a;
  }

  :global(.editable pre) {
    background: rgba(120, 110, 90, 0.08);
    padding: 10px 12px;
    border-radius: 10px;
  }

  :global(.editable .wa-figure),
  :global(.editable .wa-table) {
    display: grid;
    gap: 6px;
    border: 1px dashed rgba(37, 99, 235, 0.35);
    border-radius: 14px;
    padding: 10px 12px;
    margin: 10px 0;
    background: rgba(255, 255, 255, 0.8);
  }

  :global(.editable .wa-figure-box),
  :global(.editable .wa-table-box) {
    width: 100%;
    min-height: 160px;
    border-radius: 12px;
    background: rgba(15, 23, 42, 0.05);
    display: grid;
    place-items: center;
    font-weight: 600;
    color: rgba(15, 23, 42, 0.6);
    overflow: hidden;
  }

  :global(.editable .wa-figure-box svg) {
    width: 100%;
    height: auto;
    display: block;
  }

  :global(.editable .wa-figure-loading) {
    font-size: 12px;
    color: rgba(15, 23, 42, 0.6);
  }

  :global(.editable figcaption),
  :global(.editable .wa-table-caption) {
    font-size: 13px;
    color: #5b4a33;
  }

  :global(.editable img) {
    max-width: 100%;
    height: auto;
    border-radius: 8px;
    margin: 10px 0;
    transition: opacity 0.3s ease;
  }

  :global(.editable img[data-src]) {
    opacity: 0.3;
    background: rgba(200, 180, 150, 0.1);
  }

  :global(.editable pre) {
    background: #2d2d2d;
    color: #ccc;
    padding: 16px;
    border-radius: 8px;
    overflow-x: auto;
    margin: 10px 0;
    font-family: 'Courier New', Consolas, Monaco, monospace;
    font-size: 14px;
    line-height: 1.5;
  }

  :global(.editable pre code) {
    background: none;
    padding: 0;
    border-radius: 0;
  }

  :global(.editable .math-inline) {
    display: inline-block;
    margin: 0 2px;
    color: #1a5490;
  }

  :global(.editable .math-block) {
    display: block;
    margin: 16px 0;
    padding: 12px;
    background: rgba(26, 84, 144, 0.05);
    border-left: 3px solid #1a5490;
    overflow-x: auto;
  }

  :global(.editable table) {
    width: 100%;
    border-collapse: collapse;
    margin: 10px 0;
  }

  :global(.editable table td),
  :global(.editable table th) {
    border: 1px solid rgba(90, 70, 45, 0.25);
    padding: 8px;
  }

  :global(.editable a) {
    color: #a5722a;
    text-decoration: underline;
  }

  :global(.editable u) {
    text-decoration: underline;
  }

  :global(.editable s),
  :global(.editable del) {
    text-decoration: line-through;
  }

  .find-replace-panel {
    position: fixed;
    top: 120px;
    right: 32px;
    background: #fffdf8;
    border: 1px solid rgba(90, 70, 45, 0.18);
    border-radius: 14px;
    padding: 12px;
    box-shadow: 0 12px 30px rgba(70, 50, 20, 0.2);
    display: grid;
    gap: 8px;
    z-index: 100;
  }

  .find-replace-row {
    display: flex;
    gap: 8px;
    align-items: center;
  }

  .find-replace-panel input {
    flex: 1;
    border: 1px solid rgba(90, 70, 45, 0.18);
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 13px;
    background: rgba(255, 255, 255, 0.85);
  }

  .btn-small {
    border: 1px solid rgba(90, 70, 45, 0.18);
    background: rgba(255, 255, 255, 0.75);
    padding: 6px 12px;
    border-radius: 8px;
    cursor: pointer;
    font-size: 12px;
    transition: background 0.15s;
  }

  .btn-small:hover {
    background: rgba(240, 230, 210, 0.9);
  }

  .extended-toolbar {
    display: flex;
    gap: 4px;
    padding: 8px;
    background: rgba(255, 255, 255, 0.7);
    border: 1px solid rgba(90, 70, 45, 0.12);
    border-radius: 12px;
    margin-bottom: 8px;
    flex-wrap: wrap;
    align-items: center;
  }

  .toolbar-group {
    position: relative;
  }

  .tool-btn {
    border: 1px solid rgba(90, 70, 45, 0.12);
    background: rgba(255, 255, 255, 0.85);
    padding: 6px 10px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 14px;
    transition: background 0.15s;
    min-width: 32px;
  }

  .tool-btn:hover {
    background: rgba(240, 230, 210, 0.9);
  }

  .tool-select {
    border: 1px solid rgba(90, 70, 45, 0.12);
    background: rgba(255, 255, 255, 0.85);
    padding: 6px 8px;
    border-radius: 6px;
    font-size: 13px;
    cursor: pointer;
  }

  .separator {
    width: 1px;
    height: 20px;
    background: rgba(90, 70, 45, 0.2);
    margin: 0 4px;
  }

  .dropdown-panel {
    position: absolute;
    top: 100%;
    left: 0;
    margin-top: 4px;
    background: #fffdf8;
    border: 1px solid rgba(90, 70, 45, 0.18);
    border-radius: 8px;
    box-shadow: 0 8px 20px rgba(70, 50, 20, 0.2);
    z-index: 100;
    max-height: 300px;
    overflow-y: auto;
    min-width: 120px;
  }

  .dropdown-item {
    display: block;
    width: 100%;
    border: none;
    background: none;
    padding: 8px 12px;
    text-align: left;
    cursor: pointer;
    font-size: 13px;
    transition: background 0.15s;
  }

  .dropdown-item:hover {
    background: rgba(240, 230, 210, 0.5);
  }

  .color-grid {
    display: grid;
    grid-template-columns: repeat(7, 1fr);
    gap: 4px;
    padding: 8px;
    min-width: auto;
  }

  .color-item {
    width: 28px;
    height: 28px;
    border: 1px solid rgba(90, 70, 45, 0.2);
    border-radius: 4px;
    cursor: pointer;
    transition: transform 0.15s;
  }

  .color-item:hover {
    transform: scale(1.1);
    border-color: rgba(90, 70, 45, 0.5);
  }

  :global(.editable .footnotes-section) {
    margin-top: 40px;
    padding-top: 20px;
  }

  :global(.editable .footnotes-section h3) {
    font-size: 16px;
    margin-bottom: 12px;
  }

  :global(.editable .footnote-item) {
    font-size: 13px;
    color: #5b4a33;
    margin-bottom: 8px;
    line-height: 1.6;
  }

  :global(.editable .footnote-item sup) {
    color: #a5722a;
    margin-right: 6px;
  }

  :global(.editable .toc-section a:hover) {
    text-decoration: underline;
  }
</style>
