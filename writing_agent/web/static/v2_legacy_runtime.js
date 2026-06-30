(() => {
  function el(id) {
    return document.getElementById(id)
  }

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;')
  }

  function renderMarkdown(text) {
    const lines = String(text || '').replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n')
    const out = []
    let listMode = ''
    const closeList = () => {
      if (!listMode) return
      out.push(listMode === 'ol' ? '</ol>' : '</ul>')
      listMode = ''
    }
    for (const raw of lines) {
      const line = String(raw || '')
      const trimmed = line.trim()
      const heading = /^(#{1,6})\s+(.+)$/.exec(trimmed)
      if (heading) {
        closeList()
        const level = Math.min(6, heading[1].length)
        out.push(`<h${level}>${escapeHtml(heading[2])}</h${level}>`)
        continue
      }
      const ordered = /^\d+\.\s+(.+)$/.exec(trimmed)
      const bullet = /^[-*]\s+(.+)$/.exec(trimmed)
      if (ordered || bullet) {
        const nextMode = ordered ? 'ol' : 'ul'
        if (listMode !== nextMode) {
          closeList()
          listMode = nextMode
          out.push(nextMode === 'ol' ? '<ol>' : '<ul>')
        }
        out.push(`<li>${escapeHtml((ordered || bullet)[1])}</li>`)
        continue
      }
      if (!trimmed) {
        closeList()
        continue
      }
      closeList()
      out.push(`<p>${escapeHtml(line)}</p>`)
    }
    closeList()
    return out.join('\n')
  }

  function setActiveTab(name) {
    const source = el('source')
    const preview = el('preview')
    if (!source || !preview) return
    const normalized = name === 'edit' ? 'source' : name
    document.querySelectorAll('.tab[data-tab]').forEach((tab) => {
      tab.classList.toggle('active', tab.getAttribute('data-tab') === name)
    })
    source.classList.toggle('hidden', normalized !== 'source')
    preview.classList.toggle('hidden', normalized !== 'preview')
    if (normalized === 'preview') {
      preview.innerHTML = renderMarkdown(source.value || '')
    }
  }

  async function loadDoc(docId) {
    const source = el('source')
    if (!source || !docId) return
    try {
      const resp = await fetch(`/api/doc/${encodeURIComponent(docId)}`)
      if (!resp.ok) return
      const data = await resp.json()
      source.value = String(data.text || data.doc_text || '')
      const title = el('docTitle')
      if (title) title.value = String(data.title || '')
    } catch {
      // Keep the editor usable when the metadata request is unavailable.
    }
  }

  async function saveDoc(docId) {
    const source = el('source')
    if (!source || !docId) return
    await fetch(`/api/doc/${encodeURIComponent(docId)}/save`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: source.value || '' })
    })
  }

  function init() {
    const app = document.querySelector('.app')
    if (!app) return
    const docId = app.getAttribute('data-doc-id') || document.body.getAttribute('data-doc-id') || ''

    document.querySelectorAll('.tab[data-tab]').forEach((tab) => {
      tab.addEventListener('click', () => setActiveTab(tab.getAttribute('data-tab') || 'edit'))
    })

    const source = el('source')
    if (source) {
      source.addEventListener('input', () => {
        const preview = el('preview')
        if (preview && !preview.classList.contains('hidden')) {
          preview.innerHTML = renderMarkdown(source.value || '')
        }
      })
    }

    el('btnSave')?.addEventListener('click', () => {
      saveDoc(docId).catch((err) => console.warn('[writing-agent] save failed', err))
    })
    el('btnOpen')?.addEventListener('click', () => {
      const input = el('importFile')
      if (input) input.click()
    })
    el('btnStop')?.addEventListener('click', () => {})

    loadDoc(docId).catch(() => {})
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init)
  } else {
    init()
  }
})()
