# 学术论文图形渲染与画布重构说明（2026-03-13）

## 1. 重构目标

本次重构聚焦两个问题：

1. 默认生成文档中的流程图/架构图/时序图过于玩具化，只是简单方块加直线，缺少论文配图应有的层次、分组和版式。
2. 画布接口与导出链路使用了不同层级的 fallback 逻辑，导致前端生成图和导出到 docx 的图不一致。

本次实现采用“单一图形协议 + 单一渲染风格 + 默认自动补全”的方式统一后端与前端。

## 2. 参考依据（官方资料）

### 2.1 Mermaid 官方文档

- Flowcharts Syntax: https://mermaid.js.org/syntax/flowchart.html
- 关键启发：
  - 流程图应支持 subgraph / direction / 多种边样式。
  - 节点与边标签应支持自动换行，避免长文本直接撑坏布局。
  - 复杂图建议使用更强布局器，不要把所有节点硬塞成单列。

### 2.2 Graphviz 官方文档

- dot layered layout: https://graphviz.org/docs/layouts/dot/
- rankdir: https://graphviz.org/docs/attr-types/rankdir/
- ranksep: https://graphviz.org/docs/attrs/ranksep/
- clusters: https://graphviz.org/docs/clusters/
- clusterrank: https://graphviz.org/docs/attrs/clusterrank/
- 关键启发：
  - 有方向的系统流程应优先采用 layered / hierarchical layout。
  - `rankdir`、`ranksep`、`nodesep` 本质上是在控制阅读方向与层间空白。
  - cluster/subgraph 是正规架构图的核心，不应把“层”画成裸矩形堆叠。
  - 集群/层容器应有自己的标签、边界与布局语义。

### 2.3 PlantUML 官方文档

- Sequence Diagram: https://plantuml.com/sequence-diagram
- Component Diagram: https://plantuml.com/component-diagram
- 关键启发：
  - 时序图不只是箭头串起来，还应有 participant header、lifeline、activation、return arrow。
  - 架构图/组件图应强调组件边界、别名、关系方向和可维护的结构表达。

### 2.4 Nature figure guide

- Preparing figures: https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/
- 关键启发：
  - 论文配图优先使用 vector artwork。
  - 文本、箭头、边框都应保持可编辑和可缩放。
  - 字体、线宽、颜色应统一，图缩小后仍然可读。

## 3. 本次确定的工程原则

1. SVG 优先，PNG 仅作为 docx 嵌入兼容输出。
2. 浅色学术风格优先，禁止默认深色炫技图。
3. 架构图必须支持 lane / layer / cluster 语义。
4. 流程图必须支持节点类型、阶段分组、正交连接线与标签自动换行。
5. 时序图必须支持 participant、lifeline、activation bar、虚线返回消息。
6. 稀疏 spec 不再直接输出玩具图，而是先做 spec enrichment，再渲染。
7. 前端画布、默认文档导出、图形评分必须共用同一套图形 schema 与 enrich 逻辑。

## 4. 图形协议升级

统一支持以下 schema：

```json
{
  "type": "flow | architecture | sequence | er | timeline | bar | line | pie",
  "caption": "图题",
  "data": {
    "lanes": [{"id": "capability", "title": "能力层"}],
    "nodes": [{"id": "n1", "label": "检索服务", "subtitle": "RAG/事实包", "kind": "service", "lane": "capability"}],
    "edges": [{"from": "n1", "to": "n2", "label": "证据片段", "style": "solid | dashed"}],
    "participants": ["用户", "API网关"],
    "messages": [{"from": "用户", "to": "API网关", "label": "提交任务", "style": "solid | dashed"}]
  }
}
```

其中：

- `flow` 与 `architecture` 共用 `nodes/edges/lanes`。
- `sequence` 使用 `participants/messages`。
- 节点支持 `label/subtitle/kind/lane`，不再只有 `text`。
- 边支持 `from/to/label/style`，兼容旧字段 `src/dst`。

## 5. 已落地的后端改造

### 5.1 新增图形设计核心模块

新增文件：`writing_agent/v2/diagram_design.py`

职责：

- 统一 diagram kind 归一化。
- 统一 flow / architecture / sequence 的 spec enrichment。
- 为稀疏 prompt 生成更专业的建议 spec。
- 提供新的专业 SVG 渲染器：
  - `render_flow_or_architecture_svg`
  - `render_professional_sequence_svg`

### 5.2 文档导出默认图片升级

修改：`writing_agent/v2/figure_render.py`

- `render_figure_svg()` 改为优先走新的专业渲染器。
- `extract_figure_specs()` 在 renderable 检查前先执行 `enrich_figure_spec()`。
- `score_figure_spec()` 改为基于 enrich 后 spec 评分。
- 增加 cache version，避免旧图命中旧缓存。
- flow / architecture 图开始计入：
  - lane 是否存在
  - 节点类型多样性
  - subtitle 丰富度
  - generic label 惩罚

### 5.3 默认章节图自动补全升级

修改：`writing_agent/v2/graph_section_draft_domain.py`

- 在章节图 marker 规范化阶段调用 `enrich_figure_spec()`。
- 对 caption 有语义但 data 稀疏的图，允许自动补全为可渲染的专业图。
- 默认导出文档中的图片不再依赖“模型一次就画对”。

### 5.4 编辑画布接口升级

修改：`writing_agent/web/api/editing_flow.py`

- 新增 `architecture` 为一等图形类型。
- LLM diagram schema 升级到 richer schema。
- flow / architecture / sequence 的 fallback 改为 `suggest_diagram_spec()`。
- 归一化阶段支持 `lane/subtitle/kind/style`。

### 5.5 老图形渲染入口兜底升级

修改：`writing_agent/diagrams/render_svg.py`

- 老的 `render_flowchart_svg()` 也转接到新专业 renderer。
- 避免旧路径仍然输出单列方块图。

### 5.6 前端画布升级

修改：`writing_agent/web/frontend_svelte/src/lib/components/DiagramCanvas.svelte`

- 新增 `architecture` 图形类型。
- 新增更贴近论文系统设计图的 quick templates。
- JSON 编辑提示升级到 `lanes / nodes / edges` schema。

### 5.7 默认生成偏好升级

修改：`writing_agent/web/app_v2.py`

- 默认 `figure_types` 增加 `architecture`，让系统默认允许产出更正规的系统设计图。

## 6. 本次图形风格约束

### 6.1 流程图

- 默认按阶段或 lane 分组，而不是单列堆叠。
- 连线优先采用正交折线，减少视觉噪音。
- 节点支持 badge、subtitle、差异化边框。
- 决策节点与数据节点采用不同视觉语义。

### 6.2 架构图

- 默认按“接入层 / 编排层 / 能力层 / 数据层 / 治理层”渲染。
- group/lane/layer 会被保留并转成容器区块。
- 架构图节点支持 service / data / control / actor 等类型。
- 同一层的节点做均匀布局，而不是简单上下排列。

### 6.3 时序图

- participant 头部、lifeline、消息线、activation bar、返回虚线全部作为默认元素。
- 响应/结果类消息会被自动识别为 dashed style。
- 支持更长消息标签并做中间气泡展示，避免直接压在线上。

## 7. 默认文档图片的直接收益

1. 章节里已有的 architecture spec 将自动显示为分层架构图，而不是简单方块栈。
2. 章节里已有的 sequence spec 将自动显示 participant 与 lifeline，而不是普通横线箭头。
3. 仅有 caption 或稀疏 data 的 figure，在 caption 具备语义时会被自动补成可用图，不再直接退化为空图或玩具图。

## 8. Remaining Optional Enhancements

1. Add an optional legend for architecture diagrams.
2. Add dedicated decision-branch routing for dense flow diagrams.
3. Add `ref / divider / note` semantics for sequence diagrams.

## 9. Completion Notes

- Semantic auto-selection is active: caption/section semantics can now upgrade generic `flow` specs into `timeline`, `pie`, `bar`, `line`, or `er` when the incoming data is too sparse to justify a flowchart.
- Generation-time semantic prior is active: the diagram request pipeline now passes a `semantic_preferred_type` hint and rejects invalid explicit `type` values instead of silently collapsing them to `flow`.
- Caption-to-figure consistency scoring is active: mismatched captions now lower figure scores and surface `caption_kind_mismatch` or `caption_data_low_overlap` in the manifest instead of silently passing toy figures.
- ER rendering is now on the same paper-grade visual system as the other chart families, including crow-foot-style cardinality markers for `0`, `1`, and `N` endpoints.
- The broadened regression suite covers semantic inference, scoring penalties, DOCX image visibility, structured marker stripping, and full export rendering.
