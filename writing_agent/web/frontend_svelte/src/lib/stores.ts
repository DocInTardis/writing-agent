import { derived, get, writable } from 'svelte/store'
import type { ChatMessage, ThoughtItem, ToastItem, EditorCommand } from './types'
import type { DocumentV3 } from './editor-v3/model'

export const docId = writable('')
export const instruction = writable('')
export const sourceText = writable('')
export const docIr = writable<Record<string, unknown> | null>(null)
export const documentV3 = writable<DocumentV3 | null>(null)
export const docIrDirty = writable(false)
export const flowStatus = writable('就绪')
export const docStatus = writable('就绪')
export const chat = writable<ChatMessage[]>([])
export const thinkingSummary = writable('等待解析…')
export const thinkingSteps = writable<string[]>([])
export const thinkingMissing = writable<string[]>([])
export const thoughtLog = writable<ThoughtItem[]>([])
export const ribbonOpen = writable(false)
export const generating = writable(false)
export const editorCommand = writable<EditorCommand | null>(null)
export const history = writable<string[]>([])
export const historyIndex = writable(-1)

export type PageSettings = {
  pageSize: 'A4' | 'A5' | 'LETTER'
  orientation: 'portrait' | 'landscape'
  marginTop: number
  marginBottom: number
  marginLeft: number
  marginRight: number
  showHeader: boolean
  headerText: string
  showFooter: boolean
  footerText: string
  pageNumbers: boolean
  pageNumberPosition: 'left' | 'center' | 'right'
}

export const pageSettings = writable<PageSettings>({
  pageSize: 'A4',
  orientation: 'portrait',
  marginTop: 2.54,
  marginBottom: 2.54,
  marginLeft: 3.18,
  marginRight: 3.18,
  showHeader: false,
  headerText: '',
  showFooter: false,
  footerText: '',
  pageNumbers: true,
  pageNumberPosition: 'center'
})

export async function loadPageSettings() {
  const id = get(docId)
  if (!id) return
  const response = await fetch(`/api/doc/${id}`)
  if (!response.ok) return
  const data = await response.json()
  const prefs = data.generation_prefs || {}
  const current = get(pageSettings)
  const numeric = (value: unknown, fallback: number) => {
    const parsed = Number(value)
    return Number.isFinite(parsed) && parsed >= 0 ? parsed : fallback
  }
  pageSettings.set({
    pageSize: ['A4', 'A5', 'LETTER'].includes(String(prefs.page_size || '').toUpperCase())
      ? String(prefs.page_size).toUpperCase() as PageSettings['pageSize']
      : current.pageSize,
    orientation: prefs.page_orientation === 'landscape' ? 'landscape' : 'portrait',
    marginTop: numeric(prefs.page_margin_top_cm, current.marginTop),
    marginBottom: numeric(prefs.page_margin_bottom_cm, current.marginBottom),
    marginLeft: numeric(prefs.page_margin_left_cm, current.marginLeft),
    marginRight: numeric(prefs.page_margin_right_cm, current.marginRight),
    showHeader: Boolean(prefs.include_header ?? current.showHeader),
    headerText: String(prefs.header_text || ''),
    showFooter: Boolean(prefs.include_footer ?? current.showFooter),
    footerText: String(prefs.footer_text || ''),
    pageNumbers: Boolean(prefs.page_numbers ?? current.pageNumbers),
    pageNumberPosition: ['left', 'center', 'right'].includes(String(prefs.page_number_position || ''))
      ? prefs.page_number_position
      : current.pageNumberPosition
  })
}

export const wordCount = derived(sourceText, ($text) => String($text || '').replace(/\s/g, '').length)

export const toasts = writable<ToastItem[]>([])
export const darkMode = writable(false)
export const isLoading = writable(false)

export const useRustEngine = writable(false)
let chatSaveTimer: ReturnType<typeof setTimeout> | null = null
let thoughtsSaveTimer: ReturnType<typeof setTimeout> | null = null

if (typeof window !== 'undefined') {
  ;(window as any).__waGetStore = (name: string) => {
    const map: Record<string, any> = {
      docId,
      instruction,
      sourceText,
      docIr,
      documentV3,
      docIrDirty,
      flowStatus,
      docStatus,
      generating,
      wordCount
    }
    const store = map[name]
    return store ? get(store) : undefined
  }
}

export async function loadChat() {
  const id = get(docId)
  if (!id) return
  const resp = await fetch(`/api/doc/${id}/chat`)
  if (!resp.ok) return
  const data = await resp.json()
  const items = Array.isArray(data.items) ? data.items : []
  chat.set(items)
}

export async function loadThoughts() {
  const id = get(docId)
  if (!id) return
  const resp = await fetch(`/api/doc/${id}/thoughts`)
  if (!resp.ok) return
  const data = await resp.json()
  const items = Array.isArray(data.items) ? data.items : []
  thoughtLog.set(items)
}

async function persistChatRemote(items: ChatMessage[]) {
  const id = get(docId)
  if (!id) return
  await fetch(`/api/doc/${id}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items: items.slice(-200) })
  })
}

async function persistThoughtsRemote(items: ThoughtItem[]) {
  const id = get(docId)
  if (!id) return
  await fetch(`/api/doc/${id}/thoughts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ items: items.slice(-200) })
  })
}

export function appendChat(role: ChatMessage['role'], text: string) {
  const msg: ChatMessage = { role, text: String(text || '').trim() }
  if (!msg.text) return
  chat.update((items) => {
    const next = [...items, msg]
    if (chatSaveTimer) clearTimeout(chatSaveTimer)
    chatSaveTimer = setTimeout(() => {
      persistChatRemote(next).catch(() => {})
    }, 300)
    return next
  })
}

export function pushThought(label: string, detail: string, timeLabel?: string) {
  const item: ThoughtItem = { label, detail, time: timeLabel || new Date().toLocaleTimeString() }
  thoughtLog.update((items) => {
    const next = [...items, item].slice(-200)
    if (thoughtsSaveTimer) clearTimeout(thoughtsSaveTimer)
    thoughtsSaveTimer = setTimeout(() => {
      persistThoughtsRemote(next).catch(() => {})
    }, 300)
    return next
  })
}

export function pushToast(message: string, type: ToastItem['type'] = 'info') {
  const id = Date.now()
  const item: ToastItem = { id, message, type }
  toasts.update((items) => [...items, item])
  setTimeout(() => {
    toasts.update((items) => items.filter((t) => t.id !== id))
  }, 2600)
}

export function pushHistory(text: string) {
  const t = String(text || '')
  history.update((items) => {
    const next = items.slice(0, get(historyIndex) + 1)
    if (next[next.length - 1] === t) return items
    next.push(t)
    const capped = next.slice(-50)
    historyIndex.set(capped.length - 1)
    return capped
  })
}

export function undoHistory() {
  const idx = get(historyIndex)
  if (idx <= 0) return
  historyIndex.set(idx - 1)
  const items = get(history)
  sourceText.set(items[idx - 1] || '')
  docIrDirty.set(true)
}

export function redoHistory() {
  const idx = get(historyIndex)
  const items = get(history)
  if (idx >= items.length - 1) return
  historyIndex.set(idx + 1)
  sourceText.set(items[idx + 1] || '')
  docIrDirty.set(true)
}
