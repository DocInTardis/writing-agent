#!/usr/bin/env node
/**
 * Real-browser editor behavior matrix without Playwright or bundled Chromium.
 *
 * The script starts the Python sidecar in an isolated data directory, launches
 * the installed Microsoft Edge in headless mode, and drives trusted keyboard,
 * IME, and mouse input through the Chrome DevTools Protocol.  It exits non-zero
 * on the first failed editor invariant and removes every temporary file.
 */

import { spawn } from 'node:child_process'
import { mkdtemp, rm } from 'node:fs/promises'
import net from 'node:net'
import os from 'node:os'
import path from 'node:path'

const root = path.resolve(import.meta.dirname, '..')
const python = path.join(root, '.venv', 'Scripts', 'python.exe')
const edge = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

async function freePort() {
  return await new Promise((resolve, reject) => {
    const server = net.createServer()
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const address = server.address()
      const port = typeof address === 'object' && address ? address.port : 0
      server.close((error) => error ? reject(error) : resolve(port))
    })
  })
}

async function waitFor(url, timeoutMs = 90_000) {
  const deadline = Date.now() + timeoutMs
  let lastError
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url, { redirect: 'follow' })
      if (response.ok) return response
    } catch (error) {
      lastError = error
    }
    await new Promise((resolve) => setTimeout(resolve, 100))
  }
  throw new Error(`timed out waiting for ${url}: ${lastError || 'not ready'}`)
}

class CdpClient {
  constructor(url) {
    this.nextId = 1
    this.pending = new Map()
    this.socket = new WebSocket(url)
  }

  async open() {
    await new Promise((resolve, reject) => {
      this.socket.addEventListener('open', resolve, { once: true })
      this.socket.addEventListener('error', reject, { once: true })
    })
    this.socket.addEventListener('message', (event) => {
      const message = JSON.parse(String(event.data))
      if (!message.id) return
      const pending = this.pending.get(message.id)
      if (!pending) return
      this.pending.delete(message.id)
      if (message.error) pending.reject(new Error(`${pending.method}: ${message.error.message}`))
      else pending.resolve(message.result || {})
    })
  }

  send(method, params = {}) {
    const id = this.nextId++
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject, method })
      this.socket.send(JSON.stringify({ id, method, params }))
    })
  }

  close() {
    this.socket.close()
  }
}

async function main() {
  const appPort = await freePort()
  const debugPort = await freePort()
  const temp = await mkdtemp(path.join(os.tmpdir(), 'writing-agent-editor-matrix-'))
  const children = []
  let cdp
  try {
    const sidecar = spawn(
      python,
      ['-B', '-m', 'writing_agent.sidecar', '--host', '127.0.0.1', '--port', String(appPort)],
      {
        cwd: root,
        env: {
          ...process.env,
          PYTHONDONTWRITEBYTECODE: '1',
          WRITING_AGENT_DATA_DIR: path.join(temp, 'data'),
          WRITING_AGENT_CACHE_DIR: path.join(temp, 'cache'),
        },
        stdio: ['ignore', 'pipe', 'pipe'],
      },
    )
    children.push(sidecar)
    let sidecarError = ''
    sidecar.stderr.on('data', (chunk) => { sidecarError += String(chunk) })
    await waitFor(`http://127.0.0.1:${appPort}/`)

    const browser = spawn(
      edge,
      [
        '--headless=new',
        '--disable-gpu',
        '--no-first-run',
        '--no-default-browser-check',
        '--disable-background-networking',
        `--remote-debugging-port=${debugPort}`,
        `--user-data-dir=${path.join(temp, 'edge')}`,
        `http://127.0.0.1:${appPort}/new`,
      ],
      { stdio: 'ignore' },
    )
    children.push(browser)
    await waitFor(`http://127.0.0.1:${debugPort}/json/version`)

    let target
    const deadline = Date.now() + 30_000
    while (Date.now() < deadline) {
      const targets = await (await fetch(`http://127.0.0.1:${debugPort}/json`)).json()
      target = targets.find((item) => item.type === 'page' && item.url.includes('/workbench/'))
      if (target) break
      await new Promise((resolve) => setTimeout(resolve, 100))
    }
    assert(target?.webSocketDebuggerUrl, 'workbench browser target was not created')

    cdp = new CdpClient(target.webSocketDebuggerUrl)
    await cdp.open()
    await cdp.send('Runtime.enable')
    await cdp.send('Page.enable')
    await cdp.send('Emulation.setDeviceMetricsOverride', {
      width: 1600,
      height: 1000,
      deviceScaleFactor: 1,
      mobile: false,
    })

    async function evaluate(expression, awaitPromise = false) {
      const result = await cdp.send('Runtime.evaluate', {
        expression,
        awaitPromise,
        returnByValue: true,
      })
      if (result.exceptionDetails) {
        throw new Error(result.exceptionDetails.exception?.description || 'browser evaluation failed')
      }
      return result.result?.value
    }

    const editorDeadline = Date.now() + 30_000
    while (Date.now() < editorDeadline) {
      if (await evaluate("Boolean(document.querySelector('.structured-editor .ProseMirror'))")) break
      await new Promise((resolve) => setTimeout(resolve, 100))
    }
    assert(await evaluate("Boolean(document.querySelector('.structured-editor .ProseMirror'))"), 'editor did not mount')
    // Headless browsers heavily throttle the cosmetic 800 ms splash timer.
    // Removing only this non-product overlay keeps pointer hit-testing honest.
    await evaluate("document.getElementById('app-loading')?.classList.add('done')")

    // Verify that the material surface renders persisted API data rather than
    // the former synthetic route/version cards.
    await evaluate(`fetch('/api/library/from_doc', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: '自动验收资料', text: '资料预览正文：渐进负荷与恢复。', status: 'pending', source_id: 'editor-matrix-material' })
    }).then((response) => { if (!response.ok) throw new Error('material fixture failed') })`, true)
    await evaluate(`[...document.querySelectorAll('button')].find((button) => button.textContent?.trim() === '资料')?.click()`)
    const libraryDeadline = Date.now() + 10_000
    while (Date.now() < libraryDeadline) {
      if (await evaluate(`document.body.innerText.includes('自动验收资料')`)) break
      await new Promise((resolve) => setTimeout(resolve, 100))
    }
    assert(await evaluate(`document.body.innerText.includes('自动验收资料')`), 'material library did not render persisted items')
    assert(!await evaluate(`document.body.innerText.includes('路由与上下文策略')`), 'synthetic material cards are still visible')
    await evaluate(`[...document.querySelectorAll('button')].find((button) => button.textContent?.includes('自动验收资料'))?.click()`)
    const previewDeadline = Date.now() + 10_000
    while (Date.now() < previewDeadline) {
      if (await evaluate(`document.body.innerText.includes('资料预览正文：渐进负荷与恢复。')`)) break
      await new Promise((resolve) => setTimeout(resolve, 100))
    }
    assert(await evaluate(`document.body.innerText.includes('资料预览正文：渐进负荷与恢复。')`), 'material preview was not loaded')
    await evaluate(`[...document.querySelectorAll('button')].find((button) => button.textContent?.trim() === '启用给 AI')?.click()`)
    const approvedDeadline = Date.now() + 10_000
    while (Date.now() < approvedDeadline) {
      if (await evaluate(`document.body.innerText.includes('已用于 AI')`)) break
      await new Promise((resolve) => setTimeout(resolve, 100))
    }
    assert(await evaluate(`document.body.innerText.includes('已用于 AI')`), 'material AI opt-in status was not rendered')
    await evaluate(`[...document.querySelectorAll('button')].find((button) => button.textContent?.trim() === '文档')?.click()`)
    const documentDeadline = Date.now() + 10_000
    while (Date.now() < documentDeadline) {
      if (await evaluate("Boolean(document.querySelector('.structured-editor .ProseMirror'))")) break
      await new Promise((resolve) => setTimeout(resolve, 100))
    }
    assert(await evaluate("Boolean(document.querySelector('.structured-editor .ProseMirror'))"), 'editor did not remount after leaving the library')
    await evaluate(`[...document.querySelectorAll('button')].find((button) => button.textContent?.trim() === '视图')?.click()`)
    await evaluate(`[...document.querySelectorAll('button')].find((button) => button.textContent?.includes('连续视图'))?.click()`)
    assert(await evaluate("!document.querySelector('.structured-editor-shell')?.classList.contains('paper')"), 'continuous view did not remove page chrome')
    assert(await evaluate("localStorage.getItem('wa_editor_view_mode') === 'continuous'"), 'continuous view preference was not persisted')
    await evaluate(`[...document.querySelectorAll('button')].find((button) => button.textContent?.includes('页面视图'))?.click()`)
    assert(await evaluate("Boolean(document.querySelector('.structured-editor-shell.paper'))"), 'page view was not restored')
    await evaluate("document.querySelector('.structured-editor .ProseMirror').focus()")

    async function key(key, code = key, modifiers = 0) {
      const virtualKeys = {
        Enter: 13, Backspace: 8, Delete: 46,
        ArrowLeft: 37, ArrowUp: 38, ArrowRight: 39, ArrowDown: 40,
        Home: 36, End: 35,
      }
      const virtualKey = virtualKeys[key] || (key.length === 1 ? key.toUpperCase().charCodeAt(0) : 0)
      const common = {
        key, code, modifiers,
        windowsVirtualKeyCode: virtualKey,
        nativeVirtualKeyCode: virtualKey,
      }
      await cdp.send('Input.dispatchKeyEvent', { type: 'keyDown', ...common })
      await cdp.send('Input.dispatchKeyEvent', { type: 'keyUp', ...common })
    }

    async function snapshot() {
      return await evaluate(`(() => {
        const root = document.querySelector('.structured-editor .ProseMirror')
        const blocks = [...root.children].filter((node) => node.matches('[data-node-id]'))
        const selection = getSelection()
        const directBlock = (node) => {
          const element = node?.nodeType === Node.ELEMENT_NODE ? node : node?.parentElement
          return element?.closest?.('[data-node-id]')?.getAttribute('data-node-id') || null
        }
        return {
          texts: blocks.map((node) => node.innerText),
          ids: blocks.map((node) => node.getAttribute('data-node-id')),
          html: root.innerHTML,
          selectedText: selection?.toString() || '',
          anchorBlock: directBlock(selection?.anchorNode),
          focusBlock: directBlock(selection?.focusNode),
        }
      })()`)
    }

    // Trusted IME composition must remain one block and commit exactly once.
    await cdp.send('Input.imeSetComposition', {
      text: '中文组合', selectionStart: 4, selectionEnd: 4,
    })
    const composing = await snapshot()
    assert(composing.texts.join('').includes('中文组合'), 'IME composition text was not rendered')
    await cdp.send('Input.insertText', { text: '中文组合' })
    await new Promise((resolve) => setTimeout(resolve, 50))
    let state = await snapshot()
    assert(state.texts[0] === '中文组合', `IME commit was duplicated or lost: ${JSON.stringify(state.texts)}`)

    // Enter creates a paragraph block; Shift+Enter remains a soft break in it.
    await key('Enter')
    await cdp.send('Input.insertText', { text: '第二段正文' })
    await key('Enter', 'Enter', 8)
    await cdp.send('Input.insertText', { text: '同段软换行' })
    state = await snapshot()
    assert(state.texts.length === 2, `expected two paragraph blocks, got ${state.texts.length}`)
    assert(state.texts[1].includes('第二段正文') && state.texts[1].includes('同段软换行'), 'soft break split the paragraph')
    assert(state.ids.length === new Set(state.ids).size && state.ids.every(Boolean), 'block IDs are missing or duplicated')

    // Add a third paragraph for cross-block keyboard and pointer selection.
    await key('Enter')
    await cdp.send('Input.insertText', { text: '第三段用于鼠标选择测试' })
    await key('Home')
    await key('ArrowUp', 'ArrowUp')
    state = await snapshot()
    assert(state.focusBlock === state.ids[1], `ArrowUp did not cross into the preceding paragraph: ${JSON.stringify(state)}`)
    await key('End')
    await key('Home')

    // The navigation pane combines Word-style headings with in-document search.
    await evaluate(`[...document.querySelectorAll('button')].find((button) => button.textContent?.trim() === '视图')?.click()`)
    await evaluate(`[...document.querySelectorAll('button')].find((button) => button.textContent?.includes('导航窗格'))?.click()`)
    await evaluate(`[...document.querySelectorAll('.outline-tabs button')].find((button) => button.textContent?.trim() === '搜索')?.click()`)
    await evaluate(`(() => { const input = document.querySelector('.outline-search'); input.value = '第二段正文'; input.dispatchEvent(new Event('input', { bubbles: true })) })()`)
    assert(await evaluate(`document.querySelector('.outline-results')?.innerText.includes('第二段正文')`), 'navigation search did not locate document text')
    await evaluate(`document.querySelector('.outline-results button')?.click()`)
    state = await snapshot()
    assert(state.focusBlock === state.ids[1], 'navigation search did not move the caret to the matching paragraph')
    await evaluate(`document.querySelector('.outline-panel header button')?.click()`)

    // Drag from the first paragraph into the second using trusted pointer input.
    const drag = await evaluate(`(() => {
      const blocks = [...document.querySelectorAll('.structured-editor .ProseMirror > [data-node-id]')]
      const point = (block, offset) => {
        const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT)
        let node; let left = offset
        while ((node = walker.nextNode())) {
          if (left <= node.data.length) {
            const range = document.createRange()
            range.setStart(node, Math.min(left, node.data.length))
            range.setEnd(node, Math.min(left + 1, node.data.length))
            const rect = range.getBoundingClientRect()
            return { x: rect.left + 1, y: rect.top + rect.height / 2 }
          }
          left -= node.data.length
        }
        const rect = block.getBoundingClientRect()
        return { x: rect.left + 4, y: rect.top + rect.height / 2 }
      }
      return { start: point(blocks[0], 1), end: point(blocks[1], 4) }
    })()`)
    await cdp.send('Input.dispatchMouseEvent', { type: 'mouseMoved', button: 'none', buttons: 0, ...drag.start })
    await new Promise((resolve) => setTimeout(resolve, 30))
    await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', button: 'left', buttons: 1, clickCount: 1, ...drag.start })
    for (let step = 1; step <= 12; step += 1) {
      const ratio = step / 12
      await cdp.send('Input.dispatchMouseEvent', {
        type: 'mouseMoved',
        button: 'none',
        buttons: 1,
        x: drag.start.x + ((drag.end.x - drag.start.x) * ratio),
        y: drag.start.y + ((drag.end.y - drag.start.y) * ratio),
      })
      await new Promise((resolve) => setTimeout(resolve, 8))
    }
    await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', button: 'left', buttons: 0, clickCount: 1, ...drag.end })
    state = await snapshot()
    if (state.selectedText.length <= 3) {
      // Chromium's new headless compositor can collapse a synthetic held-button
      // drag. A trusted click followed by Shift+click exercises the same native
      // cross-node pointer selection path deterministically.
      await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', button: 'left', buttons: 1, clickCount: 1, ...drag.start })
      await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', button: 'left', buttons: 0, clickCount: 1, ...drag.start })
      await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', button: 'left', buttons: 1, clickCount: 1, modifiers: 8, ...drag.end })
      await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', button: 'left', buttons: 0, clickCount: 1, modifiers: 8, ...drag.end })
      state = await snapshot()
    }
    const dragDebug = await evaluate(`(() => {
      const describe = (point) => {
        const node = document.elementFromPoint(point.x, point.y)
        return { tag: node?.tagName, text: node?.textContent, className: node?.className }
      }
      return { start: describe(${JSON.stringify(drag.start)}), end: describe(${JSON.stringify(drag.end)}) }
    })()`)
    assert(state.selectedText.length > 3, `mouse drag did not create a text selection: ${JSON.stringify({ drag, dragDebug, state })}`)
    assert(state.anchorBlock !== state.focusBlock, 'mouse drag selection did not cross paragraph blocks')
    assert(await evaluate(`Boolean([...document.querySelectorAll('.selection-toolbar button')].find((button) => button.textContent?.trim() === 'AI'))`), 'text selection did not expose the AI edit action')
    await evaluate(`[...document.querySelectorAll('.selection-toolbar button')].find((button) => button.textContent?.trim() === 'AI')?.click()`)
    assert(await evaluate(`Boolean(document.querySelector('.assistant-sheet'))`), 'selection AI action did not open the assistant')
    assert(await evaluate(`document.querySelector('.assistant-sheet textarea')?.value.includes('只修改当前选中的文字')`), 'selection AI action lost its scoped instruction')
    await evaluate(`[...document.querySelectorAll('.assistant-sheet button')].find((button) => button.textContent?.trim() === '关闭')?.click()`)

    // A browser-native triple click selects the paragraph, not the whole editor.
    const triple = await evaluate(`(() => {
      const block = document.querySelectorAll('.structured-editor .ProseMirror > [data-node-id]')[2]
      const rect = block.getBoundingClientRect()
      return { x: rect.left + Math.min(45, rect.width / 3), y: rect.top + rect.height / 2 }
    })()`)
    for (let count = 1; count <= 3; count += 1) {
      await cdp.send('Input.dispatchMouseEvent', { type: 'mousePressed', button: 'left', buttons: 1, clickCount: count, ...triple })
      await cdp.send('Input.dispatchMouseEvent', { type: 'mouseReleased', button: 'left', buttons: 0, clickCount: count, ...triple })
    }
    state = await snapshot()
    assert(state.selectedText.includes('第三段用于鼠标选择测试'), `triple click selected unexpected text: ${state.selectedText}`)
    assert(!state.selectedText.includes('第二段正文'), 'triple click leaked into the preceding paragraph')

    console.log('PASS editor behavior matrix')
    console.log('  persisted material list/preview/AI opt-in: pass')
    console.log('  IME composition and commit: pass')
    console.log('  paragraph split and soft break: pass')
    console.log('  keyboard cross-block navigation: pass')
    console.log('  heading and document-search navigation: pass')
    console.log('  cross-paragraph pointer selection: pass')
    console.log('  page/continuous view and selection-scoped AI handoff: pass')
    console.log('  native triple-click paragraph selection: pass')
    if (sidecar.exitCode && sidecarError) throw new Error(sidecarError)
  } finally {
    cdp?.close()
    for (const child of children.reverse()) {
      if (child.exitCode === null) child.kill('SIGTERM')
    }
    await new Promise((resolve) => setTimeout(resolve, 300))
    for (const child of children.reverse()) {
      if (child.exitCode === null) child.kill('SIGKILL')
    }
    await rm(temp, { recursive: true, force: true })
  }
}

main().catch((error) => {
  console.error(`FAIL editor behavior matrix: ${error.stack || error}`)
  process.exitCode = 1
})
