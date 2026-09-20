<script lang="ts">
  import './EditorWorkbench.css'
  import 'katex/dist/katex.min.css'
  import 'prismjs/themes/prism-tomorrow.css'
  import renderMathInElement from 'katex/contrib/auto-render'
  import Prism from 'prismjs'
  import 'prismjs/components/prism-c'
  import 'prismjs/components/prism-cpp'
  import 'prismjs/components/prism-java'
  import 'prismjs/components/prism-python'
  import 'prismjs/components/prism-sql'
  import { onMount } from 'svelte'
  import {
    editorCommand,
    sourceText,
    docIr,
    docIrDirty,
    pushHistory,
    undoHistory,
    redoHistory,
    generating,
    wordCount,
    docId,
    history,
    historyIndex,
    pageSettings,
    loadPageSettings
  } from '../stores'
  import { renderDocument, docIrToMarkdown, textToDocIr } from '../utils/markdown'
  import {
    DOC_TITLE_TARGET_ID,
    isSectionTargetId,
    normalizeBlockIds,
    realBlockTargetIds,
    sectionIdFromTarget,
    targetIdForElement
  } from '../workbench/inlineTargets'
  import {
    insertBlockAfter,
    insertBlockBefore,
    replaceInDocIr,
    updateBlock,
    updateDocTitle,
    updateSectionTitle
  } from '../editor/docIrMutations'
  import { htmlToDocIr, htmlToMarkdown, makeId } from '../editor/htmlConversion'
  import {
    documentEngineReady,
    initDocumentEngine,
    measureDocument,
    mirrorMarkdown,
    redoMarkdown,
    undoMarkdown
  } from '../engine/documentEngine'

  let editor = $state<HTMLDivElement | null>(null)
  let lastMarkdown = $state('')
  let lastRenderSig = $state('')
  let renderMode = $state<'text' | 'doc'>('text')
  let historyTimer = $state<ReturnType<typeof setTimeout> | null>(null)
  let syncTimer = $state<ReturnType<typeof setTimeout> | null>(null)
  let docTextTimer = $state<ReturnType<typeof setTimeout> | null>(null)
  let sourceUnsub: (() => void) | null = null
  let docIrUnsub: (() => void) | null = null
  let {
    showToolbar = true,
    paper = true,
    lockEditing = false,
    onblockedit,
    onblockselect,
    ontoolbarstate
  }: {
    showToolbar?: boolean
    paper?: boolean
    lockEditing?: boolean
    onblockedit?: (payload: any) => void
    onblockselect?: (payload: any) => void
    ontoolbarstate?: (state: any) => void
  } = $props()
  let editingEl = $state<HTMLElement | null>(null)
  let editingKey = $state('')
  let composing = $state(false)
  let pendingRenderSig = $state<string | null>(null)
  let pendingFocusBlockId = $state('')
  let editCommitTimer = $state<ReturnType<typeof setTimeout> | null>(null)
  let selectedBlockIds = $state<string[]>([])
  let selectedBlockEls = $state<HTMLElement[]>([])
  let selectedAnchorId = $state('')
  let dragSelectSeed = $state<{ x: number; y: number } | null>(null)
  let dragSelecting = $state(false)
  let dragRect = $state({ left: 0, top: 0, width: 0, height: 0 })
  let suppressClickOnce = $state(false)
  let nativeRedoHint = $state(false)
  let lastToolbarStateSig = $state('')
  let blockClipboard = $state<Array<Record<string, unknown>>>([])
  let savedTextRange: Range | null = null
  let selectionToolbar = $state({ visible: false, left: 0, top: 0, text: '', words: 0 })
  let objectToolbar = $state({ visible: false, left: 0, top: 0, kind: '', blockId: '' })
  let figureEditorOpen = $state(false)
  let figureDraftCaption = $state('')
  let figureDraftJson = $state('')
  let tableEditorOpen = $state(false)
  let tableDraftCaption = $state('')
  let tableDraftTsv = $state('')
  let tableInsertOpen = $state(false)
  let tableInsertRows = $state(4)
  let tableInsertCols = $state(3)
  let tableInsertCaption = $state('表格标题')
  let showNavigationPane = $state(true)
  let editorZoom = $state(100)
  let gutterAnchor: HTMLElement | null = null
  let outlineItems = $state<Array<{ id: string; text: string; level: number }>>([])
  let documentMeta = $state({ currentPage: 1, pages: 1, paragraphs: 0, chars: 0, selected: 0 })
  type SlashCommandItem = {
    id: string
    label: string
    desc: string
    command: string
    keywords: string[]
  }
  const slashCommandCatalog: SlashCommandItem[] = [
    { id: 'heading1', label: '标题 1', desc: '插入一级标题', command: 'heading1', keywords: ['h1', '标题', '一级'] },
    { id: 'heading2', label: '标题 2', desc: '插入二级标题', command: 'heading2', keywords: ['h2', '标题', '二级'] },
    { id: 'paragraph', label: '正文段落', desc: '切换为正文段落', command: 'paragraph', keywords: ['正文', '段落', 'p'] },
    { id: 'list-bullet', label: '无序列表', desc: '插入项目符号列表', command: 'list-bullet', keywords: ['列表', 'bullet', '无序'] },
    { id: 'list-number', label: '有序列表', desc: '插入编号列表', command: 'list-number', keywords: ['列表', '编号', '有序'] },
    { id: 'quote', label: '引用块', desc: '插入引用格式', command: 'quote', keywords: ['引用', 'quote'] },
    { id: 'code', label: '代码块', desc: '插入代码块', command: 'code', keywords: ['代码', 'code'] },
    { id: 'table', label: '表格', desc: '插入表格', command: 'table', keywords: ['表格', 'table'] },
    { id: 'image', label: '图片', desc: '插入图片', command: 'image', keywords: ['图片', 'image', '图'] },
    { id: 'toc', label: '目录', desc: '生成目录', command: 'toc', keywords: ['目录', 'toc'] },
    { id: 'footnote', label: '脚注', desc: '插入脚注', command: 'footnote', keywords: ['脚注', 'footnote'] },
    { id: 'math-inline', label: '行内公式', desc: '插入行内 LaTeX 公式', command: 'math-inline', keywords: ['公式', 'math', 'latex'] },
    { id: 'math-block', label: '公式块', desc: '插入块级 LaTeX 公式', command: 'math-block', keywords: ['公式块', 'math', 'latex'] },
  ]
  let slashMenuOpen = $state(false)
  let slashMenuLeft = $state(0)
  let slashMenuTop = $state(0)
  let slashMenuActive = $state(0)
  let slashMenuQuery = $state('')

  function emptyHintText() {
    if ($generating) return '正在生成内容，暂不可直接编辑…'
    if (lockEditing) return '正在渲染内容，暂不可编辑，请稍候…'
    return '在这里直接编辑或等待生成内容…'
  }

  function syncEditorUiFlags() {
    if (!editor) return
    const readonly = $generating || lockEditing
    // The page is one continuous editing host. Paragraphs remain semantic
    // DocIR blocks, but they are not separate input boxes. This lets native
    // caret navigation and wrapped lines behave like a desktop word processor.
    editor.setAttribute('contenteditable', readonly ? 'false' : 'true')
    editor.dataset.readonly = readonly ? '1' : '0'
    editor.dataset.emptyHint = emptyHintText()
  }

  function setEmptyFlag(text: string) {
    if (!editor) return
    const empty = !String(text || '').trim()
    editor.dataset.empty = empty ? '1' : '0'
    syncEditorUiFlags()
  }

  function docIrHasRenderableContent(value: unknown) {
    if (!value || typeof value !== 'object') return false
    const obj = value as Record<string, unknown>
    const hasSectionContent = (items: Array<unknown>): boolean => {
      for (const item of items) {
        if (!item || typeof item !== 'object') continue
        const sec = item as Record<string, unknown>
        if (String(sec.title || '').trim()) return true
        const blocks = Array.isArray(sec.blocks) ? (sec.blocks as Array<unknown>) : []
        if (blocks.length > 0) return true
        const children = Array.isArray(sec.children) ? (sec.children as Array<unknown>) : []
        if (children.length && hasSectionContent(children)) return true
      }
      return false
    }
    const sections = Array.isArray(obj.sections) ? (obj.sections as Array<unknown>) : []
    if (sections.length > 0 && hasSectionContent(sections)) return true
    const blocks = Array.isArray(obj.blocks) ? (obj.blocks as Array<unknown>) : []
    return blocks.length > 0
  }

  function createSeedDoc(title = '') {
    return {
      title: String(title || '').trim(),
      sections: [
        {
          id: makeId(),
          title: '',
          level: 1,
          blocks: [{ id: makeId(), type: 'paragraph', text: '' }],
          children: []
        }
      ]
    }
  }

  function syncFromStore(immediate = false) {
    if (!editor) return
    const next = String($sourceText || '')
    const doc = $docIr
    const hasDocIr = docIrHasRenderableContent(doc)
    if (!hasDocIr && !next.trim()) {
      const seed = createSeedDoc(
        doc && typeof doc === 'object' ? String((doc as Record<string, unknown>).title || '') : ''
      )
      docIr.set(seed)
      docIrDirty.set(false)
      return
    }
    const preferText = !hasDocIr
    const sig = hasDocIr ? `doc:${docIrSignature(doc)}` : `text:${next}`
    if (editingEl && editor.contains(editingEl) && sig !== lastRenderSig) {
      pendingRenderSig = sig
      return
    }
    if (sig !== lastRenderSig) {
      if (syncTimer) clearTimeout(syncTimer)
      const renderNow = () => {
        editor!.innerHTML = renderDocument(next, doc, preferText)
        renderMode = preferText ? 'text' : 'doc'
        lastMarkdown = next
        lastRenderSig = sig
        pendingRenderSig = null
        setEmptyFlag(next)
        syncEditorUiFlags()
        markEditableBlocks()
        refreshSelectedBlock()
        if (pendingFocusBlockId) {
          const target = editor!.querySelector(
            `[data-block-id="${CSS.escape(pendingFocusBlockId)}"]`
          ) as HTMLElement | null
          pendingFocusBlockId = ''
          if (target) focusEditableAtStart(target)
        }
        renderMathInEditor()
        highlightCodeBlocks()
        renderFiguresInEditor()
        applyPageSettingsToEditor()
        setEditorZoom(editorZoom)
        refreshDocumentMeta()
      }
      if (immediate) renderNow()
      else syncTimer = setTimeout(renderNow, 100)
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
    const editable = !$generating && !lockEditing
    if (editable) el.removeAttribute('contenteditable')
    else el.setAttribute('contenteditable', 'false')
    el.setAttribute('spellcheck', 'false')
    if (editable) el.dataset.waEdit = '1'
    else delete el.dataset.waEdit
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
      if (tag === 'figure' || tag === 'table' || el.classList.contains('wa-page-break')) {
        el.setAttribute('contenteditable', 'false')
        delete el.dataset.waEdit
        return
      }
      setEditableAttrs(el)
    })
  }

  function focusEditableAtStart(el: HTMLElement) {
    editor?.focus()
    const range = document.createRange()
    range.selectNodeContents(el)
    range.collapse(true)
    const selection = window.getSelection()
    selection?.removeAllRanges()
    selection?.addRange(range)
    editingEl = el
    editingKey = String(el.dataset.blockId || el.dataset.sectionId || el.dataset.docTitle || '')
  }

  function pageSizeCm(): [number, number] {
    const settings = $pageSettings
    const sizes: Record<string, [number, number]> = {
      A4: [21, 29.7], A5: [14.8, 21], LETTER: [21.59, 27.94]
    }
    let [width, height] = sizes[settings.pageSize] || sizes.A4
    if (settings.orientation === 'landscape') [width, height] = [height, width]
    return [width, height]
  }

  function visualPageHeight(): number {
    if (!editor) return 1
    const [widthCm, heightCm] = pageSizeCm()
    const rect = editor.getBoundingClientRect()
    return Math.max(1, rect.width * (heightCm / widthCm))
  }

  function updateFooterText(pages: number) {
    if (!editor) return
    const settings = $pageSettings
    const footer = editor.querySelector('.wa-footer') as HTMLElement | null
    if (!footer) return
    footer.style.display = settings.showFooter || settings.pageNumbers ? 'block' : 'none'
    footer.style.textAlign = settings.pageNumberPosition
    const pageText = settings.pageNumbers ? `第 ${Math.max(1, pages)} 页，共 ${Math.max(1, pages)} 页` : ''
    footer.textContent = [settings.showFooter ? settings.footerText : '', pageText].filter(Boolean).join('　')
  }

  function caretPage(pages: number): number {
    if (!editor) return 1
    const selection = window.getSelection()
    if (!selection || selection.rangeCount === 0 || !selectionInsideEditor()) return documentMeta.currentPage
    const range = selection.getRangeAt(0).cloneRange()
    range.collapse(true)
    const caretRect = range.getBoundingClientRect()
    const editorRect = editor.getBoundingClientRect()
    if (!caretRect || !editorRect.height) return documentMeta.currentPage
    const offset = Math.max(0, caretRect.top - editorRect.top)
    return Math.max(1, Math.min(pages, Math.floor(offset / visualPageHeight()) + 1))
  }

  function refreshDocumentMeta() {
    if (!editor) return
    const headings = Array.from(editor.querySelectorAll('h1, h2, h3, h4, h5, h6')) as HTMLElement[]
    outlineItems = headings
      .map((heading, index) => {
        if (!heading.id) heading.id = `wa-heading-${index + 1}`
        return {
          id: heading.id,
          text: String(heading.textContent || '').trim(),
          level: Number(heading.tagName.slice(1)) || 1
        }
      })
      .filter((item) => Boolean(item.text))
    const body = editor.querySelector('.wa-body') as HTMLElement | null
    const countRoot = body || editor
    const paragraphs = countRoot.querySelectorAll('p, li, h1, h2, h3, h4, h5, h6').length
    const chars = String(countRoot.innerText || '').replace(/\s/g, '').length
    const enginePages = Number(editor.dataset.enginePages || 0)
    const pageHeight = visualPageHeight()
    const visualPages = Math.max(1, Math.ceil(editor.getBoundingClientRect().height / pageHeight))
    const measuredPages = enginePages > 0 ? Math.max(enginePages, visualPages) : visualPages
    const manualPages = editor.querySelectorAll('.wa-page-break').length + 1
    const pages = Math.max(manualPages, measuredPages)
    documentMeta = { ...documentMeta, currentPage: caretPage(pages), pages, paragraphs, chars }
    updateFooterText(pages)
  }

  function setEditorZoom(value: number) {
    editorZoom = Math.max(60, Math.min(180, Math.round(value / 10) * 10))
    if (editor) editor.style.zoom = `${editorZoom}%`
  }

  function jumpToOutline(id: string) {
    const target = editor?.querySelector(`#${CSS.escape(id)}`) as HTMLElement | null
    target?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    target?.focus()
  }

  function selectParagraphText(block: HTMLElement, extend = false) {
    if (!editor || !editor.contains(block)) return
    const range = document.createRange()
    if (extend && gutterAnchor && editor.contains(gutterAnchor)) {
      const blocks = Array.from(editor.querySelectorAll('[data-block-id], [data-section-id], [data-doc-title="1"]')) as HTMLElement[]
      const from = blocks.indexOf(gutterAnchor)
      const to = blocks.indexOf(block)
      if (from >= 0 && to >= 0) {
        const first = blocks[Math.min(from, to)]
        const last = blocks[Math.max(from, to)]
        range.setStartBefore(first)
        range.setEndAfter(last)
      } else {
        range.selectNodeContents(block)
      }
    } else {
      range.selectNodeContents(block)
      gutterAnchor = block
    }
    const selection = window.getSelection()
    selection?.removeAllRanges()
    selection?.addRange(range)
    savedTextRange = range.cloneRange()
    clearSelectedBlock()
    queueMicrotask(() => updateSelectionContext())
  }

  function findEditableRoot(target: EventTarget | null): HTMLElement | null {
    if (!target || !(target instanceof HTMLElement) || !editor) return null
    const el = target.closest('[data-wa-edit="1"]') as HTMLElement | null
    if (!el || !editor.contains(el)) return null
    return el
  }

  function resolveEditableElement(target: EventTarget | null): HTMLElement | null {
    const direct = findEditableRoot(target)
    if (direct) return direct
    const active = document.activeElement as HTMLElement | null
    const fromActive = findEditableRoot(active)
    if (fromActive) return fromActive
    const sel = window.getSelection()
    const anchor = sel?.anchorNode || null
    if (anchor instanceof HTMLElement) return findEditableRoot(anchor)
    if (anchor && (anchor as Node).parentElement) return findEditableRoot((anchor as Node).parentElement)
    return null
  }

  function resolveEditableFromSelection(): HTMLElement | null {
    const sel = window.getSelection()
    const anchor = sel?.anchorNode || null
    if (anchor instanceof HTMLElement) return findEditableRoot(anchor)
    if (anchor && (anchor as Node).parentElement) return findEditableRoot((anchor as Node).parentElement)
    return null
  }

  function resolveEditableAtCaret(): HTMLElement | null {
    if (!editor) return null
    const sel = window.getSelection()
    if (!sel || sel.rangeCount === 0) return null
    const range = sel.getRangeAt(0).cloneRange()
    range.collapse(true)
    const rect = range.getBoundingClientRect()
    if (rect) {
      const x = Math.max(0, rect.left + Math.max(1, rect.width / 2))
      const y = Math.max(0, rect.top + Math.max(1, rect.height / 2))
      const hit = document.elementFromPoint(x, y) as HTMLElement | null
      const fromHit = findEditableRoot(hit)
      if (fromHit) return fromHit
      const byY = nearestEditableByClickY(y)
      if (byY) return byY
    }
    return editor.querySelector('[data-wa-edit="1"]') as HTMLElement | null
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
    const computed = window.getComputedStyle(el)
    const out: Record<string, string> = {}
    const align = style.textAlign || el.getAttribute('align') || computed.textAlign || ''
    if (align) out.align = align
    const lineHeightRaw = style.lineHeight || computed.lineHeight
    if (lineHeightRaw) {
      let lineHeight = lineHeightRaw
      const lhPx = /^(\d+(?:\.\d+)?)px$/.exec(lineHeightRaw)
      const fsPx = /^(\d+(?:\.\d+)?)px$/.exec(style.fontSize || computed.fontSize || '')
      if (lhPx && fsPx) {
        const ratio = Number(lhPx[1]) / Number(fsPx[1])
        if (Number.isFinite(ratio) && ratio > 0) {
          lineHeight = ratio.toFixed(2).replace(/\.00$/, '')
        }
      }
      out.lineHeight = lineHeight
    }
    const indent = style.textIndent || computed.textIndent
    if (indent) out.indent = indent
    const marginTop = style.marginTop || computed.marginTop
    if (marginTop) out.marginTop = marginTop
    const marginBottom = style.marginBottom || computed.marginBottom
    if (marginBottom) out.marginBottom = marginBottom
    const fontFamily = style.fontFamily || computed.fontFamily
    if (fontFamily) out.fontFamily = fontFamily
    const fontSizeRaw = style.fontSize || computed.fontSize
    if (fontSizeRaw) {
      let fontSize = fontSizeRaw
      const px = /^(\d+(?:\.\d+)?)px$/.exec(fontSizeRaw)
      if (px) {
        const pt = Math.round((Number(px[1]) * 72) / 96)
        if (Number.isFinite(pt) && pt > 0) fontSize = `${pt}pt`
      }
      out.fontSize = fontSize
    }
    const fontWeight = style.fontWeight || computed.fontWeight
    if (fontWeight) out.fontWeight = fontWeight
    const fontStyle = style.fontStyle || computed.fontStyle
    if (fontStyle) out.fontStyle = fontStyle
    const color = style.color || computed.color
    if (color) out.color = color
    const background = style.backgroundColor || computed.backgroundColor
    if (background && background !== 'transparent' && background !== 'rgba(0, 0, 0, 0)') {
      out.background = background
    }
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
    walk(el, { text: '' })
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

  function scheduleDocTextSync(nextDoc: Record<string, unknown>, delayMs = 180) {
    if (docTextTimer) clearTimeout(docTextTimer)
    docTextTimer = setTimeout(() => {
      const text = docIrToMarkdown(nextDoc) || ''
      mirrorMarkdown(text, true)
      const metrics = measureDocument(editor?.clientWidth || 794)
      if (editor && metrics) {
        editor.dataset.enginePages = String(metrics.pageCount)
        editor.dataset.engineBlocks = String(metrics.blockCount)
      }
      sourceText.set(text)
      lastMarkdown = text
      setEmptyFlag(text)
      pushHistory(text)
    }, delayMs)
  }

  function applyDocIrUpdate(nextDoc: Record<string, unknown>, opts?: { immediate?: boolean; render?: boolean }) {
    const needsRender = opts?.render !== false
    if (needsRender) {
      if (editCommitTimer) {
        clearTimeout(editCommitTimer)
        editCommitTimer = null
      }
      editingEl = null
      editingKey = ''
      lastRenderSig = ''
    }
    docIr.set(nextDoc)
    docIrDirty.set(false)
    if (!needsRender) lastRenderSig = `doc:${docIrSignature(nextDoc)}`
    scheduleDocTextSync(nextDoc, opts?.immediate ? 0 : 180)
    if (needsRender) queueMicrotask(() => syncFromStore(true))
  }

  function scheduleCommit(el: HTMLElement, delayMs = 160) {
    if (editCommitTimer) clearTimeout(editCommitTimer)
    editCommitTimer = setTimeout(() => {
      commitEditableElement(el)
    }, delayMs)
  }

  function commitEditableElement(el: HTMLElement, opts?: { immediate?: boolean }) {
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
    applyDocIrUpdate(nextDoc, { ...opts, render: false })
  }

  function flushPendingEditableState() {
    if (historyTimer || hasUntrackedParagraphStructure()) {
      if (historyTimer) {
        clearTimeout(historyTimer)
        historyTimer = null
      }
      reconcileEditorDom()
      return
    }
    if (editCommitTimer) {
      clearTimeout(editCommitTimer)
      editCommitTimer = null
    }
    const active = editingEl || resolveEditableElement(document.activeElement)
    if (active) {
      commitEditableElement(active, { immediate: true })
      return
    }
    if (docTextTimer) {
      clearTimeout(docTextTimer)
      docTextTimer = null
    }
    const doc = $docIr
    if (!doc || typeof doc !== 'object') return
    const text = docIrToMarkdown(doc as Record<string, unknown>) || ''
    sourceText.set(text)
    lastMarkdown = text
    setEmptyFlag(text)
  }

  function allBlockElements(): HTMLElement[] {
    if (!editor) return []
    const nodes = editor.querySelectorAll('[data-block-id], [data-section-id], [data-doc-title="1"]')
    return Array.from(nodes) as HTMLElement[]
  }

  function blockIdOf(el: HTMLElement | null): string {
    return targetIdForElement(el)
  }

  function blockById(id: string): HTMLElement | null {
    if (!editor || !id) return null
    if (id === DOC_TITLE_TARGET_ID) {
      return editor.querySelector('[data-doc-title="1"]') as HTMLElement | null
    }
    if (isSectionTargetId(id)) {
      const sectionId = sectionIdFromTarget(id)
      if (!sectionId) return null
      return editor.querySelector(`[data-section-id="${CSS.escape(sectionId)}"]`) as HTMLElement | null
    }
    return editor.querySelector(`[data-block-id="${CSS.escape(id)}"]`) as HTMLElement | null
  }

  function sectionMetaByBlockId(id: string): { sectionId: string; sectionTitle: string } {
    if (!editor || !id) return { sectionId: '', sectionTitle: '' }
    if (id === DOC_TITLE_TARGET_ID) {
      const title = editor.querySelector('[data-doc-title="1"]') as HTMLElement | null
      return {
        sectionId: DOC_TITLE_TARGET_ID,
        sectionTitle: title ? normalizeInlineText(plainTextFromElement(title)) : '文档标题'
      }
    }
    const sectionIdTarget = sectionIdFromTarget(id)
    if (sectionIdTarget) {
      const sectionEl = editor.querySelector(`[data-section-id="${CSS.escape(sectionIdTarget)}"]`) as HTMLElement | null
      const sectionTitle = sectionEl ? normalizeInlineText(plainTextFromElement(sectionEl).replace(/^#+\s*/, '')) : ''
      return { sectionId: sectionIdTarget, sectionTitle }
    }
    let currentSectionId = ''
    let currentSectionTitle = ''
    const nodes = Array.from(editor.querySelectorAll('[data-section-id], [data-block-id]')) as HTMLElement[]
    for (const node of nodes) {
      const sid = String(node.dataset.sectionId || '').trim()
      if (sid) {
        currentSectionId = sid
        currentSectionTitle = normalizeInlineText(plainTextFromElement(node).replace(/^#+\s*/, ''))
      }
      const bid = String(node.dataset.blockId || '').trim()
      if (bid && bid === id) {
        return { sectionId: currentSectionId, sectionTitle: currentSectionTitle }
      }
    }
    return { sectionId: '', sectionTitle: '' }
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
      const section = sectionMetaByBlockId(id)
      const kind: 'block' | 'section' | 'title' =
        id === DOC_TITLE_TARGET_ID ? 'title' : isSectionTargetId(id) ? 'section' : 'block'
      return {
        id,
        text,
        kind,
        style: extractBlockStyle(el) || {},
        sectionId: section.sectionId,
        sectionTitle: section.sectionTitle
      }
    })
    if (!blocks.length) {
      onblockselect?.({ blockId: '', blockIds: [], blocks: [], text: '', rect: null, style: {} })
      return
    }
    const primaryEl = selectedBlockEls[0]
    const primaryId = blockIdOf(primaryEl)
    const primaryText = plainTextFromElement(primaryEl)
    const rect = primaryEl.getBoundingClientRect()
    onblockselect?.({
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
    if (!selectedBlockIds.length) objectToolbar.visible = false
    queueMicrotask(() => emitToolbarState())
  }

  function selectObjectBlock(block: HTMLElement) {
    const id = blockIdOf(block)
    if (!id) return
    window.getSelection()?.removeAllRanges()
    setSelectedBlocksByIds([id], id)
    const rect = block.getBoundingClientRect()
    const kind = block.classList.contains('wa-image') ? 'image' : block.classList.contains('wa-figure') ? 'figure' : block.classList.contains('wa-table') ? 'table' : 'object'
    objectToolbar = {
      visible: true,
      left: Math.max(10, Math.min(window.innerWidth - 430, rect.left)),
      top: Math.max(62, rect.top - 42),
      kind,
      blockId: id
    }
  }

  function insertParagraphBesideObject(position: 'before' | 'after') {
    const doc = $docIr
    const blockId = objectToolbar.blockId
    if (!doc || typeof doc !== 'object' || !blockId) return
    const paragraph: Record<string, unknown> = { id: makeId(), type: 'paragraph', text: '' }
    const next = position === 'before'
      ? insertBlockBefore(doc as Record<string, unknown>, blockId, paragraph)
      : insertBlockAfter(doc as Record<string, unknown>, blockId, paragraph)
    if (!next) return
    pendingFocusBlockId = String(paragraph.id)
    objectToolbar.visible = false
    applyDocIrUpdate(next, { immediate: true })
  }

  function deleteSelectedObject() {
    const doc = $docIr
    if (!doc || typeof doc !== 'object' || !objectToolbar.blockId) return
    const next = deleteBlocksByIds(doc as Record<string, unknown>, [objectToolbar.blockId])
    if (!next) return
    objectToolbar.visible = false
    applyDocIrUpdate(next, { immediate: true })
    clearSelectedBlock()
  }

  function openFigureEditor() {
    const doc = $docIr
    if (!doc || typeof doc !== 'object' || !objectToolbar.blockId) return
    const block = collectBlocksByIds(doc as Record<string, unknown>, [objectToolbar.blockId])[0]
    const figure = block?.figure && typeof block.figure === 'object' ? block.figure as Record<string, unknown> : {}
    figureDraftCaption = String(figure.caption || '')
    figureDraftJson = JSON.stringify(figure, null, 2)
    figureEditorOpen = true
  }

  function saveFigureEditor() {
    const doc = $docIr
    if (!doc || typeof doc !== 'object' || !objectToolbar.blockId) return
    let figure: Record<string, unknown>
    try {
      figure = figureDraftJson.trim() ? JSON.parse(figureDraftJson) : {}
    } catch {
      alert('图表数据不是有效的 JSON')
      return
    }
    figure.caption = figureDraftCaption.trim() || String(figure.caption || '图示')
    const next = updateBlock(doc as Record<string, unknown>, objectToolbar.blockId, { type: 'figure', figure })
    if (!next) return
    figureCache.clear()
    figureEditorOpen = false
    objectToolbar.visible = false
    lastRenderSig = ''
    applyDocIrUpdate(next, { immediate: true })
  }

  function tableToTsv(table: Record<string, unknown>) {
    const columns = Array.isArray(table.columns) ? table.columns.map((value) => String(value ?? '')) : []
    const rows = Array.isArray(table.rows)
      ? table.rows.map((row) => Array.isArray(row) ? row.map((value) => String(value ?? '')) : [])
      : []
    return [columns, ...rows].filter((row) => row.length).map((row) => row.join('\t')).join('\n')
  }

  function tsvToTable(tsv: string, caption: string) {
    const lines = String(tsv || '')
      .split(/\r?\n/)
      .map((line) => line.split('\t').map((cell) => cell.trim()))
      .filter((row) => row.some(Boolean))
    const columns = lines.shift() || ['列 1']
    const rows = lines.length ? lines : [columns.map(() => '')]
    return { caption: caption.trim() || '表格', columns, rows }
  }

  function openTableEditor() {
    const doc = $docIr
    if (!doc || typeof doc !== 'object' || !objectToolbar.blockId) return
    const block = collectBlocksByIds(doc as Record<string, unknown>, [objectToolbar.blockId])[0]
    const table = block?.table && typeof block.table === 'object' ? block.table as Record<string, unknown> : {}
    tableDraftCaption = String(table.caption || '表格')
    tableDraftTsv = tableToTsv(table)
    tableEditorOpen = true
  }

  function saveTableEditor() {
    const doc = $docIr
    if (!doc || typeof doc !== 'object' || !objectToolbar.blockId) return
    const table = tsvToTable(tableDraftTsv, tableDraftCaption)
    const next = updateBlock(doc as Record<string, unknown>, objectToolbar.blockId, { type: 'table', table })
    if (!next) return
    tableEditorOpen = false
    objectToolbar.visible = false
    lastRenderSig = ''
    applyDocIrUpdate(next, { immediate: true })
  }

  function insertTableFromDialog() {
    const doc = $docIr
    if (!doc || typeof doc !== 'object') return
    const rows = Math.max(1, Math.min(30, Number(tableInsertRows) || 1))
    const cols = Math.max(1, Math.min(12, Number(tableInsertCols) || 1))
    const tableBlock: Record<string, unknown> = {
      id: makeId(),
      type: 'table',
      table: {
        caption: tableInsertCaption.trim() || '表格',
        columns: Array.from({ length: cols }, (_, index) => `列 ${index + 1}`),
        rows: Array.from({ length: rows }, () => Array.from({ length: cols }, () => ''))
      }
    }
    const paragraph: Record<string, unknown> = { id: makeId(), type: 'paragraph', text: '' }
    const anchor = resolveEditableFromSelection() || editingEl
    const anchorId = String(anchor?.dataset.blockId || '')
    const next = anchorId
      ? insertBlocksAfter(doc as Record<string, unknown>, anchorId, [tableBlock, paragraph])
      : appendBlocksToDoc(doc as Record<string, unknown>, [tableBlock, paragraph])
    if (!next) return
    tableInsertOpen = false
    pendingFocusBlockId = String(paragraph.id)
    applyDocIrUpdate(next, { immediate: true })
  }

  function clearSelectedBlock() {
    setSelectedBlocksByIds([])
  }

  function selectionInsideEditor() {
    if (!editor) return false
    const sel = window.getSelection()
    if (!sel || sel.rangeCount === 0) return false
    const anchor = sel.anchorNode
    const focus = sel.focusNode
    return Boolean(anchor && focus && editor.contains(anchor) && editor.contains(focus))
  }

  function hasNativeTextSelection() {
    const sel = window.getSelection()
    if (!sel || sel.rangeCount === 0) return false
    if (sel.isCollapsed) return false
    return selectionInsideEditor()
  }

  function collectBlocksByIds(doc: Record<string, unknown>, ids: string[]): Array<Record<string, unknown>> {
    const wanted = new Set(realBlockTargetIds(ids))
    if (!wanted.size) return []
    const out: Array<Record<string, unknown>> = []
    const walk = (sections: Array<Record<string, unknown>>) => {
      for (const sec of sections) {
        const blocks = Array.isArray(sec.blocks) ? (sec.blocks as Array<Record<string, unknown>>) : []
        for (const block of blocks) {
          const id = String(block.id || '')
          if (id && wanted.has(id)) out.push(block)
        }
        const children = Array.isArray(sec.children) ? (sec.children as Array<Record<string, unknown>>) : []
        if (children.length) walk(children)
      }
    }
    const sections = Array.isArray(doc.sections) ? (doc.sections as Array<Record<string, unknown>>) : []
    walk(sections)
    return out
  }

  function blockToPlainText(block: Record<string, unknown>): string {
    const t = String(block.type || 'paragraph').toLowerCase()
    if (t === 'list') {
      const items = Array.isArray(block.items) ? (block.items as Array<unknown>) : []
      return items.map((item) => String(item ?? '').trim()).filter(Boolean).join('\n')
    }
    if (t === 'table') {
      const table = block.table && typeof block.table === 'object' ? (block.table as Record<string, unknown>) : {}
      return String(table.caption || '表格')
    }
    if (t === 'figure') {
      const fig = block.figure && typeof block.figure === 'object' ? (block.figure as Record<string, unknown>) : {}
      return String(fig.caption || '图片')
    }
    return String(block.text || '').trim()
  }

  async function writeClipboardText(text: string) {
    const payload = String(text || '')
    if (!payload) return false
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(payload)
        return true
      }
    } catch {}
    try {
      const area = document.createElement('textarea')
      area.value = payload
      area.style.position = 'fixed'
      area.style.opacity = '0'
      document.body.appendChild(area)
      area.focus()
      area.select()
      const ok = document.execCommand('copy')
      area.remove()
      return ok
    } catch {
      return false
    }
  }

  async function readClipboardText() {
    try {
      if (navigator.clipboard && navigator.clipboard.readText) {
        return await navigator.clipboard.readText()
      }
    } catch {}
    return ''
  }

  function cloneBlockForPaste(block: Record<string, unknown>, index: number): Record<string, unknown> {
    const cloned = JSON.parse(JSON.stringify(block || {})) as Record<string, unknown>
    const rawType = String(cloned.type || 'paragraph').toLowerCase()
    cloned.id = makeId()
    if (!['paragraph', 'text', 'p', 'list', 'table', 'figure', 'heading'].includes(rawType)) {
      cloned.type = 'paragraph'
      cloned.text = blockToPlainText(block)
    }
    if ((rawType === 'text' || rawType === 'p') && typeof cloned.text !== 'string') {
      cloned.text = blockToPlainText(block)
    }
    if (rawType === 'paragraph' && typeof cloned.text !== 'string') {
      cloned.text = blockToPlainText(block)
    }
    if (!cloned.id) cloned.id = `${makeId()}_${index + 1}`
    return cloned
  }

  function insertBlocksAfter(doc: Record<string, unknown>, blockId: string, blocksToInsert: Array<Record<string, unknown>>) {
    if (!blocksToInsert.length) return null
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
            nextBlocks.splice(idx + 1, 0, ...blocksToInsert)
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

  function appendBlocksToDoc(doc: Record<string, unknown>, blocksToInsert: Array<Record<string, unknown>>) {
    if (!blocksToInsert.length) return null
    const sections = Array.isArray(doc.sections) ? (doc.sections as Array<Record<string, unknown>>) : []
    if (!sections.length) return null
    const first = sections[0]
    const firstBlocks = Array.isArray(first.blocks) ? (first.blocks as Array<Record<string, unknown>>) : []
    const nextFirst = { ...first, blocks: [...firstBlocks, ...blocksToInsert] }
    const nextSections = sections.slice()
    nextSections[0] = nextFirst
    return { ...doc, sections: nextSections }
  }

  function deleteBlocksByIds(doc: Record<string, unknown>, ids: string[]): Record<string, unknown> | null {
    const target = new Set(realBlockTargetIds(ids))
    if (!target.size) return null
    let changed = false
    const walk = (sections: Array<Record<string, unknown>>) => {
      let localChanged = false
      const nextSections = sections.map((sec) => {
        let touched = false
        let nextSec = sec
        const blocks = Array.isArray(sec.blocks) ? (sec.blocks as Array<Record<string, unknown>>) : []
        if (blocks.length) {
          const nextBlocks = blocks.filter((b) => !target.has(String(b.id || '')))
          if (nextBlocks.length !== blocks.length) {
            nextSec = { ...nextSec, blocks: nextBlocks }
            touched = true
          }
        }
        const children = Array.isArray(sec.children) ? (sec.children as Array<Record<string, unknown>>) : []
        if (children.length) {
          const nextChildren = walk(children)
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
    const nextSections = walk(sections)
    if (!changed) return null
    return { ...doc, sections: nextSections }
  }

  function buildToolbarState() {
    const readonly = $generating || lockEditing
    const focused = hasEditableFocus()
    let bold = false
    let italic = false
    let underline = false
    const historyCanUndo = $historyIndex > 0
    const historyCanRedo = $historyIndex >= 0 && $historyIndex < $history.length - 1
    let canUndo = !readonly && (focused || historyCanUndo)
    let canRedo = !readonly && (focused || historyCanRedo || nativeRedoHint)
    try {
      bold = Boolean(document.queryCommandState('bold'))
      italic = Boolean(document.queryCommandState('italic'))
      underline = Boolean(document.queryCommandState('underline'))
    } catch {}
    try {
      const nativeUndo = Boolean(document.queryCommandEnabled('undo'))
      const nativeRedo = Boolean(document.queryCommandEnabled('redo'))
      canUndo = !readonly && (nativeUndo || historyCanUndo)
      canRedo = !readonly && (nativeRedo || historyCanRedo || nativeRedoHint)
    } catch {}
    const hasSelection = hasNativeTextSelection() || selectedBlockIds.length > 0
    const canCopy = hasSelection
    const canCut = !readonly && hasSelection
    const canPaste = !readonly && (focused || selectedBlockIds.length > 0)
    return {
      focused,
      readonly,
      bold,
      italic,
      underline,
      hasSelection,
      canUndo,
      canRedo,
      canCopy,
      canCut,
      canPaste
    }
  }

  function emitToolbarState(force = false) {
    const state = buildToolbarState()
    const sig = JSON.stringify(state)
    if (!force && sig === lastToolbarStateSig) return
    lastToolbarStateSig = sig
    ontoolbarstate?.(state)
  }

  function refreshToolbarStateSoon() {
    emitToolbarState(true)
    queueMicrotask(() => emitToolbarState(true))
    setTimeout(() => emitToolbarState(true), 20)
    setTimeout(() => emitToolbarState(true), 80)
    setTimeout(() => emitToolbarState(true), 160)
    setTimeout(() => emitToolbarState(true), 320)
  }

  async function copySelectionWithFallback() {
    if (hasNativeTextSelection()) {
      document.execCommand('copy')
      return true
    }
    if (!$docIr || typeof $docIr !== 'object') return false
    const ids = realBlockTargetIds(selectedBlockIds)
    if (!ids.length) return false
    const blocks = collectBlocksByIds($docIr as Record<string, unknown>, ids)
    if (!blocks.length) return false
    blockClipboard = blocks.map((b, idx) => cloneBlockForPaste(b, idx))
    const text = blocks.map((b) => blockToPlainText(b)).filter(Boolean).join('\n\n')
    await writeClipboardText(text)
    return true
  }

  async function cutSelectionWithFallback() {
    if (hasNativeTextSelection()) {
      document.execCommand('cut')
      return true
    }
    if (!$docIr || typeof $docIr !== 'object') return false
    const ids = realBlockTargetIds(selectedBlockIds)
    if (!ids.length) return false
    const copied = await copySelectionWithFallback()
    if (!copied) return false
    const nextDoc = deleteBlocksByIds($docIr as Record<string, unknown>, ids)
    if (!nextDoc) return false
    applyDocIrUpdate(nextDoc)
    setSelectedBlocksByIds([])
    return true
  }

  async function pasteSelectionWithFallback() {
    if (hasNativeTextSelection()) {
      const text = await readClipboardText()
      if (!text) return false
      document.execCommand('insertText', false, text)
      return true
    }
    if (!$docIr || typeof $docIr !== 'object') return false
    const anchorIds = realBlockTargetIds(selectedBlockIds)
    const anchorId = anchorIds.length ? anchorIds[anchorIds.length - 1] : ''
    let payloadBlocks = blockClipboard.map((b, idx) => cloneBlockForPaste(b, idx))
    if (!payloadBlocks.length) {
      const text = (await readClipboardText()).trim()
      if (!text) return false
      payloadBlocks = text
        .split(/\n{2,}/)
        .map((part) => part.trim())
        .filter(Boolean)
        .map((part, idx) => ({ id: `${makeId()}_${idx + 1}`, type: 'paragraph', text: part }))
    }
    const baseDoc = $docIr as Record<string, unknown>
    const nextDoc = anchorId
      ? insertBlocksAfter(baseDoc, anchorId, payloadBlocks)
      : appendBlocksToDoc(baseDoc, payloadBlocks)
    if (!nextDoc) return false
    applyDocIrUpdate(nextDoc)
    setSelectedBlocksByIds(payloadBlocks.map((b) => String(b.id || '')).filter(Boolean))
    return true
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
    if (!$generating && !lockEditing) editor.dataset.caretActive = '1'
    if (target.closest('a,button,input,textarea,select,[data-wa-no-marquee="1"]')) return
    const block = target.closest('[data-block-id], [data-section-id], [data-doc-title="1"]') as HTMLElement | null
    if (block && editor.contains(block)) {
      const blockRect = block.getBoundingClientRect()
      const inSelectionGutter = event.clientX >= blockRect.left - 34 && event.clientX < blockRect.left + 3
      if (inSelectionGutter && !event.altKey && !event.ctrlKey && !event.metaKey) {
        event.preventDefault()
        selectParagraphText(block, event.shiftKey)
        suppressClickOnce = true
        return
      }
    }
    if (block && editor.contains(block) && (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey)) {
      const id = blockIdOf(block)
      if (id) {
        event.preventDefault()
        if (event.shiftKey) {
          selectRangeTo(id)
        } else if (event.ctrlKey || event.metaKey) {
          toggleSelectedBlock(id)
        } else {
          setSelectedBlocksByIds([id], id)
        }
        suppressClickOnce = true
        return
      }
    }
    if (!event.altKey) return
    dragSelectSeed = { x: event.clientX, y: event.clientY }
    dragSelecting = false
    dragRect = { left: event.clientX, top: event.clientY, width: 0, height: 0 }
    window.addEventListener('mousemove', handleMarqueeMouseMove)
    window.addEventListener('mouseup', handleMarqueeMouseUp)
  }

  function placeCaretAtBlockEnd(el: HTMLElement) {
    if (!el.isContentEditable) return
    editor?.focus()
    const range = document.createRange()
    range.selectNodeContents(el)
    const empty = !normalizeInlineText(plainTextFromElement(el))
    range.collapse(empty)
    const sel = window.getSelection()
    sel?.removeAllRanges()
    sel?.addRange(range)
  }

  function nearestEditableByClickY(y: number): HTMLElement | null {
    if (!editor) return null
    const nodes = Array.from(editor.querySelectorAll('[data-wa-edit="1"]')) as HTMLElement[]
    if (!nodes.length) return null
    nodes.sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top)
    const first = nodes[0]
    const last = nodes[nodes.length - 1]
    if (y <= first.getBoundingClientRect().top + 4) return first
    if (y >= last.getBoundingClientRect().bottom - 4) return last
    let best = first
    let bestDist = Number.POSITIVE_INFINITY
    for (const node of nodes) {
      const rect = node.getBoundingClientRect()
      const center = rect.top + rect.height / 2
      const dist = Math.abs(y - center)
      if (dist < bestDist) {
        best = node
        bestDist = dist
      }
    }
    return best
  }

  function isBlockRailClick(event: MouseEvent, block: HTMLElement): boolean {
    const rect = block.getBoundingClientRect()
    return event.clientX <= rect.left + 18
  }

  function handleEditorClick(event: MouseEvent) {
    if (slashMenuOpen) closeSlashMenu()
    if (suppressClickOnce) {
      suppressClickOnce = false
      return
    }
    const target = event.target as HTMLElement | null
    if (!target || !editor) return
    const textBlock = target.closest('p[data-block-id], h1, h2, h3, h4, h5, h6, [data-section-id], [data-doc-title="1"]') as HTMLElement | null
    if (event.detail >= 3 && textBlock && editor.contains(textBlock)) {
      event.preventDefault()
      selectParagraphText(textBlock)
      return
    }
    const object = target.closest('figure[data-block-id], .wa-table[data-block-id], .wa-page-break[data-block-id]') as HTMLElement | null
    if (object && editor.contains(object)) {
      event.preventDefault()
      selectObjectBlock(object)
      return
    }
    const block = target.closest('[data-block-id], [data-section-id], [data-doc-title="1"]') as HTMLElement | null
    if (!block || !editor.contains(block)) {
      clearSelectedBlock()
      if (!$generating && !lockEditing) {
        const anchor =
          nearestEditableByClickY(event.clientY) ||
          (editor.querySelector('[data-wa-edit="1"]') as HTMLElement | null)
        if (anchor) placeCaretAtBlockEnd(anchor)
      }
      return
    }
    const id = blockIdOf(block)
    if (!id) {
      clearSelectedBlock()
      return
    }
    const railSelectMode = isBlockRailClick(event, block)
    const appendMode = event.ctrlKey || event.metaKey
    const explicitBlockSelect = event.shiftKey || appendMode || event.altKey || railSelectMode
    if (!explicitBlockSelect) {
      clearSelectedBlock()
      return
    }
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

  function currentSlashMenuItems(): SlashCommandItem[] {
    const q = String(slashMenuQuery || '').trim().toLowerCase()
    if (!q) return slashCommandCatalog
    return slashCommandCatalog.filter((item) => {
      const haystack = `${item.label} ${item.desc} ${item.keywords.join(' ')}`.toLowerCase()
      return haystack.includes(q)
    })
  }

  function closeSlashMenu() {
    slashMenuOpen = false
    slashMenuQuery = ''
    slashMenuActive = 0
  }

  function caretViewportRect(): DOMRect | null {
    const sel = window.getSelection()
    if (!sel || sel.rangeCount === 0) return null
    const range = sel.getRangeAt(0).cloneRange()
    range.collapse(true)
    let rect = range.getBoundingClientRect()
    if (!rect || (rect.width === 0 && rect.height === 0)) {
      const marker = document.createElement('span')
      marker.textContent = '\u200b'
      marker.style.opacity = '0'
      range.insertNode(marker)
      rect = marker.getBoundingClientRect()
      marker.remove()
      sel.removeAllRanges()
      sel.addRange(range)
    }
    return rect || null
  }

  function openSlashMenu(target: EventTarget | null) {
    if ($generating || lockEditing) return
    const editable = resolveEditableElement(target)
    if (!editable) return
    const rect = caretViewportRect() || editable.getBoundingClientRect()
    const width = 320
    const height = 320
    slashMenuLeft = Math.min(Math.max(12, rect.left), Math.max(12, window.innerWidth - width - 12))
    slashMenuTop = Math.min(Math.max(72, rect.bottom + 8), Math.max(72, window.innerHeight - height - 12))
    slashMenuQuery = ''
    slashMenuActive = 0
    slashMenuOpen = true
  }

  function moveSlashActive(delta: number) {
    const items = currentSlashMenuItems()
    if (!items.length) {
      slashMenuActive = 0
      return
    }
    const next = (slashMenuActive + delta + items.length) % items.length
    slashMenuActive = next
  }

  function runSlashCommandByIndex(index: number) {
    const items = currentSlashMenuItems()
    if (!items.length) {
      closeSlashMenu()
      return
    }
    const item = items[Math.max(0, Math.min(index, items.length - 1))]
    closeSlashMenu()
    applyCommand(item.command)
    const active = resolveEditableElement(document.activeElement)
    if (active) scheduleCommit(active, 0)
    queueMicrotask(() => emitToolbarState())
  }

  function mountParagraphBeside(
    reference: HTMLElement,
    block: Record<string, unknown>,
    position: 'before' | 'after'
  ) {
    const paragraph = document.createElement('p')
    paragraph.dataset.blockId = String(block.id || '')
    if (reference.tagName.toLowerCase() === 'p') paragraph.style.cssText = reference.style.cssText
    const text = String(block.text || '')
    if (text) paragraph.textContent = text
    else paragraph.appendChild(document.createElement('br'))
    setEditableAttrs(paragraph)
    if (position === 'before') reference.before(paragraph)
    else reference.after(paragraph)
    focusEditableAtStart(paragraph)
    refreshDocumentMeta()
  }

  function placeCaretAtTextOffset(el: HTMLElement, offset: number) {
    editor?.focus()
    const range = document.createRange()
    let remaining = Math.max(0, offset)
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT)
    let node = walker.nextNode()
    while (node) {
      const length = (node.textContent || '').length
      if (remaining <= length) {
        range.setStart(node, remaining)
        range.collapse(true)
        const selection = window.getSelection()
        selection?.removeAllRanges()
        selection?.addRange(range)
        editingEl = el
        editingKey = String(el.dataset.blockId || '')
        return
      }
      remaining -= length
      node = walker.nextNode()
    }
    placeCaretAtBlockEnd(el)
    editingEl = el
    editingKey = String(el.dataset.blockId || '')
  }

  function splitTextBlockAtCaret(el: HTMLElement): boolean {
    const tag = el.tagName.toLowerCase()
    if (!el.dataset.blockId || (tag !== 'p' && !/^h[1-6]$/.test(tag))) return false
    const doc = $docIr
    if (!doc || typeof doc !== 'object') return false
    const blockId = String(el.dataset.blockId)
    const rawText = plainTextFromElement(el)
    const caret = getCaretOffset(el)
    const offset = caret == null ? rawText.length : Math.max(0, Math.min(rawText.length, caret))
    const beforeText = normalizeInlineText(rawText.slice(0, offset))
    const afterText = normalizeInlineText(rawText.slice(offset))
    const blockStyle = extractBlockStyle(el)
    const isHeading = /^h[1-6]$/.test(tag)

    if (offset === 0) {
      const newBlock: Record<string, unknown> = { id: makeId(), type: 'paragraph', text: '' }
      if (blockStyle && tag === 'p') newBlock.style = blockStyle
      const nextDoc = insertBlockBefore(doc, blockId, newBlock)
      if (!nextDoc) return false
      mountParagraphBeside(el, newBlock, 'before')
      applyDocIrUpdate(nextDoc, { render: false })
      return true
    }

    if (offset >= rawText.length) {
      const payload: Record<string, unknown> = isHeading
        ? { type: 'heading', level: Number(tag.slice(1)), text: beforeText.replace(/\n+/g, ' ').trim() }
        : { type: 'paragraph', text: beforeText }
      if (blockStyle) payload.style = blockStyle
      const committedDoc = updateBlock(doc, blockId, payload) || doc
      const newBlock: Record<string, unknown> = { id: makeId(), type: 'paragraph', text: '' }
      if (blockStyle && tag === 'p') newBlock.style = blockStyle
      const nextDoc = insertBlockAfter(committedDoc, blockId, newBlock)
      if (!nextDoc) return false
      mountParagraphBeside(el, newBlock, 'after')
      applyDocIrUpdate(nextDoc, { render: false })
      return true
    }

    const payload: Record<string, unknown> = isHeading
      ? { type: 'heading', level: Number(tag.slice(1)), text: beforeText.replace(/\n+/g, ' ').trim() }
      : { type: 'paragraph', text: beforeText }
    if (blockStyle) payload.style = blockStyle
    const updated = updateBlock(doc, blockId, payload)
    const newBlock: Record<string, unknown> = { id: makeId(), type: 'paragraph', text: afterText }
    if (!isHeading && blockStyle) newBlock.style = blockStyle
    const nextDoc = insertBlockAfter(updated || doc, blockId, newBlock)
    if (!nextDoc) return false
    el.textContent = beforeText
    mountParagraphBeside(el, newBlock, 'after')
    applyDocIrUpdate(nextDoc, { render: false })
    return true
  }

  function mergeTextBlockWithPrevious(el: HTMLElement): boolean {
    const selection = window.getSelection()
    if (!selection || !selection.isCollapsed || getCaretOffset(el) !== 0) return false
    const tag = el.tagName.toLowerCase()
    if (!el.dataset.blockId || (tag !== 'p' && !/^h[1-6]$/.test(tag))) return false
    const blocks = Array.from(editor?.querySelectorAll('[data-block-id]') || []) as HTMLElement[]
    const index = blocks.indexOf(el)
    if (index <= 0) return false
    const previous = blocks[index - 1]
    const previousTag = previous.tagName.toLowerCase()
    if (!previous.dataset.blockId || (previousTag !== 'p' && !/^h[1-6]$/.test(previousTag))) return false
    const doc = $docIr
    if (!doc || typeof doc !== 'object') return false

    const previousInline = extractRunsFromElement(previous)
    const currentInline = extractRunsFromElement(el)
    const boundary = previousInline.text.length
    const payload: Record<string, unknown> = /^h[1-6]$/.test(previousTag)
      ? { type: 'heading', level: Number(previousTag.slice(1)), text: previousInline.text + currentInline.text }
      : { type: 'paragraph', text: previousInline.text + currentInline.text }
    if (previousInline.runs || currentInline.runs) {
      payload.runs = [
        ...(previousInline.runs || [{ text: previousInline.text }]),
        ...(currentInline.runs || [{ text: currentInline.text }])
      ].filter((run) => String(run.text || ''))
    }
    const updated = updateBlock(doc, String(previous.dataset.blockId), payload)
    if (!updated) return false
    const nextDoc = deleteBlocksByIds(updated, [String(el.dataset.blockId)])
    if (!nextDoc) return false

    if (previous.querySelector(':scope > br') && !previousInline.text) previous.innerHTML = ''
    while (el.firstChild) previous.appendChild(el.firstChild)
    el.remove()
    placeCaretAtTextOffset(previous, boundary)
    refreshDocumentMeta()
    applyDocIrUpdate(nextDoc, { render: false })
    return true
  }

  function handleBeforeInput(event: InputEvent) {
    if ($generating || lockEditing || composing) return
    if (event.inputType !== 'insertParagraph') return
    const el =
      resolveEditableElement(event.target) ||
      resolveEditableFromSelection() ||
      resolveEditableAtCaret()
    if (!el) return
    // IME and embedded webviews do not always deliver a useful keydown target.
    // Intercept before the browser mutates the DOM so Enter is always a DocIR
    // block operation and never a whole-document reparse.
    if (splitTextBlockAtCaret(el)) event.preventDefault()
  }

  function hasUntrackedParagraphStructure(): boolean {
    if (!editor) return false
    const body = editor.querySelector('.wa-body') as HTMLElement | null
    if (!body) return false
    const seenBlockIds = new Set<string>()
    return Array.from(body.children).some((node) => {
      const el = node as HTMLElement
      const blockId = String(el.dataset.blockId || '')
      // Chromium clones data-* attributes when a multiline paste splits a
      // paragraph. Duplicate block IDs therefore mean new semantic paragraphs
      // even though every element appears to be tracked.
      if (blockId) {
        if (seenBlockIds.has(blockId)) return true
        seenBlockIds.add(blockId)
        return false
      }
      if (el.dataset.sectionId || el.dataset.docTitle === '1') return false
      if (el.matches('figure, table, .wa-table, .wa-figure, .wa-page-break')) return false
      return el.matches('p, div, h1, h2, h3, h4, h5, h6, ul, ol, blockquote, pre')
    })
  }

  function handleEditableFocus(event: FocusEvent) {
    if (editor) editor.dataset.caretActive = '1'
    if ($generating || lockEditing) {
      ;(event.target as HTMLElement | null)?.blur?.()
      if (editor) delete editor.dataset.caretActive
      emitToolbarState()
      return
    }
    const el = findEditableRoot(event.target) || resolveEditableFromSelection()
    if (!el) return
    editingEl = el
    editingKey = String(el.dataset.blockId || el.dataset.sectionId || el.dataset.docTitle || '')
    queueMicrotask(() => emitToolbarState())
  }

  function handleEditableBlur(event: FocusEvent) {
    if (slashMenuOpen) closeSlashMenu()
    const el = findEditableRoot(event.target) || editingEl
    if (el) {
      if (!$generating && !lockEditing) {
        if (hasUntrackedParagraphStructure()) reconcileEditorDom()
        else commitEditableElement(el, { immediate: true })
      }
      if (editingEl === el) {
        editingEl = null
        editingKey = ''
      }
      if (pendingRenderSig && pendingRenderSig !== lastRenderSig) {
        syncFromStore()
      }
    }
    queueMicrotask(() => {
      if (!editor) return
      const active = document.activeElement as HTMLElement | null
      if (active && editor.contains(active)) editor.dataset.caretActive = '1'
      else delete editor.dataset.caretActive
    })
    queueMicrotask(() => emitToolbarState())
  }

  function handleEditableInput(event: Event) {
    if ($generating || lockEditing) return
    if (composing) return
    const inputType = event instanceof InputEvent ? String(event.inputType || '') : ''
    // Do not rely on inputType: WebView2 and clipboard bridges may report a
    // multiline paste as ordinary insertText. The DOM structure is the source
    // of truth, so reconcile whenever Chromium has cloned a paragraph block.
    if (hasUntrackedParagraphStructure()) {
      handleInput(0)
      return
    }
    // Some browsers target the outer editing host for Enter, so the keydown
    // block splitter cannot always identify the active DocIR block. In that
    // case the browser has already created the visual paragraph; reconcile
    // the whole editable tree immediately so the new paragraph and trailing
    // text cannot be lost by a later per-block commit.
    if (inputType === 'insertParagraph') {
      handleInput(0)
      return
    }
    // A multiline paste can make the browser create new paragraph elements.
    // Reconcile that structure as a document operation instead of attaching
    // all pasted paragraphs to whichever block happened to own the caret.
    if (inputType === 'insertFromPaste' || inputType === 'insertFromDrop') {
      queueMicrotask(() => {
        if (hasUntrackedParagraphStructure()) handleInput(0)
        else {
          const pastedInto = resolveEditableElement(event.target) || resolveEditableFromSelection()
          if (pastedInto) scheduleCommit(pastedInto, 0)
        }
      })
      return
    }
    if (inputType === 'historyUndo') nativeRedoHint = true
    else if (inputType === 'historyRedo') nativeRedoHint = false
    else nativeRedoHint = false
    const historyNavigation = inputType === 'historyUndo' || inputType === 'historyRedo'
    if (historyNavigation) refreshToolbarStateSoon()
    const el = resolveEditableElement(event.target)
    if (!el) return
    editingEl = el
    editingKey = String(el.dataset.blockId || el.dataset.sectionId || el.dataset.docTitle || '')
    scheduleCommit(el)
    queueMicrotask(() => refreshDocumentMeta())
    if (!historyNavigation) queueMicrotask(() => emitToolbarState())
  }

  function handleCompositionStart() {
    composing = true
    emitToolbarState()
  }

  function handleCompositionEnd(event: CompositionEvent) {
    composing = false
    handleEditableInput(event)
    queueMicrotask(() => emitToolbarState())
  }


  function ensureEditableFocus(): HTMLElement | null {
    if (!editor) return null
    if (selectionInsideEditor()) {
      const selectedRoot = resolveEditableFromSelection()
      if (selectedRoot) return selectedRoot
    }
    const active = document.activeElement as HTMLElement | null
    const activeRoot = findEditableRoot(active)
    if (activeRoot) return activeRoot
    const caretRoot = resolveEditableAtCaret()
    if (caretRoot) return caretRoot
    const selected = selectedBlockEls[0] || null
    if (selected && selected.isContentEditable) {
      editor.focus()
      return selected
    }
    const first = editor.querySelector('[data-wa-edit="1"]') as HTMLElement | null
    if (first) {
      editor.focus()
      return first
    }
    return null
  }

  function hasEditableFocus() {
    if (!editor) return false
    const active = document.activeElement as HTMLElement | null
    return Boolean(active && editor.contains(active) && active.isContentEditable)
  }

  function runNativeUndoRedo(kind: 'undo' | 'redo') {
    const active = ensureEditableFocus()
    if (!active) return false
    try {
      const ok = document.execCommand(kind)
      if (!ok) return false
      scheduleCommit(active, 0)
      return true
    } catch {
      return false
    }
  }

  function applyPageSettingsToEditor() {
    if (!editor) return
    const settings = $pageSettings
    const [width, height] = pageSizeCm()
    editor.style.width = `min(100%, ${width}cm)`
    editor.style.minHeight = `${height}cm`
    editor.style.padding = `${settings.marginTop}cm ${settings.marginRight}cm ${settings.marginBottom}cm ${settings.marginLeft}cm`
    const header = editor.querySelector('.wa-header') as HTMLElement | null
    const footer = editor.querySelector('.wa-footer') as HTMLElement | null
    if (header) {
      header.style.display = settings.showHeader && settings.headerText.trim() ? 'block' : 'none'
      header.textContent = settings.headerText || ''
    }
    if (footer) {
      updateFooterText(documentMeta.pages)
    }
    queueMicrotask(() => refreshDocumentMeta())
  }

  function updateSelectionContext() {
    const sel = window.getSelection()
    if (editor) {
      const pages = Math.max(1, documentMeta.pages)
      documentMeta = { ...documentMeta, currentPage: caretPage(pages) }
    }
    if (!editor || !sel || sel.rangeCount === 0 || sel.isCollapsed || !selectionInsideEditor()) {
      selectionToolbar.visible = false
      documentMeta = { ...documentMeta, selected: 0 }
      return
    }
    const range = sel.getRangeAt(0)
    savedTextRange = range.cloneRange()
    const text = sel.toString()
    const rect = range.getBoundingClientRect()
    if (!text.trim() || (!rect.width && !rect.height)) {
      selectionToolbar.visible = false
      return
    }
    const width = 342
    selectionToolbar = {
      visible: true,
      left: Math.max(10, Math.min(window.innerWidth - width - 10, rect.left + rect.width / 2 - width / 2)),
      top: Math.max(58, rect.top - 43),
      text,
      words: text.replace(/\s/g, '').length
    }
    documentMeta = { ...documentMeta, selected: selectionToolbar.words }
  }

  function restoreSavedTextRange() {
    if (!savedTextRange || !editor) return false
    const container = savedTextRange.commonAncestorContainer
    if (!editor.contains(container)) return false
    const sel = window.getSelection()
    sel?.removeAllRanges()
    sel?.addRange(savedTextRange.cloneRange())
    return true
  }

  function runRustUndoRedo(kind: 'undo' | 'redo') {
    if (!documentEngineReady()) return false
    const markdown = kind === 'undo' ? undoMarkdown() : redoMarkdown()
    if (markdown == null) return false
    const currentTitle =
      $docIr && typeof $docIr === 'object'
        ? String(($docIr as Record<string, unknown>).title || '')
        : ''
    const nextDoc = textToDocIr(markdown, currentTitle)
    if (nextDoc) {
      docIr.set(nextDoc)
      docIrDirty.set(false)
    }
    sourceText.set(markdown)
    pushHistory(markdown)
    lastRenderSig = ''
    syncFromStore()
    return true
  }

  function applyCommand(cmd: string) {
    const readonly = $generating || lockEditing
    const lower = String(cmd || '').toLowerCase()
    if (lower === 'copy') {
      void copySelectionWithFallback()
      emitToolbarState()
      return
    }
    if (lower === 'cut') {
      if (!readonly) void cutSelectionWithFallback()
      emitToolbarState()
      return
    }
    if (lower === 'paste') {
      if (!readonly) void pasteSelectionWithFallback()
      emitToolbarState()
      return
    }
    if (lower === 'find-replace') {
      showFindReplace = true
      return
    }
    if (lower === 'view-outline') {
      showNavigationPane = !showNavigationPane
      return
    }
    if (lower === 'zoom-in') return setEditorZoom(editorZoom + 10)
    if (lower === 'zoom-out') return setEditorZoom(editorZoom - 10)
    if (lower === 'zoom-100') return setEditorZoom(100)
    if (lower === 'undo') {
      if (readonly) {
        emitToolbarState()
        return
      }
      if (!runNativeUndoRedo('undo') && !runRustUndoRedo('undo')) undoHistory()
      nativeRedoHint = true
      refreshToolbarStateSoon()
      return
    }
    if (lower === 'redo') {
      if (readonly) {
        emitToolbarState()
        return
      }
      if (!runNativeUndoRedo('redo') && !runRustUndoRedo('redo')) redoHistory()
      nativeRedoHint = false
      refreshToolbarStateSoon()
      return
    }
    restoreSavedTextRange()
    const commandTarget = ensureEditableFocus()
    if (!commandTarget) return

    const exec = (name: string, value?: string) => {
      restoreSavedTextRange()
      const ok = document.execCommand(name, false, value)
      savedTextRange = window.getSelection()?.rangeCount ? window.getSelection()!.getRangeAt(0).cloneRange() : savedTextRange
      scheduleCommit(commandTarget, 0)
      refreshToolbarStateSoon()
      return ok
    }
    
    // 基础格式
    if (cmd === 'bold') return exec('bold')
    if (cmd === 'italic') return exec('italic')
    if (cmd === 'underline') return exec('underline')
    if (cmd === 'strikethrough') return exec('strikeThrough')
    if (cmd === 'superscript') return exec('superscript')
    if (cmd === 'subscript') return exec('subscript')
    
    // 标题
    if (cmd === 'heading1') return exec('formatBlock', 'H1')
    if (cmd === 'heading2') return exec('formatBlock', 'H2')
    if (cmd === 'heading3') return exec('formatBlock', 'H3')
    if (cmd === 'heading4') return exec('formatBlock', 'H4')
    if (cmd === 'heading5') return exec('formatBlock', 'H5')
    if (cmd === 'heading6') return exec('formatBlock', 'H6')
    if (cmd === 'paragraph') return exec('formatBlock', 'P')
    
    // 列表与缩进
    if (cmd === 'list-bullet') return exec('insertUnorderedList')
    if (cmd === 'list-number') return exec('insertOrderedList')
    if (cmd === 'indent') return exec('indent')
    if (cmd === 'outdent') return exec('outdent')
    if (cmd === 'quote') return exec('formatBlock', 'BLOCKQUOTE')
    
    // 对齐
    if (cmd === 'align-left') return exec('justifyLeft')
    if (cmd === 'align-center') return exec('justifyCenter')
    if (cmd === 'align-right') return exec('justifyRight')
    if (cmd === 'align-justify') return exec('justifyFull')
    
    // 行距
    if (cmd.startsWith('line-height:')) {
      const height = cmd.slice(12)
      const sel = window.getSelection()
      if (sel && sel.rangeCount) {
        const range = sel.getRangeAt(0)
        let node: Node | null = range.commonAncestorContainer
        if (node.nodeType === Node.TEXT_NODE) node = node.parentElement
        if (node instanceof HTMLElement) {
          let block = node.closest('p, div, h1, h2, h3, blockquote')
          if (block instanceof HTMLElement) {
            block.style.lineHeight = height
            scheduleCommit(block, 0)
          }
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
        let node: Node | null = range.commonAncestorContainer
        if (node.nodeType === Node.TEXT_NODE) node = node.parentElement
        if (node instanceof HTMLElement) {
          let block = node.closest('p, div, h1, h2, h3')
          if (block instanceof HTMLElement) {
            block.style.margin = margin
            scheduleCommit(block, 0)
          }
        }
      }
      return
    }
    
    // 首行缩进
    if (cmd === 'indent-first') {
      const sel = window.getSelection()
      if (sel && sel.rangeCount) {
        const range = sel.getRangeAt(0)
        let node: Node | null = range.commonAncestorContainer
        if (node.nodeType === Node.TEXT_NODE) node = node.parentElement
        if (node instanceof HTMLElement) {
          let block = node.closest('p, div')
          if (block instanceof HTMLElement) {
            block.style.textIndent = '2em'
            scheduleCommit(block, 0)
          }
        }
      }
      return
    }
    
    // 颜色
    if (cmd.startsWith('color:')) {
      const color = cmd.slice(6)
      return exec('foreColor', color)
    }
    if (cmd.startsWith('bgcolor:')) {
      const color = cmd.slice(8)
      return exec('hiliteColor', color)
    }
    
    // 字体
    if (cmd.startsWith('font:')) {
      const font = cmd.slice(5)
      return exec('fontName', font)
    }
    
    // 字号
    if (cmd.startsWith('size:')) {
      const raw = cmd.slice(5).trim()
      const size = /^\d+(\.\d+)?$/.test(raw) ? `${raw}px` : raw
      restoreSavedTextRange()
      document.execCommand('fontSize', false, '7')
      commandTarget.querySelectorAll('font[size="7"]').forEach((node) => {
        const span = document.createElement('span')
        span.style.fontSize = size
        while (node.firstChild) span.appendChild(node.firstChild)
        node.replaceWith(span)
      })
      scheduleCommit(commandTarget, 0)
      refreshToolbarStateSoon()
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
      const anchorId = String(commandTarget.dataset.blockId || '')
      const input = document.createElement('input')
      input.type = 'file'
      input.accept = 'image/*'
      input.onchange = async (e) => {
        const file = (e.target as HTMLInputElement).files?.[0]
        if (!file) return
        const reader = new FileReader()
        reader.onload = (ev) => {
          const dataUrl = ev.target?.result as string
          const doc = $docIr
          if (!doc || typeof doc !== 'object') return
          const imageBlock: Record<string, unknown> = {
            id: makeId(),
            type: 'figure',
            figure: { type: 'image', src: dataUrl, caption: file.name.replace(/\.[^.]+$/, '') || '图片' }
          }
          const paragraph: Record<string, unknown> = { id: makeId(), type: 'paragraph', text: '' }
          const next = anchorId
            ? insertBlocksAfter(doc as Record<string, unknown>, anchorId, [imageBlock, paragraph])
            : appendBlocksToDoc(doc as Record<string, unknown>, [imageBlock, paragraph])
          if (next) {
            pendingFocusBlockId = String(paragraph.id)
            applyDocIrUpdate(next, { immediate: true })
          }
        }
        reader.readAsDataURL(file)
      }
      input.click()
      return
    }

    if (cmd === 'page-break') {
      const doc = $docIr
      if (!doc || typeof doc !== 'object') return
      const anchorId = String(commandTarget.dataset.blockId || '')
      const breakBlock: Record<string, unknown> = { id: makeId(), type: 'page_break' }
      const paragraph: Record<string, unknown> = { id: makeId(), type: 'paragraph', text: '' }
      const next = anchorId
        ? insertBlocksAfter(doc as Record<string, unknown>, anchorId, [breakBlock, paragraph])
        : appendBlocksToDoc(doc as Record<string, unknown>, [breakBlock, paragraph])
      if (next) {
        pendingFocusBlockId = String(paragraph.id)
        applyDocIrUpdate(next, { immediate: true })
      }
      return
    }
    
    // 表格
    if (cmd === 'table') {
      tableInsertOpen = true
      return
    }

    if (cmd === 'caption') {
      if (!objectToolbar.blockId) {
        alert('请先单击选择图片、图表或表格。')
        return
      }
      const doc = $docIr
      if (!doc || typeof doc !== 'object') return
      const block = collectBlocksByIds(doc as Record<string, unknown>, [objectToolbar.blockId])[0]
      if (!block) return
      const isTable = String(block.type || '') === 'table'
      const current = isTable
        ? String((block.table as Record<string, unknown> | undefined)?.caption || '')
        : String((block.figure as Record<string, unknown> | undefined)?.caption || '')
      const caption = prompt(isTable ? '表格题注：' : '图片题注：', current || (isTable ? '表 1 ' : '图 1 '))
      if (!caption) return
      const payload = isTable
        ? { type: 'table', table: { ...(block.table as Record<string, unknown> || {}), caption } }
        : { type: 'figure', figure: { ...(block.figure as Record<string, unknown> || {}), caption } }
      const next = updateBlock(doc as Record<string, unknown>, objectToolbar.blockId, payload)
      if (next) {
        objectToolbar.visible = false
        applyDocIrUpdate(next, { immediate: true })
      }
      return
    }

    if (cmd === 'cross-reference') {
      const targets = outlineItems.map((item, index) => `${index + 1}. ${item.text}`).join('\n')
      if (!targets) {
        alert('当前文档中没有可引用的标题。')
        return
      }
      const value = prompt(`输入要引用的标题序号：\n${targets}`, '1')
      const index = Number(value) - 1
      const target = outlineItems[index]
      if (!target) return
      return exec('insertText', `见“${target.text}”`)
    }

    if (cmd === 'thesis-structure') {
      const doc = $docIr
      if (!doc || typeof doc !== 'object') return
      const blocks: Array<Record<string, unknown>> = [
        { id: makeId(), type: 'heading', level: 1, text: '摘要' },
        { id: makeId(), type: 'paragraph', text: '在此撰写中文摘要。' },
        { id: makeId(), type: 'heading', level: 1, text: 'Abstract' },
        { id: makeId(), type: 'paragraph', text: 'Write the English abstract here.' },
        { id: makeId(), type: 'page_break' },
        { id: makeId(), type: 'heading', level: 1, text: '1 绪论' },
        { id: makeId(), type: 'heading', level: 2, text: '1.1 研究背景' },
        { id: makeId(), type: 'paragraph', text: '' },
        { id: makeId(), type: 'heading', level: 1, text: '2 相关理论与关键技术' },
        { id: makeId(), type: 'paragraph', text: '' },
        { id: makeId(), type: 'heading', level: 1, text: '3 系统分析与设计' },
        { id: makeId(), type: 'paragraph', text: '' },
        { id: makeId(), type: 'heading', level: 1, text: '4 系统实现' },
        { id: makeId(), type: 'paragraph', text: '' },
        { id: makeId(), type: 'heading', level: 1, text: '5 系统测试' },
        { id: makeId(), type: 'paragraph', text: '' },
        { id: makeId(), type: 'heading', level: 1, text: '6 总结与展望' },
        { id: makeId(), type: 'paragraph', text: '' },
        { id: makeId(), type: 'heading', level: 1, text: '参考文献' },
        { id: makeId(), type: 'paragraph', text: '' },
        { id: makeId(), type: 'heading', level: 1, text: '致谢' },
        { id: makeId(), type: 'paragraph', text: '' }
      ]
      const next = appendBlocksToDoc(doc as Record<string, unknown>, blocks)
      if (next) applyDocIrUpdate(next, { immediate: true })
      return
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
    if (cmd === 'clear-format') return exec('removeFormat')
  }

  function handleKeydown(e: KeyboardEvent) {
    const ctrl = e.ctrlKey || e.metaKey
    const key = String(e.key || '').toLowerCase()
    const blockShortcutMode = !hasEditableFocus() && selectedBlockIds.length > 0
    const activeEditable =
      resolveEditableElement(e.target) ||
      resolveEditableFromSelection() ||
      resolveEditableAtCaret()
    if (slashMenuOpen) {
      if (key === 'escape') {
        e.preventDefault()
        closeSlashMenu()
        return
      }
      if (key === 'arrowdown') {
        e.preventDefault()
        moveSlashActive(1)
        return
      }
      if (key === 'arrowup') {
        e.preventDefault()
        moveSlashActive(-1)
        return
      }
      if (key === 'enter' || key === 'tab') {
        e.preventDefault()
        runSlashCommandByIndex(slashMenuActive)
        return
      }
      if (key === 'backspace') {
        e.preventDefault()
        slashMenuQuery = String(slashMenuQuery || '').slice(0, -1)
        slashMenuActive = 0
        return
      }
      if (!ctrl && !e.altKey && !e.metaKey && e.key.length === 1) {
        e.preventDefault()
        slashMenuQuery += e.key
        slashMenuActive = 0
        return
      }
    }
    if (!ctrl && !e.altKey && e.key === '/' && activeEditable) {
      e.preventDefault()
      openSlashMenu(e.target)
      return
    }
    if (ctrl && key === 'b') {
      e.preventDefault()
      applyCommand('bold')
      return
    }
    if (ctrl && key === 'i') {
      e.preventDefault()
      applyCommand('italic')
      return
    }
    if (ctrl && key === 'u') {
      e.preventDefault()
      applyCommand('underline')
      return
    }
    if (ctrl && e.shiftKey && key === 'x') {
      e.preventDefault()
      applyCommand('strikethrough')
      return
    }
    if (ctrl && key === 'z' && e.shiftKey) {
      e.preventDefault()
      applyCommand('redo')
      return
    }
    if (ctrl && key === 'z') {
      e.preventDefault()
      applyCommand('undo')
      return
    }
    if (ctrl && key === 'y') {
      e.preventDefault()
      applyCommand('redo')
      return
    }
    if (ctrl && key === 'k') {
      e.preventDefault()
      applyCommand('link')
      return
    }
    if (ctrl && key === 'f') {
      e.preventDefault()
      showFindReplace = true
      emitToolbarState()
      return
    }
    if (ctrl && key === 'c') {
      if (blockShortcutMode && !hasNativeTextSelection()) {
        e.preventDefault()
        applyCommand('copy')
        return
      }
    }
    if (ctrl && key === 'x') {
      if (blockShortcutMode && !hasNativeTextSelection()) {
        e.preventDefault()
        applyCommand('cut')
        return
      }
    }
    if (ctrl && key === 'v') {
      if (blockShortcutMode && !hasNativeTextSelection()) {
        e.preventDefault()
        applyCommand('paste')
        return
      }
    }
    if (!ctrl && !e.altKey && key === 'backspace' && activeEditable) {
      if (mergeTextBlockWithPrevious(activeEditable)) {
        e.preventDefault()
        return
      }
    }
    if (e.key === 'Enter' && e.shiftKey && !ctrl) {
      const el = activeEditable
      if (el && el.dataset.blockId) {
        const tag = el.tagName.toLowerCase()
        if (tag !== 'ul' && tag !== 'ol') {
          e.preventDefault()
          document.execCommand('insertLineBreak')
          scheduleCommit(el, 0)
          queueMicrotask(() => emitToolbarState())
          return
        }
      }
    }
    if (e.key === 'Enter' && ctrl) {
      e.preventDefault()
      applyCommand('page-break')
      return
    }
    if (e.key === 'Enter' && !e.shiftKey && !ctrl) {
      const el = activeEditable
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
          splitTextBlockAtCaret(el)
          return
        }
      }
    }
    queueMicrotask(() => emitToolbarState())
  }

  let showFindReplace = $state(false)
  let findText = $state('')
  let replaceText = $state('')
  let showFontPanel = $state(false)
  let showColorPanel = $state(false)
  let showBgColorPanel = $state(false)
  let showLineHeightPanel = $state(false)
  let showTableMenu = $state(false)
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
      newCell.style.cssText = (cell as HTMLElement).style.cssText
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
    if (!editor) return
    // KaTeX auto-render walks adjacent text nodes and may move the first
    // character across editable block boundaries even when the document has
    // no formula. Keep ordinary prose untouched and only invoke it when a
    // supported delimiter is actually present.
    const text = String(editor.textContent || '')
    if (!text.includes('$')) return
    try {
      renderMathInElement(editor, {
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
    if (!editor) return
    editor.querySelectorAll('pre code').forEach((block) => {
      Prism.highlightElement(block)
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

  function reconcileEditorDom() {
    if (!editor) return
    historyTimer = null
    // Always serialize the latest DOM. Capturing HTML when the event fires
    // allows subsequent keystrokes to be overwritten by a stale snapshot.
    const html = editor.innerHTML || ''
    const markdown = htmlToMarkdown(html)
    lastMarkdown = markdown
    const currentTitle =
      $docIr && typeof $docIr === 'object'
        ? String(($docIr as Record<string, unknown>).title || '')
        : ''
    const doc = htmlToDocIr(html, currentTitle)
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
  }

  function handleInput(delayMs = 300) {
    if (!editor) return
    if (historyTimer) clearTimeout(historyTimer)
    if (delayMs <= 0) {
      reconcileEditorDom()
      return
    }
    historyTimer = setTimeout(() => reconcileEditorDom(), delayMs)
  }

  const unsubscribe = editorCommand.subscribe((cmd) => {
    if (cmd) {
      const command = typeof cmd === 'string' ? cmd : cmd.command
      if (command === 'commit') {
        flushPendingEditableState()
        editorCommand.set(null)
        queueMicrotask(() => emitToolbarState())
        return
      }
      applyCommand(command)
      editorCommand.set(null)
      queueMicrotask(() => emitToolbarState())
    }
  })

  onMount(() => {
    void loadPageSettings().then(() => applyPageSettingsToEditor())
    syncFromStore()
    if (!docIrHasRenderableContent($docIr)) {
      const fromText = String($sourceText || '').trim()
      const currentTitle =
        $docIr && typeof $docIr === 'object'
          ? String(($docIr as Record<string, unknown>).title || '')
          : ''
      const doc = fromText ? textToDocIr(fromText, currentTitle) : null
      if (doc) {
        docIr.set(doc)
        docIrDirty.set(false)
      } else {
        docIr.set(createSeedDoc(currentTitle))
        docIrDirty.set(false)
      }
    }
    sourceUnsub = sourceText.subscribe(() => syncFromStore())
    docIrUnsub = docIr.subscribe(() => syncFromStore())
    const initialMarkdown = docIrHasRenderableContent($docIr)
      ? docIrToMarkdown($docIr as Record<string, unknown>) || ''
      : String($sourceText || '')
    void initDocumentEngine(initialMarkdown).then((ready) => {
      if (!editor) return
      editor.dataset.engine = ready ? 'rust-wasm' : 'typescript-fallback'
      if (ready) {
        const metrics = measureDocument(editor.clientWidth || 794)
        if (metrics) {
          editor.dataset.enginePages = String(metrics.pageCount)
          editor.dataset.engineBlocks = String(metrics.blockCount)
        }
      }
    })
    
    renderMathInEditor()
    highlightCodeBlocks()
    
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
    const onSelectionChange = () => {
      updateSelectionContext()
      emitToolbarState()
    }
    const onEditorMouseUp = () => {
      updateSelectionContext()
      emitToolbarState()
    }
    const onEditorKeyUp = () => emitToolbarState()
    const onPageSettingsChanged = () => applyPageSettingsToEditor()
    const onWindowKeydown = (event: KeyboardEvent) => {
      if (event.defaultPrevented) return
      const ctrl = event.ctrlKey || event.metaKey
      if (!ctrl) return
      const target = event.target as HTMLElement | null
      const editingOutside =
        Boolean(target?.closest('input, textarea, select')) ||
        Boolean(target && target.isContentEditable && !editor?.contains(target))
      if (editingOutside) return
      const key = String(event.key || '').toLowerCase()
      if (!hasEditableFocus() && !selectedBlockIds.length) return
      const blockShortcutMode = !hasEditableFocus() && selectedBlockIds.length > 0
      if (key === 'c') {
        if (blockShortcutMode && !hasNativeTextSelection()) {
          event.preventDefault()
          applyCommand('copy')
        }
        return
      }
      if (key === 'x') {
        if (blockShortcutMode && !hasNativeTextSelection()) {
          event.preventDefault()
          applyCommand('cut')
        }
        return
      }
      if (key === 'v') {
        if (blockShortcutMode && !hasNativeTextSelection()) {
          event.preventDefault()
          applyCommand('paste')
        }
        return
      }
      if (key === 'z' && event.shiftKey) {
        event.preventDefault()
        applyCommand('redo')
        return
      }
      if (key === 'z') {
        event.preventDefault()
        applyCommand('undo')
        return
      }
      if (key === 'y') {
        event.preventDefault()
        applyCommand('redo')
      }
    }
    document.addEventListener('selectionchange', onSelectionChange)
    editor?.addEventListener('mouseup', onEditorMouseUp)
    editor?.addEventListener('keyup', onEditorKeyUp)
    window.addEventListener('keydown', onWindowKeydown)
    window.addEventListener('wa-page-settings-changed', onPageSettingsChanged)
    emitToolbarState(true)
    
    return () => {
      finishMarqueeSelection()
      unsubscribe()
      if (sourceUnsub) sourceUnsub()
      imgObserver.disconnect()
      observer.disconnect()
      document.removeEventListener('selectionchange', onSelectionChange)
      editor?.removeEventListener('mouseup', onEditorMouseUp)
      editor?.removeEventListener('keyup', onEditorKeyUp)
      window.removeEventListener('keydown', onWindowKeydown)
      window.removeEventListener('wa-page-settings-changed', onPageSettingsChanged)
      if (syncTimer) clearTimeout(syncTimer)
      if (historyTimer) clearTimeout(historyTimer)
      if (docTextTimer) clearTimeout(docTextTimer)
      if (editCommitTimer) clearTimeout(editCommitTimer)
    }
  })

  $effect(() => {
    const running = $generating || lockEditing
    if (editor) {
      syncEditorUiFlags()
      markEditableBlocks()
      if (running && editingEl) {
        editingEl.blur()
        editingEl = null
        editingKey = ''
      }
      emitToolbarState()
    }
  })

  $effect(() => {
    $pageSettings
    queueMicrotask(() => applyPageSettingsToEditor())
  })
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
      <button class="tool-btn" onclick={() => (showFontPanel = !showFontPanel)} title="字体">
        <span style="font-family: serif;">A</span>
      </button>
      {#if showFontPanel}
        <div class="dropdown-panel">
          {#each fontList as font}
            <button class="dropdown-item" onclick={() => { applyCommand('font:' + font); showFontPanel = false }} style="font-family: {font}">
              {font}
            </button>
          {/each}
        </div>
      {/if}
    </div>
    
    <div class="toolbar-group">
      <select class="tool-select" onchange={(e) => applyCommand('size:' + e.currentTarget.value)}>
        <option value="">字号</option>
        {#each fontSizes as size}
          <option value={size}>{size}pt</option>
        {/each}
      </select>
    </div>
    
    <div class="toolbar-group">
      <button class="tool-btn" onclick={() => (showColorPanel = !showColorPanel)} title="文字颜色">
        <span style="color: #FF0000;">A</span>
      </button>
      {#if showColorPanel}
        <div class="dropdown-panel color-grid">
          {#each colors as color}
            <button 
              class="color-item" 
              style="background: {color};" 
              aria-label={`文字颜色 ${color}`}
              onclick={() => { applyCommand('color:' + color); showColorPanel = false }}
            ></button>
          {/each}
        </div>
      {/if}
    </div>
    
    <div class="toolbar-group">
      <button class="tool-btn" onclick={() => (showBgColorPanel = !showBgColorPanel)} title="背景颜色">
        <span style="background: #FFFF00;">█</span>
      </button>
      {#if showBgColorPanel}
        <div class="dropdown-panel color-grid">
          {#each colors as color}
            <button 
              class="color-item" 
              style="background: {color};" 
              aria-label={`背景颜色 ${color}`}
              onclick={() => { applyCommand('bgcolor:' + color); showBgColorPanel = false }}
            ></button>
          {/each}
        </div>
      {/if}
    </div>
    
    <span class="separator"></span>
    
    <button class="tool-btn" onclick={() => applyCommand('align-left')} title="左对齐">≡</button>
    <button class="tool-btn" onclick={() => applyCommand('align-center')} title="居中">≡</button>
    <button class="tool-btn" onclick={() => applyCommand('align-right')} title="右对齐">≡</button>
    <button class="tool-btn" onclick={() => applyCommand('align-justify')} title="两端对齐">≡</button>
    
    <span class="separator"></span>
    
    <button class="tool-btn" onclick={() => applyCommand('superscript')} title="上标">x2</button>
    <button class="tool-btn" onclick={() => applyCommand('subscript')} title="下标">x?</button>
    <button class="tool-btn" onclick={() => applyCommand('hr')} title="水平线">—</button>
    
    <span class="separator"></span>
    
    <div class="toolbar-group">
      <button class="tool-btn" onclick={() => (showLineHeightPanel = !showLineHeightPanel)} title="行距">
        ?
      </button>
      {#if showLineHeightPanel}
        <div class="dropdown-panel">
          {#each lineHeights as height}
            <button class="dropdown-item" onclick={() => { applyCommand('line-height:' + height); showLineHeightPanel = false }}>
              {height}倍行距
            </button>
          {/each}
        </div>
      {/if}
    </div>
    
    <button class="tool-btn" onclick={() => applyCommand('indent-first')} title="首行缩进">?</button>
    <button class="tool-btn" onclick={() => applyCommand('margin:10px 0')} title="段间距">?</button>
    
    <span class="separator"></span>
    
    <button class="tool-btn" onclick={() => applyCommand('math-inline')} title="行内公式">??(??)</button>
    <button class="tool-btn" onclick={() => applyCommand('math-block')} title="公式块">∫</button>
    
    <span class="separator"></span>
    
    <button class="tool-btn" onclick={() => applyCommand('footnote')} title="插入脚注">※</button>
    <button class="tool-btn" onclick={() => applyCommand('toc')} title="生成目录">?</button>
    
    <span class="separator"></span>
    
    <div class="toolbar-group">
      <button class="tool-btn" onclick={() => (showTableMenu = !showTableMenu)} title="表格">
        ?
      </button>
      {#if showTableMenu}
        <div class="dropdown-panel">
          <button class="dropdown-item" onclick={() => { applyCommand('table'); showTableMenu = false }}>插入表格</button>
          <button class="dropdown-item" onclick={() => { mergeTableCells(); showTableMenu = false }}>合并单元格</button>
          <button class="dropdown-item" onclick={() => { insertTableRow(); showTableMenu = false }}>插入行</button>
          <button class="dropdown-item" onclick={() => { insertTableCol(); showTableMenu = false }}>插入列</button>
          <button class="dropdown-item" onclick={() => { deleteTableRow(); showTableMenu = false }}>删除行</button>
          <button class="dropdown-item" onclick={() => { deleteTableCol(); showTableMenu = false }}>删除列</button>
        </div>
      {/if}
    </div>
    </div>
  {/if}

  <div class:with-navigation={showNavigationPane} class="editor-workspace">
    {#if showNavigationPane}
      <aside class="navigation-pane" aria-label="文档导航">
        <header>
          <strong>导航</strong>
          <button onclick={() => (showNavigationPane = false)} title="关闭导航窗格">×</button>
        </header>
        <div class="navigation-tabs"><span class="active">标题导航</span></div>
        {#if outlineItems.length}
          <nav>
            {#each outlineItems as item}
              <button style={`--outline-level:${Math.max(0, item.level - 1)}`} onclick={() => jumpToOutline(item.id)}>{item.text}</button>
            {/each}
          </nav>
        {:else}
          <p>应用“标题 1–3”后，这里会形成论文目录。</p>
        {/if}
      </aside>
    {/if}
    <div class="paper-stage">
      <div class="ruler" aria-hidden="true"><span>0</span><span>2</span><span>4</span><span>6</span><span>8</span><span>10</span><span>12</span><span>14</span><span>16</span></div>
      <div
        class="editable"
        data-render-mode={renderMode}
        bind:this={editor}
        contenteditable="true"
        role="region"
        aria-label="文档编辑区"
        onmousedown={handleEditorMouseDown}
        onbeforeinput={handleBeforeInput}
        oninput={handleEditableInput}
        onfocusin={handleEditableFocus}
        onfocusout={handleEditableBlur}
        oncompositionstart={handleCompositionStart}
        oncompositionend={handleCompositionEnd}
        onclick={handleEditorClick}
        onkeydown={handleKeydown}
      ></div>
    </div>
  </div>

  <footer class="word-status-bar">
    <span>第 {documentMeta.currentPage} 页，共 {documentMeta.pages} 页</span>
    <span>{documentMeta.chars} 字符</span>
    <span>{documentMeta.paragraphs} 段</span>
    {#if documentMeta.selected > 0}<span>已选择 {documentMeta.selected} 字</span>{/if}
    <span class="status-spacer"></span>
    <button onclick={() => setEditorZoom(editorZoom - 10)} title="缩小">−</button>
    <input aria-label="缩放" type="range" min="60" max="180" step="10" value={editorZoom} oninput={(event) => setEditorZoom(Number(event.currentTarget.value))} />
    <button onclick={() => setEditorZoom(editorZoom + 10)} title="放大">＋</button>
    <button class="zoom-value" onclick={() => setEditorZoom(100)}>{editorZoom}%</button>
  </footer>

  {#if selectionToolbar.visible}
    <div
      class="selection-toolbar"
      style={`left:${selectionToolbar.left}px;top:${selectionToolbar.top}px;`}
      role="toolbar"
      tabindex="0"
      aria-label="选中文字工具栏"
      onmousedown={(event) => event.preventDefault()}
    >
      <button onclick={() => applyCommand('bold')} title="加粗"><strong>B</strong></button>
      <button onclick={() => applyCommand('italic')} title="斜体"><em>I</em></button>
      <button onclick={() => applyCommand('underline')} title="下划线"><u>U</u></button>
      <button onclick={() => applyCommand('strikethrough')} title="删除线"><s>ab</s></button>
      <span></span>
      <button onclick={() => applyCommand('align-left')} title="左对齐">≡</button>
      <button onclick={() => applyCommand('list-bullet')} title="项目符号">•≡</button>
      <button onclick={() => applyCommand('color:#c00000')} title="红色文字" class="text-red">A</button>
      <button onclick={() => applyCommand('bgcolor:#fff2cc')} title="高亮" class="highlight">A</button>
      <small>{selectionToolbar.words} 字</small>
    </div>
  {/if}

  {#if objectToolbar.visible}
    <div
      class="object-toolbar"
      style={`left:${objectToolbar.left}px;top:${objectToolbar.top}px;`}
      role="toolbar"
      tabindex="0"
      aria-label="对象工具栏"
      onmousedown={(event) => event.preventDefault()}
    >
      <strong>{objectToolbar.kind === 'image' ? '图片' : objectToolbar.kind === 'figure' ? '图表' : objectToolbar.kind === 'table' ? '表格' : '对象'}</strong>
      <button onclick={() => insertParagraphBesideObject('before')}>上方插入段落</button>
      <button onclick={() => insertParagraphBesideObject('after')}>下方插入段落</button>
      {#if objectToolbar.kind === 'figure' || objectToolbar.kind === 'image'}<button onclick={openFigureEditor}>编辑</button>{/if}
      {#if objectToolbar.kind === 'table'}<button onclick={openTableEditor}>编辑表格</button>{/if}
      <button class="danger" onclick={deleteSelectedObject}>删除</button>
    </div>
  {/if}

  {#if tableInsertOpen}
    <div class="figure-editor-backdrop" onclick={() => (tableInsertOpen = false)} role="presentation"></div>
    <div class="figure-editor-dialog compact-dialog" role="dialog" aria-modal="true" aria-label="插入表格" tabindex="-1">
      <header><strong>插入表格</strong><button onclick={() => (tableInsertOpen = false)}>×</button></header>
      <div class="table-size-fields">
        <label>列数<input type="number" min="1" max="12" bind:value={tableInsertCols} /></label>
        <label>数据行数<input type="number" min="1" max="30" bind:value={tableInsertRows} /></label>
      </div>
      <label>题注<input bind:value={tableInsertCaption} /></label>
      <p>第一行会作为表头。插入后可选中表格并通过“编辑表格”粘贴 Excel 数据。</p>
      <footer><button onclick={() => (tableInsertOpen = false)}>取消</button><button class="primary" onclick={insertTableFromDialog}>插入</button></footer>
    </div>
  {/if}

  {#if tableEditorOpen}
    <div class="figure-editor-backdrop" onclick={() => (tableEditorOpen = false)} role="presentation"></div>
    <div class="figure-editor-dialog" role="dialog" aria-modal="true" aria-label="编辑表格" tabindex="-1">
      <header><strong>编辑表格</strong><button onclick={() => (tableEditorOpen = false)}>×</button></header>
      <label>题注<input bind:value={tableDraftCaption} /></label>
      <label>表格数据<textarea class="table-data-editor" rows="14" bind:value={tableDraftTsv}></textarea></label>
      <p>使用 Tab 分隔列、换行分隔行；第一行是表头。可直接从 Excel 复制并粘贴。</p>
      <footer><button onclick={() => (tableEditorOpen = false)}>取消</button><button class="primary" onclick={saveTableEditor}>应用</button></footer>
    </div>
  {/if}

  {#if figureEditorOpen}
    <div class="figure-editor-backdrop" onclick={() => (figureEditorOpen = false)} role="presentation"></div>
    <div class="figure-editor-dialog" role="dialog" aria-modal="true" aria-label="编辑图表" tabindex="-1">
      <header><strong>编辑图表或图片</strong><button onclick={() => (figureEditorOpen = false)}>×</button></header>
      <label>标题<input bind:value={figureDraftCaption} /></label>
      <label>图表数据<textarea rows="14" bind:value={figureDraftJson}></textarea></label>
      <p>修改类型、节点、连接、标签或图片信息后，图表会立即重新渲染。</p>
      <footer><button onclick={() => (figureEditorOpen = false)}>取消</button><button class="primary" onclick={saveFigureEditor}>应用并重新渲染</button></footer>
    </div>
  {/if}

  {#if slashMenuOpen}
    <div
      class="slash-menu"
      style={`left:${slashMenuLeft}px;top:${slashMenuTop}px;`}
      role="listbox"
      tabindex="-1"
      aria-label="插入命令菜单"
      onmousedown={(e) => e.stopPropagation()}
    >
      <div class="slash-menu-head">
        <span>/ 命令</span>
        <span class="query">{slashMenuQuery || '全部'}</span>
      </div>
      {#if currentSlashMenuItems().length === 0}
        <div class="slash-empty">无匹配命令，按 Backspace 删除关键字。</div>
      {:else}
        <div class="slash-list">
          {#each currentSlashMenuItems() as item, idx}
            <button
              class={`slash-item ${idx === slashMenuActive ? 'active' : ''}`}
              role="option"
              aria-selected={idx === slashMenuActive}
              onmouseenter={() => (slashMenuActive = idx)}
              onclick={() => runSlashCommandByIndex(idx)}
            >
              <span class="slash-label">{item.label}</span>
              <span class="slash-desc">{item.desc}</span>
            </button>
          {/each}
        </div>
      {/if}
      <div class="slash-menu-foot">↑↓ 选择 · Enter 执行 · Esc 关闭</div>
    </div>
  {/if}

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
        <button class="btn-small" onclick={findNext}>下一个</button>
        <button class="btn-small" onclick={() => (showFindReplace = false)}>?</button>
      </div>
      <div class="find-replace-row">
        <input type="text" bind:value={replaceText} placeholder="替换为..." />
        <button class="btn-small" onclick={replaceNext}>替换</button>
        <button class="btn-small" onclick={replaceAll}>全部替换</button>
      </div>
    </div>
  {/if}
</div>



