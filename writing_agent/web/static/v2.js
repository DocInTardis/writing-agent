(() => {
  const current = document.currentScript
  let query = ''
  if (current && typeof current.src === 'string') {
    const idx = current.src.indexOf('?')
    if (idx >= 0) query = current.src.slice(idx)
  }

  const runtime = document.createElement('script')
  runtime.src = `/static/v2_legacy_runtime.js${query}`
  runtime.async = false
  runtime.defer = false
  runtime.crossOrigin = 'anonymous'
  runtime.onerror = () => {
    if (typeof console !== 'undefined' && console.error) {
      console.error('Failed to load legacy runtime: /static/v2_legacy_runtime.js')
    }
  }
  document.head.appendChild(runtime)
})()
