<script lang="ts">
  import { sanitizeDiagramPrompt } from '../utils/ai_payload'

  let {
    open = false,
    docId = '',
    onclose,
    oninsert
  }: {
    open?: boolean
    docId?: string
    onclose?: () => void
    oninsert?: (payload: { spec: Record<string, unknown>; svg: string; kind: Kind }) => void
  } = $props()


  type Kind = 'flow' | 'architecture' | 'er' | 'sequence' | 'state' | 'class' | 'gantt' | 'mindmap' | 'quadrant' | 'radar' | 'scatter' | 'heatmap' | 'funnel' | 'sankey' | 'swot' | 'timeline' | 'bar' | 'line' | 'pie'
  type PanelMode = 'studio' | 'history'

  const kindOptions: Array<{ value: Kind; label: string }> = [
    { value: 'flow', label: '流程图' },
    { value: 'architecture', label: '架构图' },
    { value: 'er', label: 'ER 图' },
    { value: 'sequence', label: '时序图' },
    { value: 'state', label: '状态图' },
    { value: 'class', label: '类图' },
    { value: 'gantt', label: 'Gantt 图' },
    { value: 'mindmap', label: '思维导图' },
    { value: 'quadrant', label: '四象限' },
    { value: 'radar', label: '雷达图' },
    { value: 'scatter', label: '散点图' },
    { value: 'heatmap', label: '热力图' },
    { value: 'funnel', label: '漏斗图' },
    { value: 'sankey', label: '桑基图' },
    { value: 'swot', label: 'SWOT图' },
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
    architecture: [
      '用户端、桌面应用、业务服务、文档内核、模型接口、资料库',
      '界面层、命令层、文档模型、布局引擎、导出层之间的依赖关系',
      '本地优先架构：Tauri 壳、Svelte 界面、Python 服务、Rust 文档内核'
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
    state: [
      '草稿 -> 待审核 -> 已通过 -> 已发布',
      '新建 -> 处理中 -> 待确认 -> 已完成',
      '待提交 -> 审批中 -> 已驳回/已批准'
    ],
    class: [
      '用户、项目、文档、引用之间的类关系',
      '课程、教师、学生、选课记录的领域模型',
      '订单、商品、库存、支付的类图'
    ],
    gantt: [
      '立项 M1-M2，开发 M2-M4，测试 M4-M5，上线 M5',
      '调研、建模、实现、评估四阶段排期',
      '论文写作：选题、综述、实验、定稿计划'
    ],
    mindmap: [
      '论文主题 -> 背景、方法、实验、结论',
      '系统设计 -> 用户、能力、数据、治理',
      '研究问题 -> 现状、痛点、方案、验证'
    ],
    quadrant: [
      '需求优先级四象限：高价值高成本等事项分布',
      '风险与收益矩阵',
      '技术方案在影响力与落地难度上的定位'
    ],
    radar: [
      '模型在准确率、鲁棒性、效率、成本上的多维评估',
      '候选方案能力画像对比',
      '系统质量维度雷达图'
    ],
    scatter: [
      '不同实验样本在成本和性能上的散点分布',
      '方案点在延迟与准确率上的关系',
      '算法版本在资源消耗与质量上的相关性'
    ],
    heatmap: [
      '章节与风险等级的热力图矩阵',
      '模块与问题密度的热点分布',
      '实验维度与性能强度热力图'
    ],
    funnel: [
      '候选方案从初筛到最终采用的漏斗图',
      '样本从收集到纳入分析的转化漏斗',
      '线索到成交的阶段收敛过程'
    ],
    sankey: [
      '需求输入到生成、校核、交付的流向图',
      '资源从来源到各模块分配的桑基图',
      '用户路径分流与结果去向分析'
    ],
    swot: [
      '系统方案的 SWOT 分析',
      '论文选题的优势、劣势、机会、威胁',
      '项目立项的战略评估 SWOT 图'
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

  let panelMode: PanelMode = $state('studio')
  let kind: Kind = $state('flow')
  let prompt = $state('')
  let optimizeInput = $state('')
  let loading = $state(false)
  let error = $state('')
  let svg = $state('')
  let spec: Record<string, unknown> | null = $state(null)
  let zoom = $state(1)

  let historyItems: Array<{
    id: number
    kind: Kind
    prompt: string
    spec: Record<string, unknown>
    svg: string
    ts: number
  }> = $state([])

  function panelTitle(mode: PanelMode) {
    if (mode === 'history') return '最近生成'
    return '创建图表'
  }

  function closeCanvas() {
    onclose?.()
  }

  function useTemplate(text: string) {
    prompt = sanitizeDiagramPrompt(text)
  }

  function normalizeKind(raw: unknown): Kind {
    const v = String(raw || '').trim().toLowerCase()
    if (v === 'architecture') return 'architecture'
    if (v === '架构图' || v === '系统架构图') return 'architecture'
    if (v === 'er') return 'er'
    if (v === 'er图' || v === '实体关系图') return 'er'
    if (v === 'sequence') return 'sequence'
    if (v === '时序图') return 'sequence'
    if (v === 'state') return 'state'
    if (v === '状态图' || v === '状态机图') return 'state'
    if (v === 'class') return 'class'
    if (v === '类图') return 'class'
    if (v === 'gantt') return 'gantt'
    if (v === '甘特图' || v === 'gantt图') return 'gantt'
    if (v === 'mindmap') return 'mindmap'
    if (v === '思维导图' || v === '脑图') return 'mindmap'
    if (v === 'quadrant') return 'quadrant'
    if (v === '四象限' || v === '四象限图') return 'quadrant'
    if (v === 'radar') return 'radar'
    if (v === '雷达图') return 'radar'
    if (v === 'scatter') return 'scatter'
    if (v === '散点图') return 'scatter'
    if (v === 'heatmap') return 'heatmap'
    if (v === '热力图') return 'heatmap'
    if (v === 'funnel') return 'funnel'
    if (v === '漏斗图') return 'funnel'
    if (v === 'sankey') return 'sankey'
    if (v === '桑基图') return 'sankey'
    if (v === 'swot') return 'swot'
    if (v === 'swot图') return 'swot'
    if (v === 'timeline') return 'timeline'
    if (v === '时间线') return 'timeline'
    if (v === 'bar') return 'bar'
    if (v === '柱状图') return 'bar'
    if (v === 'line') return 'line'
    if (v === '折线图') return 'line'
    if (v === 'pie') return 'pie'
    if (v === '饼图') return 'pie'
    return 'flow'
  }

  function ensureObject(value: unknown): Record<string, unknown> {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      throw new Error('图形规范不是对象')
    }
    return value as Record<string, unknown>
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
    pushHistory(sourcePrompt, sourceKind, nextSpec, nextSvg)
  }

  async function generateDiagram(customPrompt?: string) {
    const finalPrompt = sanitizeDiagramPrompt(customPrompt || prompt || '')
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
    const ask = sanitizeDiagramPrompt(optimizeInput)
    if (!ask) return
    if (!spec) {
      await generateDiagram(ask)
      return
    }
    const context = JSON.stringify(spec).slice(0, 1800)
    await generateDiagram(`在当前图基础上优化：${ask}\n当前规范：${context}`)
  }

  function restoreHistory(item: { kind: Kind; prompt: string; spec: Record<string, unknown>; svg: string }) {
    kind = item.kind
    prompt = sanitizeDiagramPrompt(item.prompt)
    spec = item.spec
    svg = item.svg
    panelMode = 'studio'
  }

  function handleInsert() {
    if (!spec) return
    oninsert?.({ spec, svg, kind })
  }

  async function copySvg() {
    if (!svg) return
    try {
      await navigator.clipboard.writeText(svg)
    } catch {
      error = '复制 SVG 失败，请检查浏览器权限'
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
    onclick={(e) => { if (e.target === e.currentTarget) closeCanvas() }}
    onkeydown={handleBackdropKeydown}
  >
    <section class="canvas-shell" aria-label="AI 画布系统">
      <header class="canvas-topbar">
        <div class="title-wrap">
          <h3>图表</h3>
          <p>描述内容，生成后可继续用自然语言修改并插入正文。</p>
        </div>
        <div class="top-actions">
          <button class="btn ghost" onclick={() => (panelMode = 'studio')}>创建</button>
          <button class="btn ghost" onclick={() => (panelMode = 'history')}>最近生成</button>
          <button class="btn ghost" onclick={resetCanvas}>清空</button>
          <button class="close-btn" onclick={closeCanvas} aria-label="关闭">×</button>
        </div>
      </header>

      <div class="canvas-main">
        <aside class="canvas-sidebar">
          <div class="panel-title">{panelTitle(panelMode)}</div>

          {#if panelMode === 'studio'}
            <label class="kind-select">
              <span>图表类型</span>
              <select bind:value={kind}>
                {#each kindOptions as item}<option value={item.value}>{item.label}</option>{/each}
              </select>
            </label>

            <div class="template-list">
              {#each quickTemplates[kind] as t}
                <button class="template-chip" onclick={() => useTemplate(t)}>{t}</button>
              {/each}
            </div>

            <textarea
              class="prompt-box"
              rows="5"
              bind:value={prompt}
              placeholder="输入你要绘制的内容，例如：用户登录到下单的关键流程。"
            ></textarea>

            <div class="canvas-actions">
              <button class="btn primary" onclick={() => generateDiagram()} disabled={loading || !prompt.trim()}>
                {loading ? '生成中...' : '生成图形'}
              </button>
              <button class="btn ghost" onclick={handleInsert} disabled={!spec}>插入文档</button>
            </div>

            <textarea
              class="prompt-box mini"
              rows="3"
              bind:value={optimizeInput}
              placeholder="二次优化，例如：改成更简洁的 5 个节点，强调异常分支。"
            ></textarea>
            <button class="btn ghost" onclick={optimizeCurrent} disabled={loading || !optimizeInput.trim()}>
              AI 二次优化
            </button>
          {/if}

          {#if panelMode === 'history'}
            <div class="history-list">
              {#if historyItems.length === 0}
                <div class="empty">暂无历史记录</div>
              {:else}
                {#each historyItems as item}
                  <button class="history-item" onclick={() => restoreHistory(item)}>
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
              <button class="btn ghost" onclick={() => (zoom = Math.max(0.4, Number((zoom - 0.1).toFixed(1))))}>-</button>
              <span>{Math.round(zoom * 100)}%</span>
              <button class="btn ghost" onclick={() => (zoom = Math.min(2.2, Number((zoom + 0.1).toFixed(1))))}>+</button>
              <button class="btn ghost" onclick={() => (zoom = 1)}>重置缩放</button>
            </div>
            <div class="export-group">
              <button class="btn ghost" onclick={copySvg} disabled={!svg}>复制 SVG</button>
              <button class="btn ghost" onclick={downloadSvg} disabled={!svg}>下载 SVG</button>
              <button class="btn primary" onclick={handleInsert} disabled={!spec}>插入正文</button>
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
                <p>选择图表类型，输入内容后即可生成。生成结果仍可继续修改。</p>
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
    background: rgba(21, 31, 46, 0.28);
    z-index: 24;
    display: grid;
    place-items: center;
    padding: 16px;
  }

  .canvas-shell {
    width: min(1480px, calc(100vw - 32px));
    height: min(92vh, 980px);
    border-radius: var(--wa-radius-lg);
    background: var(--wa-surface);
    color: var(--wa-text);
    border: 1px solid var(--wa-border);
    box-shadow: var(--wa-shadow-float);
    display: grid;
    grid-template-rows: auto 1fr;
    overflow: hidden;
  }

  .canvas-topbar {
    display: flex;
    justify-content: space-between;
    gap: 12px;
    padding: 14px 16px;
    border-bottom: 1px solid var(--wa-border);
    background: var(--wa-surface);
  }

  .title-wrap h3 {
    margin: 0 0 4px 0;
    font-size: 18px;
  }

  .title-wrap p {
    margin: 0;
    font-size: 12px;
    color: var(--wa-text-muted);
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
    background: transparent;
    color: var(--wa-text-secondary);
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
    border-right: 1px solid var(--wa-border);
    padding: 12px;
    display: grid;
    gap: 10px;
    overflow: auto;
    align-content: start;
  }

  .panel-title {
    font-size: 13px;
    font-weight: 700;
    color: var(--wa-text);
  }

  .kind-select { display: grid; gap: 5px; color: var(--wa-text-secondary); font-size: 12px; }
  .kind-select select { width: 100%; height: 34px; padding: 0 9px; border: 1px solid var(--wa-border-strong); border-radius: var(--wa-radius); background: var(--wa-surface); color: var(--wa-text); }

  .template-chip,
  .history-item {
    border: 1px solid var(--wa-border);
    border-radius: var(--wa-radius);
    background: var(--wa-surface);
    color: var(--wa-text-secondary);
    cursor: pointer;
    font-size: 12px;
    padding: 7px 9px;
  }

  .template-list {
    display: grid;
    gap: 6px;
  }

  .template-chip {
    text-align: left;
    background: var(--wa-surface-subtle);
  }

  .prompt-box {
    border: 1px solid var(--wa-border-strong);
    border-radius: var(--wa-radius);
    padding: 10px 12px;
    font-size: 13px;
    line-height: 1.5;
    resize: vertical;
    background: var(--wa-surface);
    color: var(--wa-text);
  }

  .prompt-box.mini {
    min-height: 72px;
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
    color: var(--wa-text-secondary);
  }

  .history-item > div:nth-child(3) {
    color: var(--wa-text-muted);
    font-size: 11px;
  }

  .canvas-stage {
    min-width: 0;
    min-height: 0;
    padding: 12px;
    display: grid;
    grid-template-rows: auto 1fr;
    gap: 10px;
    background: var(--wa-surface);
  }

  .stage-toolbar {
    display: flex;
    justify-content: space-between;
    gap: 10px;
    flex-wrap: wrap;
    border: 1px solid var(--wa-border);
    border-radius: var(--wa-radius);
    padding: 8px 10px;
    background: var(--wa-surface);
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
    border: 1px solid var(--wa-border);
    border-radius: var(--wa-radius-lg);
    background:
      linear-gradient(0deg, rgba(248, 250, 252, 0.82), rgba(248, 250, 252, 0.82)),
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
    color: var(--wa-text-muted);
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
    border-radius: var(--wa-radius);
    cursor: pointer;
    font-size: 12px;
  }

  .btn.primary {
    background: var(--wa-accent);
    color: #fff;
  }

  .btn.ghost {
    background: var(--wa-surface);
    color: var(--wa-text-secondary);
    border: 1px solid var(--wa-border);
  }

  .btn:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }

  .error {
    color: var(--wa-danger);
    font-size: 12px;
    background: rgba(254, 242, 242, 0.9);
    border: 1px solid rgba(220, 38, 38, 0.35);
    border-radius: 10px;
    padding: 8px 10px;
  }

  .empty {
    font-size: 12px;
    color: var(--wa-text-muted);
    padding: 10px;
    border: 1px dashed rgba(231, 229, 228, 1);
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
      border-bottom: 1px solid rgba(231, 229, 228, 1);
    }

  }
</style>
