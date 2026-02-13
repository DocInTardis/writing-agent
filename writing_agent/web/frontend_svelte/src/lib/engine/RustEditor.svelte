<script lang="ts">
  import { onMount, onDestroy } from 'svelte'
  import { sourceText, editorCommand, wordCount } from '../stores'
  import type { EditorCommand } from '../types'
  import { createWasmEditor, isWasmAvailable } from './wasmLoader'

  export let placeholder = '在这里直接编辑或等待生成内容…'

  let canvas: HTMLCanvasElement
  let ctx: CanvasRenderingContext2D | null = null
  let wasmEditor: any = null
  let animationFrame: number | null = null
  let containerEl: HTMLDivElement
  let resizeObserver: ResizeObserver | null = null

  let width = 800
  let height = 600
  let hasContent = false

  onMount(async () => {
    if (!isWasmAvailable()) {
      console.error('Rust 引擎不可用')
      return
    }

    try {
      wasmEditor = createWasmEditor()
      ctx = canvas.getContext('2d')

      if (containerEl) {
        const rect = containerEl.getBoundingClientRect()
        width = Math.max(320, Math.floor(rect.width))
        height = Math.max(240, Math.floor(rect.height))
      }

      const currentDoc = $sourceText
      if (currentDoc) {
        if (typeof wasmEditor.loadText === 'function') {
          wasmEditor.loadText(currentDoc)
        } else if (typeof wasmEditor.importMarkdown === 'function') {
          wasmEditor.importMarkdown(currentDoc)
        } else {
          wasmEditor.loadJson(JSON.stringify({ blocks: [] }))
        }
        hasContent = true
      } else {
        wasmEditor.loadJson(JSON.stringify({ blocks: [] }))
      }

      startRenderLoop()

      canvas.addEventListener('keydown', handleKeydown)
      canvas.addEventListener('mousedown', handleMouseDown)

      canvas.focus()

      if (containerEl && typeof ResizeObserver !== 'undefined') {
        resizeObserver = new ResizeObserver(() => {
          const rect = containerEl.getBoundingClientRect()
          width = Math.max(320, Math.floor(rect.width))
          height = Math.max(240, Math.floor(rect.height))
        })
        resizeObserver.observe(containerEl)
      }
    } catch (error) {
      console.error('Rust 编辑器初始化失败:', error)
    }
  })

  onDestroy(() => {
    if (animationFrame) {
      cancelAnimationFrame(animationFrame)
    }
    canvas?.removeEventListener('keydown', handleKeydown)
    canvas?.removeEventListener('mousedown', handleMouseDown)
    resizeObserver?.disconnect()
  })

  function startRenderLoop() {
    const render = () => {
      if (!ctx || !wasmEditor) return

      ctx.fillStyle = '#fffdf8'
      ctx.fillRect(0, 0, width, height)

      try {
        const layout = wasmEditor.layout(width - 80)

        ctx.fillStyle = '#2b2416'
        ctx.font = '16px "Microsoft YaHei", sans-serif'
        let y = 40

        if (Array.isArray(layout)) {
          layout.forEach((block: any) => {
            ctx!.fillText(`Block ${block.id.slice(0, 8)}... (${block.lines} lines)`, 40, y)
            y += block.height + 10
          })
        }

        if (!hasContent) {
          ctx.fillStyle = '#b9aa90'
          ctx.font = '16px "Microsoft YaHei", sans-serif'
          ctx.fillText(placeholder, 40, 48)
        }

        const cursorPos = wasmEditor.getCursorPosition()
        if (cursorPos) {
          ctx.fillStyle = '#a5722a'
          ctx.fillRect(40, y - 20, 2, 20)
        }

        const stats = wasmEditor.getStats()
        if (stats) {
          wordCount.set(stats.charCount || 0)
          hasContent = hasContent || (stats.charCount || 0) > 0
        }
      } catch (error) {
        console.error('渲染错误:', error)
      }

      animationFrame = requestAnimationFrame(render)
    }

    render()
  }

  function handleMouseDown() {
    canvas?.focus()
  }

  function handleKeydown(e: KeyboardEvent) {
    if (!wasmEditor) return

    if (e.key === 'Backspace') {
      e.preventDefault()
      wasmEditor.deleteBackward()
      if (typeof wasmEditor.checkpoint === 'function') wasmEditor.checkpoint()
      hasContent = true
      syncToStore()
    } else if (e.key === 'Enter') {
      e.preventDefault()
      wasmEditor.insertText('\n')
      if (typeof wasmEditor.checkpoint === 'function') wasmEditor.checkpoint()
      hasContent = true
      syncToStore()
    } else if (!e.ctrlKey && !e.metaKey && !e.altKey && e.key.length === 1) {
      e.preventDefault()
      wasmEditor.insertText(e.key)
      if (typeof wasmEditor.checkpoint === 'function') wasmEditor.checkpoint()
      hasContent = true
      syncToStore()
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault()
      wasmEditor.moveCursor(-1)
    } else if (e.key === 'ArrowRight') {
      e.preventDefault()
      wasmEditor.moveCursor(1)
    } else if (e.ctrlKey || e.metaKey) {
      if (e.key === 'b') {
        e.preventDefault()
        wasmEditor.toggleBold()
        syncToStore()
      } else if (e.key === 'i') {
        e.preventDefault()
        wasmEditor.toggleItalic()
        syncToStore()
      } else if (e.key === 'u') {
        e.preventDefault()
        wasmEditor.toggleUnderline()
        syncToStore()
      } else if (e.key === 'z') {
        e.preventDefault()
        if (e.shiftKey) {
          wasmEditor.redo()
        } else {
          wasmEditor.undo()
        }
        syncToStore()
      }
    }
  }

  function syncToStore() {
    if (!wasmEditor) return
    try {
      const json = wasmEditor.exportJson()
      sourceText.set(json)
      if (typeof wasmEditor.exportMarkdown === 'function') {
        const md = wasmEditor.exportMarkdown()
        const count = String(md || '').replace(/\s/g, '').length
        wordCount.set(count)
        hasContent = hasContent || count > 0
      }
    } catch (error) {
      console.error('同步失败:', error)
    }
  }

  const unsubscribe = editorCommand.subscribe((cmd) => {
    if (!cmd || !wasmEditor) return

    try {
      switch (cmd) {
        case 'bold':
          wasmEditor.toggleBold()
          break
        case 'italic':
          wasmEditor.toggleItalic()
          break
        case 'underline':
          wasmEditor.toggleUnderline()
          break
        case 'heading1':
          wasmEditor.setHeading(1)
          break
        case 'heading2':
          wasmEditor.setHeading(2)
          break
        case 'heading3':
          wasmEditor.setHeading(3)
          break
        case 'list-bullet':
          wasmEditor.toggleList(false)
          break
        case 'list-number':
          wasmEditor.toggleList(true)
          break
        case 'undo':
          wasmEditor.undo()
          break
        case 'redo':
          wasmEditor.redo()
          break
      }
      syncToStore()
    } catch (error) {
      console.error('命令执行失败:', error)
    } finally {
      editorCommand.set(null)
    }
  })

  onDestroy(() => {
    unsubscribe()
  })
</script>

<div class="rust-editor-container" bind:this={containerEl} on:click={handleMouseDown}>
  <canvas
    bind:this={canvas}
    {width}
    {height}
    class="rust-canvas"
    tabindex="0"
  ></canvas>
</div>

<style>
  .rust-editor-container {
    width: 100%;
    height: 100%;
    background: #fffdf8;
    border-radius: 16px;
    overflow: hidden;
  }

  .rust-canvas {
    width: 100%;
    height: 100%;
    cursor: text;
    outline: none;
  }

  .rust-canvas:focus {
    outline: 2px solid rgba(165, 114, 42, 0.3);
    outline-offset: -2px;
  }
</style>
