<script lang="ts">
  export interface KGNode {
    id: string
    name: string
    type: 'method' | 'dataset' | 'concept' | 'claim' | 'author' | 'metric'
    distance?: number
  }

  export interface KGEdge {
    from: string
    to: string
    relation: string
  }

  let {
    nodes = [] as KGNode[],
    edges = [] as KGEdge[],
    width = 480,
    height = 320,
    onNodeClick,
  }: {
    nodes?: KGNode[]
    edges?: KGEdge[]
    width?: number
    height?: number
    onNodeClick?: (node: KGNode) => void
  } = $props()

  const colors: Record<string, string> = {
    method: '#4a90d9',
    dataset: '#7cb342',
    concept: '#f5a623',
    claim: '#d0021b',
    author: '#9013fe',
    metric: '#50e3c2',
  }

  function layout(nodesArr: KGNode[]) {
    const cx = width / 2
    const cy = height / 2
    const maxRadius = Math.min(width, height) * 0.38
    const map = new Map<string, { x: number; y: number }>()
    if (nodesArr.length === 0) return map
    // Center node = first claim or first node
    const centerIdx = nodesArr.findIndex((n) => n.type === 'claim')
    const ordered = centerIdx >= 0
      ? [nodesArr[centerIdx], ...nodesArr.slice(0, centerIdx), ...nodesArr.slice(centerIdx + 1)]
      : nodesArr
    ordered.forEach((n, i) => {
      if (i === 0 && n.type === 'claim') {
        map.set(n.id, { x: cx, y: cy })
        return
      }
      const ring = (n.distance ?? 1)
      const angle = ((i - 1) / Math.max(1, ordered.length - 1)) * Math.PI * 2
      const r = maxRadius * (0.35 + 0.65 * (ring / Math.max(2, ring)))
      map.set(n.id, {
        x: cx + Math.cos(angle) * r,
        y: cy + Math.sin(angle) * r,
      })
    })
    return map
  }

  const posMap = $derived(layout(nodes))

  function pos(id: string) {
    return posMap.get(id) || { x: 0, y: 0 }
  }
</script>

<div class="kg-view" style="width:{width}px;height:{height}px">
  <svg {width} {height} viewBox="0 0 {width} {height}">
    {#each edges as e}
      {@const p0 = pos(e.from)}
      {@const p1 = pos(e.to)}
      <line x1={p0.x} y1={p0.y} x2={p1.x} y2={p1.y} class="edge" />
      <text
        x={(p0.x + p1.x) / 2}
        y={(p0.y + p1.y) / 2 - 4}
        class="edge-label"
      >{e.relation}</text>
    {/each}
    {#each nodes as n}
      {@const p = pos(n.id)}
      <g
        class="node"
        role="button"
        tabindex="0"
        onclick={() => onNodeClick?.(n)}
        onkeydown={(ev) => { if (ev.key === 'Enter' || ev.key === ' ') onNodeClick?.(n) }}
      >
        <circle
          cx={p.x}
          cy={p.y}
          r={n.type === 'claim' ? 14 : 10}
          fill={colors[n.type] || '#999'}
          stroke="#fff"
          stroke-width="2"
        />
        <text
          x={p.x}
          y={p.y + (n.type === 'claim' ? 26 : 22)}
          text-anchor="middle"
          class="node-label"
        >{n.name.length > 14 ? n.name.slice(0, 13) + '…' : n.name}</text>
      </g>
    {/each}
  </svg>
  <div class="legend">
    {#each Object.entries(colors) as [type, color]}
      <span class="legend-item"><span class="dot" style="background:{color}"></span>{type}</span>
    {/each}
  </div>
</div>

<style>
  .kg-view {
    border: 1px solid rgba(90, 70, 45, 0.12);
    border-radius: 8px;
    background: #fffdf8;
    position: relative;
    overflow: hidden;
  }
  svg { display: block; }
  .edge {
    stroke: rgba(90, 70, 45, 0.25);
    stroke-width: 1.5;
  }
  .edge-label {
    font-size: 9px;
    fill: rgba(90, 70, 45, 0.7);
    pointer-events: none;
  }
  .node { cursor: pointer; }
  .node-label {
    font-size: 10px;
    fill: #2b2416;
    pointer-events: none;
  }
  .legend {
    position: absolute;
    bottom: 6px;
    left: 6px;
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    background: rgba(255, 253, 248, 0.9);
    padding: 3px 6px;
    border-radius: 6px;
    font-size: 10px;
  }
  .legend-item {
    display: inline-flex;
    align-items: center;
    gap: 3px;
  }
  .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    display: inline-block;
  }
</style>
