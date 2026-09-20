<script lang="ts">
  import Icon from '../components/Icon.svelte'
  import PageSetupPanel from './PageSetupPanel.svelte'
  import type { EditorCommand } from '../types'
  import type { ResumeState } from './types'

  type RibbonTab = 'home' | 'insert' | 'layout' | 'references' | 'review' | 'view' | 'assistant'
  type EditorToolbarState = {
    bold: boolean
    italic: boolean
    underline: boolean
    readonly: boolean
    focused: boolean
    canUndo: boolean
    canRedo: boolean
    canCopy: boolean
    canCut: boolean
    canPaste: boolean
    styleId?: string
    fontFamily?: string
    fontSize?: string
    alignment?: string
    lineSpacing?: number | null
    letterSpacing?: string
    textTransform?: string
    firstLineIndentEm?: number | null
    leftIndentEm?: number | null
    rightIndentEm?: number | null
    spaceBeforePt?: number | null
    spaceAfterPt?: number | null
    styles?: Array<{ id: string; name: string }>
  }

  let {
    libraryViewMode = $bindable<'grid' | 'masonry' | 'list'>('grid'),
    librarySearch,
    librarySelectAll = $bindable(false),
    filteredCount,
    showAdvancedToolbar = $bindable(false),
    showAiRatePanel = $bindable(false),
    showPlagiarismPanel = $bindable(false),
    showFeedbackPanel = $bindable(false),
    planConfirmDecision = $bindable<'approved' | 'interrupted'>('approved'),
    planConfirmScore = $bindable(5),
    editorToolbarState,
    generating,
    instruction,
    resumeState,
    onRunEditorCommand,
    onOpenCanvas,
    onOpenCitations,
    onOpenInfoDrawer,
    onRunBatch,
    onGenerate,
    onPersistPlanConfirmPreference,
    onStop,
    onResume
  }: {
    libraryViewMode: 'grid' | 'masonry' | 'list'
    librarySearch: string
    librarySelectAll: boolean
    filteredCount: number
    showAdvancedToolbar: boolean
    showAiRatePanel: boolean
    showPlagiarismPanel: boolean
    showFeedbackPanel: boolean
    planConfirmDecision: 'approved' | 'interrupted'
    planConfirmScore: number
    editorToolbarState: EditorToolbarState
    generating: boolean
    instruction: string
    resumeState: ResumeState | null
    onRunEditorCommand: (cmd: EditorCommand) => void
    onOpenCanvas: () => void
    onOpenCitations: () => void
    onOpenInfoDrawer: () => void
    onRunBatch: () => void
    onGenerate: (instruction: string) => void
    onPersistPlanConfirmPreference: () => void | Promise<void>
    onStop: () => void
    onResume: () => void | Promise<void>
  } = $props()

  let activeTab = $state<RibbonTab>('home')
  const tabs: Array<{ id: RibbonTab; label: string }> = [
    { id: 'home', label: '开始' },
    { id: 'insert', label: '插入' },
    { id: 'layout', label: '布局' },
    { id: 'references', label: '引用' },
    { id: 'review', label: '审阅' },
    { id: 'view', label: '视图' },
    { id: 'assistant', label: '助手' }
  ]

  function command(value: string) {
    onRunEditorCommand(value as EditorCommand)
  }
</script>

<div class="doc-toolbar word-ribbon">
  <div class="ribbon-tabs" role="tablist" aria-label="编辑功能区">
    {#each tabs as tab}
      <button
        class:active={activeTab === tab.id}
        role="tab"
        aria-selected={activeTab === tab.id}
        onclick={() => (activeTab = tab.id)}
      >{tab.label}</button>
    {/each}
  </div>

  <div class="ribbon-content">
    {#if activeTab === 'home'}
      <div class="ribbon-group compact" aria-label="剪贴板">
        <button class="tool-btn" title="撤销 Ctrl+Z" onclick={() => command('undo')} disabled={!editorToolbarState.canUndo}><Icon name="undo" size={15} /></button>
        <button class="tool-btn" title="重做 Ctrl+Y" onclick={() => command('redo')} disabled={!editorToolbarState.canRedo}><Icon name="redo" size={15} /></button>
        <button class="tool-btn" title="剪切 Ctrl+X" onclick={() => command('cut')} disabled={!editorToolbarState.canCut}>✂</button>
        <button class="tool-btn" title="复制 Ctrl+C" onclick={() => command('copy')} disabled={!editorToolbarState.canCopy}>▣</button>
        <button class="tool-btn" title="粘贴 Ctrl+V" onclick={() => command('paste')} disabled={!editorToolbarState.canPaste}><Icon name="paste" size={15} /></button>
        <span class="ribbon-label">剪贴板</span>
      </div>
      <div class="ribbon-group wide" aria-label="字体与样式">
        <div class="ribbon-row">
          <select aria-label="段落样式" value={`style:${editorToolbarState.styleId || 'normal'}`} onchange={(event) => command(event.currentTarget.value)}>
            {#each editorToolbarState.styles || [] as style (style.id)}
              <option value={`style:${style.id}`}>{style.name}</option>
            {/each}
          </select>
          <button class="tool-btn" title="管理文档样式" onclick={() => command('style-manager')}>样式…</button>
          <select aria-label="字体" value={editorToolbarState.fontFamily || 'Microsoft YaHei'} onchange={(event) => command(`font:${event.currentTarget.value}`)}>
            <option value="Microsoft YaHei">微软雅黑</option>
            <option value="SimSun">宋体</option>
            <option value="SimHei">黑体</option>
            <option value="KaiTi">楷体</option>
            <option value="Arial">Arial</option>
            <option value="Times New Roman">Times New Roman</option>
          </select>
          <select class="size-select" aria-label="字号" value={editorToolbarState.fontSize || '14px'} onchange={(event) => command(`size:${event.currentTarget.value}`)}>
            <option value="10px">10</option><option value="12px">12</option><option value="14px">14</option>
            <option value="16px">16</option><option value="18px">18</option><option value="22px">22</option>
            <option value="28px">28</option><option value="36px">36</option>
          </select>
        </div>
        <div class="ribbon-row">
          <button class:active={editorToolbarState.bold} class="tool-btn glyph" title="加粗 Ctrl+B" onclick={() => command('bold')}><strong>B</strong></button>
          <button class:active={editorToolbarState.italic} class="tool-btn glyph" title="斜体 Ctrl+I" onclick={() => command('italic')}><em>I</em></button>
          <button class:active={editorToolbarState.underline} class="tool-btn glyph underline" title="下划线 Ctrl+U" onclick={() => command('underline')}>U</button>
        <button class="tool-btn glyph strike" title="删除线" onclick={() => command('strikethrough')}>ab</button>
        <button class="tool-btn glyph" title="上标" onclick={() => command('superscript')}>x²</button>
        <button class="tool-btn glyph" title="下标" onclick={() => command('subscript')}>x₂</button>
          <button class="tool-btn color-tool" title="文字颜色" onclick={() => command('color:#c00000')}>A<span class="color-line red"></span></button>
          <button class="tool-btn color-tool" title="突出显示" onclick={() => command('bgcolor:#fff2cc')}>A<span class="color-line yellow"></span></button>
          <button class="tool-btn" title="清除格式" onclick={() => command('clear-format')}><Icon name="clear" size={15} /></button>
        </div>
        <span class="ribbon-label">字体</span>
      </div>
      <div class="ribbon-group wide" aria-label="段落">
        <div class="ribbon-row">
          <button class="tool-btn" title="项目符号" onclick={() => command('list-bullet')}><Icon name="listBullet" size={15} /></button>
          <button class="tool-btn" title="编号" onclick={() => command('list-number')}><Icon name="listNumber" size={15} /></button>
          <button class="tool-btn align-glyph" title="左对齐" onclick={() => command('align-left')}>≡</button>
          <button class="tool-btn align-glyph center" title="居中" onclick={() => command('align-center')}>≡</button>
          <button class="tool-btn align-glyph right" title="右对齐" onclick={() => command('align-right')}>≡</button>
          <button class="tool-btn align-glyph justify" title="两端对齐" onclick={() => command('align-justify')}>≡</button>
          <button class="tool-btn" title="减少缩进" onclick={() => command('outdent')}>←</button>
          <button class="tool-btn" title="增加缩进" onclick={() => command('indent')}>→</button>
          <select class="line-select" aria-label="行距" value={String(editorToolbarState.lineSpacing || 1.5)} onchange={(event) => command(`line-height:${event.currentTarget.value}`)}>
            <option value="1">1.0</option><option value="1.15">1.15</option><option value="1.5">1.5</option><option value="2">2.0</option><option value="2.5">2.5</option>
          </select>
          <button class:active={showAdvancedToolbar} class="tool-btn" title="更多段落与字符格式" onclick={() => (showAdvancedToolbar = !showAdvancedToolbar)}>⋯</button>
        </div>
        <span class="ribbon-label">段落</span>
      </div>
      {#if showAdvancedToolbar}
        <div class="ribbon-group advanced-format" aria-label="高级格式">
          <label>字距
            <select value={editorToolbarState.letterSpacing || '0pt'} onchange={(event) => command(`letter-spacing:${event.currentTarget.value}`)}>
              <option value="-0.5pt">紧缩</option><option value="0pt">标准</option><option value="0.5pt">加宽 0.5</option><option value="1pt">加宽 1</option><option value="2pt">加宽 2</option>
            </select>
          </label>
          <label>大小写
            <select value={editorToolbarState.textTransform || 'none'} onchange={(event) => command(`text-transform:${event.currentTarget.value}`)}>
              <option value="none">原样</option><option value="uppercase">大写</option><option value="lowercase">小写</option><option value="capitalize">首字母大写</option>
            </select>
          </label>
          <label>段前
            <input type="number" min="0" max="72" step="1" value={editorToolbarState.spaceBeforePt ?? 0} onchange={(event) => command(`space-before:${event.currentTarget.value}`)} />
          </label>
          <label>段后
            <input type="number" min="0" max="72" step="1" value={editorToolbarState.spaceAfterPt ?? 0} onchange={(event) => command(`space-after:${event.currentTarget.value}`)} />
          </label>
          <label>左缩进
            <input type="number" min="0" max="20" step="0.5" value={editorToolbarState.leftIndentEm ?? 0} onchange={(event) => command(`left-indent:${event.currentTarget.value}`)} />
          </label>
          <label>右缩进
            <input type="number" min="0" max="20" step="0.5" value={editorToolbarState.rightIndentEm ?? 0} onchange={(event) => command(`right-indent:${event.currentTarget.value}`)} />
          </label>
          <button class="tool-btn" title="段落边框" onclick={() => command('border-color:#9ca3af')}>□</button>
          <button class="tool-btn" title="段落底纹" onclick={() => command('shading-color:#f3f4f6')}>▨</button>
          <span class="ribbon-label">高级格式</span>
        </div>
      {/if}
    {:else if activeTab === 'insert'}
      <div class="ribbon-group action-group">
        <button class="ribbon-action" onclick={() => command('markdown-import')}><span>MD↓</span>导入 Markdown</button>
        <button class="ribbon-action" onclick={() => command('markdown-export')}><span>MD↑</span>导出 Markdown</button>
        <button class="ribbon-action" onclick={() => command('table')}><span>▦</span>表格</button>
        <button class="ribbon-action" onclick={() => command('image')}><span>▧</span>图片</button>
        <button class="ribbon-action" disabled title="链接编辑将在对象与引用阶段启用"><span>↗</span>链接</button>
        <button class="ribbon-action" onclick={() => command('quote')}><Icon name="quote" size={17} />引用</button>
        <button class="ribbon-action" onclick={() => command('code')}><Icon name="code" size={17} />代码</button>
        <button class="ribbon-action" onclick={() => command('hr')}><span>—</span>分隔线</button>
        <button class="ribbon-action" onclick={() => command('page-break')}><span>↵</span>分页符</button>
        <button class="ribbon-action" disabled title="论文结构模板尚未启用"><span>§</span>论文结构</button>
        <button class="ribbon-action" onclick={onOpenCanvas}><Icon name="diagram" size={17} />图形</button>
      </div>
    {:else if activeTab === 'layout'}
      <div class="ribbon-group action-group">
        <button class="ribbon-action" onclick={() => command('line-height:1')}>单倍行距</button>
        <button class="ribbon-action" onclick={() => command('line-height:1.5')}>1.5 倍</button>
        <button class="ribbon-action" onclick={() => command('line-height:2')}>双倍行距</button>
        <button class="ribbon-action" onclick={() => command('indent-first')}>首行缩进</button>
        <button class="ribbon-action" onclick={() => command('margin:10px 0')}>段落间距</button>
        <button class="ribbon-action" onclick={() => command('page-break')}>分页符</button>
        <PageSetupPanel />
        <button class="ribbon-action" onclick={onOpenInfoDrawer}>页面信息</button>
      </div>
    {:else if activeTab === 'references'}
      <div class="ribbon-group action-group">
        <button class="ribbon-action" disabled title="自动目录将在引用阶段启用"><span>☷</span>目录</button>
        <button class="ribbon-action" disabled title="脚注将在引用阶段启用"><span>¹</span>脚注</button>
        <button class="ribbon-action" onclick={() => command('caption')}><span>图1</span>题注</button>
        <button class="ribbon-action" disabled title="交叉引用将在引用阶段启用"><span>↪</span>交叉引用</button>
        <button class="ribbon-action" disabled title="行内公式将在对象阶段启用"><span>π</span>行内公式</button>
        <button class="ribbon-action" onclick={() => command('math-block')}><span>∫</span>公式块</button>
        <button class="ribbon-action" onclick={onOpenCitations}><Icon name="cite" size={17} />引文管理</button>
      </div>
    {:else if activeTab === 'review'}
      <div class="ribbon-group action-group">
        <button class="ribbon-action" onclick={() => command('find-replace')}><span>⌕</span>查找替换</button>
        <button class="ribbon-action" onclick={() => command('proofread')}><span>✓</span>基础校对</button>
        <button class:active={showPlagiarismPanel} class="ribbon-action" onclick={() => (showPlagiarismPanel = !showPlagiarismPanel)}><Icon name="shield" size={17} />查重</button>
        <button class:active={showAiRatePanel} class="ribbon-action" onclick={() => (showAiRatePanel = !showAiRatePanel)}><Icon name="ai" size={17} />AI 痕迹</button>
        <button class:active={showFeedbackPanel} class="ribbon-action" onclick={() => (showFeedbackPanel = !showFeedbackPanel)}><Icon name="star" size={17} />评分</button>
        <button class="ribbon-action" onclick={onRunBatch}><Icon name="batch" size={17} />批量处理</button>
      </div>
    {:else if activeTab === 'view'}
      <div class="ribbon-group action-group">
        <button class="ribbon-action" onclick={() => command('view-outline')}><span>☰</span>导航窗格</button>
        <button class="ribbon-action" onclick={() => command('zoom-out')}><span>−</span>缩小</button>
        <button class="ribbon-action" onclick={() => command('zoom-100')}><span>100%</span>实际大小</button>
        <button class="ribbon-action" onclick={() => command('zoom-in')}><span>＋</span>放大</button>
        <button class="ribbon-action" onclick={() => command('view-shortcuts')}><span>⌨</span>快捷键</button>
      </div>
    {:else}
      <div class="ribbon-group assistant-group">
        <span class="assistant-hint">生成和润色只在需要时使用，不影响普通编辑。</span>
        <button class="btn primary icon-btn-text" onclick={() => onGenerate(instruction)} disabled={generating}><Icon name="play" className="ui-icon" /><span>{generating ? '处理中…' : '开始生成'}</span></button>
        <button class="btn ghost icon-btn-text" onclick={onStop} disabled={!generating}><Icon name="stop" className="ui-icon" /><span>停止</span></button>
        {#if resumeState && !generating}
          <button class="btn ghost icon-btn-text" onclick={onResume}><Icon name="resume" className="ui-icon" /><span>继续</span></button>
        {/if}
      </div>
    {/if}
  </div>
</div>

<style>
  .advanced-format {
    display: grid;
    grid-template-columns: repeat(4, minmax(82px, 1fr));
    gap: 4px 8px;
    min-width: 430px;
  }
  .advanced-format label {
    display: grid;
    grid-template-columns: auto minmax(50px, 1fr);
    align-items: center;
    gap: 4px;
    color: #687386;
    font-size: 11px;
  }
  .advanced-format select,
  .advanced-format input {
    box-sizing: border-box;
    width: 100%;
    height: 25px;
    min-width: 0;
    border: 1px solid #d4dae3;
    border-radius: 3px;
    background: #fff;
    color: #293241;
    font-size: 11px;
  }
</style>
