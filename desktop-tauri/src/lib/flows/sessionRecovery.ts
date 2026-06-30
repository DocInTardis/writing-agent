const KEY_PREFIX = 'wa_session_recovery:'

export interface RecoverySnapshot {
  docId: string
  text: string
  cursorAnchor?: string
  updatedAt: number
}

export function saveRecovery(snapshot: RecoverySnapshot): void {
  if (typeof window === 'undefined' || !snapshot?.docId) return
  const key = KEY_PREFIX + snapshot.docId
  window.localStorage.setItem(key, JSON.stringify(snapshot))
}

export function loadRecovery(docId: string): RecoverySnapshot | null {
  if (typeof window === 'undefined' || !docId) return null
  const raw = window.localStorage.getItem(KEY_PREFIX + docId)
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return null
    return {
      docId: String(parsed.docId || docId),
      text: String(parsed.text || ''),
      cursorAnchor: parsed.cursorAnchor ? String(parsed.cursorAnchor) : undefined,
      updatedAt: Number(parsed.updatedAt || 0)
    }
  } catch {
    return null
  }
}

export function clearRecovery(docId: string): void {
  if (typeof window === 'undefined' || !docId) return
  window.localStorage.removeItem(KEY_PREFIX + docId)
}
