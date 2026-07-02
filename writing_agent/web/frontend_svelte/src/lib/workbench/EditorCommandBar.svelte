<script lang="ts">
  import Icon from '../components/Icon.svelte'
  import type { EditorCommand } from '../types'
  import type { ResumeState } from './types'

  type EditorToolbarState = {
    bold: boolean
    readonly: boolean
    focused: boolean
    canUndo: boolean
    canCopy: boolean
    canCut: boolean
    canPaste: boolean
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
</script>

<div class="library-command-bar">
  <div class="library-view-switch">
    <button
      class={`view-btn ${libraryViewMode === 'grid' ? 'active' : ''}`}
      onclick={() => (libraryViewMode = 'grid')}
      title="网格视图"
    >
      <Icon name="grid" className="ui-icon" />
    </button>
    <button
      class={`view-btn ${libraryViewMode === 'masonry' ? 'active' : ''}`}
      onclick={() => (libraryViewMode = 'masonry')}
      title="瀑布视图"
    >
      <Icon name="masonry" className="ui-icon" />
    </button>
    <button
      class={`view-btn ${libraryViewMode === 'list' ? 'active' : ''}`}
      onclick={() => (libraryViewMode = 'list')}
      title="列表视图"
    >
      <Icon name="list" className="ui-icon" />
    </button>
  </div>
  <div class="library-counter">{librarySearch ? `搜索：${librarySearch}` : '实时文档工作区'}</div>
  <div class="library-actions">
    <button class="btn ghost icon-btn-text" onclick={() => (librarySelectAll = !librarySelectAll)}>
      <Icon name="select" className="ui-icon" />
      <span>{librarySelectAll ? '取消全选' : '全选资料'}</span>
    </button>
    <button class="btn ghost icon-btn-text">
      <Icon name="batch" className="ui-icon" />
      <span>批处理 ({librarySelectAll ? filteredCount : 1})</span>
    </button>
    <button class="btn ghost icon-btn-text" onclick={onOpenInfoDrawer}>
      <Icon name="doc" className="ui-icon" />
      <span>文档信息</span>
    </button>
  </div>
</div>

<div class="doc-toolbar">
  <div class="toolbar-line primary">
    <div class="toolbar-cluster core">
      <span class="cluster-label">创作核心</span>
      <button class="tool-btn" onclick={() => onRunEditorCommand('heading1')} aria-label="一级标题">
        <Icon name="h1" size={14} className="ui-icon sm" />
      </button>
      <button class="tool-btn" onclick={() => onRunEditorCommand('heading2')} aria-label="二级标题">
        <Icon name="h2" size={14} className="ui-icon sm" />
      </button>
      <button
        class={`tool-btn ${editorToolbarState.bold ? 'active' : ''}`}
        title="加粗 Ctrl/Cmd+B"
        aria-label="加粗"
        onclick={() => onRunEditorCommand('bold')}
        disabled={editorToolbarState.readonly || !editorToolbarState.focused}
      >
        <Icon name="bold" size={14} className="ui-icon sm" />
      </button>
      <button class="tool-btn" onclick={() => onRunEditorCommand('list-bullet')} aria-label="无序列表">
        <Icon name="listBullet" size={14} className="ui-icon sm" />
      </button>
      <button class="tool-btn" onclick={() => onRunEditorCommand('list-number')} aria-label="有序列表">
        <Icon name="listNumber" size={14} className="ui-icon sm" />
      </button>
      <span class="tool-sep"></span>
      <button class="tool-btn" onclick={onOpenCanvas} aria-label="图形画布">
        <Icon name="diagram" size={14} className="ui-icon sm" />
      </button>
      <button class="tool-btn" onclick={onOpenCitations} aria-label="引用管理">
        <Icon name="cite" size={14} className="ui-icon sm" />
      </button>
    </div>
    <button class="btn ghost btn-sm toolbar-advanced-toggle" onclick={() => (showAdvancedToolbar = !showAdvancedToolbar)}>
      {showAdvancedToolbar ? '收起高级' : '高级操作'}
    </button>
    <button class="btn primary icon-btn-text toolbar-generate-btn" onclick={() => onGenerate(instruction)} disabled={generating}>
      <Icon name="play" className="ui-icon" />
      <span>{generating ? '生成中...' : '生成'}</span>
    </button>
  </div>
  {#if showAdvancedToolbar}
    <div class="toolbar-line secondary">
      <div class="toolbar-cluster">
        <span class="cluster-label">结构与编辑</span>
        <button class="tool-btn" title="撤销 Ctrl/Cmd+Z" aria-label="撤销" onclick={() => onRunEditorCommand('undo')} disabled={!editorToolbarState.canUndo}>
          <Icon name="undo" size={14} className="ui-icon sm" />
        </button>
        <button class="tool-btn" title="重做 Ctrl/Cmd+Y" aria-label="重做" onclick={() => onRunEditorCommand('redo')} disabled={editorToolbarState.readonly}>
          <Icon name="redo" size={14} className="ui-icon sm" />
        </button>
        <button class="tool-btn" title="复制 Ctrl/Cmd+C" aria-label="复制" onclick={() => onRunEditorCommand('copy')} disabled={!editorToolbarState.canCopy}>
          <Icon name="copy" size={14} className="ui-icon sm" />
        </button>
        <button class="tool-btn" title="剪切 Ctrl/Cmd+X" aria-label="剪切" onclick={() => onRunEditorCommand('cut')} disabled={!editorToolbarState.canCut}>
          <Icon name="cut" size={14} className="ui-icon sm" />
        </button>
        <button class="tool-btn" title="粘贴 Ctrl/Cmd+V" aria-label="粘贴" onclick={() => onRunEditorCommand('paste')} disabled={!editorToolbarState.canPaste}>
          <Icon name="paste" size={14} className="ui-icon sm" />
        </button>
        <button class="tool-btn" title="清除格式" aria-label="清除格式" onclick={() => onRunEditorCommand('clear-format')} disabled={editorToolbarState.readonly || !editorToolbarState.focused}>
          <Icon name="clear" size={14} className="ui-icon sm" />
        </button>
        <button class="tool-btn" onclick={() => onRunEditorCommand('quote')} aria-label="引用块">
          <Icon name="quote" size={14} className="ui-icon sm" />
        </button>
        <button class="tool-btn" onclick={() => onRunEditorCommand('code')} aria-label="代码块">
          <Icon name="code" size={14} className="ui-icon sm" />
        </button>
      </div>
      <div class="toolbar-cluster compact">
        <span class="cluster-label">高级操作</span>
        <button class="btn ghost icon-btn-text" onclick={onRunBatch}>
          <Icon name="batch" className="ui-icon" />
          <span>批处理</span>
        </button>
        <button
          class="btn ghost icon-btn-text"
          data-testid="ai-rate-toggle"
          onclick={() => (showAiRatePanel = !showAiRatePanel)}
        >
          <Icon name="ai" className="ui-icon" />
          <span>{showAiRatePanel ? '收起 AI 率' : 'AI 率检测'}</span>
        </button>
        <button
          class="btn ghost icon-btn-text"
          data-testid="plagiarism-toggle"
          onclick={() => (showPlagiarismPanel = !showPlagiarismPanel)}
        >
          <Icon name="shield" className="ui-icon" />
          <span>{showPlagiarismPanel ? '收起查重' : '查重检测'}</span>
        </button>
        <button
          class="btn ghost icon-btn-text"
          data-testid="feedback-toggle"
          onclick={() => (showFeedbackPanel = !showFeedbackPanel)}
        >
          <Icon name="star" className="ui-icon" />
          <span>{showFeedbackPanel ? '收起评分' : '满意度评分'}</span>
        </button>
        <div class="plan-confirm-inline">
          <span class="plan-confirm-label">计划确认</span>
          <select
            class="plan-confirm-select"
            bind:value={planConfirmDecision}
            onchange={() => void onPersistPlanConfirmPreference()}
          >
            <option value="approved">通过</option>
            <option value="interrupted">终止</option>
          </select>
          <label class="plan-confirm-score">
            <span>评分</span>
            <input
              type="number"
              min="0"
              max="5"
              step="1"
              bind:value={planConfirmScore}
              onchange={() => void onPersistPlanConfirmPreference()}
            />
          </label>
        </div>
        <button class="btn ghost icon-btn-text" onclick={onStop} disabled={!generating}>
          <Icon name="stop" className="ui-icon" />
          <span>停止</span>
        </button>
        {#if resumeState && !generating}
          <button class="btn ghost icon-btn-text" onclick={onResume}>
            <Icon name="resume" className="ui-icon" />
            <span>续跑</span>
          </button>
        {/if}
      </div>
    </div>
  {/if}
</div>
