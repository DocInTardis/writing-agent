# Route 驱动分流落地方案（2026-03-03）

## 1. 目标

将当前“edges 固定顺序执行 + service 层 if/else 分流”的模式，升级为“graph route 显式分流 + 双引擎一致执行”的模式，核心目标：

1. 分流规则从隐式逻辑迁移到图契约（可审计、可回放）。
2. LangGraph / Native 两个后端在路由选择与执行结果上保持一致。
3. 非流式主生成链路支持 route-graph 执行（可控开关）。
4. 失败时保留原有 fallback，不降低可用性。

## 2. 设计原则

1. 先做“可观测和可回退”的路由执行，再做更细粒度分支扩展。
2. 对已有路径保持兼容：默认保留 legacy graph，route-graph 通过开关灰度。
3. route 负责“走哪条链路”，节点 handler 负责“在链路内做什么”。
4. 所有路由决策写入 state / event metadata，保证 resume/replay 可解释。

## 3. 路由模型（第一版）

当前图节点：`planner -> writer -> reviewer -> qa`。

路由定义升级为：

1. `format_only`：`match = format_only==true`，`entry_node = qa`
2. `resume_sections`：`match = len(resume_sections)>0`，`entry_node = writer`
3. `compose_mode`：`match = compose_mode in {'auto','continue','overwrite'}`，`entry_node = planner`

路由优先级：按定义顺序自上而下匹配，命中即停。

## 4. 执行顺序（必须按此顺序实施）

### Step A：文档与契约

1. 更新图契约 route entry（`graph_contracts.py`）。
2. 明确 route 顺序和匹配规则，避免多路由冲突。

### Step B：引擎能力（Native + LangGraph 一致）

1. 在 `dual_engine.py` 增加 route 选择器（匹配表达式求值）。
2. 根据命中 route 的 `entry_node` 生成“可达子图执行序列”。
3. 增加 route 级默认 state 补全（仅用于被跳过上游节点时的必需字段）。
4. 将 `route_id/entry_node` 注入 state 与 event metadata。
5. Native 与 LangGraph 路径都应用同一套 route 选择规则。

### Step C：业务接入（非流式主链路）

1. 在 `generation_service.py` 增加 route-graph 开关：
   - `WRITING_AGENT_USE_ROUTE_GRAPH=1`：走 `run_generate_graph_dual_engine`
   - 其他值：保留 legacy `run_generate_graph`
2. 接入时保持原有 fallback 语义（异常或文本不足回退 single-pass）。
3. 在 `app_v2.py` 暴露 dual 函数导入，供 service 调用。

### Step D：测试与回归

1. 新增 dual-engine 路由分流单测：
   - `format_only` 仅执行 `qa`
   - `resume_sections` 从 `writer` 开始
   - metadata 包含 route 信息
2. 新增 generation service route-graph 接入测试：
   - 开关开启时调用 dual graph
   - 开关关闭时保持 legacy graph
3. 跑定向回归，确保现有约束与编辑链路不回退。

## 5. 风险与控制

1. 风险：route entry 跳过上游节点后，后续 contract 缺字段。
   - 控制：仅补最小必需默认字段，不放宽 validate_contract。
2. 风险：LangGraph 与 Native 行为偏差。
   - 控制：统一 route 选择逻辑，事件 metadata 带 route_id 对账。
3. 风险：全量切换影响线上稳定。
   - 控制：通过 `WRITING_AGENT_USE_ROUTE_GRAPH` 灰度开关渐进启用。

### Step E：流式链路接入（generate/stream）

1. `generate/stream` 主链路接入同一开关 `WRITING_AGENT_USE_ROUTE_GRAPH`：
   - 开启时走 `run_generate_graph_dual_engine`
   - 关闭时保持 legacy `run_generate_graph`
2. 流式链路补齐 `compose_mode + resume_sections + cursor_anchor` 指令约束组装。
3. 流式链路在 `resume_sections` 场景下跳过 quick-edit/ai-edit 快捷分支，避免和章节续写语义冲突。
4. 新增流式接入测试，验证开关开/关两种路径调用行为。

### Step F：章节生成接入（generate/section）

1. `generate/section` 同步接入 `WRITING_AGENT_USE_ROUTE_GRAPH` 开关。
2. route-graph 开启时走 dual graph，并传递：
   - `compose_mode='continue'`
   - `resume_sections=[section]`
3. route-graph 关闭时保持 legacy graph，不改变既有行为。
4. 新增章节生成开关开/关测试。

### Step G：可观测性回传（API/SSE）

1. route-graph 路径在返回体中补充 `graph_meta`：
   - `path`（`route_graph`）
   - `trace_id`
   - `engine`
   - `route_id`
   - `route_entry`
2. 非流式 `/generate`、流式 `/generate/stream`、章节 `/generate/section` 三条路径统一行为。
3. legacy graph 保持无 `graph_meta`，避免前端误判。

### Step H：前端诊断接入与回退回归

1. Svelte workbench 消费 `graph_meta`：
   - 非流式 `/generate` 响应；
   - 流式 `final` 事件；
   - `/generate/section` 章节重试响应。
2. 诊断展示统一：
   - 顶部状态栏增加 route/entry/engine 可视化；
   - thoughts 面板记录 route 诊断日志，便于排障。
3. API 契约文档补充 `graph_meta` 字段规范（可选字段、出现条件、兼容策略）。
4. 新增 route-graph 异常回退测试：
   - dual graph 抛错时必须回退 single-pass；
   - 回退路径不应返回 `graph_meta`，避免前端误判为 route-graph 成功。
5. 新增 shortcut 分支契约测试：
   - quick-edit/ai-edit 命中时不进入 route-graph；
   - 即使开关开启，也不返回 `graph_meta`，保证“执行路径”语义准确。

## 6. 完成标准

1. 文档、代码、测试三者一致。
2. route-graph 开关开启时可稳定生成，并可回退。
3. 所有新增单测通过，关键既有回归通过。
