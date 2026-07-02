<script lang="ts">
  import { formatVersionSummary, formatVersionTime } from './versions'

  let {
    versionLoading,
    versionError,
    versionGroups,
    versionMessage = $bindable(''),
    versionDiff,
    onRefresh,
    onCommit,
    onCheckout,
    onCompare
  }: {
    versionLoading: boolean
    versionError: string
    versionGroups: Array<any>
    versionMessage: string
    versionDiff: string
    onRefresh: () => void
    onCommit: () => void
    onCheckout: (id: string) => void
    onCompare: (id: string) => void
  } = $props()
</script>

<aside class="side-panel">
  <div class="panel-card version-panel">
    <div class="panel-header">
      <div>
        <div class="panel-title">版本树</div>
        <div class="panel-sub">自动小版本 · 手动大版本</div>
      </div>
      <button class="icon-btn" onclick={onRefresh} title="刷新">刷新</button>
    </div>
    <div class="major-commit">
      <input class="version-input" placeholder="输入版本说明" bind:value={versionMessage} />
      <button class="btn primary" onclick={onCommit}>保存版本</button>
    </div>
    {#if versionLoading}
      <div class="panel-empty">加载中...</div>
    {:else if versionError}
      <div class="panel-empty">{versionError}</div>
    {:else if versionGroups.length === 0}
      <div class="panel-empty">暂无版本</div>
    {:else}
      <div class="version-groups">
        {#each versionGroups as group}
          <div class="version-group">
            <div class={`version-major ${group.major?.is_current ? 'current' : ''}`}>
              <div class="version-title">
                <span>{group.major?.message || '未命名'}</span>
                <span class={`badge ${group.major?.kind === 'major' ? 'major' : 'minor'}`}>
                  {group.major?.kind === 'major' ? '大版本' : '小版本'}
                </span>
              </div>
              <div class="version-meta">
                <span>{formatVersionTime(group.major?.timestamp || 0)}</span>
                <span>{String(group.major?.version_id || '').slice(0, 7)}</span>
              </div>
              {#if formatVersionSummary(group.major?.summary)}
                <div class="version-summary">{formatVersionSummary(group.major?.summary)}</div>
              {/if}
              <div class="version-actions">
                <button class="btn ghost" onclick={() => onCheckout(group.major?.version_id)} disabled={group.major?.is_current}>切换</button>
                <button class="btn ghost" onclick={() => onCompare(group.major?.version_id)} disabled={group.major?.is_current}>对比</button>
              </div>
            </div>
            {#if group.minors && group.minors.length}
              <div class="version-minors">
                {#each group.minors as v}
                  <div class={`version-minor ${v.is_current ? 'current' : ''}`}>
                    <div>
                      <div class="minor-title">{v.message || '未命名'}</div>
                      {#if formatVersionSummary(v.summary)}
                        <div class="version-summary">{formatVersionSummary(v.summary)}</div>
                      {/if}
                      <div class="minor-meta">{formatVersionTime(v.timestamp)}</div>
                    </div>
                    <div class="minor-actions">
                      <button class="btn ghost" onclick={() => onCheckout(v.version_id)} disabled={v.is_current}>切换</button>
                      <button class="btn ghost" onclick={() => onCompare(v.version_id)} disabled={v.is_current}>对比</button>
                    </div>
                  </div>
                {/each}
              </div>
            {/if}
          </div>
        {/each}
      </div>
    {/if}
    <div class="version-diff">
      <div class="panel-sub">对比结果</div>
      <pre>{versionDiff || '请选择版本进行对比'}</pre>
    </div>
  </div>
</aside>
