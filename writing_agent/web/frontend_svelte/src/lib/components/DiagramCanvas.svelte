<script lang="ts">
  import { createEventDispatcher } from 'svelte'

  export let open = false
  export let docId = ''
  const dispatch = createEventDispatcher()

  type Kind = 'flow' | 'er' | 'sequence' | 'timeline' | 'bar' | 'line' | 'pie'
  type PanelMode = 'studio' | 'json' | 'history'

  const kindOptions: Array<{ value: Kind; label: string }> = [
    { value: 'flow', label: '流程图' },
    { value: 'er', label: 'ER 图' },
    { value: 'sequence', label: '时序图' },
    { value: 'timeline', label: '时间线' },
    { value: 'bar', label: '柱状图' },
    { value: 'line', label: '折线图' },
    { value: 'pie', label: '饼图' }
  ]

  const quickTemplates: Record<Kind, string[]> = {
    flow: [
      '需求分析 -> 方案设计 -> 开发实现 -> 测试验收 -> 上线运营',
      '用户登录 -> 权限校验 -> 数据查询 -> 结果返回',
      '问题发现 -> 原因定位 -> 修复验证 -> 发布回归'
    ],
    er: [
      '电商系统：用户、订单、商品、支付',
      '教学系统：学生、课程、教师、选课记录',
      '医院系统：患者、医生、挂号、检查报告'
    ],
    sequence: [
      '用户 -> 网关 -> 认证服务 -> 业务服务 -> 数据库',
      '浏览器 -> 服务端 -> 缓存 -> 数据库',
      '客户端 -> API -> 队列 -> Worker -> 存储'
    ],
    timeline: [
      '立项 -> 调研 -> 设计 -> 开发 -> 测试 -> 发布',
      '需求冻结 -> 联调 -> 验收 -> 复盘',
      '周一需求 -> 周三开发 -> 周五发布'
    ],
    bar: [
      '近 3 个月活跃用户对比',
      '三种方案成本对比',
      '各模块缺陷数统计'
    ],
    line: [
      'Q1-Q4 访问量变化趋势',
      '模型版本准确率变化',
      '系统响应时间趋势'
    ],
    pie: [
      '项目成本占比：人力、硬件、云资源、其他',
      '问题类型占比：功能、性能、兼容性、体验',
      '用户来源占比：自然、投放、活动、推荐'
    ]
  }

  let panelMode: PanelMode = 'studio'
  let kind: Kind = 'flow'
  let prompt = ''
  let optimizeInput = ''
  let loading = false
  let error = ''
  let svg = ''
  let spec: Record<string, unknown> | null = null
  let specText = ''
  let zoom = 1

  let historyItems: Array<{
    id: number
    kind: Kind
    prompt: string
    spec: Record<string, unknown>
    svg: string
    ts: number
  }> = []

  function panelTitle(mode: PanelMode) {
    if (mode === 'json') return '规范编辑'
    if (mode === 'history') return '历史画布'
    return '智能画布'
  }

  function closeCanvas() {
    dispatch('close')
  }

  function useTemplate(text: string) {
    prompt = text
  }

  function normalizeKind(raw: unknown): Kind {
    const v = String(raw || '').trim().toLowerCase()
    if (v === 'er') return 'er'
    if (v === 'sequence') return 'sequence'
    if (v === 'timeline') return 'timeline'
    if (v === 'bar') return 'bar'
    if (v === 'line') return 'line'
    if (v === 'pie') return 'pie'
    return 'flow'
  }

  function ensureObject(value: unknown): Record<string, unknown> {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      throw new Error('图形规范不是对象')
    }
    return value as Record<string, unknown>
  }

  function stringifySafe(value: unknown) {
    return JSON.stringify(
      value,
      (_k, v) => (typeof v === 'string' ? v.replace(/\u0000/g, '') : v),
      2
    )
  }

  function pushHistory(sourcePrompt: string, sourceKind: Kind, nextSpec: Record<string, unknown>, nextSvg: string) {
    historyItems = [
      {
        id: Date.now(),
        kind: sourceKind,
        prompt: sourcePrompt,
        spec: nextSpec,
        svg: nextSvg,
        ts: Date.now()
      },
      ...historyItems
    ].slice(0, 40)
  }

  async function renderSpec(nextSpec: Record<string, unknown>, sourcePrompt: string, sourceKind: Kind) {
    const render = await fetch('/api/figure/render', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ spec: nextSpec })
    })
    if (!render.ok) throw new Error(await render.text())
    const fig = await render.json()
    const nextSvg = String(fig.svg || '')
    svg = nextSvg
    spec = nextSpec
    specText = stringifySafe(nextSpec)
    pushHistory(sourcePrompt, sourceKind, nextSpec, nextSvg)
  }

  async function generateDiagram(customPrompt?: string) {
    const finalPrompt = String(customPrompt || prompt || '').trim()
    if (!docId) {
      error = '文档未加载'
      return
    }
    if (!finalPrompt) return
    loading = true
    error = ''
    try {
      const resp = await fetch(`/api/doc/${docId}/diagram/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: finalPrompt, kind })
      })
      if (!resp.ok) throw new Error(await resp.text())
      const data = await resp.json()
      const nextSpec = ensureObject(data.spec || {})
      await renderSpec(nextSpec, finalPrompt, kind)
      panelMode = 'studio'
    } catch (err) {
      error = err instanceof Error ? err.message : '图形生成失败'
    } finally {
      loading = false
    }
  }

  async function optimizeCurrent() {
    const ask = optimizeInput.trim()
    if (!ask) return
    if (!spec) {
      await generateDiagram(ask)
      return
    }
    const context = JSON.stringify(spec).slice(0, 1800)
    await generateDiagram(`在当前图基础上优化：${ask}\n当前规范：${context}`)
  }

  async function applySpecText() {
    const raw = String(specText || '').trim()
    if (!raw) return
    loading = true
    error = ''
    try {
      const parsed = ensureObject(JSON.parse(raw))
      const parsedKind = normalizeKind(parsed.type)
      kind = parsedKind
      await renderSpec(parsed, '手动编辑规范', parsedKind)
      panelMode = 'studio'
    } catch (err) {
      error = err instanceof Error ? err.message : '规范解析失败'
    } finally {
      loading = false
    }
  }

  function restoreHistory(item: { kind: Kind; prompt: string; spec: Record<string, unknown>; svg: string }) {
    kind = item.kind
    prompt = item.prompt
    spec = item.spec
    svg = item.svg
    specText = stringifySafe(item.spec)
    panelMode = 'studio'
  }

  function handleInsert() {
    if (!spec) return
    dispatch('insert', { spec })
  }

  async function copySvg() {
    if (!svg) return
    try {
      await navigator.clipboard.writeText(svg)
    } catch {
      error = '复制 SVG 失败，请检查浏览器权限'
    }
  }

  async function copySpec() {
    if (!specText.trim()) return
    try {
      await navigator.clipboard.writeText(specText)
    } catch {
      error = '复制规范失败，请检查浏览器权限'
    }
  }

  function downloadSvg() {
    if (!svg) return
    const blob = new Blob([svg], { type: 'image/svg+xml;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `canvas-${Date.now()}.svg`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  }

  function resetCanvas() {
    svg = ''
    spec = null
    specText = ''
    optimizeInput = ''
    error = ''
    zoom = 1
  }

  function handleBackdropKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') closeCanvas()
  }
</script>

{#if open}
  <div
    class="canvas-backdrop"
    role="button"
    tabindex="0"
    aria-label="关闭画布"
    on:click|self={closeCanvas}
    on:keydown={handleBackdropKeydown}
  >
    <section class="canvas-shell" aria-label="AI 画布系统">
      <header class="canvas-topbar">
        <div class="title-wrap">
          <h3>AI 画布系统</h3>
          <p>同页完成生成、修改、预览、插入，支持流程图/ER 图/时序图/统计图。</p>
        </div>
        <div class="top-actions">
          <button class="btn ghost" on:click={() => (panelMode = 'studio')}>工作台</button>
          <button class="btn ghost" on:click={() => (panelMode = 'json')}>JSON</button>
          <button class="btn ghost" on:click={() => (panelMode = 'history')}>历史</button>
          <button class="btn ghost" on:click={resetCanvas}>清空</button>
          <button class="close-btn" on:click={closeCanvas} aria-label="关闭">×</button>
        </div>
      </header>

      <div class="canvas-main">
        <aside class="canvas-sidebar">
          <div class="panel-title">{panelTitle(panelMode)}</div>

          {#if panelMode === 'studio'}
            <div class="kind-grid">
              {#each kindOptions as item}
                <button
                  class={`kind-chip ${kind === item.value ? 'active' : ''}`}
                  on:click={() => (kind = item.value)}
                >
                  {item.label}
                </button>
              {/each}
            </div>

            <div class="template-list">
              {#each quickTemplates[kind] as t}
                <button class="template-chip" on:click={() => useTemplate(t)}>{t}</button>
              {/each}
            </div>

            <textarea
              class="prompt-box"
              rows="5"
              bind:value={prompt}
              placeholder="输入你要绘制的内容，例如：用户登录到下单的关键流程。"
            ></textarea>

            <div class="canvas-actions">
              <button class="btn primary" on:click={() => generateDiagram()} disabled={loading || !prompt.trim()}>
                {loading ? '生成中...' : '生成图形'}
              </button>
              <button class="btn ghost" on:click={handleInsert} disabled={!spec}>插入文档</button>
            </div>

            <textarea
              class="prompt-box mini"
              rows="3"
              bind:value={optimizeInput}
              placeholder="二次优化，例如：改成更简洁的 5 个节点，强调异常分支。"
            ></textarea>
            <button class="btn ghost" on:click={optimizeCurrent} disabled={loading || !optimizeInput.trim()}>
              AI 二次优化
            </button>
          {/if}

          {#if panelMode === 'json'}
            <textarea
              class="spec-editor"
              rows="18"
              bind:value={specText}
              placeholder="可直接编辑 JSON 规范，例如：type=flow，caption=示例，data 包含 nodes/edges。"
            ></textarea>
            <div class="canvas-actions">
              <button class="btn primary" on:click={applySpecText} disabled={loading || !specText.trim()}>
                应用规范
              </button>
              <button class="btn ghost" on:click={copySpec} disabled={!specText.trim()}>复制规范</button>
            </div>
          {/if}

          {#if panelMode === 'history'}
            <div class="history-list">
              {#if historyItems.length === 0}
                <div class="empty">暂无历史记录</div>
              {:else}
                {#each historyItems as item}
                  <button class="history-item" on:click={() => restoreHistory(item)}>
                    <div>{kindOptions.find((k) => k.value === item.kind)?.label || item.kind}</div>
                    <div>{item.prompt || '无描述'}</div>
                    <div>{new Date(item.ts).toLocaleString()}</div>
                  </button>
                {/each}
              {/if}
            </div>
          {/if}

          {#if error}
            <div class="error">{error}</div>
          {/if}
        </aside>

        <section class="canvas-stage">
          <div class="stage-toolbar">
            <div class="zoom-group">
              <button class="btn ghost" on:click={() => (zoom = Math.max(0.4, Number((zoom - 0.1).toFixed(1))))}>-</button>
              <span>{Math.round(zoom * 100)}%</span>
              <button class="btn ghost" on:click={() => (zoom = Math.min(2.2, Number((zoom + 0.1).toFixed(1))))}>+</button>
              <button class="btn ghost" on:click={() => (zoom = 1)}>重置缩放</button>
            </div>
            <div class="export-group">
              <button class="btn ghost" on:click={copySvg} disabled={!svg}>复制 SVG</button>
              <button class="btn ghost" on:click={downloadSvg} disabled={!svg}>下载 SVG</button>
              <button class="btn primary" on:click={handleInsert} disabled={!spec}>插入正文</button>
            </div>
          </div>

          <div class="preview-wrap">
            {#if svg}
              <div class="svg-host">
                <div class="svg-scale" style={`transform: scale(${zoom});`}>
                  {@html svg}
                </div>
              </div>
            {:else}
              <div class="placeholder">
                <h4>画布预览区</h4>
                <p>左侧输入描述后点击“生成图形”，或切换到 JSON 手动编辑规范。</p>
              </div>
            {/if}
          </div>
        </section>
      </div>
    </section>
  </div>
{/if}

<style>
  .canvas-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(15, 23, 42, 0.52);
    z-index: 24;
    display: grid;
    place-items: center;
    padding: 16px;
  }

  .canvas-shell {
    width: min(1480px, calc(100vw - 32px));
    height: min(92vh, 980px);
    border-radius: 20px;
    background: rgba(255, 255, 255, 0.985);
    border: 1px solid rgba(148, 163, 184, 0.28);
    box-shadow: 0 30px 80px rgba(15, 23, 42, 0.45);
    display: grid;
    grid-template-rows: auto 1fr;
    overflow: hidden;
  }

  .canvas-topbar {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    padding: 14px 16px;
    border-bottom: 1px solid rgba(148, 163, 184, 0.22);
    background: linear-gradient(90deg, rgba(37, 99, 235, 0.1), rgba(14, 165, 233, 0.08));
  }

  .title-wrap h3 {
    margin: 0 0 4px 0;
    font-size: 18px;
  }

  .title-wrap p {
    margin: 0;
    font-size: 12px;
    color: rgba(51, 65, 85, 0.78);
  }

  .top-actions {
    display: flex;
    gap: 8px;
    align-items: center;
    flex-wrap: wrap;
    justify-content: flex-end;
  }

  .close-btn {
    border: none;
    background: rgba(15, 23, 42, 0.08);
    width: 32px;
    height: 32px;
    border-radius: 10px;
    cursor: pointer;
    font-size: 20px;
    line-height: 1;
  }

  .canvas-main {
    min-height: 0;
    display: grid;
    grid-template-columns: 360px 1fr;
  }

  .canvas-sidebar {
    border-right: 1px solid rgba(148, 163, 184, 0.2);
    padding: 12px;
    display: grid;
    gap: 10px;
    overflow: auto;
    align-content: start;
  }

  .panel-title {
    font-size: 13px;
    font-weight: 700;
    color: #0f172a;
  }

  .kind-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 6px;
  }

  .kind-chip,
  .template-chip,
  .history-item {
    border: 1px solid rgba(148, 163, 184, 0.3);
    border-radius: 10px;
    background: #fff;
    cursor: pointer;
    font-size: 12px;
    padding: 7px 9px;
  }

  .kind-chip.active {
    border-color: rgba(37, 99, 235, 0.5);
    background: rgba(37, 99, 235, 0.12);
    color: #1e3a8a;
    font-weight: 600;
  }

  .template-list {
    display: grid;
    gap: 6px;
  }

  .template-chip {
    text-align: left;
    background: rgba(248, 250, 252, 0.95);
  }

  .prompt-box,
  .spec-editor {
    border: 1px solid rgba(148, 163, 184, 0.32);
    border-radius: 12px;
    padding: 10px 12px;
    font-size: 13px;
    line-height: 1.5;
    resize: vertical;
    background: #fff;
  }

  .prompt-box.mini {
    min-height: 72px;
  }

  .spec-editor {
    min-height: 320px;
    font-family: Consolas, "Courier New", monospace;
    font-size: 12px;
  }

  .canvas-actions {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }

  .history-list {
    display: grid;
    gap: 8px;
  }

  .history-item {
    text-align: left;
    display: grid;
    gap: 2px;
    line-height: 1.35;
  }

  .history-item > div:nth-child(1) {
    font-weight: 600;
  }

  .history-item > div:nth-child(2) {
    color: rgba(51, 65, 85, 0.8);
  }

  .history-item > div:nth-child(3) {
    color: rgba(51, 65, 85, 0.62);
    font-size: 11px;
  }

  .canvas-stage {
    min-width: 0;
    min-height: 0;
    padding: 12px;
    display: grid;
    grid-template-rows: auto 1fr;
    gap: 10px;
    background: linear-gradient(180deg, rgba(241, 245, 249, 0.8), rgba(248, 250, 252, 0.95));
  }

  .stage-toolbar {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    flex-wrap: wrap;
    border: 1px solid rgba(148, 163, 184, 0.2);
    border-radius: 12px;
    padding: 8px 10px;
    background: rgba(255, 255, 255, 0.9);
  }

  .zoom-group,
  .export-group {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }

  .preview-wrap {
    min-height: 0;
    border: 1px solid rgba(148, 163, 184, 0.22);
    border-radius: 16px;
    background:
      linear-gradient(0deg, rgba(248, 250, 252, 0.72), rgba(248, 250, 252, 0.72)),
      repeating-linear-gradient(90deg, rgba(148, 163, 184, 0.08) 0, rgba(148, 163, 184, 0.08) 1px, transparent 1px, transparent 24px),
      repeating-linear-gradient(0deg, rgba(148, 163, 184, 0.08) 0, rgba(148, 163, 184, 0.08) 1px, transparent 1px, transparent 24px);
    overflow: auto;
    padding: 24px;
  }

  .svg-host {
    min-width: 100%;
    min-height: 100%;
    display: grid;
    place-items: center;
  }

  .svg-scale {
    transform-origin: top center;
  }

  .svg-scale :global(svg) {
    max-width: 100%;
    height: auto;
  }

  .placeholder {
    min-height: 100%;
    display: grid;
    place-content: center;
    text-align: center;
    color: rgba(51, 65, 85, 0.74);
    gap: 8px;
  }

  .placeholder h4 {
    margin: 0;
    font-size: 18px;
  }

  .placeholder p {
    margin: 0;
    font-size: 13px;
  }

  .btn {
    border: none;
    padding: 8px 12px;
    border-radius: 10px;
    cursor: pointer;
    font-size: 12px;
  }

  .btn.primary {
    background: linear-gradient(135deg, #2563eb, #0ea5e9);
    color: #fff;
  }

  .btn.ghost {
    background: rgba(15, 23, 42, 0.08);
    color: #0f172a;
  }

  .btn:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }

  .error {
    color: #ef4444;
    font-size: 12px;
    background: rgba(254, 242, 242, 0.9);
    border: 1px solid rgba(248, 113, 113, 0.35);
    border-radius: 10px;
    padding: 8px 10px;
  }

  .empty {
    font-size: 12px;
    color: rgba(51, 65, 85, 0.7);
    padding: 10px;
    border: 1px dashed rgba(148, 163, 184, 0.4);
    border-radius: 10px;
    background: rgba(248, 250, 252, 0.7);
  }

  @media (max-width: 1100px) {
    .canvas-shell {
      width: min(980px, calc(100vw - 24px));
    }

    .canvas-main {
      grid-template-columns: 320px 1fr;
    }
  }

  @media (max-width: 900px) {
    .canvas-shell {
      width: calc(100vw - 12px);
      height: calc(100vh - 12px);
      border-radius: 14px;
    }

    .canvas-main {
      grid-template-columns: 1fr;
      grid-template-rows: auto 1fr;
    }

    .canvas-sidebar {
      border-right: none;
      border-bottom: 1px solid rgba(148, 163, 184, 0.2);
    }

    .kind-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }
</style>
