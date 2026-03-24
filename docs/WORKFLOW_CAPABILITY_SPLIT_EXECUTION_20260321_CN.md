# 编排后端 / 业务能力正交拆分执行清单（第一阶段）

## 目标

在不改变现有生成语义、路由语义、fallback 语义的前提下，先完成第一阶段重构：

1. 将“运行时编排后端”与“业务能力实现”拆成两个正交维度。
2. 保持 `state_engine` 继续作为编排运行时层。
3. 引入 `workflows` 作为工作流装配层。
4. 引入 `capabilities` 作为业务能力层。
5. 让 `writing_agent.v2.graph_runner.run_generate_graph_dual_engine` 不再内联业务节点实现，而是委托到工作流装配层。

## 本阶段范围

仅覆盖生成主链路的 dual-engine 入口，不在本阶段处理：

- `generation_service` 的进一步瘦身
- revise / inline edit / stream workflow 的全面迁移
- LangGraph 默认后端切换
- 跨所有能力域的大规模移动或重命名

## 交付物

- `writing_agent/capabilities/`
- `writing_agent/workflows/`
- 对 `writing_agent/v2/graph_runner.py` 的最小接线重构
- 对应测试与执行记录

## 严格执行步骤

- [x] Step 1：新增执行清单并记录范围
- [x] Step 2：新增 `capabilities` 层契约与生成相关能力适配
- [x] Step 3：新增 `workflows/generate_workflow.py`，承接 dual-engine 工作流装配
- [x] Step 4：重构 `writing_agent/v2/graph_runner.py`，改为委托工作流层
- [x] Step 5：补充/调整针对新分层的单元测试
- [x] Step 6：运行聚焦验证测试并处理回归
- [x] Step 7：回填执行记录，确认全部完成

## 完成判定

以下条件全部满足才算完成：

1. `state_engine` 仍只负责图契约、路由、checkpoint、resume、replay、backend 选择。
2. `graph_runner.py` 不再内联 planner / plan_confirm / writer / reviewer / qa 的业务实现。
3. 业务节点实现落在 `capabilities`，装配逻辑落在 `workflows`。
4. 现有 dual-engine 相关测试通过。
5. 本文档执行记录更新为完成状态。

## 执行记录

### 2026-03-21 计划建立

- 状态：进行中
- 说明：建立第一阶段执行清单，范围限定为 dual-engine 生成主链路解耦。

### 2026-03-21 执行结果

- 状态：完成
- 说明：已完成第一阶段 dual-engine 生成主链路的“运行时后端 / 工作流装配 / 业务能力”初步分层。

### 2026-03-21 代码落地记录

- 新增 `writing_agent/capabilities/contracts.py`：沉淀工作流请求与依赖契约。
- 新增 `writing_agent/capabilities/planning.py`：承接 planner / plan_confirm 业务能力。
- 新增 `writing_agent/capabilities/composition.py`：承接 writer 业务能力。
- 新增 `writing_agent/capabilities/quality.py`：承接 reviewer / qa 业务能力。
- 新增 `writing_agent/workflows/generate_workflow.py`：负责 dual-engine 生成工作流装配与 runtime 调用。
- 更新 `writing_agent/v2/graph_runner.py`：`run_generate_graph_dual_engine` 改为委托工作流层，不再内联业务节点实现。
- 新增 `tests/unit/test_generate_workflow.py`：为新增工作流装配层提供直接单测保护。

### 2026-03-21 验证记录

- 单测命令：`.\.venv\Scripts\python -m pytest -q tests/unit/test_generate_workflow.py tests/unit/test_dual_graph_engine.py tests/unit/test_plan_confirm_flow.py`
- 单测结果：`9 passed`
- 静态检查命令：`.\.venv\Scripts\python -m ruff check writing_agent/capabilities writing_agent/workflows tests/unit/test_generate_workflow.py`
- 静态检查结果：通过

### 2026-03-21 范围结论

- 本阶段未修改 `state_engine` 的运行时职责。
- 本阶段未切换 LangGraph 为默认后端。
- 本阶段完成的是“先正交拆层，再保留现有 backend 切换机制”的第一刀，为后续继续迁移 revise / stream / inline edit workflow 提供骨架。

## 第二阶段目标

在第一阶段完成 `graph_runner -> workflows/capabilities` 解耦后，继续向服务层推进：

1. 将 `GenerationService._run_graph_with_fallback` 的主流程下沉到 `workflows`。
2. 让 `generation_service` 仅保留参数整理与委托，不再承载 route-graph / legacy graph / single-pass fallback 的主编排逻辑。
3. 保持现有路由开关、指标记录、语义失败不降级等行为不变。

## 第二阶段严格执行步骤

- [x] Phase2-Step 1：在本文档登记第二阶段目标与范围
- [x] Phase2-Step 2：新增服务层生成工作流 facade
- [x] Phase2-Step 3：将 `generation_service._run_graph_with_fallback` 改为委托 workflow
- [x] Phase2-Step 4：补充 workflow 直接单测
- [x] Phase2-Step 5：运行 route-graph / semantic-failover 回归测试
- [x] Phase2-Step 6：回填第二阶段执行记录

## 第二阶段完成判定

以下条件全部满足才算完成：

1. `GenerationService._run_graph_with_fallback` 变成薄委托层。
2. route-graph 开关、legacy graph、single-pass fallback 行为保持不变。
3. route-graph 指标记录仍然完整。
4. semantic failure 不会触发 single-pass fallback 的行为保持不变。
5. 第二阶段执行记录完成回填。

## 第二阶段执行记录

### 2026-03-21 第二阶段计划

- 状态：进行中
- 说明：将服务层生成主流程从 `generation_service` 下沉到 `workflows` facade。

### 2026-03-21 第二阶段执行结果

- 状态：完成
- 说明：已将 `GenerationService` 中的 graph + fallback 主流程下沉到 `workflows` facade，服务层改为薄委托。

### 2026-03-21 第二阶段代码落地记录

- 新增 `writing_agent/workflows/generate_request_workflow.py`：承接 `route_graph / legacy_graph / single_pass fallback` 主流程。
- 更新 `writing_agent/workflows/__init__.py`：导出第二阶段 facade。
- 更新 `writing_agent/web/services/generation_service.py`：`_run_graph_with_fallback` 改为构造请求并委托 workflow。
- 新增 `tests/unit/test_generate_request_workflow.py`：直接覆盖 route-graph 成功路径与 semantic failure 不降级路径。

### 2026-03-21 第二阶段验证记录

- 静态检查命令：`.\.venv\Scripts\python -m ruff check writing_agent/workflows/generate_request_workflow.py writing_agent/web/services/generation_service.py tests/unit/test_generate_request_workflow.py tests/unit/test_generation_semantic_failover.py`
- 静态检查结果：通过
- 回归命令：`.\.venv\Scripts\python -m pytest -q tests/unit/test_generate_request_workflow.py tests/unit/test_generation_semantic_failover.py tests/test_generation_route_graph.py tests/unit/test_generate_workflow.py tests/unit/test_dual_graph_engine.py tests/unit/test_plan_confirm_flow.py`
- 回归结果：`24 passed`

### 2026-03-21 第二阶段范围结论

- 第二阶段已将服务层生成主流程向 `workflows` 下沉一步。
- route-graph 指标记录、legacy graph 路径、fallback 语义、semantic failure 不降级语义均保持不变。
- 本阶段仍未切换 LangGraph 为默认后端；该事项保留到后续阶段。

## 第三阶段目标

继续向服务辅助层推进，将 `generate_section` 的 route-graph / legacy graph 分流也下沉到 `workflows`：

1. 新增 section 生成 workflow facade。
2. 让 `generation_service_runtime.run_section_generation_request` 只保留请求校验、文档落盘与委托。
3. 保持 section 生成现有 route-graph 开关与输出语义不变。

## 第三阶段严格执行步骤

- [x] Phase3-Step 1：在本文档登记第三阶段目标与范围
- [x] Phase3-Step 2：新增 section 生成 workflow facade
- [x] Phase3-Step 3：将 `run_section_generation_request` 改为委托 workflow
- [x] Phase3-Step 4：补充 section workflow 直接单测
- [x] Phase3-Step 5：运行 section route-graph 回归测试
- [x] Phase3-Step 6：回填第三阶段执行记录

## 第三阶段完成判定

以下条件全部满足才算完成：

1. `run_section_generation_request` 变成薄委托层。
2. `generate_section` 的 route-graph / legacy graph 语义保持不变。
3. 现有 `tests/test_generation_route_graph.py` 中 section 相关用例继续通过。
4. 第三阶段执行记录完成回填。

## 第三阶段执行记录

### 2026-03-21 第三阶段计划

- 状态：进行中
- 说明：将 section 生成的 route-graph / legacy graph 分流下沉到 workflow facade。

### 2026-03-21 第三阶段执行结果

- 状态：完成
- 说明：已将 section 生成的 route-graph / legacy graph 分流下沉到 workflow facade，service runtime 改为薄委托。

### 2026-03-21 第三阶段代码落地记录

- 新增 `writing_agent/workflows/generate_section_request_workflow.py`：承接 section 生成的 route-graph / legacy graph 分流。
- 更新 `writing_agent/workflows/__init__.py`：导出第三阶段 facade。
- 更新 `writing_agent/web/services/generation_service_runtime.py`：`run_section_generation_request` 改为构造请求并委托 workflow。
- 新增 `tests/unit/test_generate_section_request_workflow.py`：直接覆盖 section route-graph 与 legacy graph 两条路径。

### 2026-03-21 第三阶段验证记录

- 静态检查命令：`.\.venv\Scripts\python -m ruff check writing_agent/workflows/generate_section_request_workflow.py writing_agent/web/services/generation_service_runtime.py tests/unit/test_generate_section_request_workflow.py`
- 静态检查结果：通过
- 回归命令：`.\.venv\Scripts\python -m pytest -q tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- 回归结果：`14 passed`
- 组合回归命令：`.\.venv\Scripts\python -m pytest -q tests/unit/test_generate_workflow.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/unit/test_generation_semantic_failover.py tests/unit/test_dual_graph_engine.py tests/unit/test_plan_confirm_flow.py tests/test_generation_route_graph.py`
- 组合回归结果：`26 passed`

### 2026-03-21 第三阶段范围结论

- 第三阶段已将 section 生成的主分流逻辑向 `workflows` 下沉一步。
- section 生成的 route-graph 开关与 legacy graph 语义保持不变。
- 后续若继续推进，最自然的下一阶段是流式生成路径 `app_v2_generate_stream_runtime.py` 的同类下沉。

## 第四阶段目标

继续推进到流式生成路径，将 `app_v2_generate_stream_runtime.py` 中的 route-graph / legacy graph / single-pass stream fallback 主流程下沉到 `workflows`：

1. 新增流式生成 workflow facade。
2. 让 `app_v2_generate_stream_runtime.py` 中的主图执行逻辑改为委托 workflow。
3. 保持流式 route-graph、semantic failure 不降级、single-pass stream fallback 的现有行为不变。

## 第四阶段严格执行步骤

- [x] Phase4-Step 1：在本文档登记第四阶段目标与范围
- [x] Phase4-Step 2：新增流式生成 workflow facade
- [x] Phase4-Step 3：将流式生成主图执行逻辑改为委托 workflow
- [x] Phase4-Step 4：补充 workflow 直接单测
- [x] Phase4-Step 5：运行 stream route-graph 回归测试
- [x] Phase4-Step 6：回填第四阶段执行记录

## 第四阶段完成判定

以下条件全部满足才算完成：

1. `app_v2_generate_stream_runtime.py` 中 route-graph / legacy / fallback 主流程被下沉到 workflow facade。
2. 流式 route-graph 成功、semantic failure 不降级、single-pass stream fallback 回退路径保持不变。
3. `tests/test_generation_route_graph.py` 中 stream 相关用例继续通过。
4. 第四阶段执行记录完成回填。

## 第四阶段执行记录

### 2026-03-21 第四阶段计划

- 状态：进行中
- 说明：将流式生成主图执行逻辑下沉到 workflow facade。

### 2026-03-21 第四阶段执行结果

- 状态：完成
- 说明：已将流式生成的 route-graph / legacy graph / single-pass stream fallback 主流程下沉到 workflow facade。

### 2026-03-21 第四阶段代码落地记录

- 新增 `writing_agent/workflows/generate_stream_request_workflow.py`：承接流式生成的 route-graph / legacy graph / single-pass stream fallback 主流程。
- 更新 `writing_agent/workflows/__init__.py`：导出第四阶段 facade。
- 更新 `writing_agent/web/app_v2_generate_stream_runtime.py`：将流式主图执行逻辑改为委托 workflow，并保留 trace / metric / persistence 语义。
- 新增 `tests/unit/test_generate_stream_request_workflow.py`：直接覆盖流式 route-graph 成功与 semantic failure 不降级路径。

### 2026-03-21 第四阶段验证记录

- 静态检查命令：`.\.venv\Scripts\python -m ruff check writing_agent/workflows/generate_stream_request_workflow.py tests/unit/test_generate_stream_request_workflow.py`
- 静态检查结果：通过
- stream 回归命令：`.\.venv\Scripts\python -m pytest -q tests/unit/test_generate_stream_request_workflow.py tests/test_generation_route_graph.py`
- stream 回归结果：`14 passed`
- 组合回归命令：`.\.venv\Scripts\python -m pytest -q tests/unit/test_generate_workflow.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generation_semantic_failover.py tests/unit/test_dual_graph_engine.py tests/unit/test_plan_confirm_flow.py tests/test_generation_route_graph.py`
- 组合回归结果：`28 passed`

### 2026-03-21 第四阶段范围结论

- 第四阶段已将流式生成主图执行逻辑向 `workflows` 下沉一步。
- 流式 route-graph 成功、semantic failure 不降级、single-pass stream fallback 语义保持不变。
- 继续推进时，下一自然阶段是“在 native fallback 保底下，将默认 graph backend 从 `native` 过渡到 `auto`”。

## 第五阶段目标

在保留 native fallback 保底的前提下，开始逐步让 LangGraph 成为默认后端：

1. 为默认 backend 切换补充安全测试。
2. 将 `should_use_langgraph()` 的默认值从 `native` 调整为 `auto`。
3. 保持在未安装 LangGraph 或 LangGraph 执行失败时自动回退 native。

## 第五阶段严格执行步骤

- [x] Phase5-Step 1：在本文档登记第五阶段目标与范围
- [x] Phase5-Step 2：补充默认 backend 切换的安全测试
- [x] Phase5-Step 3：将默认 graph backend 从 `native` 调整为 `auto`
- [x] Phase5-Step 4：更新相关文档说明
- [x] Phase5-Step 5：运行 backend 回归测试
- [x] Phase5-Step 6：回填第五阶段执行记录

## 第五阶段完成判定

以下条件全部满足才算完成：

1. `should_use_langgraph()` 在未设置环境变量时默认返回 `True`。
2. 显式设置 `WRITING_AGENT_GRAPH_ENGINE=native` 时仍能关闭 LangGraph。
3. LangGraph 执行失败时仍会自动回退 native。
4. 第五阶段执行记录完成回填。

## 第五阶段执行记录

### 2026-03-21 第五阶段计划

- 状态：进行中
- 说明：在保留 native fallback 的前提下，将默认 graph backend 从 `native` 过渡到 `auto`。

### 2026-03-21 第五阶段执行结果

- 状态：完成
- 说明：已在保留 native fallback 的前提下，将默认 graph backend 从 `native` 过渡到 `auto`。

### 2026-03-21 第五阶段代码落地记录

- 更新 `writing_agent/state_engine/dual_engine.py`：`should_use_langgraph()` 默认环境值从 `native` 调整为 `auto`。
- 更新 `docs/GRAPH_DUAL_ENGINE.md`：补充默认 `auto` 且 native fallback 的说明。
- 更新 `tests/unit/test_dual_graph_engine.py`：新增默认 backend、显式 native、langgraph 失败回退 native 的安全测试。

### 2026-03-21 第五阶段验证记录

- 静态检查命令：`.\.venv\Scripts\python -m ruff check writing_agent/state_engine/dual_engine.py tests/unit/test_dual_graph_engine.py`
- 静态检查结果：通过
- 回归命令：`.\.venv\Scripts\python -m pytest -q tests/unit/test_dual_graph_engine.py tests/unit/test_generate_workflow.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generation_semantic_failover.py tests/unit/test_plan_confirm_flow.py tests/test_generation_route_graph.py`
- 回归结果：`31 passed`

### 2026-03-21 第五阶段范围结论

- 默认 graph backend 已从 `native` 过渡到 `auto`。
- 在未安装 LangGraph 或 LangGraph 执行失败时，仍会自动回退 native。
- 显式设置 `WRITING_AGENT_GRAPH_ENGINE=native` 时，仍可完全关闭 LangGraph。

## 第六阶段目标

继续把修订链路纳入 `workflows`：

1. 新增 `revise_doc` workflow facade。
2. 让 `run_revision_request` 变成薄委托层。
3. 保持 selected revision、unscoped fallback、hard gate reject 的现有行为不变。

## 第六阶段严格执行步骤

- [x] Phase6-Step 1：在本文档登记第六阶段目标与范围
- [x] Phase6-Step 2：新增修订 workflow facade
- [x] Phase6-Step 3：将 `run_revision_request` 改为委托 workflow
- [x] Phase6-Step 4：补充 workflow 直接单测
- [x] Phase6-Step 5：运行 revise 相关回归测试
- [x] Phase6-Step 6：回填第六阶段执行记录

## 第六阶段完成判定

以下条件全部满足才算完成：

1. `run_revision_request` 变成薄委托层。
2. selected revision 成功路径保持不变。
3. unscoped fallback 与 hard gate reject 路径保持不变。
4. 第六阶段执行记录完成回填。

## 第六阶段执行记录

### 2026-03-21 第六阶段计划

- 状态：进行中
- 说明：将修订主流程从 `generation_service_runtime` 下沉到 workflow facade。

### 2026-03-21 第六阶段执行结果

- 状态：完成
- 说明：已将 `revise_doc` 主流程下沉到 workflow facade，`run_revision_request` 改为薄委托。

### 2026-03-21 第六阶段代码落地记录

- 新增 `writing_agent/workflows/revision_request_workflow.py`：承接 selected revision、unscoped fallback、hard gate reject 主流程。
- 更新 `writing_agent/workflows/__init__.py`：导出第六阶段 facade。
- 更新 `writing_agent/web/services/generation_service_runtime.py`：`run_revision_request` 改为构造请求并委托 workflow。
- 新增 `tests/unit/test_revision_request_workflow.py`：直接覆盖 selected revision 成功和 hard gate reject 两条关键路径。

### 2026-03-21 第六阶段验证记录

- 静态检查命令：`.\.venv\Scripts\python -m ruff check writing_agent/workflows/revision_request_workflow.py writing_agent/web/services/generation_service_runtime.py tests/unit/test_revision_request_workflow.py tests/test_revise_doc_constraints.py`
- 静态检查结果：通过
- revise 回归命令：`.\.venv\Scripts\python -m pytest -q tests/unit/test_revision_request_workflow.py tests/test_revise_doc_constraints.py`
- revise 回归结果：`8 passed`
- 组合回归命令：`.\.venv\Scripts\python -m pytest -q tests/unit/test_dual_graph_engine.py tests/unit/test_generate_workflow.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_revision_request_workflow.py tests/unit/test_generation_semantic_failover.py tests/unit/test_plan_confirm_flow.py tests/test_generation_route_graph.py tests/test_revise_doc_constraints.py`
- 组合回归结果：`39 passed`

### 2026-03-21 第六阶段范围结论

- 第六阶段已将修订主流程向 `workflows` 下沉一步。
- selected revision、unscoped fallback、hard gate reject 语义保持不变。
- 继续推进时，下一自然阶段是将 `inline edit` / `editing_flow` 按相同模式迁到 `workflows/capabilities`。

## 第七阶段目标

继续把编辑链路纳入 `workflows/capabilities`：

1. 新增 `inline-ai` / `inline-ai/stream` workflow facade。
2. 引入 editing capability，承接 inline 参数归一化、context trim 后上下文装配与 block preview 变体组装。
3. 让 `writing_agent/web/api/editing_flow.py` 中的 inline / block edit 入口变成薄委托层。
4. 保持 `inline-ai`、`inline-ai/stream`、`block-edit`、`block-edit/preview` 既有语义不变。

## 第七阶段严格执行步骤

- [x] Phase7-Step 1：在本文档登记第七阶段目标与范围
- [x] Phase7-Step 2：新增 editing capability 与 workflow facade
- [x] Phase7-Step 3：将 `editing_flow.py` 中 inline / block edit 入口改为委托 workflow
- [x] Phase7-Step 4：补充 workflow 直接单测
- [x] Phase7-Step 5：运行编辑链路相关回归测试
- [x] Phase7-Step 6：回填第七阶段执行记录

## 第七阶段完成判定

以下条件全部满足才算完成：

1. `editing_flow.py` 中的 `inline-ai`、`inline-ai/stream`、`block-edit`、`block-edit/preview` 入口变成薄委托层。
2. inline context trim、stream `context_meta` 先于 token 事件、block preview 候选与错误回填语义保持不变。
3. 新增 direct workflow 单测覆盖关键路径。
4. 第七阶段执行记录完成回填。

## 第七阶段执行记录

### 2026-03-21 第七阶段计划

- 状态：进行中
- 说明：将 `inline-ai` / `block-edit` 主流程从 `editing_flow` 下沉到 `workflows/capabilities`。

### 2026-03-21 第七阶段执行结果

- 状态：完成
- 说明：已将 `inline-ai` / `inline-ai/stream` / `block-edit` / `block-edit/preview` 主流程下沉到 `workflows/capabilities`，`editing_flow.py` 改为薄委托。

### 2026-03-21 第七阶段代码落地记录

- 新增 `writing_agent/capabilities/editing.py`：承接 inline 参数归一化、tone 参数装配、block preview 变体组装与 DocIR 克隆辅助。
- 新增 `writing_agent/workflows/editing_request_workflow.py`：承接 `inline-ai` / `inline-ai/stream` / `block-edit` / `block-edit/preview` 主流程。
- 更新 `writing_agent/workflows/__init__.py`：导出第七阶段 facade。
- 更新 `writing_agent/web/api/editing_flow.py`：将 inline / block edit 入口改为构造请求并委托 workflow。
- 新增 `tests/unit/test_editing_request_workflow.py`：直接覆盖 inline context 装配、stream `context_meta` 顺序、block edit 更新提交与 preview 候选/错误回填。

### 2026-03-21 第七阶段验证记录

- 静态检查命令：`.\.venv\Scripts\python -m ruff check writing_agent/capabilities/editing.py writing_agent/workflows/editing_request_workflow.py writing_agent/workflows/__init__.py writing_agent/web/api/editing_flow.py tests/unit/test_editing_request_workflow.py`
- 静态检查结果：通过
- 编辑链路回归命令：`.\.venv\Scripts\python -m pytest -q tests/unit/test_editing_request_workflow.py tests/unit/test_inline_context_policy.py tests/test_inline_ai_stream_context_meta.py tests/test_flow_router_registration.py`
- 编辑链路回归结果：`8 passed`
- 组合回归命令：`.\.venv\Scripts\python -m pytest -q tests/unit/test_dual_graph_engine.py tests/unit/test_generate_workflow.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_revision_request_workflow.py tests/unit/test_editing_request_workflow.py tests/unit/test_generation_semantic_failover.py tests/unit/test_plan_confirm_flow.py tests/unit/test_inline_context_policy.py tests/test_generation_route_graph.py tests/test_revise_doc_constraints.py tests/test_inline_ai_stream_context_meta.py tests/test_flow_router_registration.py`
- 组合回归结果：`47 passed`

### 2026-03-21 第七阶段范围结论

- 第七阶段已将编辑主流程向 `workflows/capabilities` 下沉一步。
- inline context trim、stream `context_meta` 发射顺序、block edit preview 候选/错误回填语义保持不变。
- 继续推进时，下一自然阶段是将 `editing_flow` 中剩余的 `doc_ir_ops` / `doc_ir_diff` / `render_figure` / `diagram_generate` 入口也改为薄委托。

## 第八阶段目标

完成 `editing_flow` 剩余入口的 workflow 下沉，形成整块薄路由：

1. 新增 `doc_ir_ops` / `doc_ir_diff` workflow facade。
2. 新增 `render_figure` / `diagram_generate` workflow facade。
3. 让 `writing_agent/web/api/editing_flow.py` 的剩余入口也变成薄委托层。
4. 保持图示生成约束、渲染安全与 doc_ir 变换语义不变。

## 第八阶段严格执行步骤

- [x] Phase8-Step 1：在本文档登记第八阶段目标与范围
- [x] Phase8-Step 2：扩展 editing workflow facade 覆盖剩余入口
- [x] Phase8-Step 3：将 `editing_flow.py` 中剩余入口改为委托 workflow
- [x] Phase8-Step 4：补充 workflow 直接单测
- [x] Phase8-Step 5：运行 diagram / editing 相关回归测试
- [x] Phase8-Step 6：回填第八阶段执行记录

## 第八阶段完成判定

以下条件全部满足才算完成：

1. `editing_flow.py` 中的 `doc_ir_ops`、`doc_ir_diff`、`render_figure`、`diagram_generate` 入口变成薄委托层。
2. 图示生成的 prompt 约束与 fallback 语义保持不变。
3. `render_figure` 的 SVG 安全清洗语义与 `doc_ir` 变换语义保持不变。
4. 第八阶段执行记录完成回填。

## 第八阶段执行记录

### 2026-03-21 第八阶段计划

- 状态：进行中
- 说明：完成 `editing_flow` 剩余入口的 workflow 下沉，使整个编辑 API 模块收敛为薄路由层。

### 2026-03-21 第八阶段执行结果

- 状态：完成
- 说明：已将 `doc_ir_ops` / `doc_ir_diff` / `render_figure` / `diagram_generate` 主流程下沉到 workflow facade，`editing_flow.py` 形成整块薄委托层。

### 2026-03-21 第八阶段代码落地记录

- 更新 `writing_agent/workflows/editing_request_workflow.py`：新增 `DocIRRequest`、`RenderFigureRequest`、`DiagramGenerateRequest` 及对应 facade。
- 更新 `writing_agent/workflows/__init__.py`：导出第八阶段 facade。
- 更新 `writing_agent/web/api/editing_flow.py`：将 `doc_ir_ops` / `doc_ir_diff` / `render_figure` / `diagram_generate` 改为构造请求并委托 workflow。
- 更新 `tests/unit/test_editing_request_workflow.py`：新增 doc_ir ops、doc_ir diff、render figure、diagram generate 直接单测。

### 2026-03-21 第八阶段验证记录

- 静态检查命令：`.\.venv\Scripts\python -m ruff check writing_agent/workflows/editing_request_workflow.py writing_agent/workflows/__init__.py writing_agent/web/api/editing_flow.py tests/unit/test_editing_request_workflow.py`
- 静态检查结果：通过
- diagram / editing 回归命令：`.\.venv\Scripts\python -m pytest -q tests/unit/test_editing_request_workflow.py tests/unit/test_inline_context_policy.py tests/test_inline_ai_stream_context_meta.py tests/test_diagram_generate_constraints.py tests/test_flow_router_registration.py`
- diagram / editing 回归结果：`15 passed`
- 组合回归命令：`.\.venv\Scripts\python -m pytest -q tests/unit/test_dual_graph_engine.py tests/unit/test_generate_workflow.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_revision_request_workflow.py tests/unit/test_editing_request_workflow.py tests/unit/test_generation_semantic_failover.py tests/unit/test_plan_confirm_flow.py tests/unit/test_inline_context_policy.py tests/test_generation_route_graph.py tests/test_revise_doc_constraints.py tests/test_inline_ai_stream_context_meta.py tests/test_diagram_generate_constraints.py tests/test_flow_router_registration.py`
- 组合回归结果：`54 passed`

### 2026-03-21 第八阶段范围结论

- 第八阶段已将 `editing_flow` 剩余入口全部改为 workflow 薄委托。
- `editing_flow.py` 现在只保留路由装配、上下文 trim / diagram helper 等局部辅助函数，不再内联主要业务执行流程。
- 当前执行台账中登记的第 1–8 阶段内容已全部完成。

## 后续演进清单

- [x] Phase9：将 inline context trim 与 block text helper 从 `editing_flow.py` 下沉到 `capabilities/editing.py`
- [x] Phase10：将 diagram spec 解析 / 约束 / fallback 逻辑从 `editing_flow.py` 下沉到 `capabilities/diagramming.py`

## 第九阶段目标

继续压缩 `editing_flow.py` 的本地业务辅助：

1. 将 inline context trim 逻辑下沉到 `capabilities/editing.py`。
2. 删除 `editing_flow.py` 中已不再需要的 block text helper 重复实现。
3. 保持 `tests/unit/test_inline_context_policy.py` 的行为不变。

## 第九阶段严格执行步骤

- [x] Phase9-Step 1：在本文档登记第九阶段目标与范围
- [x] Phase9-Step 2：将 inline context trim 下沉到 editing capability
- [x] Phase9-Step 3：清理 `editing_flow.py` 中重复 helper
- [x] Phase9-Step 4：补充 / 复用直接单测验证 capability 语义
- [x] Phase9-Step 5：运行 inline context 相关回归测试
- [x] Phase9-Step 6：回填第九阶段执行记录

## 第十阶段目标

将 diagram 业务能力与 HTTP 路由彻底拆开：

1. 新增 `capabilities/diagramming.py` 承接 diagram spec 解析、规范化、LLM 约束提示与 fallback。
2. 让 `editing_flow.py` 不再内联 diagram spec 业务实现，只保留调用 capability 的薄适配。
3. 保持 diagram generate 相关测试语义不变。

## 第十阶段严格执行步骤

- [x] Phase10-Step 1：在本文档登记第十阶段目标与范围
- [x] Phase10-Step 2：新增 diagramming capability 并迁移 diagram 业务逻辑
- [x] Phase10-Step 3：将 `editing_flow.py` 中 diagram helper 改为薄适配或直接委托
- [x] Phase10-Step 4：补充 capability 直接单测
- [x] Phase10-Step 5：运行 diagram / editing 相关回归测试
- [x] Phase10-Step 6：回填第十阶段执行记录

## 第九阶段完成判定

以下条件全部满足才算完成：

1. `editing_flow.py` 中的 inline context trim 实现下沉到 `capabilities/editing.py`。
2. `editing_flow.py` 中重复的 block text helper 被移除。
3. `tests/unit/test_inline_context_policy.py` 语义保持不变。
4. 第九阶段执行记录完成回填。

## 第九阶段执行记录

### 2026-03-21 第九阶段计划

- 状态：进行中
- 说明：继续压缩 `editing_flow.py` 的局部业务辅助，将 inline context trim 与遗留重复 helper 下沉到 capability 层。

### 2026-03-21 第九阶段执行结果

- 状态：完成
- 说明：已将 inline context trim 逻辑下沉到 `capabilities/editing.py`，并移除 `editing_flow.py` 中重复的 block text helper。

### 2026-03-21 第九阶段代码落地记录

- 更新 `writing_agent/capabilities/editing.py`：新增 `trim_inline_context`，承接 inline context window / budget trim 逻辑。
- 更新 `writing_agent/web/api/editing_flow.py`：`_trim_inline_context` 改为薄包装；删除重复的 `_extract_block_text_from_ir`。
- 新增 `tests/unit/test_editing_capability.py`：直接覆盖 trim window / budget 与自定义窗口边界语义。

### 2026-03-21 第九阶段验证记录

- 静态检查命令：`.\.venv\Scripts\python -m ruff check writing_agent/capabilities/editing.py writing_agent/web/api/editing_flow.py tests/unit/test_editing_capability.py tests/unit/test_inline_context_policy.py`
- 静态检查结果：通过
- inline context 回归命令：`.\.venv\Scripts\python -m pytest -q tests/unit/test_editing_capability.py tests/unit/test_inline_context_policy.py tests/unit/test_editing_request_workflow.py tests/test_inline_ai_stream_context_meta.py tests/test_flow_router_registration.py`
- inline context 回归结果：`12 passed`

### 2026-03-21 第九阶段范围结论

- 第九阶段进一步压缩了 `editing_flow.py` 的本地业务实现。
- inline context trim 语义与既有测试保持一致。
- 下一自然阶段是将 diagram spec 解析 / 约束 / fallback 逻辑整体迁出路由文件。

## 第十阶段完成判定

以下条件全部满足才算完成：

1. `capabilities/diagramming.py` 承接 diagram spec 解析、规范化、LLM 约束提示与 fallback。
2. `editing_flow.py` 不再内联 diagram 业务实现，只保留薄适配。
3. diagram generate 相关测试语义保持不变。
4. 第十阶段执行记录完成回填。

## 第十阶段执行记录

### 2026-03-21 第十阶段计划

- 状态：进行中
- 说明：将 diagram 业务能力从 `editing_flow.py` 整块迁移到 capability 层，并保持路由层继续薄化。

### 2026-03-21 第十阶段执行结果

- 状态：完成
- 说明：已新增 `capabilities/diagramming.py` 承接 diagram spec 解析 / 约束 / fallback 逻辑，`editing_flow.py` 改为 capability 薄适配。

### 2026-03-21 第十阶段代码落地记录

- 新增 `writing_agent/capabilities/diagramming.py`：承接 JSON 提取、diagram kind 规范化、spec payload 规范化、LLM 约束提示、semantic fallback 与 prompt builder。
- 更新 `writing_agent/capabilities/__init__.py`：导出 `trim_inline_context` 与 diagramming 能力入口。
- 更新 `writing_agent/web/api/editing_flow.py`：删除内联 diagram helper，仅保留 `_diagram_spec_from_prompt` 薄适配。
- 新增 `tests/unit/test_diagramming_capability.py`：直接覆盖 tagged prompt escape 与 semantic fallback 两条关键能力路径。

### 2026-03-21 第十阶段验证记录

- 静态检查命令：`.\.venv\Scripts\python -m ruff check writing_agent/capabilities/__init__.py writing_agent/capabilities/diagramming.py writing_agent/web/api/editing_flow.py tests/unit/test_diagramming_capability.py`
- 静态检查结果：通过
- diagram / editing 回归命令：`.\.venv\Scripts\python -m pytest -q tests/unit/test_editing_capability.py tests/unit/test_inline_context_policy.py tests/unit/test_diagramming_capability.py tests/test_diagram_generate_constraints.py tests/unit/test_editing_request_workflow.py tests/test_inline_ai_stream_context_meta.py tests/test_flow_router_registration.py`
- diagram / editing 回归结果：`19 passed`
- 组合回归命令：`.\.venv\Scripts\python -m pytest -q tests/unit/test_dual_graph_engine.py tests/unit/test_generate_workflow.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_revision_request_workflow.py tests/unit/test_editing_request_workflow.py tests/unit/test_editing_capability.py tests/unit/test_diagramming_capability.py tests/unit/test_generation_semantic_failover.py tests/unit/test_plan_confirm_flow.py tests/unit/test_inline_context_policy.py tests/test_generation_route_graph.py tests/test_revise_doc_constraints.py tests/test_inline_ai_stream_context_meta.py tests/test_diagram_generate_constraints.py tests/test_flow_router_registration.py`
- 组合回归结果：`58 passed`

### 2026-03-21 第十阶段范围结论

- 第十阶段已将 diagram 业务能力完整迁出路由文件。
- `editing_flow.py` 当前只保留路由装配、轻量包装与 capability / workflow 委托。
- 当前这份台账中登记的后续演进清单已全部执行完成。

## 第二批后续演进清单

- [x] Phase11：将 fallback prompt / single-pass generate 逻辑从 `app_v2_generation_helpers_runtime.py` 下沉到 `capabilities/fallback_generation.py`
- [x] Phase12：将生成质量检查 / prompt echo 判定从 `app_v2_generation_helpers_runtime.py` 下沉到 `capabilities/generation_quality.py`

## 第十一阶段目标

继续压缩生成 helper runtime 中的业务能力泄漏：

1. 将 fallback prompt 组装与 single-pass generate / stream / heartbeat 主逻辑下沉到 capability 层。
2. 保持 `app_v2._build_fallback_prompt`、`app_v2._single_pass_generate`、`app_v2._single_pass_generate_stream` 对外签名不变。
3. 保持 node backend 与 route graph fallback 相关测试语义不变。

## 第十一阶段严格执行步骤

- [x] Phase11-Step 1：在本文档登记第十一阶段目标与范围
- [x] Phase11-Step 2：新增 fallback generation capability
- [x] Phase11-Step 3：将 helper runtime 中 fallback 生成入口改为薄包装
- [x] Phase11-Step 4：补充 capability 直接单测
- [x] Phase11-Step 5：运行 fallback / route graph / node backend 回归测试
- [x] Phase11-Step 6：回填第十一阶段执行记录

## 第十一阶段完成判定

以下条件全部满足才算完成：

1. `capabilities/fallback_generation.py` 承接 fallback prompt 与 single-pass generate 逻辑。
2. `app_v2_generation_helpers_runtime.py` 中相关入口变成薄包装。
3. `tests/test_generation_fallback_prompt_constraints.py` 与 node backend 回归语义保持不变。
4. 第十一阶段执行记录完成回填。

## 第十一阶段执行记录

### 2026-03-21 第十一阶段计划

- 状态：进行中
- 说明：将 fallback prompt / single-pass generate 主逻辑从 runtime helper 下沉到 capability 层，并保留 `app_v2` 旧函数名。

### 2026-03-21 第十一阶段执行结果

- 状态：完成
- 说明：已新增 `capabilities/fallback_generation.py` 承接 fallback prompt、single-pass generate、heartbeat 与 stream 逻辑，`app_v2_generation_helpers_runtime.py` 改为薄包装。

### 2026-03-21 第十一阶段代码落地记录

- 新增 `writing_agent/capabilities/fallback_generation.py`：承接 fallback prompt section 提取、tagged prompt 组装、length control、single-pass generate / heartbeat / stream 主逻辑。
- 更新 `writing_agent/web/app_v2_generation_helpers_runtime.py`：`_default_outline_from_instruction`、`_fallback_prompt_sections`、`_build_fallback_prompt`、`_single_pass_generate`、`_single_pass_generate_with_heartbeat`、`_single_pass_generate_stream` 改为薄包装。
- 更新 `writing_agent/capabilities/__init__.py`：导出 fallback generation 能力入口。
- 新增 `tests/unit/test_fallback_generation_capability.py`：直接覆盖 tagged fallback prompt 与 length control / sanitize 语义。

### 2026-03-21 第十一阶段验证记录

- 静态检查命令：`.\.venv\Scripts\python -m ruff check writing_agent/capabilities/__init__.py writing_agent/capabilities/fallback_generation.py tests/unit/test_fallback_generation_capability.py`
- 静态检查结果：通过
- fallback / route graph / node backend 回归命令：`.\.venv\Scripts\python -m pytest -q tests/unit/test_fallback_generation_capability.py tests/test_generation_fallback_prompt_constraints.py tests/integration/test_node_backend_generation_path.py tests/test_generation_route_graph.py`
- fallback / route graph / node backend 回归结果：`19 passed`

### 2026-03-21 第十一阶段范围结论

- 第十一阶段已将 fallback 生成能力整体迁出 helper runtime。
- `app_v2` 旧导出函数名保持不变，route graph fallback 与 node backend 语义保持稳定。
- 下一自然阶段是将生成质量检查与 prompt echo 判定也迁出 helper runtime。

## 第十二阶段目标

完成生成 helper runtime 中质量判定能力的拆分：

1. 新增 `capabilities/generation_quality.py` 承接生成质量检查与 prompt echo 判定。
2. 让 `app_v2_generation_helpers_runtime.py` 中 `_check_generation_quality` / `_looks_like_prompt_echo` 改为薄包装。
3. 保持 revise / route graph / fallback 相关语义不变。

## 第十二阶段严格执行步骤

- [x] Phase12-Step 1：在本文档登记第十二阶段目标与范围
- [x] Phase12-Step 2：新增 generation quality capability
- [x] Phase12-Step 3：将 helper runtime 中质量判定入口改为薄包装
- [x] Phase12-Step 4：补充 capability 直接单测
- [x] Phase12-Step 5：运行生成质量相关回归测试
- [x] Phase12-Step 6：回填第十二阶段执行记录

## 第十二阶段完成判定

以下条件全部满足才算完成：

1. `capabilities/generation_quality.py` 承接质量检查与 prompt echo 判定逻辑。
2. `app_v2_generation_helpers_runtime.py` 中对应入口变成薄包装。
3. revise / route graph / fallback 相关测试语义保持不变。
4. 第十二阶段执行记录完成回填。

## 第十二阶段执行记录

### 2026-03-21 第十二阶段计划

- 状态：进行中
- 说明：将生成质量检查与 prompt echo 判定从 helper runtime 下沉到 capability 层，进一步压缩运行时文件中的业务实现。

### 2026-03-21 第十二阶段执行结果

- 状态：完成
- 说明：已新增 `capabilities/generation_quality.py` 承接质量检查与 prompt echo 判定，`app_v2_generation_helpers_runtime.py` 改为薄包装。

### 2026-03-21 第十二阶段代码落地记录

- 新增 `writing_agent/capabilities/generation_quality.py`：承接生成质量检查与 prompt echo 判定逻辑。
- 更新 `writing_agent/web/app_v2_generation_helpers_runtime.py`：`_check_generation_quality` 与 `_looks_like_prompt_echo` 改为薄包装。
- 更新 `writing_agent/capabilities/__init__.py`：导出 generation quality 能力入口。
- 新增 `tests/unit/test_generation_quality_capability.py`：直接覆盖 short / duplicate / heading 问题检测与 prompt echo 正反例。

### 2026-03-21 第十二阶段验证记录

- 静态检查命令：`.\.venv\Scripts\python -m ruff check writing_agent/capabilities/__init__.py writing_agent/capabilities/generation_quality.py tests/unit/test_generation_quality_capability.py`
- 静态检查结果：通过
- 生成质量相关回归命令：`.\.venv\Scripts\python -m pytest -q tests/unit/test_generation_quality_capability.py tests/unit/test_revision_request_workflow.py tests/test_generation_route_graph.py tests/test_generation_fallback_prompt_constraints.py`
- 生成质量相关回归结果：通过
- 组合回归命令：`.\.venv\Scripts\python -m pytest -q tests/unit/test_dual_graph_engine.py tests/unit/test_generate_workflow.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_revision_request_workflow.py tests/unit/test_editing_request_workflow.py tests/unit/test_editing_capability.py tests/unit/test_diagramming_capability.py tests/unit/test_fallback_generation_capability.py tests/unit/test_generation_quality_capability.py tests/unit/test_generation_semantic_failover.py tests/unit/test_plan_confirm_flow.py tests/unit/test_inline_context_policy.py tests/test_generation_route_graph.py tests/test_revise_doc_constraints.py tests/test_inline_ai_stream_context_meta.py tests/test_diagram_generate_constraints.py tests/test_generation_fallback_prompt_constraints.py tests/test_flow_router_registration.py tests/integration/test_node_backend_generation_path.py`
- 组合回归结果：`65 passed`

### 2026-03-21 第十二阶段范围结论

- 第十二阶段已将生成质量检查与 prompt echo 判定迁出 helper runtime。
- `app_v2_generation_helpers_runtime.py` 继续向“运行时装配 / 环境桥接”收敛。
- 当前这份台账中登记的第二批后续演进清单已全部执行完成。

## ?????

- [x] Phase50: introduce generate execution driver deps

## ???????

??????? generate workflow facade?? execution driver ?????????????? driver deps?

1. ? `generate_request_workflow.py` ?? workflow-level driver deps dataclass????? primary ???primary ???graph-failed failover ? finalized result ?????
2. ? `_execute_generate_workflow_driver` ??????? driver deps???????????????
3. ?? legacy / route-graph path?metric ???semantic failure ?? fallback ????????????

## ???????????

- [x] Phase50-Step 1: register Phase50 goal and scope in this ledger
- [x] Phase50-Step 2: add workflow-level generate execution driver deps dataclass
- [x] Phase50-Step 3: refactor non-stream generate entrypoint and driver to use the deps object
- [x] Phase50-Step 4: add focused coverage for injected route-graph deps recovery semantics
- [x] Phase50-Step 5: run generate workflow / route-graph regression tests
- [x] Phase50-Step 6: backfill Phase50 execution records

## ?????????

?????????????

1. `generate_request_workflow.py` ???? execution driver deps dataclass?
2. `_execute_generate_workflow_driver` ??????????????
3. legacy / route-graph path?metric ??? semantic failure ?? fallback ???????
4. ?? generate workflow ? route-graph ?????????
5. ??????????????

## ?????????

### 2026-03-23 ???????

- ??????
- ?????? non-stream generate workflow ? execution driver ???????????? driver deps ???

### 2026-03-23 ?????????

- ?????
- ?????? execution driver deps dataclass??? non-stream generate ? execution driver ???????? driver deps ?????

### 2026-03-23 ???????????

- ?? `writing_agent/workflows/generate_request_workflow.py`??? `GenerateExecutionDriverDeps`????? primary ???primary ???graph-failed failover ? finalized result ?????
- ?? `writing_agent/workflows/generate_request_workflow.py`?`_execute_generate_workflow_driver` ?????????????????????? driver deps ???
- ?? `tests/unit/test_generate_request_workflow.py`??? injected route-graph deps recovery ????? route-graph failure ? fallback ???path ? error-code ???????

### 2026-03-23 ?????????

- ruff command: `.\.venv\Scripts\python -m ruff check writing_agent/workflows/generate_request_workflow.py tests/unit/test_generate_request_workflow.py`
- ruff result: passed
- generate targeted tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_generate_request_workflow.py`
- generate targeted tests result: `11 passed`
- targeted workflow tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/unit/test_generate_stream_request_workflow.py`
- targeted workflow tests result: `62 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `74 passed`

### 2026-03-23 ?????????

- ??????? non-stream generate workflow ? execution driver ????????? driver deps ???
- `generate_request_workflow.py` ??? deps?runtime state?outcome carriers?execution driver ? driver deps ????????????????
- ??????????????

## ??????

- [x] Phase49: consolidate generate execution driver skeleton

## ????????

??????? generate workflow facade?? primary / failover / finalize ?????????????????

1. ? `generate_request_workflow.py` ?? workflow-level execution driver helper??? primary branch ???graph-failed fallback ??? finalized result ???
2. ????????? execution driver ??????????????????????????
3. ?? legacy / route-graph path?metric ???semantic failure ?? fallback ????????????

## ????????????

- [x] Phase49-Step 1: register Phase49 goal and scope in this ledger
- [x] Phase49-Step 2: add workflow-level generate execution driver helper
- [x] Phase49-Step 3: refactor non-stream generate entrypoint to delegate to the execution driver
- [x] Phase49-Step 4: add focused coverage for injected-deps legacy failure recovery semantics
- [x] Phase49-Step 5: run generate workflow / route-graph regression tests
- [x] Phase49-Step 6: backfill Phase49 execution records

## ??????????

?????????????

1. `generate_request_workflow.py` ???? execution driver helper?
2. ?????????? primary try/except ? finalized result ?????
3. legacy / route-graph path?metric ??? semantic failure ?? fallback ???????
4. ?? generate workflow ? route-graph ?????????
5. ???????????????

## ??????????

### 2026-03-23 ????????

- ??????
- ?????? non-stream generate workflow ? primary / failover / finalize ????????? execution driver ???

### 2026-03-23 ??????????

- ?????
- ?????? execution driver helper?? primary branch ???graph-failed fallback ??? finalized result ??????? workflow-level ??????

### 2026-03-23 ????????????

- ?? `writing_agent/workflows/generate_request_workflow.py`??? `GenerateExecutionResult` ? `_execute_generate_workflow_driver`????? primary / failover / finalize ?????
- ?? `writing_agent/workflows/generate_request_workflow.py`??? `run_generate_graph_with_fallback` ???????? primary try/except ? finalized result ????????? execution driver ????????
- ?? `tests/unit/test_generate_request_workflow.py`??? injected-deps legacy failure ??????? route graph ??? legacy failure ? fallback ???path ? error-code ???????

### 2026-03-23 ??????????

- ruff command: `.\.venv\Scripts\python -m ruff check writing_agent/workflows/generate_request_workflow.py tests/unit/test_generate_request_workflow.py`
- ruff result: passed
- generate targeted tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_generate_request_workflow.py`
- generate targeted tests result: `10 passed`
- targeted workflow tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/unit/test_generate_stream_request_workflow.py`
- targeted workflow tests result: `61 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `73 passed`

### 2026-03-23 ??????????

- ???????? non-stream generate workflow ? primary / failover / finalize ????????? execution driver ???
- `generate_request_workflow.py` ???????????????????????????????? workflow-level driver helper?
- ??????????????

## ??????

- [x] Phase48: introduce generate outcome carriers

## ????????

??????? generate workflow facade?? primary / metric / finalized ????? dict ??????????

1. ? `generate_request_workflow.py` ?? workflow-level dataclass????? primary branch outcome?metric plan ? finalized result?
2. ? primary-result ???metric ???????????????????????? key-string ???
3. ?? legacy / route-graph path?metric ???semantic failure ?? fallback ????????????

## ????????????

- [x] Phase48-Step 1: register Phase48 goal and scope in this ledger
- [x] Phase48-Step 2: add workflow-level generate outcome carrier dataclasses
- [x] Phase48-Step 3: refactor non-stream generate workflow helpers to use the outcome carriers
- [x] Phase48-Step 4: add focused coverage for legacy graph failure path semantics
- [x] Phase48-Step 5: run generate workflow / route-graph regression tests
- [x] Phase48-Step 6: backfill Phase48 execution records

## ??????????

?????????????

1. `generate_request_workflow.py` ???? primary outcome?metric plan ? finalized result dataclass?
2. primary result ???metric ???????????????? dict key?
3. legacy / route-graph path?metric ??? semantic failure ?? fallback ???????
4. ?? generate workflow ? route-graph ?????????
5. ???????????????

## ??????????

### 2026-03-23 ????????

- ??????
- ?????? non-stream generate workflow ?????????? helper ???????? dict ?????????????

### 2026-03-23 ??????????

- ?????
- ?????? `GenerateMetricPlan`?`GeneratePrimaryOutcome`?`GenerateFinalizedResult`??? primary-result ???metric ???????????????????????

### 2026-03-23 ????????????

- ?? `writing_agent/workflows/generate_request_workflow.py`??? `GenerateMetricPlan`?`GeneratePrimaryOutcome`?`GenerateFinalizedResult`??? primary / metric / finalized helper ???????????
- ?? `writing_agent/workflows/generate_request_workflow.py`?route-graph / legacy branch helper ?????? dict?primary-result apply ? finalize ?????????????
- ?? `tests/unit/test_generate_request_workflow.py`??? legacy graph failure path ????? legacy path ? `graph_failed` ? path ? error-code ???????

### 2026-03-23 ??????????

- ruff command: `.\.venv\Scripts\python -m ruff check writing_agent/workflows/generate_request_workflow.py tests/unit/test_generate_request_workflow.py`
- ruff result: passed
- generate targeted tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_generate_request_workflow.py`
- generate targeted tests result: `9 passed`
- targeted workflow tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/unit/test_generate_stream_request_workflow.py`
- targeted workflow tests result: `60 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `72 passed`

### 2026-03-23 ??????????

- ???????? non-stream generate workflow ???? primary / metric / finalized ???????????????
- `generate_request_workflow.py` ??????????metric plan ????????????????? stream workflow ???????
- ??????????????

## ??????

- [x] Phase47: consolidate generate metric and path helpers

## ????????

??????? generate workflow facade?? metric ??? graph path / error-code ????????? helper?

1. ? `generate_request_workflow.py` ?? workflow-level helper??? primary success metric?graph failure metric ? graph path ?????
2. ? `graph_failed` / `graph_insufficient` ???? path ? error-code ?????? helper ?????????? failover helper ????????
3. ?? metric ???legacy / route-graph path ???semantic failure ?? fallback ????????????

## ????????????

- [x] Phase47-Step 1: register Phase47 goal and scope in this ledger
- [x] Phase47-Step 2: add workflow-level metric / path planning helpers
- [x] Phase47-Step 3: refactor non-stream generate workflow execution to delegate metric planning to the helpers
- [x] Phase47-Step 4: add focused coverage for route-graph failure metric error-code semantics
- [x] Phase47-Step 5: run generate workflow / route-graph regression tests
- [x] Phase47-Step 6: backfill Phase47 execution records

## ??????????

?????????????

1. `generate_request_workflow.py` ???? metric / path planning helpers?
2. `graph_failed` / `graph_insufficient` ? path ? error-code ????????????
3. legacy / route-graph path?metric ??? semantic failure ?? fallback ???????
4. ?? generate workflow ? route-graph ?????????
5. ???????????????

## ??????????

### 2026-03-23 ????????

- ??????
- ??????? non-stream generate workflow ?? metric ??? path ??????????????? primary / failover / finalize ???

### 2026-03-23 ??????????

- ?????
- ?????? metric / path planning helpers??? primary success metric?graph failure metric ? error-code ??????? helper ??????

### 2026-03-23 ????????????

- ?? `writing_agent/workflows/generate_request_workflow.py`??? `_prepare_generate_metric_plan` ? `_record_generate_metric_plan`??? primary success ? failover ??????? metric plan ???
- ?? `writing_agent/workflows/generate_request_workflow.py`?? primary branch ????? route selection ? runtime state??? route-graph ??????? path ?? `graph_failed` metric?
- ?? `tests/unit/test_generate_request_workflow.py`??? route-graph failure metric error-code ????????? error-code ? path ?????

### 2026-03-23 ??????????

- ruff command: `.\.venv\Scripts\python -m ruff check writing_agent/workflows/generate_request_workflow.py tests/unit/test_generate_request_workflow.py`
- ruff result: passed
- generate targeted tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_generate_request_workflow.py`
- generate targeted tests result: `8 passed`
- targeted workflow tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/unit/test_generate_stream_request_workflow.py`
- targeted workflow tests result: `59 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `71 passed`

### 2026-03-23 ??????????

- ???????? non-stream generate workflow ???? metric / path ????????? helper?
- `generate_request_workflow.py` ???????????? primary branch?failover ? finalize ????????
- ??????????????

## ??????

- [x] Phase46: introduce generate runtime state carrier

## ????????

??????? generate workflow facade???????????????? state carrier?

1. ? `generate_request_workflow.py` ?? workflow-level runtime state dataclass????? `final_text`?`problems`?`graph_meta`?`prompt_trace`?terminal state ? failover ???
2. ? primary-result ?????????????? runtime state ? helper?
3. ?? `graph_failed` / `graph_insufficient` metric ???semantic failure ?? fallback ????????????

## ????????????

- [x] Phase46-Step 1: register Phase46 goal and scope in this ledger
- [x] Phase46-Step 2: add workflow-level generate runtime state carrier and apply helper
- [x] Phase46-Step 3: refactor non-stream generate workflow execution to use the state carrier
- [x] Phase46-Step 4: add focused coverage for graph-failed fallback recovery semantics
- [x] Phase46-Step 5: run generate workflow / route-graph regression tests
- [x] Phase46-Step 6: backfill Phase46 execution records

## ??????????

?????????????

1. `generate_request_workflow.py` ???? generate runtime state dataclass?
2. primary result ???failover ????? graph meta ???? state carrier ?????
3. `graph_failed` / `graph_insufficient` metric ???semantic failure ?? fallback ???????
4. ?? generate workflow ? route-graph ?????????
5. ???????????????

## ??????????

### 2026-03-23 ????????

- ??????
- ??????? generate workflow ???? runtime state ??????????????????? helper ??????

### 2026-03-23 ??????????

- ?????
- ?????? `GenerateGraphRuntimeState` ? primary-result apply helper??? failover ??? graph meta ??????? state carrier ?????

### 2026-03-23 ????????????

- ?? `writing_agent/workflows/generate_request_workflow.py`??? `GenerateGraphRuntimeState`?`_current_generate_graph_path`?`_apply_generate_primary_result`??? metric ???single-pass failover ???????????? runtime state ???
- ?? `tests/unit/test_generate_request_workflow.py`??? graph-failed ????????? route-graph ???? fallback ????? metric ???????

### 2026-03-23 ??????????

- ruff command: `.\.venv\Scripts\python -m ruff check writing_agent/workflows/generate_request_workflow.py tests/unit/test_generate_request_workflow.py`
- ruff result: passed
- generate targeted tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_generate_request_workflow.py`
- generate targeted tests result: `7 passed`
- targeted workflow tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/unit/test_generate_stream_request_workflow.py`
- targeted workflow tests result: `58 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `70 passed`

### 2026-03-23 ??????????

- ???????? non-stream generate workflow ???? runtime state ?????????????????????
- `generate_request_workflow.py` ????? stream workflow ? deps + runtime state + helper ?????
- ??????????????

## ??????

- [x] Phase45: consolidate generate failover and finalization helpers

## ????????

??????? generate workflow facade???????????????????? workflow helper?

1. ? `generate_request_workflow.py` ?? workflow-level failover helper??? `graph_failed` ? `graph_insufficient` ?? fallback ?????
2. ? `generate_request_workflow.py` ?? workflow-level finalization helper??????????insufficient fallback ????? `graph_meta` ???
3. ?? metric ???semantic failure ?? fallback ???legacy / route-graph path ???????

## ????????????

- [x] Phase45-Step 1: register Phase45 goal and scope in this ledger
- [x] Phase45-Step 2: add workflow-level generate failover and finalization helpers
- [x] Phase45-Step 3: refactor non-stream generate top-level body to delegate to the helpers
- [x] Phase45-Step 4: add focused coverage for legacy insufficient-output failover semantics
- [x] Phase45-Step 5: run generate workflow / route-graph regression tests
- [x] Phase45-Step 6: backfill Phase45 execution records

## ??????????

?????????????

1. `generate_request_workflow.py` ???? workflow-level failover helper ? finalization helper?
2. ???????? `graph_failed` / `graph_insufficient` ? fallback ?????
3. semantic failure ?? fallback?metric ???legacy / route-graph path ???????
4. ?? generate workflow ? route-graph ?????????
5. ???????????????

## ??????????

### 2026-03-23 ????????

- ??????
- ?????????? generate workflow ??????????????????????? workflow helper?

### 2026-03-23 ??????????

- ?????
- ?????? workflow-level failover helper ? finalization helper??? non-stream generate ? fallback ????? graph meta ???

### 2026-03-23 ????????????

- ?? `writing_agent/workflows/generate_request_workflow.py`??? `_execute_generate_failover` ? `_finalize_generate_workflow_result`??????????? helper ?? `graph_failed` / `graph_insufficient` ? fallback ??? graph meta ???
- ?? `tests/unit/test_generate_request_workflow.py`??? legacy insufficient-output ??????? legacy path ?? metric ??? fallback ?????????

### 2026-03-23 ??????????

- ruff command: `.\.venv\Scripts\python -m ruff check writing_agent/workflows/generate_request_workflow.py tests/unit/test_generate_request_workflow.py`
- ruff result: passed
- generate targeted tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_generate_request_workflow.py`
- generate targeted tests result: `6 passed`
- targeted workflow tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/unit/test_generate_stream_request_workflow.py`
- targeted workflow tests result: `57 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `69 passed`

### 2026-03-23 ??????????

- ???????? non-stream generate ????????????????? workflow helper???????????
- `generate_request_workflow.py` ????????? stream workflow ? primary / failover / finalize ?????
- ??????????????

## ??????

- [x] Phase44: introduce generate workflow dependency adapter

## ????????

??????? generate workflow facade???????? `app_v2` ?????????????

1. ? `generate_request_workflow.py` ?? workflow-level `GenerateGraphDeps` ????????????
2. ???????????single-pass failover ????????????? `deps` ???
3. ?? `GenerateGraphRequest` ????????????fallback ????????????

## ????????????

- [x] Phase44-Step 1: register Phase44 goal and scope in this ledger
- [x] Phase44-Step 2: add workflow-level generate dependency adapter and default builder
- [x] Phase44-Step 3: refactor non-stream generate workflow execution to use injected deps
- [x] Phase44-Step 4: add focused coverage for injected dependency adapter semantics
- [x] Phase44-Step 5: run generate workflow / route-graph regression tests
- [x] Phase44-Step 6: backfill Phase44 execution records

## ??????????

?????????????

1. `generate_request_workflow.py` ???? `GenerateGraphDeps` ????????????
2. route-graph / legacy branch?metric ??? single-pass failover ?????? `app_v2` ???????
3. `GenerateGraphRequest` ??????? generate workflow ???????
4. ?? generate workflow ? route-graph ?????????
5. ???????????????

## ??????????

### 2026-03-23 ????????

- ??????
- ??????? generate workflow ?????????????? workflow facade ? `app_v2` ?????????????

### 2026-03-23 ??????????

- ?????
- ???????? generate workflow ?? `GenerateGraphDeps` ??? builder??? branch ???metric ???single-pass failover ?????? `deps` ???

### 2026-03-23 ????????????

- ?? `writing_agent/workflows/generate_request_workflow.py`??? `GenerateGraphDeps`?`build_generate_graph_deps`???????????? route-graph / legacy branch?metric ??? single-pass failover ????????
- ?? `tests/unit/test_generate_request_workflow.py`??? injected-deps ????????? `app_v2` ??????????????? route-graph ???

### 2026-03-23 ??????????

- ruff command: `.\.venv\Scripts\python -m ruff check writing_agent/workflows/generate_request_workflow.py tests/unit/test_generate_request_workflow.py`
- ruff result: passed
- generate targeted tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_generate_request_workflow.py`
- generate targeted tests result: `5 passed`
- targeted workflow tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/unit/test_generate_stream_request_workflow.py`
- targeted workflow tests result: `56 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `68 passed`

### 2026-03-23 ??????????

- ??????????? generate workflow ?????????????? workflow facade ? `app_v2` ?????????
- `generate_request_workflow.py` ????? stream workflow ? deps ????????? LangGraph ????????????
- ??????????????

## ???????????

- [x] Phase43: consolidate generate branch execution helpers

## ????????

Continue converging the non-stream generate workflow facade by moving route-graph and legacy branch execution skeletons out of the top-level body in `generate_request_workflow.py`:

1. Add workflow-level helpers for route-graph branch execution and legacy branch execution.
2. Refactor the top-level body to delegate branch-specific execution to those helpers.
3. Preserve backend selection semantics, branch result propagation, and downstream failover logic unchanged.

## ????????????

- [x] Phase43-Step 1: register Phase43 goal and scope in this ledger
- [x] Phase43-Step 2: add workflow-level helpers for route-graph and legacy branch execution
- [x] Phase43-Step 3: refactor the top-level body to reuse the branch helpers
- [x] Phase43-Step 4: add focused coverage for helper-driven legacy backend selection semantics
- [x] Phase43-Step 5: run generate workflow / route-graph regression tests
- [x] Phase43-Step 6: backfill Phase43 execution records

## ??????????

All conditions below must be satisfied:

1. `generate_request_workflow.py` owns explicit workflow-level helpers for route-graph and legacy branch execution.
2. The top-level workflow body no longer inlines both branch execution skeletons.
3. Backend selection semantics, branch result propagation, and downstream failover logic remain unchanged.
4. Existing generate workflow and route-graph regression tests keep their semantics unchanged.
5. Phase43 execution records are backfilled in this ledger.

## ??????????

### 2026-03-23 ????????

- ??????
- ???extract non-stream route-graph and legacy branch execution skeletons into workflow-level helpers so the top-level generate workflow body focuses on backend selection, fallback handling, and final graph meta assembly.

### 2026-03-23 ??????????

- ?????
- ???added `_execute_route_graph_branch`, `_execute_legacy_graph_branch`, and `_execute_generate_primary_branch` in `generate_request_workflow.py`, keeping branch-specific execution skeletons inside workflow helpers while the top-level body now delegates primary-branch execution before fallback and graph-meta finalization.

### 2026-03-23 ????????????

- Updated `writing_agent/workflows/generate_request_workflow.py`: added workflow-level route-graph / legacy branch helpers and routed the top-level body through a shared primary-branch executor.
- Updated `tests/unit/test_generate_request_workflow.py`: added focused coverage proving the legacy path bypasses `run_generate_graph_dual_engine` when route graph is disabled.

### 2026-03-23 ??????????

- ruff command: `.\.venv\Scripts\python -m ruff check writing_agent/workflows/generate_request_workflow.py tests/unit/test_generate_request_workflow.py`
- ruff result: passed
- generate targeted tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_generate_request_workflow.py`
- generate targeted tests result: `4 passed`
- targeted workflow tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/unit/test_generate_stream_request_workflow.py`
- targeted workflow tests result: `55 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `67 passed`

### 2026-03-23 ??????????

- Phase43 converges non-stream generate branch execution into explicit workflow helpers while preserving backend selection, branch result propagation, and downstream failover semantics.
- `generate_request_workflow.py` now keeps the top-level body focused on primary-branch selection, failover handling, and final graph-meta assembly.
- No unchecked Phase43 items remain in this ledger.

## ??????????

- [x] Phase42: consolidate generate legacy event parsing

## ????????

Continue separating orchestration-backend concerns by moving non-stream generate legacy event parsing into a shared backend helper:

1. Add a shared backend helper that parses legacy prompt-route and final events for non-stream generate workflows.
2. Refactor `generate_request_workflow.py` to reuse the shared helper in the legacy branch.
3. Preserve prompt trace accumulation, terminal status parsing, and semantic-failure problem propagation unchanged.

## ????????????

- [x] Phase42-Step 1: register Phase42 goal and scope in this ledger
- [x] Phase42-Step 2: add a shared helper for generate legacy event parsing
- [x] Phase42-Step 3: refactor `generate_request_workflow.py` legacy branch to reuse the helper
- [x] Phase42-Step 4: add focused backend coverage for legacy event parsing
- [x] Phase42-Step 5: run generate workflow / route-graph regression tests
- [x] Phase42-Step 6: backfill Phase42 execution records

## ??????????

All conditions below must be satisfied:

1. `orchestration_backend.py` owns the shared non-stream generate legacy event parser.
2. `generate_request_workflow.py` no longer inlines legacy prompt-route and final event parsing details.
3. Prompt trace accumulation, terminal status parsing, and semantic-failure problem propagation remain unchanged.
4. Existing generate workflow and route-graph regression tests keep their semantics unchanged.
5. Phase42 execution records are backfilled in this ledger.

## ??????????

### 2026-03-23 ????????

- ??????
- ???collapse non-stream generate legacy event parsing into the orchestration backend so the workflow facade keeps timeout iteration, metrics, and fallback decisions.

### 2026-03-23 ??????????

- ?????
- ???added `prepare_generate_legacy_event_observation` in the orchestration backend and refactored `generate_request_workflow.py` to reuse it while preserving prompt trace accumulation, terminal status parsing, and semantic-failure problem propagation.

### 2026-03-23 ????????????

- Updated `writing_agent/workflows/orchestration_backend.py`: added `prepare_generate_legacy_event_observation` to centralize non-stream legacy prompt-route and final-event parsing.
- Updated `writing_agent/workflows/generate_request_workflow.py`: the legacy branch now reuses the shared backend helper for event parsing.
- Updated `tests/unit/test_orchestration_backend.py`: added direct coverage for legacy prompt-route capture and semantic-failure final-event parsing.

### 2026-03-23 ??????????

- ???????`.\.venv\Scripts\python -m ruff check writing_agent/workflows/orchestration_backend.py writing_agent/workflows/generate_request_workflow.py tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py`
- ?????????
- generate targeted tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py`
- generate targeted tests result: `42 passed`
- targeted workflow tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/unit/test_generate_stream_request_workflow.py`
- targeted workflow tests result: `54 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `66 passed`

### 2026-03-23 ??????????

- Phase42 converges non-stream generate legacy event parsing inside the orchestration backend.
- `generate_request_workflow.py` now keeps timeout iteration, metrics, and fallback decisions, while legacy prompt-route and final-event parsing are collapsed behind the shared backend helper.
- ????????????????????????????

## ???????????

- [x] Phase41: consolidate generate route-graph outcome parsing

## ????????

Continue separating orchestration-backend concerns by moving non-stream generate route-graph result parsing into a shared backend helper:

1. Add a shared backend helper that normalizes non-stream generate route-graph outcomes.
2. Refactor `generate_request_workflow.py` to reuse the shared helper.
3. Preserve terminal status parsing, prompt trace normalization, and semantic-failure problem propagation unchanged.

## ????????????

- [x] Phase41-Step 1: register Phase41 goal and scope in this ledger
- [x] Phase41-Step 2: add a shared helper for generate route-graph outcome parsing
- [x] Phase41-Step 3: refactor `generate_request_workflow.py` to reuse the helper
- [x] Phase41-Step 4: add focused backend coverage for route-graph outcome parsing
- [x] Phase41-Step 5: run generate workflow / route-graph regression tests
- [x] Phase41-Step 6: backfill Phase41 execution records

## ??????????

All conditions below must be satisfied:

1. `orchestration_backend.py` owns the shared non-stream generate route-graph outcome parser.
2. `generate_request_workflow.py` no longer inlines route-graph result parsing details.
3. Terminal status parsing, prompt trace normalization, and semantic-failure problem propagation remain unchanged.
4. Existing generate workflow and route-graph regression tests keep their semantics unchanged.
5. Phase41 execution records are backfilled in this ledger.

## ??????????

### 2026-03-23 ????????

- ??????
- ???collapse non-stream generate route-graph result parsing into the orchestration backend so the workflow facade keeps metrics, fallback decisions, and final graph meta assembly.

### 2026-03-23 ??????????

- ?????
- ???added `prepare_generate_route_graph_outcome` in the orchestration backend and refactored `generate_request_workflow.py` to reuse it while preserving terminal status parsing, prompt trace normalization, and semantic-failure problem propagation.

### 2026-03-23 ????????????

- Updated `writing_agent/workflows/orchestration_backend.py`: added `prepare_generate_route_graph_outcome` to centralize non-stream route-graph outcome parsing.
- Updated `writing_agent/workflows/generate_request_workflow.py`: route-graph parsing now reuses the shared backend helper.
- Updated `tests/unit/test_orchestration_backend.py`: added direct coverage for successful and semantic-failure generate route-graph outcome parsing.

### 2026-03-23 ??????????

- ???????`.\.venv\Scripts\python -m ruff check writing_agent/workflows/orchestration_backend.py writing_agent/workflows/generate_request_workflow.py tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py`
- ?????????
- generate targeted tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py`
- generate targeted tests result: `40 passed`
- targeted workflow tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/unit/test_generate_stream_request_workflow.py`
- targeted workflow tests result: `52 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `64 passed`

### 2026-03-23 ??????????

- Phase41 converges non-stream generate route-graph outcome parsing inside the orchestration backend.
- `generate_request_workflow.py` now keeps metrics, fallback decisions, and final graph meta assembly, while route-graph result parsing is collapsed behind the shared backend helper.
- ?????????????????????????????

## ???????????

- [x] Phase40: consolidate generate single-pass failover flow

## ???????

Continue converging the non-stream generate workflow by moving repeated single-pass failover execution shells out of `generate_request_workflow.py`:

1. Add a workflow-level helper that executes non-stream single-pass failover, applies failover quality metadata updates, and records fallback metrics.
2. Refactor both graph-failure and insufficient-output fallback flows to reuse the shared helper.
3. Preserve failure reasons, metric ordering, and fallback-recovered semantics unchanged.

## ???????????

- [x] Phase40-Step 1: register Phase40 goal and scope in this ledger
- [x] Phase40-Step 2: add a workflow-level helper for non-stream single-pass failover execution
- [x] Phase40-Step 3: refactor graph-failure / insufficient-output fallback flows to reuse the helper
- [x] Phase40-Step 4: add focused coverage for helper-driven failover semantics
- [x] Phase40-Step 5: run generate workflow / route-graph regression tests
- [x] Phase40-Step 6: backfill Phase40 execution records

## ?????????

All conditions below must be satisfied:

1. `generate_request_workflow.py` owns a shared workflow-level helper for non-stream single-pass failover execution.
2. The two single-pass failover shells are no longer duplicated inline.
3. Failure reasons, metric ordering, and fallback-recovered semantics remain unchanged.
4. Existing generate workflow and route-graph regression tests keep their semantics unchanged.
5. Phase40 execution records are backfilled in this ledger.

## ?????????

### 2026-03-23 ???????

- ??????
- ???collapse repeated non-stream single-pass failover execution into a shared workflow helper so `generate_request_workflow.py` keeps only fallback triggering decisions and final metadata assembly.

### 2026-03-23 ?????????

- ?????
- ???added `_execute_single_pass_failover` in the non-stream generate workflow and refactored both graph-failure and insufficient-output fallback flows to reuse it while preserving failure reasons, metric ordering, and fallback-recovered semantics.

### 2026-03-23 ???????????

- Updated `writing_agent/workflows/generate_request_workflow.py`: added `_execute_single_pass_failover` and simplified both non-stream fallback shells to delegate to it.
- Updated `tests/unit/test_generate_request_workflow.py`: added focused coverage for route-graph insufficient-output recovery through the shared failover helper.

### 2026-03-23 ?????????

- ???????`.\.venv\Scripts\python -m ruff check writing_agent/workflows/generate_request_workflow.py tests/unit/test_generate_request_workflow.py`
- ?????????
- generate focused tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_generate_request_workflow.py`
- generate focused tests result: `3 passed`
- targeted workflow tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/unit/test_generate_stream_request_workflow.py`
- targeted workflow tests result: `50 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `62 passed`

### 2026-03-23 ?????????

- Phase40 converges non-stream single-pass failover execution inside the generate workflow facade.
- `generate_request_workflow.py` now keeps fallback triggering decisions and final metadata assembly, while repeated single-pass failover shells are collapsed behind the shared helper.
- ?????????????????????????????

## ???????????

- [x] Phase39: consolidate legacy graph invocation kwargs

## ????????

Continue separating orchestration-backend concerns by moving legacy graph invocation payload construction into a shared backend helper:

1. Add a shared backend helper that builds legacy graph invocation kwargs.
2. Refactor generate, generate-section, and generate-stream workflows to reuse the shared legacy kwargs helper.
3. Preserve legacy graph invocation semantics unchanged across all three workflows.

## ????????????

- [x] Phase39-Step 1: register Phase39 goal and scope in this ledger
- [x] Phase39-Step 2: add a shared helper for legacy graph invocation kwargs
- [x] Phase39-Step 3: refactor generate / section / stream workflows to reuse the helper
- [x] Phase39-Step 4: add focused backend coverage for legacy kwargs construction
- [x] Phase39-Step 5: run workflow / route-graph regression tests
- [x] Phase39-Step 6: backfill Phase39 execution records

## ??????????

All conditions below must be satisfied:

1. `orchestration_backend.py` owns the shared legacy graph invocation kwargs helper.
2. `generate_request_workflow.py`, `generate_section_request_workflow.py`, and `generate_stream_request_workflow.py` no longer inline legacy graph kwargs construction.
3. Legacy graph invocation semantics remain unchanged across all three workflows.
4. Existing workflow and route-graph regression tests keep their semantics unchanged.
5. Phase39 execution records are backfilled in this ledger.

## ??????????

### 2026-03-23 ????????

- ??????
- ???collapse legacy graph invocation kwargs construction into the orchestration backend so generate / section / stream workflows stop inlining the same backend payload shape.

### 2026-03-23 ??????????

- ?????
- ???added `build_legacy_graph_kwargs` in the orchestration backend and refactored generate, generate-section, and generate-stream workflows to reuse it while preserving legacy graph invocation semantics.

### 2026-03-23 ????????????

- Updated `writing_agent/workflows/orchestration_backend.py`: added `build_legacy_graph_kwargs` to centralize legacy graph invocation payload construction.
- Updated `writing_agent/workflows/generate_request_workflow.py`: legacy graph execution now reuses `build_legacy_graph_kwargs`.
- Updated `writing_agent/workflows/generate_section_request_workflow.py`: legacy section graph execution now reuses `build_legacy_graph_kwargs`.
- Updated `writing_agent/workflows/generate_stream_request_workflow.py`: legacy stream graph execution now reuses `build_legacy_graph_kwargs`.
- Updated `tests/unit/test_orchestration_backend.py`: added direct coverage for legacy graph kwargs construction.

### 2026-03-23 ??????????

- ???????`.\.venv\Scripts\python -m ruff check writing_agent/workflows/orchestration_backend.py writing_agent/workflows/generate_request_workflow.py writing_agent/workflows/generate_section_request_workflow.py writing_agent/workflows/generate_stream_request_workflow.py tests/unit/test_orchestration_backend.py`
- ?????????
- targeted workflow tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/unit/test_generate_stream_request_workflow.py`
- targeted workflow tests result: `49 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `61 passed`

### 2026-03-23 ??????????

- Phase39 converges legacy graph invocation kwargs inside the orchestration backend.
- Generate, generate-section, and generate-stream workflows now stop inlining the same legacy backend payload shape, which further tightens the orchestration-backend / workflow split.
- ?????????????????????????????

## ???????????

- [x] Phase38: consolidate stream primary branch dispatch

## ????????

Continue converging the top-level stream workflow body by moving backend selection and primary branch dispatch into a workflow-level helper:

1. Add a workflow-level helper that resolves the default orchestration backend and delegates to the route-graph or legacy branch helper.
2. Refactor the top-level workflow body to reuse the shared primary-dispatch helper.
3. Preserve backend selection semantics, branch result propagation, and downstream failover flow unchanged.

## ????????????

- [x] Phase38-Step 1: register Phase38 goal and scope in this ledger
- [x] Phase38-Step 2: add a workflow-level helper for primary branch dispatch
- [x] Phase38-Step 3: refactor the top-level workflow body to reuse the helper
- [x] Phase38-Step 4: add focused coverage for helper-driven backend selection semantics
- [x] Phase38-Step 5: run stream workflow / route-graph regression tests
- [x] Phase38-Step 6: backfill Phase38 execution records

## ??????????

All conditions below must be satisfied:

1. `generate_stream_request_workflow.py` owns a shared workflow-level helper for backend selection and primary branch dispatch.
2. The top-level workflow body no longer inlines backend selection and branch delegation.
3. Backend selection semantics, branch result propagation, and downstream failover flow remain unchanged.
4. Existing stream fallback and route-graph regression tests keep their semantics unchanged.
5. Phase38 execution records are backfilled in this ledger.

## ??????????

### 2026-03-23 ????????

- ??????
- ???collapse backend selection and primary branch dispatch into a shared workflow helper so the top-level stream workflow body keeps only graph-failure recovery and final result handoff.

### 2026-03-23 ??????????

- ?????
- ???added `_execute_stream_primary_branch` in the workflow facade and refactored the top-level body to reuse it while preserving backend selection semantics, branch result propagation, and downstream failover flow.

### 2026-03-23 ????????????

- Updated `writing_agent/workflows/generate_stream_request_workflow.py`: added `_execute_stream_primary_branch` and simplified the top-level body to delegate backend selection and branch dispatch.
- Updated `tests/unit/test_generate_stream_request_workflow.py`: strengthened legacy-branch coverage so route-graph-disabled execution now fails fast if the dual-engine runner is invoked unexpectedly.

### 2026-03-23 ??????????

- ???????`.\.venv\Scripts\python -m ruff check writing_agent/workflows/generate_stream_request_workflow.py tests/unit/test_generate_stream_request_workflow.py`
- ?????????
- workflow focused tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_generate_stream_request_workflow.py`
- workflow focused tests result: `10 passed`
- stream direct tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_stream_request_workflow.py`
- stream direct tests result: `44 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `60 passed`

### 2026-03-23 ??????????

- Phase38 converges stream primary branch dispatch inside the workflow facade.
- The top-level stream workflow body now focuses on graph-failure recovery and final result handoff, while backend selection and branch dispatch are collapsed behind the shared workflow helper.
- ?????????????????????????????

## ???????????

- [x] Phase37: consolidate stream final result handling

## ????????

Continue converging the top-level stream workflow body by moving stop handling, insufficient-output failover gating, and final return assembly into a workflow-level helper:

1. Add a workflow-level helper that finalizes stream execution results after primary branch execution or graph-failure recovery.
2. Refactor the top-level workflow body to reuse the shared final-result helper.
3. Preserve semantic-stop short-circuiting, insufficient-output fallback gating, and final-text propagation unchanged.

## ????????????

- [x] Phase37-Step 1: register Phase37 goal and scope in this ledger
- [x] Phase37-Step 2: add a workflow-level helper for final result handling
- [x] Phase37-Step 3: refactor the top-level workflow body to reuse the helper
- [x] Phase37-Step 4: add focused coverage for semantic-stop short-circuit and final-result semantics
- [x] Phase37-Step 5: run stream workflow / route-graph regression tests
- [x] Phase37-Step 6: backfill Phase37 execution records

## ??????????

All conditions below must be satisfied:

1. `generate_stream_request_workflow.py` owns a shared workflow-level helper for final result handling.
2. The top-level workflow body no longer inlines stop handling, insufficient-output failover gating, and final return assembly.
3. Semantic-stop short-circuiting, insufficient-output fallback gating, and final-text propagation remain unchanged.
4. Existing stream fallback and route-graph regression tests keep their semantics unchanged.
5. Phase37 execution records are backfilled in this ledger.

## ??????????

### 2026-03-23 ????????

- ??????
- ???collapse the remaining top-level stop handling and insufficient-output fallback gate into a shared workflow helper so the stream workflow body keeps only backend selection, branch delegation, graph-failure recovery, and final handoff.

### 2026-03-23 ??????????

- ?????
- ???added `_finalize_stream_workflow_result` in the workflow facade and refactored the top-level body to reuse it while preserving semantic-stop short-circuiting, insufficient-output failover gating, and final-text propagation.

### 2026-03-23 ????????????

- Updated `writing_agent/workflows/generate_stream_request_workflow.py`: added `_finalize_stream_workflow_result` and simplified the top-level body to delegate stop handling, insufficient-output failover gating, and final result assembly.
- Updated `tests/unit/test_generate_stream_request_workflow.py`: strengthened semantic-failure coverage to assert the short-circuit path only records `route_graph_semantic_failed` and does not trigger fallback metrics.

### 2026-03-23 ??????????

- ???????`.\.venv\Scripts\python -m ruff check writing_agent/workflows/generate_stream_request_workflow.py tests/unit/test_generate_stream_request_workflow.py`
- ?????????
- workflow focused tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_generate_stream_request_workflow.py`
- workflow focused tests result: `10 passed`
- stream direct tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_stream_request_workflow.py`
- stream direct tests result: `44 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `60 passed`

### 2026-03-23 ??????????

- Phase37 converges stream final result handling inside the workflow facade.
- The top-level stream workflow body now focuses on backend selection, branch delegation, graph-failure recovery, and final handoff, while stop handling, insufficient-output failover gating, and final return assembly are collapsed behind the shared workflow helper.
- ?????????????????????????????

## ???????????

- [x] Phase36: consolidate stream failover execution flow

## ????????

Continue converging the top-level stream workflow body by moving fallback-trigger dispatch plus single-pass recovery execution into a workflow-level helper:

1. Add a workflow-level helper that triggers stream fallback, optionally logs graph errors, executes the single-pass recovery branch, and returns the applied outcome.
2. Refactor both graph-failure and insufficient-output fallback flows to reuse the shared helper.
3. Preserve fallback trigger order, stop behavior, and final-text propagation unchanged.

## ????????????

- [x] Phase36-Step 1: register Phase36 goal and scope in this ledger
- [x] Phase36-Step 2: add a workflow-level helper for failover execution flow
- [x] Phase36-Step 3: refactor the two top-level fallback flows to reuse the helper
- [x] Phase36-Step 4: add focused coverage for helper-driven graph-failure / insufficient fallback semantics
- [x] Phase36-Step 5: run stream workflow / route-graph regression tests
- [x] Phase36-Step 6: backfill Phase36 execution records

## ??????????

All conditions below must be satisfied:

1. `generate_stream_request_workflow.py` owns a shared workflow-level helper for triggering and executing stream failover recovery.
2. The top-level workflow body no longer duplicates the two fallback execution shells.
3. Fallback trigger order, stop behavior, and final-text propagation remain unchanged.
4. Existing stream fallback and route-graph regression tests keep their semantics unchanged.
5. Phase36 execution records are backfilled in this ledger.

## ??????????

### 2026-03-23 ????????

- ??????
- ???collapse the two top-level failover execution shells into a shared workflow helper so the stream workflow body keeps only backend selection, branch delegation, and final return semantics.

### 2026-03-23 ??????????

- ?????
- ???added `_execute_stream_failover_flow` in the workflow facade and refactored both graph-failure and insufficient-output fallback flows to reuse it while preserving trigger order, stop behavior, and final-text propagation.

### 2026-03-23 ????????????

- Updated `writing_agent/workflows/generate_stream_request_workflow.py`: added `_execute_stream_failover_flow` and simplified the two top-level fallback shells to delegate to it.
- Updated `tests/unit/test_generate_stream_request_workflow.py`: added focused coverage for legacy-graph failure recovery through the shared failover helper.

### 2026-03-23 ??????????

- ???????`.\.venv\Scripts\python -m ruff check writing_agent/workflows/generate_stream_request_workflow.py tests/unit/test_generate_stream_request_workflow.py`
- ?????????
- workflow focused tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_generate_stream_request_workflow.py`
- workflow focused tests result: `10 passed`
- stream direct tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_stream_request_workflow.py`
- stream direct tests result: `44 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `60 passed`

### 2026-03-23 ??????????

- Phase36 converges stream failover execution flow inside the workflow facade.
- The top-level stream workflow body now keeps backend selection, branch delegation, and final return semantics, while duplicated fallback trigger + recovery execution shells are collapsed behind the shared workflow helper.
- ?????????????????????????????

## ???????????

- [x] Phase35: consolidate stream branch execution helpers

## ????????

Continue converging the stream workflow facade by moving the route-graph branch and legacy branch execution skeletons out of the top-level body in `generate_stream_request_workflow.py`:

1. Add workflow-level helpers for route-graph branch execution and legacy branch execution.
2. Refactor the top-level workflow body to delegate branch-specific execution to those helpers.
3. Preserve final-text propagation, semantic-stop behavior, and fallback control flow unchanged.

## ????????????

- [x] Phase35-Step 1: register Phase35 goal and scope in this ledger
- [x] Phase35-Step 2: add workflow-level helpers for route-graph and legacy branch execution
- [x] Phase35-Step 3: refactor the top-level workflow body to reuse the branch helpers
- [x] Phase35-Step 4: add focused coverage for helper-driven branch stop / final-text semantics
- [x] Phase35-Step 5: run stream workflow / route-graph regression tests
- [x] Phase35-Step 6: backfill Phase35 execution records

## ??????????

All conditions below must be satisfied:

1. `generate_stream_request_workflow.py` owns explicit workflow-level helpers for route-graph and legacy branch execution.
2. The top-level workflow body no longer inlines both branch execution skeletons.
3. Final-text propagation, semantic-stop behavior, and fallback control flow remain unchanged.
4. Existing stream fallback and route-graph regression tests keep their semantics unchanged.
5. Phase35 execution records are backfilled in this ledger.

## ??????????

### 2026-03-23 ????????

- ??????
- ???extract the route-graph and legacy branch execution skeletons into workflow-level helpers so the top-level stream workflow body focuses on backend selection, exception handling, and fallback control flow.

### 2026-03-23 ??????????

- ?????
- ???added workflow-level route-graph and legacy branch helpers and refactored the top-level body to delegate branch execution while preserving final-text propagation, semantic-stop behavior, and fallback flow.

### 2026-03-23 ????????????

- Updated `writing_agent/workflows/generate_stream_request_workflow.py`: added `_execute_route_graph_branch` and `_execute_legacy_graph_branch`, and simplified the top-level branch selection body to delegate to those helpers.
- Updated `tests/unit/test_generate_stream_request_workflow.py`: added focused coverage for the helper-driven route-graph default branch result when the dual-engine runner returns a non-dict payload.

### 2026-03-23 ??????????

- ???????`.\.venv\Scripts\python -m ruff check writing_agent/workflows/generate_stream_request_workflow.py tests/unit/test_generate_stream_request_workflow.py`
- ?????????
- workflow focused tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_generate_stream_request_workflow.py`
- workflow focused tests result: `9 passed`
- stream direct tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_stream_request_workflow.py`
- stream direct tests result: `43 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `59 passed`

### 2026-03-23 ??????????

- Phase35 converges route-graph and legacy branch execution skeletons inside the workflow facade.
- The top-level stream workflow body now focuses on backend selection, exception handling, and fallback control flow, while branch-specific execution is delegated to explicit helpers.
- ?????????????????????????????

## ???????????

- [x] Phase34: consolidate stream fallback trigger dispatch

## ????????

Continue converging stream fallback control flow by moving graph-path resolution and fallback-trigger dispatch out of inline branches in `generate_stream_request_workflow.py`:

1. Add a shared backend helper that resolves the active stream graph path and dispatches graph-failure vs insufficient-output fallback triggers.
2. Refactor the stream workflow to reuse the shared trigger-dispatch helper in both fallback entry points.
3. Preserve fallback trigger codes, metric events, and trace-context mutation order unchanged.

## ????????????

- [x] Phase34-Step 1: register Phase34 goal and scope in this ledger
- [x] Phase34-Step 2: add a shared helper for stream fallback trigger dispatch
- [x] Phase34-Step 3: refactor the workflow fallback entry points to reuse the shared helper
- [x] Phase34-Step 4: add focused coverage for graph-path resolution and trigger dispatch semantics
- [x] Phase34-Step 5: run stream workflow / route-graph regression tests
- [x] Phase34-Step 6: backfill Phase34 execution records

## ??????????

All conditions below must be satisfied:

1. `orchestration_backend.py` owns the shared stream fallback trigger dispatch helper used by the stream workflow.
2. The stream workflow no longer duplicates `route_graph` / `legacy_graph` path selection at the two fallback trigger entry points.
3. Fallback trigger codes, metric events, and trace-context mutation order remain correct for both graph-failure and insufficient-output cases.
4. Existing stream fallback and route-graph regression tests keep their semantics unchanged.
5. Phase34 execution records are backfilled in this ledger.

## ??????????

### 2026-03-23 ????????

- ??????
- ???collapse stream graph-path resolution and fallback-trigger dispatch into the orchestration backend so the workflow facade keeps only fallback branch execution and terminal outcome control flow.

### 2026-03-23 ??????????

- ?????
- ???added `resolve_stream_graph_path` and `prepare_stream_fallback_trigger` in the orchestration backend and refactored both workflow fallback entry points to reuse them while preserving trigger codes, metric events, and trace-context mutation order.

### 2026-03-23 ????????????

- Updated `writing_agent/workflows/orchestration_backend.py`: added `resolve_stream_graph_path` and `prepare_stream_fallback_trigger` to centralize graph-path resolution and graph-failure / insufficient-output trigger dispatch.
- Updated `writing_agent/workflows/generate_stream_request_workflow.py`: both fallback trigger entry points now reuse the shared backend helper and no longer inline `route_graph` / `legacy_graph` path selection.
- Updated `tests/unit/test_orchestration_backend.py`: added direct coverage for graph-path resolution and both trigger-dispatch modes.

### 2026-03-23 ??????????

- ???????`.\.venv\Scripts\python -m ruff check writing_agent/workflows/orchestration_backend.py writing_agent/workflows/generate_stream_request_workflow.py tests/unit/test_orchestration_backend.py tests/unit/test_generate_stream_request_workflow.py`
- ?????????
- stream direct tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_stream_request_workflow.py`
- stream direct tests result: `42 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `58 passed`

### 2026-03-23 ??????????

- Phase34 converges stream fallback trigger dispatch inside the orchestration backend.
- The stream workflow now keeps fallback branch execution and terminal outcome control flow, while duplicated graph-path resolution and fallback-trigger dispatch are collapsed behind the shared backend helper.
- ?????????????????????????????

## ???????????

- [x] Phase33: consolidate route-graph outcome planning

## ????????

Continue converging route-graph stream control flow by moving route-graph outcome classification and terminal payload planning out of inline branches in `generate_stream_request_workflow.py`:

1. Add a shared backend helper that classifies route-graph results into success / semantic-stop / continue outcomes and prepares the corresponding terminal payload plan.
2. Refactor the route-graph branch to reuse the shared outcome-planning helper.
3. Preserve postprocess order, semantic-failure stop behavior, and route-graph regression behavior unchanged.

## ????????????

- [x] Phase33-Step 1: register Phase33 goal and scope in this ledger
- [x] Phase33-Step 2: add a shared helper for route-graph outcome planning
- [x] Phase33-Step 3: refactor the route-graph branch to reuse the shared helper
- [x] Phase33-Step 4: add focused coverage for success / semantic-stop / continue planning semantics
- [x] Phase33-Step 5: run stream workflow / route-graph regression tests
- [x] Phase33-Step 6: backfill Phase33 execution records

## ??????????

All conditions below must be satisfied:

1. `orchestration_backend.py` owns the shared route-graph outcome-planning helper used by the stream workflow.
2. The route-graph branch no longer duplicates result classification and terminal payload planning inline.
3. Postprocess ordering, semantic-failure stop semantics, and `skip_insufficient_failover` behavior remain correct.
4. Existing stream fallback and route-graph regression tests keep their semantics unchanged.
5. Phase33 execution records are backfilled in this ledger.

## ??????????

### 2026-03-23 ????????

- ??????
- ???collapse route-graph result classification and terminal payload planning into the orchestration backend so the workflow facade keeps only route selection, final emit semantics, and fallback control flow.

### 2026-03-23 ??????????

- ?????
- ???added `prepare_stream_route_graph_outcome_plan` in the orchestration backend and refactored the route-graph branch to reuse it while preserving postprocess ordering, semantic-stop behavior, and route-graph terminal emit semantics.

### 2026-03-23 ????????????

- Updated `writing_agent/workflows/orchestration_backend.py`: added `prepare_stream_route_graph_outcome_plan` to centralize route-graph result classification and success / semantic-stop terminal payload planning.
- Updated `writing_agent/workflows/generate_stream_request_workflow.py`: the route-graph branch now consumes the shared outcome plan and keeps only final emit and fallback control flow.
- Updated `tests/unit/test_orchestration_backend.py`: added direct coverage for route-graph success, semantic-stop, and continue outcome plans.

### 2026-03-23 ??????????

- ???????`.\.venv\Scripts\python -m ruff check writing_agent/workflows/orchestration_backend.py writing_agent/workflows/generate_stream_request_workflow.py tests/unit/test_orchestration_backend.py tests/unit/test_generate_stream_request_workflow.py`
- ?????????
- stream direct tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_stream_request_workflow.py`
- stream direct tests result: `39 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `55 passed`

### 2026-03-23 ??????????

- Phase33 converges route-graph outcome planning inside the orchestration backend.
- The stream workflow now keeps route selection, terminal emit semantics, and fallback control flow, while duplicated route-graph result classification and terminal payload planning are collapsed behind the shared backend helper.
- ?????????????????????????????

## ??????????

- [x] Phase32: consolidate legacy stream event tracking

## ????????

Continue converging legacy-stream control flow by moving event-tracking and section-stall observation out of inline branches in `generate_stream_request_workflow.py`:

1. Add a shared backend helper that tracks legacy stream event timing, prompt-route trace capture, and section-stall detection.
2. Refactor the legacy stream loop to reuse the shared event-tracking helper.
3. Preserve prompt trace accumulation, max-gap timing semantics, and section-stall behavior unchanged.

## ????????????

- [x] Phase32-Step 1: register Phase32 goal and scope in this ledger
- [x] Phase32-Step 2: add a shared helper for legacy stream event tracking
- [x] Phase32-Step 3: refactor the legacy stream loop to reuse the shared helper
- [x] Phase32-Step 4: add focused coverage for prompt-route capture and section-stall detection semantics
- [x] Phase32-Step 5: run stream workflow / route-graph regression tests
- [x] Phase32-Step 6: backfill Phase32 execution records

## ??????????

All conditions below must be satisfied:

1. `orchestration_backend.py` owns the shared legacy stream event-tracking helper used by the stream workflow.
2. The legacy stream loop no longer duplicates prompt-route trace capture, max-gap tracking, and section-stall detection inline.
3. Prompt trace accumulation, `max_gap_s`, and section-stall behavior remain correct.
4. Existing stream fallback and route-graph regression tests keep their semantics unchanged.
5. Phase32 execution records are backfilled in this ledger.

## ??????????

### 2026-03-23 ????????

- ??????
- ???collapse legacy stream event tracking into the orchestration backend so the workflow facade keeps only iteration control, final payload preparation, and terminal emit semantics.

### 2026-03-23 ??????????

- ?????
- ???added `prepare_stream_legacy_event_observation` in the orchestration backend and refactored the legacy stream loop to reuse it while preserving prompt-route trace capture, max-gap timing updates, and section-stall semantics.

### 2026-03-23 ????????????

- Updated `writing_agent/workflows/orchestration_backend.py`: added `prepare_stream_legacy_event_observation` to centralize legacy stream event timing updates, prompt-route trace capture, and section-stall detection.
- Updated `writing_agent/workflows/generate_stream_request_workflow.py`: the legacy stream loop now reuses the shared observation helper before final-payload handling and event emission.
- Updated `tests/unit/test_orchestration_backend.py`: added direct coverage for prompt-route capture, section timestamp updates, and section-stall detection.

### 2026-03-23 ??????????

- ???????`.\.venv\Scripts\python -m ruff check writing_agent/workflows/orchestration_backend.py writing_agent/workflows/generate_stream_request_workflow.py tests/unit/test_orchestration_backend.py tests/unit/test_generate_stream_request_workflow.py`
- ?????????
- stream direct tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_stream_request_workflow.py`
- stream direct tests result: `36 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `52 passed`

### 2026-03-23 ??????????

- Phase32 converges legacy-stream event tracking inside the orchestration backend.
- The stream workflow now keeps legacy iteration control and terminal emit semantics, while duplicated prompt-route trace capture, max-gap timing updates, and section-stall detection are collapsed behind the shared backend helper.
- ????????????????????????????

## ??????????

- [x] Phase31: consolidate legacy stream terminal payload preparation

## ????????

Continue converging stream workflow final-payload preparation by moving duplicated legacy-stream terminal payload assembly out of inline branches in `generate_stream_request_workflow.py`:

1. Add a shared backend helper that prepares legacy-stream terminal payloads and synchronizes route metric metadata.
2. Refactor the legacy-stream final branch to reuse the shared payload preparation path.
3. Preserve prompt trace propagation, final payload shape, and legacy route-graph-disabled regression behavior unchanged.

## ????????????

- [x] Phase31-Step 1: register Phase31 goal and scope in this ledger
- [x] Phase31-Step 2: add a shared helper for legacy-stream terminal payload preparation
- [x] Phase31-Step 3: refactor the legacy final branch to reuse the shared helper
- [x] Phase31-Step 4: add focused coverage for legacy prompt trace and route metric metadata semantics
- [x] Phase31-Step 5: run stream workflow / route-graph regression tests
- [x] Phase31-Step 6: backfill Phase31 execution records

## ??????????

All conditions below must be satisfied:

1. `orchestration_backend.py` owns the shared legacy-stream terminal payload preparation helper used by the stream workflow.
2. The legacy-stream final branch no longer duplicates graph meta / prompt trace / route metric payload assembly inline.
3. Prompt trace propagation and `route_metric_meta` synchronization remain correct when route-graph is disabled.
4. Existing stream fallback and route-graph regression tests keep their semantics unchanged.
5. Phase31 execution records are backfilled in this ledger.

## ??????????

### 2026-03-23 ????????

- ??????
- ???collapse the legacy-stream final payload assembly into the orchestration backend so the workflow facade keeps only legacy iteration, postprocess choice, and terminal emit semantics.

### 2026-03-23 ??????????

- ?????
- ???added `prepare_stream_legacy_terminal_payload` in the orchestration backend and refactored the legacy final branch to reuse it while preserving prompt trace propagation, final payload shape, and route metric semantics.

### 2026-03-23 ????????????

- Updated `writing_agent/workflows/orchestration_backend.py`: added `prepare_stream_legacy_terminal_payload` to centralize legacy final payload assembly, legacy graph meta construction, prompt trace attachment, and route metric metadata synchronization.
- Updated `writing_agent/workflows/generate_stream_request_workflow.py`: the legacy final branch now reuses the shared backend helper and drops inline legacy graph meta / prompt trace / route metric payload assembly.
- Updated `tests/unit/test_orchestration_backend.py`: added direct coverage for legacy terminal payload preparation.
- Updated `tests/unit/test_generate_stream_request_workflow.py`: added a route-graph-disabled workflow test covering legacy prompt trace propagation and `route_metric_meta` synchronization.

### 2026-03-23 ??????????

- ???????`.\.venv\Scripts\python -m ruff check writing_agent/workflows/orchestration_backend.py writing_agent/workflows/generate_stream_request_workflow.py tests/unit/test_orchestration_backend.py tests/unit/test_generate_stream_request_workflow.py`
- ?????????
- stream direct tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_stream_request_workflow.py`
- stream direct tests result: `33 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `49 passed`

### 2026-03-23 ??????????

- Phase31 converges legacy-stream terminal payload preparation inside the orchestration backend.
- The stream workflow now keeps legacy iteration and terminal emit semantics, while duplicated legacy graph meta / prompt trace / route metric payload assembly is collapsed behind the shared backend helper.
- ????????????????????????????

## ??????????

- [x] Phase30: consolidate route-graph terminal payload preparation

## ???????

Continue converging route-graph stream terminal payload preparation by moving duplicated payload/meta assembly out of inline branches in `generate_stream_request_workflow.py`:

1. Add a shared backend helper that prepares route-graph terminal payloads and route metric metadata updates for stream final outcomes.
2. Refactor route-graph success and route-graph semantic-failure branches to reuse the shared payload preparation path.
3. Preserve final payload shape, prompt trace attachment semantics, and route-graph regression behavior unchanged.

## ???????????

- [x] Phase30-Step 1: register Phase30 goal and scope in this ledger
- [x] Phase30-Step 2: add a shared helper for route-graph terminal payload preparation
- [x] Phase30-Step 3: refactor route-graph success / semantic-failure branches to reuse the shared helper
- [x] Phase30-Step 4: add focused coverage for prompt trace and semantic-failure payload semantics
- [x] Phase30-Step 5: run stream workflow / route-graph regression tests
- [x] Phase30-Step 6: backfill Phase30 execution records

## ?????????

All conditions below must be satisfied:

1. `orchestration_backend.py` owns the shared route-graph terminal payload preparation helper used by the stream workflow.
2. Route-graph success and semantic-failure branches no longer duplicate graph meta / prompt trace / route metric payload assembly inline.
3. Prompt trace attachment semantics remain correct for both success and semantic-failure payloads.
4. Existing stream fallback and route-graph regression tests keep their semantics unchanged.
5. Phase30 execution records are backfilled in this ledger.

## ?????????

### 2026-03-23 ???????

- ??????
- ???collapse duplicated route-graph final payload preparation inside the orchestration backend so the stream workflow keeps only branch selection, postprocess choice, and final emit semantics.

### 2026-03-23 ?????????

- ?????
- ???added `prepare_stream_route_graph_terminal_payload` in the orchestration backend and refactored route-graph success / semantic-failure branches to reuse it while preserving final emit behavior, prompt trace propagation, and route metric semantics.

### 2026-03-23 ???????????

- Updated `writing_agent/workflows/orchestration_backend.py`: added `prepare_stream_route_graph_terminal_payload` to centralize route-graph terminal payload assembly, prompt-trace attachment, and route-metric metadata synchronization.
- Updated `writing_agent/workflows/generate_stream_request_workflow.py`: route-graph success and semantic-failure branches now reuse the shared payload helper while keeping final emit / timing / metric emission in the workflow facade.
- Updated `tests/unit/test_orchestration_backend.py`: added direct coverage for route-graph success and semantic-failure terminal payload preparation.
- Updated `tests/unit/test_generate_stream_request_workflow.py`: strengthened semantic-failure coverage to assert `prompt_trace` propagation and `route_metric_meta` synchronization.

### 2026-03-23 ?????????

- ???????`.\.venv\Scripts\python -m ruff check writing_agent/workflows/orchestration_backend.py writing_agent/workflows/generate_stream_request_workflow.py tests/unit/test_orchestration_backend.py tests/unit/test_generate_stream_request_workflow.py`
- ?????????
- stream direct tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_stream_request_workflow.py`
- stream direct tests result: `31 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `47 passed`

### 2026-03-23 ?????????

- Phase30 converges route-graph terminal payload preparation inside the orchestration backend.
- The stream workflow now keeps route-graph branch selection, postprocess choice, and final emit semantics, while duplicated graph meta / prompt trace / route metric payload assembly is collapsed behind the shared backend helper.
- ????????????????????????????

## 第十七批后续演进清单

- [x] Phase29: consolidate stream final outcome emission planning

## 第二十九阶段目标

Continue converging stream outcome emission by moving duplicated final-event / timing / metric planning out of inline branches in `generate_stream_request_workflow.py`:

1. Add a shared helper that emits a prepared final payload and records timing / route metrics for stream terminal outcomes.
2. Refactor route-graph success, route-graph semantic-failure, and legacy-graph final branches to reuse the shared outcome emitter.
3. Keep final payload structure, stop behavior, and route-graph regression semantics unchanged.

## 第二十九阶段严格执行步骤

- [x] Phase29-Step 1: register Phase29 goal and scope in this ledger
- [x] Phase29-Step 2: add a shared helper for terminal outcome emission and metric/timing recording
- [x] Phase29-Step 3: refactor route-graph success / semantic-failure / legacy final branches to reuse the shared helper
- [x] Phase29-Step 4: add focused workflow coverage for semantic failure payload semantics
- [x] Phase29-Step 5: run stream workflow / route-graph regression tests
- [x] Phase29-Step 6: backfill Phase29 execution records

## 第二十九阶段完成判定

All conditions below must be satisfied:

1. `generate_stream_request_workflow.py` owns a shared helper for terminal outcome emission.
2. The three terminal branches no longer duplicate final emit + timing + metric recording inline.
3. Existing stream fallback and route-graph regression tests keep their semantics unchanged.
4. Phase29 execution records are backfilled in this ledger.

## 第二十九阶段执行记录

### 2026-03-23 第二十九阶段计划

- 状态：进行中
- 说明：converge duplicated terminal outcome emission and timing / metric recording in the workflow facade because the remaining logic is final-payload specific and tightly coupled to emit semantics.

### 2026-03-23 第二十九阶段执行结果

- 状态：完成
- 说明：added a shared workflow-level `_emit_stream_terminal_outcome` helper and refactored route-graph success, route-graph semantic failure, and legacy final branches to reuse it while preserving payload structure and route metric semantics.

### 2026-03-23 第二十九阶段代码落地记录

- Updated `writing_agent/workflows/generate_stream_request_workflow.py`: added `_emit_stream_terminal_outcome` so terminal success / semantic-failure / legacy-final branches share final emit, timing, and route-metric wiring.
- Updated `tests/unit/test_generate_stream_request_workflow.py`: strengthened semantic-failure coverage to assert `status` and `graph_meta.path` semantics remain unchanged.

### 2026-03-23 第二十九阶段验证记录

- 静态检查命令：`.\.venv\Scripts\python -m ruff check writing_agent/workflows/generate_stream_request_workflow.py tests/unit/test_generate_stream_request_workflow.py`
- 静态检查结果：通过
- workflow focused tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_generate_stream_request_workflow.py`
- workflow focused tests result: `7 passed`
- stream direct tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_stream_request_workflow.py`
- stream direct tests result: `29 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `45 passed`

### 2026-03-23 第二十九阶段范围结论

- Phase29 converges stream terminal outcome emission inside the workflow facade.
- The workflow now focuses more tightly on branch selection and payload preparation, while duplicated terminal emit / timing / metric wiring is collapsed behind a shared helper.
- 当前这份台账中登记的第十七批后续演进清单已全部执行完成。

## 第十六批后续演进清单

- [x] Phase28: consolidate stream recovery branch execution in workflow facade

## 第二十八阶段目标

Continue converging the workflow facade by moving duplicated stream recovery branch execution out of `generate_stream_request_workflow.py` inline branches:

1. Add a shared workflow-level helper to run the single-pass stream recovery driver and apply its emitted outcome.
2. Refactor both fallback branches in `generate_stream_request_workflow.py` to reuse the shared branch helper instead of duplicating driver invocation and applied-result plumbing inline.
3. Keep emitted event order, stop behavior, and route-graph regression semantics unchanged.

## 第二十八阶段严格执行步骤

- [x] Phase28-Step 1: register Phase28 goal and scope in this ledger
- [x] Phase28-Step 2: add a shared workflow-level helper for recovery branch execution
- [x] Phase28-Step 3: refactor both stream recovery branches to reuse the shared helper
- [x] Phase28-Step 4: add focused workflow coverage for branch stop semantics
- [x] Phase28-Step 5: run stream workflow / route-graph regression tests
- [x] Phase28-Step 6: backfill Phase28 execution records

## 第二十八阶段完成判定

All conditions below must be satisfied:

1. `generate_stream_request_workflow.py` owns a shared recovery branch execution helper.
2. The two fallback branches no longer duplicate driver invocation plus outcome application inline.
3. Existing stream fallback and route-graph regression tests keep their semantics unchanged.
4. Phase28 execution records are backfilled in this ledger.

## 第二十八阶段执行记录

### 2026-03-23 第二十八阶段计划

- 状态：进行中
- 说明：converge duplicated recovery-branch driver invocation and applied-result plumbing inside the workflow facade because the remaining logic is emit/return specific rather than backend-specific.

### 2026-03-23 第二十八阶段执行结果

- 状态：完成
- 说明：added a shared workflow-level `_execute_single_pass_stream_recovery_branch` helper and refactored both fallback branches to reuse it while preserving emitted events and stop semantics.

### 2026-03-23 第二十八阶段代码落地记录

- Updated `writing_agent/workflows/generate_stream_request_workflow.py`: added `_execute_single_pass_stream_recovery_branch` so both fallback branches reuse the same driver invocation plus applied-result flow.
- Updated `tests/unit/test_generate_stream_request_workflow.py`: added focused coverage for graph-failure fallback-failure cascading into the insufficient branch while preserving stop semantics.

### 2026-03-23 第二十八阶段验证记录

- 静态检查命令：`.\.venv\Scripts\python -m ruff check writing_agent/workflows/generate_stream_request_workflow.py tests/unit/test_generate_stream_request_workflow.py`
- 静态检查结果：通过
- workflow focused tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_generate_stream_request_workflow.py`
- workflow focused tests result: `7 passed`
- stream direct tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_stream_request_workflow.py`
- stream direct tests result: `29 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `45 passed`

### 2026-03-23 第二十八阶段范围结论

- Phase28 converges the remaining stream recovery branch execution shell inside the workflow facade.
- The workflow now focuses more tightly on high-level branch selection and final return semantics, while duplicated recovery execution plumbing is collapsed behind a shared helper.
- 当前这份台账中登记的第十六批后续演进清单已全部执行完成。

## 第十五批后续演进清单

- [x] Phase27: consolidate stream fallback trigger preparation into backend helpers

## 第二十七阶段目标

Continue separating orchestration backend concerns by moving duplicated stream fallback trigger preparation out of `generate_stream_request_workflow.py`:

1. Extend `writing_agent/workflows/orchestration_backend.py` to own graph-failure and insufficient-output fallback trigger preparation, including trace sync, truncate-reason updates, and route metric payload assembly.
2. Refactor `generate_stream_request_workflow.py` to reuse the shared trigger helpers before invoking the single-pass stream recovery driver.
3. Keep truncate reason semantics, fallback trigger values, metric events, and route-graph regression behavior unchanged.

## 第二十七阶段严格执行步骤

- [x] Phase27-Step 1: register Phase27 goal and scope in this ledger
- [x] Phase27-Step 2: extend orchestration backend helpers for graph-failure and insufficient-output trigger preparation
- [x] Phase27-Step 3: refactor stream workflow trigger branches to reuse the shared helpers
- [x] Phase27-Step 4: add direct unit tests for the new helpers and focused workflow coverage
- [x] Phase27-Step 5: run stream workflow / route-graph regression tests
- [x] Phase27-Step 6: backfill Phase27 execution records

## 第二十七阶段完成判定

All conditions below must be satisfied:

1. `writing_agent/workflows/orchestration_backend.py` owns stream fallback trigger preparation for graph failure and insufficient output.
2. `generate_stream_request_workflow.py` no longer duplicates the two trigger-preparation blocks inline.
3. Existing stream fallback and route-graph regression tests keep their semantics unchanged.
4. Phase27 execution records are backfilled in this ledger.

## 第二十七阶段执行记录

### 2026-03-23 第二十七阶段计划

- 状态：进行中
- 说明：converge duplicated graph-failure and insufficient-output fallback trigger preparation into backend helpers so stream workflow mainly controls trigger ordering and recovery driver invocation.

### 2026-03-23 第二十七阶段执行结果

- 状态：完成
- 说明：added `prepare_stream_graph_failure_fallback_trigger` and `prepare_stream_insufficient_fallback_trigger` in `writing_agent/workflows/orchestration_backend.py` and refactored the workflow to reuse them while preserving fallback trigger values, truncate-reason semantics, and metric events.

### 2026-03-23 第二十七阶段代码落地记录

- Updated `writing_agent/workflows/orchestration_backend.py`: added `prepare_stream_graph_failure_fallback_trigger` and `prepare_stream_insufficient_fallback_trigger` to normalize trigger-side trace sync, truncate reasons, and metric recording.
- Updated `writing_agent/workflows/generate_stream_request_workflow.py`: both fallback trigger branches now reuse shared backend helpers before invoking the recovery driver.
- Updated `tests/unit/test_orchestration_backend.py`: added direct coverage for graph-failure timeout trigger handling and insufficient-output trigger preservation.
- Updated `tests/unit/test_generate_stream_request_workflow.py`: added focused timeout-fallback recovery coverage.

### 2026-03-23 第二十七阶段验证记录

- 静态检查命令：`.\.venv\Scripts\python -m ruff check writing_agent/workflows/orchestration_backend.py writing_agent/workflows/generate_stream_request_workflow.py tests/unit/test_orchestration_backend.py tests/unit/test_generate_stream_request_workflow.py`
- 静态检查结果：通过
- stream direct tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_stream_request_workflow.py`
- stream direct tests result: `28 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `44 passed`

### 2026-03-23 第二十七阶段范围结论

- Phase27 moves stream fallback trigger preparation into shared backend helpers.
- The stream workflow now focuses more tightly on high-level fallback sequencing, recovery driver invocation, and final stop decisions, while trigger-side trace / truncate / metric preparation lives behind backend helpers.
- 当前这份台账中登记的第十五批后续演进清单已全部执行完成。

## 第十四批后续演进清单

- [x] Phase26: consolidate single-pass stream recovery driver orchestration into backend helpers

## 第二十六阶段目标

Continue separating orchestration backend concerns by moving duplicated single-pass stream recovery driver orchestration out of `generate_stream_request_workflow.py`:

1. Extend `writing_agent/workflows/orchestration_backend.py` to own the normalized recovery-driver flow that executes the attempt, finalizes success, and translates recovery failure into an error plan.
2. Refactor both single-pass recovery branches in `generate_stream_request_workflow.py` to reuse the shared driver instead of duplicating the try/except shell around recovery execution.
3. Keep emitted event order, error messages, stop behavior, and route-graph regression semantics unchanged.

## 第二十六阶段严格执行步骤

- [x] Phase26-Step 1: register Phase26 goal and scope in this ledger
- [x] Phase26-Step 2: extend orchestration backend helpers for single-pass stream recovery driver orchestration
- [x] Phase26-Step 3: refactor both stream recovery branches to reuse the shared driver
- [x] Phase26-Step 4: add direct unit tests for the new helper and focused workflow coverage
- [x] Phase26-Step 5: run stream workflow / route-graph regression tests
- [x] Phase26-Step 6: backfill Phase26 execution records

## 第二十六阶段完成判定

All conditions below must be satisfied:

1. `writing_agent/workflows/orchestration_backend.py` owns single-pass stream recovery driver orchestration.
2. `generate_stream_request_workflow.py` no longer duplicates the two try/except shells around recovery execution.
3. Existing stream fallback and route-graph regression tests keep their semantics unchanged.
4. Phase26 execution records are backfilled in this ledger.

## 第二十六阶段执行记录

### 2026-03-23 第二十六阶段计划

- 状态：进行中
- 说明：converge duplicated single-pass stream recovery try/except orchestration into backend helpers so stream workflow mainly controls upstream trigger conditions and final stop decisions.

### 2026-03-23 第二十六阶段执行结果

- 状态：完成
- 说明：added `drive_single_pass_stream_recovery` in `writing_agent/workflows/orchestration_backend.py` and refactored both recovery branches to reuse it while preserving success/failure plans, emitted error messages, and stop behavior.

### 2026-03-23 第二十六阶段代码落地记录

- Updated `writing_agent/workflows/orchestration_backend.py`: added `drive_single_pass_stream_recovery` to normalize recovery attempt execution, success-plan routing, and failure-plan translation.
- Updated `writing_agent/workflows/generate_stream_request_workflow.py`: both recovery branches now reuse a shared recovery driver plus one local outcome applicator instead of duplicating the try/except shell inline.
- Updated `tests/unit/test_orchestration_backend.py`: added direct coverage for driver success and failure mapping.

### 2026-03-23 第二十六阶段验证记录

- 静态检查命令：`.\.venv\Scripts\python -m ruff check writing_agent/workflows/orchestration_backend.py writing_agent/workflows/generate_stream_request_workflow.py tests/unit/test_orchestration_backend.py tests/unit/test_generate_stream_request_workflow.py`
- 静态检查结果：通过
- stream direct tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_stream_request_workflow.py`
- stream direct tests result: `25 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `41 passed`

### 2026-03-23 第二十六阶段范围结论

- Phase26 moves single-pass stream recovery driver orchestration into shared backend helpers.
- The stream workflow now focuses more tightly on upstream fallback trigger conditions, one-pass outcome application, and final stop decisions, while recovery execution branching lives behind a shared backend entrypoint.
- 当前这份台账中登记的第十四批后续演进清单已全部执行完成。

## 第十三批后续演进清单

- [x] Phase25: consolidate single-pass stream fallback success finalization into orchestration backend helpers

## 第二十五阶段目标

Continue separating orchestration backend concerns by moving duplicated single-pass stream fallback success finalization out of `generate_stream_request_workflow.py`:

1. Extend `writing_agent/workflows/orchestration_backend.py` to own normalized success finalization planning for single-pass stream recovery attempts.
2. Refactor both single-pass recovery success branches in `generate_stream_request_workflow.py` to reuse the shared helper instead of duplicating trace sync, terminal wrapping, timing, and fallback-recovered metric planning inline.
3. Keep emitted event order, trace context semantics, and route-graph regression behavior unchanged.

## 第二十五阶段严格执行步骤

- [x] Phase25-Step 1: register Phase25 goal and scope in this ledger
- [x] Phase25-Step 2: extend orchestration backend helpers for single-pass stream fallback success finalization
- [x] Phase25-Step 3: refactor both stream fallback success branches to reuse the shared helper
- [x] Phase25-Step 4: add direct unit tests for the new helper and focused workflow success coverage
- [x] Phase25-Step 5: run stream workflow / route-graph regression tests
- [x] Phase25-Step 6: backfill Phase25 execution records

## 第二十五阶段完成判定

All conditions below must be satisfied:

1. `writing_agent/workflows/orchestration_backend.py` owns single-pass stream fallback success finalization planning.
2. `generate_stream_request_workflow.py` no longer duplicates the two fallback success finalization blocks inline.
3. Existing stream fallback and route-graph regression tests keep their semantics unchanged.
4. Phase25 execution records are backfilled in this ledger.

## 第二十五阶段执行记录

### 2026-03-23 第二十五阶段计划

- 状态：进行中
- 说明：converge duplicated single-pass stream fallback success finalization into orchestration backend helpers so stream workflow mainly controls fallback trigger selection and stop decisions.

### 2026-03-23 第二十五阶段执行结果

- 状态：完成
- 说明：added `prepare_single_pass_stream_recovery_success_plan` in `writing_agent/workflows/orchestration_backend.py` and refactored both fallback success branches to reuse it while preserving trace sync order, terminal wrapping, timing semantics, and route-graph behavior.

### 2026-03-23 第二十五阶段代码落地记录

- Updated `writing_agent/workflows/orchestration_backend.py`: added `prepare_single_pass_stream_recovery_success_plan` to normalize fallback success event assembly, trace sync, and post-emit timing / metric plans.
- Updated `writing_agent/workflows/generate_stream_request_workflow.py`: added a shared success-finalization entrypoint so both fallback success branches reuse the same backend plan instead of duplicating inline completion logic.
- Updated `tests/unit/test_orchestration_backend.py`: added direct coverage for success-plan assembly and trace-aware terminal wrapping.
- Updated `tests/unit/test_generate_stream_request_workflow.py`: added focused insufficient-output-to-single-pass-stream recovery coverage.

### 2026-03-23 第二十五阶段验证记录

- 静态检查命令：`.\.venv\Scripts\python -m ruff check writing_agent/workflows/orchestration_backend.py writing_agent/workflows/generate_stream_request_workflow.py tests/unit/test_orchestration_backend.py tests/unit/test_generate_stream_request_workflow.py`
- 静态检查结果：通过
- stream direct tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_stream_request_workflow.py`
- stream direct tests result: `23 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `39 passed`

### 2026-03-23 第二十五阶段范围结论

- Phase25 moves single-pass stream fallback success finalization into shared orchestration backend helpers.
- The stream workflow now focuses more tightly on fallback trigger selection, exception boundaries, and stop semantics, while fallback success planning lives behind a shared backend entrypoint.
- 当前这份台账中登记的第十三批后续演进清单已全部执行完成。

## 第十二批后续演进清单

- [x] Phase24: consolidate single-pass stream fallback failure handling into orchestration backend helpers

## 第二十四阶段目标

Continue separating orchestration backend concerns by moving duplicated single-pass stream fallback failure handling out of `generate_stream_request_workflow.py`:

1. Extend `writing_agent/workflows/orchestration_backend.py` to own normalized fallback-failure trace / metric / error emission planning for single-pass stream recovery attempts.
2. Refactor both single-pass recovery failure branches in `generate_stream_request_workflow.py` to reuse the shared helper instead of duplicating trace sync, metric recording, and error payload assembly inline.
3. Keep emitted error payloads, stop behavior, and route-graph regression semantics unchanged.

## 第二十四阶段严格执行步骤

- [x] Phase24-Step 1: register Phase24 goal and scope in this ledger
- [x] Phase24-Step 2: extend orchestration backend helpers for single-pass stream fallback failure handling
- [x] Phase24-Step 3: refactor both stream fallback failure branches to reuse the shared helper
- [x] Phase24-Step 4: add direct unit tests for the new helper and focused workflow failure coverage
- [x] Phase24-Step 5: run stream workflow / route-graph regression tests
- [x] Phase24-Step 6: backfill Phase24 execution records

## 第二十四阶段完成判定

All conditions below must be satisfied:

1. `writing_agent/workflows/orchestration_backend.py` owns single-pass stream fallback failure planning.
2. `generate_stream_request_workflow.py` no longer duplicates the two fallback failure handling blocks inline.
3. Existing stream fallback and route-graph regression tests keep their semantics unchanged.
4. Phase24 execution records are backfilled in this ledger.

## 第二十四阶段执行记录

### 2026-03-22 第二十四阶段计划

- 状态：进行中
- 说明：converge duplicated single-pass stream fallback failure handling into orchestration backend helpers so stream workflow mainly controls trigger selection, success ordering, and terminal stop semantics.

### 2026-03-22 第二十四阶段执行结果

- 状态：完成
- 说明：added `handle_single_pass_stream_recovery_failure` in `writing_agent/workflows/orchestration_backend.py` and refactored both fallback failure branches to reuse it while preserving emitted error payloads and stop semantics.

### 2026-03-22 第二十四阶段代码落地记录

- Updated `writing_agent/workflows/orchestration_backend.py`: added `handle_single_pass_stream_recovery_failure` to normalize trace sync, fallback-failed metric recording, and error event planning.
- Updated `writing_agent/workflows/generate_stream_request_workflow.py`: both fallback failure branches now reuse the shared helper instead of duplicating trace / metric / error assembly inline.
- Updated `tests/unit/test_orchestration_backend.py`: added direct coverage for fallback failure handling.
- Updated `tests/unit/test_generate_stream_request_workflow.py`: added focused insufficient-output fallback-failure coverage.

### 2026-03-22 第二十四阶段验证记录

- 静态检查命令：`.\.venv\Scripts\python -m ruff check writing_agent/workflows/orchestration_backend.py writing_agent/workflows/generate_stream_request_workflow.py tests/unit/test_orchestration_backend.py tests/unit/test_generate_stream_request_workflow.py`
- 静态检查结果：通过
- stream direct tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_stream_request_workflow.py`
- stream direct tests result: `21 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `37 passed`

### 2026-03-22 第二十四阶段范围结论

- Phase24 moves single-pass stream fallback failure handling into shared orchestration backend helpers.
- The stream workflow now focuses more tightly on fallback trigger selection, success ordering, metric timing, and terminal stop decisions, while fallback-failure trace / metric / error planning lives behind a shared backend entrypoint.
- 当前这份台账中登记的第十二批后续演进清单已全部执行完成。

## 第十一批后续演进清单

- [x] Phase23: consolidate single-pass stream fallback emission planning into orchestration backend helpers

## 第二十三阶段目标

Continue separating orchestration backend concerns by moving duplicated single-pass stream fallback emission planning out of `generate_stream_request_workflow.py`:

1. Extend `writing_agent/workflows/orchestration_backend.py` to own normalized final emission planning for single-pass stream recovery attempts.
2. Refactor both single-pass recovery branches in `generate_stream_request_workflow.py` to reuse the shared emission-planning helper instead of duplicating post-recovery event assembly inline.
3. Keep emitted delta / section / final ordering and route-graph regression semantics unchanged.

## 第二十三阶段严格执行步骤

- [x] Phase23-Step 1: register Phase23 goal and scope in this ledger
- [x] Phase23-Step 2: extend orchestration backend helpers for single-pass stream recovery emission planning
- [x] Phase23-Step 3: refactor both stream fallback branches to reuse the shared emission-planning helper
- [x] Phase23-Step 4: add direct unit tests for the new helper and focused stream fallback coverage
- [x] Phase23-Step 5: run stream workflow / route-graph regression tests
- [x] Phase23-Step 6: backfill Phase23 execution records

## 第二十三阶段完成判定

All conditions below must be satisfied:

1. `writing_agent/workflows/orchestration_backend.py` owns single-pass stream fallback final emission planning.
2. `generate_stream_request_workflow.py` no longer duplicates the two post-recovery emit sequencing blocks inline.
3. Existing stream fallback and route-graph regression tests keep their semantics unchanged.
4. Phase23 execution records are backfilled in this ledger.

## 第二十三阶段执行记录

### 2026-03-22 第二十三阶段计划

- 状态：进行中
- 说明：converge duplicated single-pass stream fallback emission planning into orchestration backend helpers so stream workflow mainly controls trigger selection, trace sync, and metrics.

### 2026-03-22 第二十三阶段执行结果

- 状态：完成
- 说明：added `prepare_single_pass_stream_recovery_emission_plan` in `writing_agent/workflows/orchestration_backend.py`, kept terminal wrapping at workflow emit time, and refactored both stream fallback branches to reuse the shared emission plan while preserving trace and event-order semantics.

### 2026-03-22 第二十三阶段代码落地记录

- Updated `writing_agent/workflows/orchestration_backend.py`: added `prepare_single_pass_stream_recovery_emission_plan` to split passthrough vs completion events for single-pass stream recovery.
- Updated `writing_agent/workflows/generate_stream_request_workflow.py`: both recovery branches now reuse a shared fallback-attempt helper and only apply `with_terminal` at final emit time after trace sync.
- Updated `tests/unit/test_orchestration_backend.py`: added direct coverage for emission-plan assembly.
- Updated `tests/unit/test_generate_stream_request_workflow.py`: added focused graph-failure-to-single-pass-stream recovery coverage.

### 2026-03-22 第二十三阶段验证记录

- 静态检查命令：`.\.venv\Scripts\python -m ruff check writing_agent/workflows/orchestration_backend.py writing_agent/workflows/generate_stream_request_workflow.py tests/unit/test_orchestration_backend.py tests/unit/test_generate_stream_request_workflow.py`
- 静态检查结果：通过
- stream direct tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_stream_request_workflow.py`
- stream direct tests result: `19 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `35 passed`

### 2026-03-22 第二十三阶段范围结论

- Phase23 moves single-pass stream fallback emission planning into shared orchestration backend helpers while preserving workflow-level trace timing and terminal wrapping order.
- The stream workflow now focuses more tightly on fallback trigger selection, trace synchronization, metric recording, and final event emission timing.
- 当前这份台账中登记的第十一批后续演进清单已全部执行完成。

## 第十批后续演进清单

- [x] Phase22: consolidate single-pass stream fallback execution capture into orchestration backend helpers

## 第二十二阶段目标

Continue separating orchestration backend concerns by moving duplicated single-pass stream fallback execution capture out of `generate_stream_request_workflow.py`:

1. Extend `writing_agent/workflows/orchestration_backend.py` to own heartbeat / section / result capture and recovery preparation for single-pass stream fallback attempts.
2. Refactor both single-pass recovery branches in `generate_stream_request_workflow.py` to reuse the shared recovery runner instead of duplicating event-capture loops inline.
3. Keep emitted delta / section / final ordering and route-graph regression semantics unchanged.

## 第二十二阶段严格执行步骤

- [x] Phase22-Step 1: register Phase22 goal and scope in this ledger
- [x] Phase22-Step 2: extend orchestration backend helpers for single-pass stream fallback execution capture
- [x] Phase22-Step 3: refactor both stream fallback branches to reuse the shared recovery runner
- [x] Phase22-Step 4: add direct unit tests for the new helper
- [x] Phase22-Step 5: run stream workflow / route-graph regression tests
- [x] Phase22-Step 6: backfill Phase22 execution records

## 第二十二阶段完成判定

All conditions below must be satisfied:

1. `writing_agent/workflows/orchestration_backend.py` owns single-pass stream fallback heartbeat / section / result capture plus recovery preparation.
2. `generate_stream_request_workflow.py` no longer duplicates the two single-pass fallback event-capture loops inline.
3. Existing stream fallback and route-graph regression tests keep their semantics unchanged.
4. Phase22 execution records are backfilled in this ledger.

## 第二十二阶段执行记录

### 2026-03-22 第二十二阶段计划

- 状态：进行中
- 说明：converge duplicated single-pass stream fallback execution capture into orchestration backend helpers so stream workflow mainly coordinates trigger conditions and emission ordering.

### 2026-03-22 第二十二阶段执行结果

- 状态：完成
- 说明：added `run_single_pass_stream_recovery` in `writing_agent/workflows/orchestration_backend.py` and refactored both stream fallback branches to reuse it while preserving emitted event order and recovery semantics.

### 2026-03-22 第二十二阶段代码落地记录

- Updated `writing_agent/workflows/orchestration_backend.py`: added `run_single_pass_stream_recovery` for heartbeat / section passthrough normalization, result capture, and recovery payload preparation.
- Updated `writing_agent/workflows/generate_stream_request_workflow.py`: both single-pass recovery branches now reuse the shared recovery runner instead of duplicating fallback stream event loops inline.
- Updated `tests/unit/test_orchestration_backend.py`: added direct coverage for passthrough event capture, recovery handoff, and empty-result behavior.

### 2026-03-22 第二十二阶段验证记录

- 静态检查命令：`.\.venv\Scripts\python -m ruff check writing_agent/workflows/orchestration_backend.py writing_agent/workflows/generate_stream_request_workflow.py tests/unit/test_orchestration_backend.py`
- 静态检查结果：通过
- stream direct tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_stream_request_workflow.py`
- stream direct tests result: `17 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `33 passed`

### 2026-03-22 第二十二阶段范围结论

- Phase22 moves single-pass stream fallback execution capture into shared orchestration backend helpers.
- The stream workflow now focuses more on fallback trigger decisions, trace sync, and emission ordering, while fallback event capture and recovery preparation live behind a shared backend entrypoint.
- 当前这份台账中登记的第十批后续演进清单已全部执行完成。

## 第九批后续演进清单

- [x] Phase21: consolidate single-pass stream fallback success payload assembly into orchestration backend helpers

## 第二十一阶段目标

Continue separating orchestration backend concerns by moving duplicated single-pass stream fallback success payload assembly out of `generate_stream_request_workflow.py`:

1. Extend `writing_agent/workflows/orchestration_backend.py` to own single-pass stream fallback success payload assembly.
2. Refactor both single-pass recovery branches in `generate_stream_request_workflow.py` to reuse the shared helper instead of duplicating postprocess / quality / graph-meta / payload assembly inline.
3. Keep stream fallback output, graph meta, and route-graph regression semantics unchanged.

## 第二十一阶段严格执行步骤

- [x] Phase21-Step 1: register Phase21 goal and scope in this ledger
- [x] Phase21-Step 2: extend orchestration backend helpers for single-pass stream fallback success payload assembly
- [x] Phase21-Step 3: refactor stream fallback recovery branches to reuse the new helper
- [x] Phase21-Step 4: add direct unit tests for the new helper
- [x] Phase21-Step 5: run stream workflow / route-graph regression tests
- [x] Phase21-Step 6: backfill Phase21 execution records

## 第二十一阶段完成判定

All conditions below must be satisfied:

1. `writing_agent/workflows/orchestration_backend.py` owns single-pass stream fallback success payload assembly.
2. `generate_stream_request_workflow.py` no longer duplicates the two fallback success payload assembly blocks inline.
3. Existing stream fallback and route-graph regression tests keep their semantics unchanged.
4. Phase21 execution records are backfilled in this ledger.

## 第二十一阶段执行记录

### 2026-03-22 第二十一阶段计划

- 状态：进行中
- 说明：converge duplicated single-pass stream fallback success payload assembly into orchestration backend helpers so stream workflow only controls branching and emission order.

### 2026-03-22 第二十一阶段执行结果

- 状态：完成
- 说明：added `prepare_single_pass_stream_recovery_result` in `writing_agent/workflows/orchestration_backend.py` and refactored both stream fallback recovery branches to reuse it while preserving output semantics.

### 2026-03-22 第二十一阶段代码落地记录

- Updated `writing_agent/workflows/orchestration_backend.py`: added `prepare_single_pass_stream_recovery_result`.
- Updated `writing_agent/workflows/generate_stream_request_workflow.py`: both single-pass recovery success branches now reuse shared fallback success payload assembly.
- Updated `tests/unit/test_orchestration_backend.py`: added direct coverage for single-pass stream recovery payload assembly.

### 2026-03-22 第二十一阶段验证记录

- 静态检查命令：`.\.venv\Scripts\python -m ruff check writing_agent/workflows/orchestration_backend.py writing_agent/workflows/generate_stream_request_workflow.py tests/unit/test_orchestration_backend.py`
- 静态检查结果：通过
- stream direct tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_stream_request_workflow.py`
- stream direct tests result: `15 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `31 passed`

### 2026-03-22 第二十一阶段范围结论

- Phase21 moves single-pass stream fallback success payload assembly into shared orchestration backend helpers.
- The stream workflow continues converging toward branch control and emission sequencing, while fallback success payload wiring becomes a shared backend concern.
- 当前这份台账中登记的第九批后续演进清单已全部执行完成。

## 第八批后续演进清单

- [x] Phase20: consolidate semantic-failover exemption rules and insufficient-output failover checks into orchestration backend helpers for generate and stream workflows

## 第二十阶段目标

Continue separating orchestration backend concerns by moving duplicated semantic-failover exemption rules and insufficient-output failover checks out of generate / stream workflows:

1. Extend `writing_agent/workflows/orchestration_backend.py` to own semantic-failover exemption rules and trimmed text-length failover checks.
2. Refactor `generate_request_workflow.py` and `generate_stream_request_workflow.py` to reuse those helpers instead of maintaining duplicated rule sets and length checks inline.
3. Keep semantic-failover skip behavior, insufficient-output fallback, and route-graph regression semantics unchanged.

## 第二十阶段严格执行步骤

- [x] Phase20-Step 1: register Phase20 goal and scope in this ledger
- [x] Phase20-Step 2: extend orchestration backend helpers for semantic-failover and insufficient-output checks
- [x] Phase20-Step 3: refactor generate and stream workflows to reuse the new helpers
- [x] Phase20-Step 4: add direct unit tests for the new rule helpers
- [x] Phase20-Step 5: run workflow / route-graph regression tests
- [x] Phase20-Step 6: backfill Phase20 execution records

## 第二十阶段完成判定

All conditions below must be satisfied:

1. `writing_agent/workflows/orchestration_backend.py` owns semantic-failover exemption rules and insufficient-output failover checks.
2. `generate_request_workflow.py` and `generate_stream_request_workflow.py` no longer inline duplicated semantic-failover rule sets and text-length failover checks.
3. Existing semantic-failover, insufficient-output fallback, and route-graph tests keep their semantics unchanged.
4. Phase20 execution records are backfilled in this ledger.

## 第二十阶段执行记录

### 2026-03-22 第二十阶段计划

- 状态：进行中
- 说明：converge duplicated semantic-failover exemption rules and insufficient-output failover checks into orchestration backend helpers so generate / stream workflows share one backend policy surface.

### 2026-03-22 第二十阶段执行结果

- 状态：完成
- 说明：added shared semantic-failover and insufficient-output helpers in `writing_agent/workflows/orchestration_backend.py` and refactored generate / stream workflows to reuse them while preserving fallback behavior.

### 2026-03-22 第二十阶段代码落地记录

- Updated `writing_agent/workflows/orchestration_backend.py`: added `should_skip_semantic_failover` and `text_requires_failover`, plus shared semantic failover reason constants.
- Updated `writing_agent/workflows/generate_request_workflow.py`: semantic-failover exemption and insufficient-output fallback checks now reuse backend helpers.
- Updated `writing_agent/workflows/generate_stream_request_workflow.py`: semantic-failover skip logic and insufficient-output fallback checks now reuse backend helpers.
- Updated `tests/unit/test_orchestration_backend.py`: added direct coverage for semantic-failover exemption matching and trimmed text-length failover checks.

### 2026-03-22 第二十阶段验证记录

- 静态检查命令：`.\.venv\Scripts\python -m ruff check writing_agent/workflows/orchestration_backend.py writing_agent/workflows/generate_request_workflow.py writing_agent/workflows/generate_stream_request_workflow.py tests/unit/test_orchestration_backend.py`
- 静态检查结果：通过
- workflow direct tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py`
- workflow direct tests result: `16 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `30 passed`

### 2026-03-22 第二十阶段范围结论

- Phase20 moves semantic-failover exemption rules and insufficient-output failover checks into shared orchestration backend helpers for both generate and stream workflows.
- Generate and stream workflows continue converging toward pure flow control, while backend recovery policy becomes a separate shared dimension.
- 当前这份台账中登记的第八批后续演进清单已全部执行完成。

## 第七批后续演进清单

- [x] Phase19: consolidate route-graph metric payload assembly into orchestration backend helpers for generate and generate-stream entry points

## 第十九阶段目标

Continue separating orchestration backend concerns by moving duplicated route-graph metric payload assembly out of entry-point code:

1. Extend `writing_agent/workflows/orchestration_backend.py` to own route-graph metric extra payload assembly and metric recorder payload construction.
2. Refactor `generate_request_workflow.py` and `app_v2_generate_stream_runtime.py` to reuse the shared helper instead of assembling route metric payloads inline.
3. Keep route-graph metrics, fallback metrics, and regression semantics unchanged.

## 第十九阶段严格执行步骤

- [x] Phase19-Step 1: register Phase19 goal and scope in this ledger
- [x] Phase19-Step 2: extend orchestration backend helpers for route metric payload assembly
- [x] Phase19-Step 3: refactor generate and generate-stream entry points to reuse the helper
- [x] Phase19-Step 4: add direct unit tests for route metric recorder helper
- [x] Phase19-Step 5: run workflow / route-graph regression tests
- [x] Phase19-Step 6: backfill Phase19 execution records

## 第十九阶段完成判定

All conditions below must be satisfied:

1. `writing_agent/workflows/orchestration_backend.py` owns route metric extra payload assembly and metric recorder payload construction.
2. `generate_request_workflow.py` and `app_v2_generate_stream_runtime.py` no longer inline route metric payload assembly blocks.
3. Existing route-graph and fallback regression tests keep their semantics unchanged.
4. Phase19 execution records are backfilled in this ledger.

## 第十九阶段执行记录

### 2026-03-22 第十九阶段计划

- 状态：进行中
- 说明：converge duplicated route-graph metric payload assembly into orchestration backend helpers so entry points only supply phase-specific inputs.

### 2026-03-22 第十九阶段执行结果

- 状态：完成
- 说明：added route metric assembly helpers in `writing_agent/workflows/orchestration_backend.py` and refactored generate / generate-stream entry points to reuse them while keeping metrics semantics unchanged.

### 2026-03-22 第十九阶段代码落地记录

- Updated `writing_agent/workflows/orchestration_backend.py`: added `build_route_metric_extra` and `record_orchestration_metric`.
- Updated `writing_agent/workflows/generate_request_workflow.py`: `_record_metric` now delegates route-graph metric payload assembly to backend helper.
- Updated `writing_agent/web/app_v2_generate_stream_runtime.py`: `_record_route_metric` now delegates route-graph metric payload assembly to backend helper.
- Updated `tests/unit/test_orchestration_backend.py`: added direct coverage for orchestration metric recorder payload construction.

### 2026-03-22 第十九阶段验证记录

- 静态检查命令：`.\.venv\Scripts\python -m ruff check writing_agent/workflows/orchestration_backend.py writing_agent/workflows/generate_request_workflow.py tests/unit/test_orchestration_backend.py`
- 静态检查结果：通过
- 说明：`writing_agent/web/app_v2_generate_stream_runtime.py` is a bind-style runtime module and is validated via behavioral regression rather than standalone `ruff` due intentionally late-bound symbols.
- workflow direct tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py`
- workflow direct tests result: `14 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `28 passed`

### 2026-03-22 第十九阶段范围结论

- Phase19 moves route-graph metric payload assembly into shared orchestration backend helpers for both generate and generate-stream entry points.
- Entry-point code continues to shrink toward phase-specific orchestration, while metric payload wiring becomes a shared backend concern.
- 当前这份台账中登记的第七批后续演进清单已全部执行完成。

## 第六批后续演进清单

- [x] Phase18: consolidate stream-workflow trace context and route metric synchronization into orchestration backend helpers

## 第十八阶段目标

Continue extracting orchestration-backend wiring details from stream workflow after Phase17 by moving trace and route-metric synchronization into shared helpers:

1. Extend `writing_agent/workflows/orchestration_backend.py` to own `trace_context` synchronization and `route_metric_meta` synchronization helpers.
2. Refactor `generate_stream_request_workflow.py` to reuse these helpers instead of mutating `trace_context` and `route_metric_meta` inline.
3. Keep stream fallback, route-graph recovery, and emitted trace semantics unchanged.

## 第十八阶段严格执行步骤

- [x] Phase18-Step 1: register Phase18 goal and scope in this ledger
- [x] Phase18-Step 2: extend orchestration backend helpers for trace and route metric synchronization
- [x] Phase18-Step 3: refactor stream workflow to reuse the synchronization helpers
- [x] Phase18-Step 4: add direct unit tests for the new synchronization helpers
- [x] Phase18-Step 5: run stream workflow / route-graph regression tests
- [x] Phase18-Step 6: backfill Phase18 execution records

## 第十八阶段完成判定

All conditions below must be satisfied:

1. `writing_agent/workflows/orchestration_backend.py` owns `sync_trace_context` and `sync_route_metric_meta` helpers.
2. `generate_stream_request_workflow.py` no longer inlines those trace / route metric synchronization blocks.
3. Existing stream and route-graph regression tests keep their semantics unchanged.
4. Phase18 execution records are backfilled in this ledger.

## 第十八阶段执行记录

### 2026-03-22 第十八阶段计划

- 状态：进行中
- 说明：continue moving stream-workflow orchestration metadata wiring into shared backend helpers, focusing on `trace_context` and `route_metric_meta` synchronization.

### 2026-03-22 第十八阶段执行结果

- 状态：完成
- 说明：added synchronization helpers in `writing_agent/workflows/orchestration_backend.py` and refactored `generate_stream_request_workflow.py` to reuse them while preserving stream trace semantics.

### 2026-03-22 第十八阶段代码落地记录

- Updated `writing_agent/workflows/orchestration_backend.py`: added `sync_route_metric_meta` and `sync_trace_context`.
- Updated `writing_agent/workflows/generate_stream_request_workflow.py`: removed inline trace / route metric synchronization and replaced them with backend helper calls.
- Updated `tests/unit/test_orchestration_backend.py`: added direct coverage for route metric synchronization and trace context synchronization with preserved fallback trigger semantics.

### 2026-03-22 第十八阶段验证记录

- 静态检查命令：`.\.venv\Scripts\python -m ruff check writing_agent/workflows/orchestration_backend.py writing_agent/workflows/generate_stream_request_workflow.py tests/unit/test_orchestration_backend.py`
- 静态检查结果：通过
- stream direct tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_stream_request_workflow.py`
- stream direct tests result: `11 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `27 passed`

### 2026-03-22 第十八阶段范围结论

- Phase18 moves stream-workflow trace context and route metric synchronization into shared orchestration backend helpers.
- The stream workflow continues to shrink toward pure control-flow semantics, while orchestration-backend state wiring becomes independently evolvable.
- 当前这份台账中登记的第六批后续演进清单已全部执行完成。

## 第五批后续演进清单

- [x] Phase17: consolidate fallback quality snapshot, terminal graph meta, and single-pass failover meta assembly for generate / stream workflows into orchestration backend helpers

## 第十七阶段目标

Continue shrinking workflow-layer backend wiring after Phase16 by moving the remaining fallback metadata assembly into shared backend helpers:

1. Extend `writing_agent/workflows/orchestration_backend.py` to own failover quality snapshot assembly, terminal graph-meta finalization, and single-pass stream failover meta assembly.
2. Refactor `generate_request_workflow.py` and `generate_stream_request_workflow.py` to reuse these helpers instead of assembling fallback metadata inline.
3. Keep fallback recovery, route-graph recovery, and graph metadata semantics unchanged.

## 第十七阶段严格执行步骤

- [x] Phase17-Step 1: register Phase17 goal and scope in this ledger
- [x] Phase17-Step 2: extend orchestration backend helpers for fallback metadata assembly
- [x] Phase17-Step 3: refactor generate / stream workflows to reuse the new helpers
- [x] Phase17-Step 4: add direct unit tests for fallback metadata helpers
- [x] Phase17-Step 5: run workflow / route-graph regression tests
- [x] Phase17-Step 6: backfill Phase17 execution records

## 第十七阶段完成判定

All conditions below must be satisfied:

1. `writing_agent/workflows/orchestration_backend.py` owns fallback quality snapshot assembly, terminal graph-meta finalization, and single-pass stream failover meta construction.
2. `generate_request_workflow.py` and `generate_stream_request_workflow.py` no longer inline those fallback metadata assembly blocks.
3. Existing fallback and route-graph regression tests keep their semantics unchanged.
4. Phase17 execution records are backfilled in this ledger.

## 第十七阶段执行记录

### 2026-03-22 第十七阶段计划

- 状态：进行中
- 说明：continue extracting backend-oriented fallback metadata assembly from generate / stream workflows into reusable orchestration backend helpers.

### 2026-03-22 第十七阶段执行结果

- 状态：完成
- 说明：extended `writing_agent/workflows/orchestration_backend.py` with fallback metadata helpers and refactored generate / stream workflows to reuse them without changing recovery semantics.

### 2026-03-22 第十七阶段代码落地记录

- Updated `writing_agent/workflows/orchestration_backend.py`: added `build_failover_quality_snapshot`, `finalize_graph_meta`, and `build_single_pass_failover_meta`.
- Updated `writing_agent/workflows/generate_request_workflow.py`: fallback quality snapshot assembly and final terminal graph-meta assembly now reuse backend helpers.
- Updated `writing_agent/workflows/generate_stream_request_workflow.py`: both single-pass fallback branches now reuse shared single-pass failover meta assembly.
- Updated `tests/unit/test_orchestration_backend.py`: direct coverage added for fallback quality snapshot, terminal graph-meta finalization, and single-pass failover meta assembly.

### 2026-03-22 第十七阶段验证记录

- 静态检查命令：`.\.venv\Scripts\python -m ruff check writing_agent/workflows/orchestration_backend.py writing_agent/workflows/generate_request_workflow.py writing_agent/workflows/generate_stream_request_workflow.py tests/unit/test_orchestration_backend.py`
- 静态检查结果：通过
- workflow direct tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py`
- workflow direct tests result: `11 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `25 passed`

### 2026-03-22 第十七阶段范围结论

- Phase17 consolidates the remaining backend-oriented fallback metadata assembly for generate / stream workflows into shared orchestration backend helpers.
- The workflow layer becomes thinner and more strictly focused on control flow, while backend metadata wiring continues to converge into a separate orthogonal dimension.
- 当前这份台账中登记的第五批后续演进清单已全部执行完成。

## 第四批后续演进清单

- [x] Phase16: consolidate orchestration backend selection and route-graph metadata assembly for generate / stream / section workflows into standalone backend module

## 第十六阶段目标

Continue separating orchestration backend concerns from business capabilities within the workflow layer:

1. Add `writing_agent/workflows/orchestration_backend.py` to own route-graph enable checks, dual-engine call argument assembly, and route-graph metadata construction.
2. Refactor `generate_request_workflow.py`, `generate_stream_request_workflow.py`, and `generate_section_request_workflow.py` to reuse the backend module instead of duplicating backend selection and route-graph metadata logic inline.
3. Keep route-graph / legacy-graph behavior and regression semantics unchanged.

## 第十六阶段严格执行步骤

- [x] Phase16-Step 1: register Phase16 goal and scope in this ledger
- [x] Phase16-Step 2: add orchestration backend module for backend selection and metadata assembly
- [x] Phase16-Step 3: refactor generate / stream / section workflows to reuse the module
- [x] Phase16-Step 4: add direct unit tests for orchestration backend helpers
- [x] Phase16-Step 5: run workflow / route-graph regression tests
- [x] Phase16-Step 6: backfill Phase16 execution records

## 第十六阶段完成判定

All conditions below must be satisfied:

1. `writing_agent/workflows/orchestration_backend.py` owns route-graph enable checks, backend call argument assembly, prompt-trace normalization, and graph metadata builders.
2. `generate_request_workflow.py`, `generate_stream_request_workflow.py`, and `generate_section_request_workflow.py` no longer inline repeated backend selection / route-graph metadata assembly blocks.
3. Existing workflow and route-graph tests keep their semantics unchanged.
4. Phase16 execution records are backfilled in this ledger.

## 第十六阶段执行记录

### 2026-03-22 第十六阶段计划

- 状态：进行中
- 说明：extract duplicated orchestration-backend selection and route-graph metadata assembly from workflow layer into a dedicated backend helper module.

### 2026-03-22 第十六阶段执行结果

- 状态：完成
- 说明：added `writing_agent/workflows/orchestration_backend.py`, refactored generate / stream / section workflows to reuse it, and added direct tests plus workflow regressions.

### 2026-03-22 第十六阶段代码落地记录

- Added `writing_agent/workflows/orchestration_backend.py`: `route_graph_enabled`, `build_route_graph_kwargs`, `normalize_prompt_trace`, `attach_prompt_trace`, `build_route_graph_meta`, and `build_legacy_graph_meta`.
- Updated `writing_agent/workflows/generate_request_workflow.py`: replaced inline route-graph enable checks, dual-engine kwargs assembly, and route-graph metadata construction with backend helper reuse.
- Updated `writing_agent/workflows/generate_stream_request_workflow.py`: replaced duplicated backend selection and route/legacy graph metadata assembly with backend helper reuse.
- Updated `writing_agent/workflows/generate_section_request_workflow.py`: route-graph selection and kwargs/meta assembly now reuse the backend helper module.
- Added `tests/unit/test_orchestration_backend.py`: direct coverage for backend flag resolution, call argument assembly, prompt-trace normalization, and graph metadata builders.

### 2026-03-22 第十六阶段验证记录

- 静态检查命令：`.\.venv\Scripts\python -m ruff check writing_agent/workflows/orchestration_backend.py writing_agent/workflows/generate_request_workflow.py writing_agent/workflows/generate_stream_request_workflow.py writing_agent/workflows/generate_section_request_workflow.py tests/unit/test_orchestration_backend.py`
- 静态检查结果：通过
- workflow direct tests command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py`
- workflow direct tests result: `10 passed`
- route-graph regression command: `.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- route-graph regression result: `12 passed`
- combined regression command: `.\.venv\Scripts\python -m pytest -q tests/unit/test_orchestration_backend.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/test_generation_route_graph.py`
- combined regression result: `22 passed`

### 2026-03-22 第十六阶段范围结论

- Phase16 moves workflow-layer orchestration-backend selection and route-graph metadata assembly into a dedicated backend helper module.
- The workflow layer now stays focused on orchestration flow semantics, while backend wiring becomes a separate, orthogonal dimension.
- 当前这份台账中登记的第四批后续演进清单已全部执行完成。

## 第三批后续演进清单

- [x] Phase13：将 `MCP citations / RAG 检索` 逻辑从 `app_v2_generation_helpers_runtime.py` 下沉到 `capabilities/mcp_retrieval.py`
- [x] Phase14：将“生成策略决策”逻辑从 `app_v2_generation_helpers_runtime.py` 下沉到 `capabilities/generation_policy.py`
- [x] Phase15：将“模型就绪 / 拉取 / 超时韧性”逻辑从 `app_v2_generation_helpers_runtime.py` 下沉到独立运行时支持模块

## 第十五阶段目标

继续压缩 helper runtime 中的基础运行时工具实现：

1. 将 `_recommended_stream_timeouts`、`_run_with_heartbeat`、`_pull_model_stream_iter`、`_pull_model_stream`、`_ensure_ollama_ready_iter`、`_ensure_ollama_ready` 迁移到独立运行时支持模块。
2. 保持 `app_v2` 旧导出函数名与 monkeypatch 点位不变。
3. 保持 generate / stream / format-only 相关测试语义不变。

## 第十五阶段严格执行步骤

- [x] Phase15-Step 1：在本文档登记第十五阶段目标与范围
- [x] Phase15-Step 2：新增运行时支持模块并迁移模型就绪 / 拉取 / 超时逻辑
- [x] Phase15-Step 3：将 helper runtime 中对应入口改为薄包装
- [x] Phase15-Step 4：补充运行时支持模块直接单测
- [x] Phase15-Step 5：运行 generate / stream 相关回归测试
- [x] Phase15-Step 6：回填第十五阶段执行记录

## 第十五阶段完成判定

以下条件全部满足才算完成：

1. `writing_agent/web/model_runtime_support.py` 承接模型就绪、模型拉取与超时韧性运行时逻辑。
2. `app_v2_generation_helpers_runtime.py` 中对应入口改为薄包装。
3. `app_v2` 旧导出函数名与 monkeypatch 点位保持不变。
4. 第十五阶段执行记录完成回填。

## 第十五阶段执行记录

### 2026-03-22 第十五阶段计划

- 状态：进行中
- 说明：将模型就绪 / 模型拉取 / 超时韧性逻辑从 helper runtime 迁出到独立运行时支持模块，继续收缩运行时编排文件。

### 2026-03-22 第十五阶段执行结果

- 状态：完成
- 说明：已新增 `writing_agent/web/model_runtime_support.py` 承接模型就绪、模型拉取与超时韧性逻辑，`app_v2_generation_helpers_runtime.py` 对应入口改为薄包装，并补齐直接单测。

### 2026-03-22 第十五阶段代码落地记录

- 新增 `writing_agent/web/model_runtime_support.py`：承接 `recommended_stream_timeouts`、`run_with_heartbeat`、`pull_model_stream_iter`、`pull_model_stream`、`ensure_ollama_ready_iter`、`ensure_ollama_ready`。
- 更新 `writing_agent/web/app_v2_generation_helpers_runtime.py`：`_recommended_stream_timeouts`、`_run_with_heartbeat`、`_pull_model_stream_iter`、`_pull_model_stream`、`_ensure_ollama_ready_iter`、`_ensure_ollama_ready` 改为薄包装。
- 新增 `tests/unit/test_model_runtime_support.py`：直接覆盖超时推荐、heartbeat 回传、模型拉取流式状态、模型就绪探测与启动语义。
- 更新 `tests/test_format_only_guard.py`：将 `test_generate_uses_session_text_when_request_text_is_empty` 的 graph stub 文本补足到非回退阈值以上，避免误触发真实 single-pass fallback，稳定组合回归。

### 2026-03-22 第十五阶段验证记录

- 静态检查命令：`.\.venv\Scripts\python -m ruff check writing_agent/web/model_runtime_support.py tests/unit/test_model_runtime_support.py tests/test_format_only_guard.py`
- 静态检查结果：通过
- 运行时支持模块单测命令：`.\.venv\Scripts\python -m pytest -q tests/unit/test_model_runtime_support.py`
- 运行时支持模块单测结果：`7 passed`
- generate / stream 定向回归命令 1：`.\.venv\Scripts\python -m pytest -q tests/test_generation_route_graph.py`
- generate / stream 定向回归结果 1：`12 passed`
- generate / stream 定向回归命令 2：`.\.venv\Scripts\python -m pytest -q tests/test_selected_revision_error_reporting.py`
- generate / stream 定向回归结果 2：`2 passed`
- generate / stream 定向回归命令 3：`.\.venv\Scripts\python -m pytest -q tests/test_selected_revision_payload_flow.py`
- generate / stream 定向回归结果 3：`2 passed`
- generate / stream 定向回归命令 4：`.\.venv\Scripts\python -m pytest -q tests/test_format_only_guard.py -k "not export_html_escapes_dangerous_text"`
- generate / stream 定向回归结果 4：`13 passed, 1 deselected`
- 组合回归命令：`.\.venv\Scripts\python -m pytest -q tests/unit/test_model_runtime_support.py tests/test_generation_route_graph.py tests/test_selected_revision_error_reporting.py tests/test_selected_revision_payload_flow.py tests/test_format_only_guard.py -k "not export_html_escapes_dangerous_text"`
- 组合回归结果：`36 passed, 1 deselected`

### 2026-03-22 第十五阶段范围结论

- 第十五阶段已将“模型就绪 / 拉取 / 超时韧性”运行时逻辑迁出 helper runtime。
- `app_v2_generation_helpers_runtime.py` 进一步收敛为“运行时装配 / 兼容包装”层。
- 当前这份台账中登记的第三批后续演进清单已全部执行完成。
## 第十四阶段目标

继续压缩 helper runtime 中的决策型业务逻辑：

1. 将 `_system_pressure_high`、`_should_use_fast_generate`、`_summarize_analysis` 下沉到 capability 层。
2. 保持 `app_v2` 旧导出函数名与 monkeypatch 点位不变。
3. 保持 generate / stream / format-only 相关测试语义不变。

## 第十四阶段严格执行步骤

- [x] Phase14-Step 1：在本文档登记第十四阶段目标与范围
- [x] Phase14-Step 2：新增 generation policy capability
- [x] Phase14-Step 3：将 helper runtime 中相关入口改为薄包装
- [x] Phase14-Step 4：补充 capability 直接单测
- [x] Phase14-Step 5：运行 generate / stream 相关回归测试
- [x] Phase14-Step 6：回填第十四阶段执行记录

## 第十四阶段完成判定

以下条件全部满足才算完成：

1. `capabilities/generation_policy.py` 承接 `_system_pressure_high`、`_should_use_fast_generate`、`_summarize_analysis` 逻辑。
2. `app_v2_generation_helpers_runtime.py` 中对应入口改为薄包装。
3. `app_v2` 旧导出函数名与 monkeypatch 点位保持不变。
4. 第十四阶段执行记录完成回填。

## 第十四阶段执行记录

### 2026-03-21 第十四阶段计划

- 状态：进行中
- 说明：将“生成策略决策”逻辑从 helper runtime 下沉到 capability 层，继续压缩运行时文件中的业务决策实现。

### 2026-03-21 第十四阶段执行结果

- 状态：完成
- 说明：已新增 `capabilities/generation_policy.py` 承接系统压力判断、fast generate 决策与分析摘要逻辑，`app_v2_generation_helpers_runtime.py` 改为薄包装。

### 2026-03-21 第十四阶段代码落地记录

- 新增 `writing_agent/capabilities/generation_policy.py`：承接 `system_pressure_high`、`should_use_fast_generate`、`summarize_analysis`。
- 更新 `writing_agent/web/app_v2_generation_helpers_runtime.py`：`_system_pressure_high`、`_should_use_fast_generate`、`_summarize_analysis` 改为薄包装。
- 更新 `writing_agent/capabilities/__init__.py`：导出 generation policy 能力入口。
- 新增 `tests/unit/test_generation_policy_capability.py`：直接覆盖系统压力阈值、fast generate 决策与分析摘要输出。

### 2026-03-21 第十四阶段验证记录

- 静态检查命令：`.\.venv\Scripts\python -m ruff check writing_agent/capabilities/__init__.py writing_agent/capabilities/generation_policy.py tests/unit/test_generation_policy_capability.py`
- 静态检查结果：通过
- generate / stream 相关回归命令：`.\.venv\Scripts\python -m pytest -q tests/unit/test_generation_policy_capability.py tests/test_generation_route_graph.py tests/test_selected_revision_error_reporting.py tests/test_selected_revision_payload_flow.py tests/test_format_only_guard.py -k "not export_html_escapes_dangerous_text"`
- generate / stream 相关回归结果：`32 passed, 1 deselected`
- 组合回归命令：`.\.venv\Scripts\python -m pytest -q tests/unit/test_dual_graph_engine.py tests/unit/test_generate_workflow.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_revision_request_workflow.py tests/unit/test_editing_request_workflow.py tests/unit/test_editing_capability.py tests/unit/test_diagramming_capability.py tests/unit/test_fallback_generation_capability.py tests/unit/test_generation_quality_capability.py tests/unit/test_mcp_retrieval_capability.py tests/unit/test_generation_policy_capability.py tests/unit/test_generation_semantic_failover.py tests/unit/test_plan_confirm_flow.py tests/unit/test_inline_context_policy.py tests/test_generation_route_graph.py tests/test_revise_doc_constraints.py tests/test_inline_ai_stream_context_meta.py tests/test_diagram_generate_constraints.py tests/test_generation_fallback_prompt_constraints.py tests/test_flow_router_registration.py tests/test_selected_revision_error_reporting.py tests/test_selected_revision_payload_flow.py tests/integration/test_node_backend_generation_path.py`
- 组合回归结果：`75 passed`

### 2026-03-21 第十四阶段范围结论

- 第十四阶段已将“生成策略决策”业务能力迁出 helper runtime。
- `app_v2_generation_helpers_runtime.py` 继续向“运行时装配 / 环境桥接”收敛。
- 当前这份台账中登记的第三批后续演进清单已全部执行完成。

## 第十三阶段目标

继续压缩生成 helper runtime 中的业务能力泄漏：

1. 将 `MCP citations` 缓存加载与会话注入逻辑下沉到 capability 层。
2. 将 `mcp rag search / retrieve / search_chunks` URI 组装与结果解析逻辑下沉到 capability 层。
3. 保持 `app_v2._ensure_mcp_citations`、`app_v2._mcp_rag_search`、`app_v2._mcp_rag_retrieve`、`app_v2._mcp_rag_search_chunks` 对外签名不变。

## 第十三阶段严格执行步骤

- [x] Phase13-Step 1：在本文档登记第十三阶段目标与范围
- [x] Phase13-Step 2：新增 MCP retrieval capability
- [x] Phase13-Step 3：将 helper runtime 中 citations / rag 检索入口改为薄包装
- [x] Phase13-Step 4：补充 capability 直接单测
- [x] Phase13-Step 5：运行 rag / document 相关回归测试
- [x] Phase13-Step 6：回填第十三阶段执行记录

## 第十三阶段完成判定

以下条件全部满足才算完成：

1. `capabilities/mcp_retrieval.py` 承接 `MCP citations` 缓存加载 / 会话注入与 `mcp rag` URI 组装 / 结果解析逻辑。
2. `app_v2_generation_helpers_runtime.py` 中相关入口改为薄包装。
3. `app_v2` 旧导出函数名保持不变。
4. 第十三阶段执行记录完成回填。

## 第十三阶段执行记录

### 2026-03-21 第十三阶段计划

- 状态：进行中
- 说明：将 `MCP citations / RAG 检索` 逻辑从 helper runtime 下沉到 capability 层，进一步压缩运行时文件中的业务实现。

### 2026-03-21 第十三阶段执行结果

- 状态：完成
- 说明：已新增 `capabilities/mcp_retrieval.py` 承接 citations 缓存 / 注入与 rag URI 组装 / 结果解析逻辑，`app_v2_generation_helpers_runtime.py` 改为薄包装。

### 2026-03-21 第十三阶段代码落地记录

- 新增 `writing_agent/capabilities/mcp_retrieval.py`：承接 `mcp_first_json`、`mcp_rag_enabled`、`load_mcp_citations_cached`、`ensure_mcp_citations`、`mcp_rag_search`、`mcp_rag_retrieve`、`mcp_rag_search_chunks`。
- 更新 `writing_agent/web/app_v2_generation_helpers_runtime.py`：`_load_mcp_citations_cached`、`_ensure_mcp_citations`、`_mcp_rag_enabled`、`_mcp_first_json`、`_mcp_rag_search`、`_mcp_rag_retrieve`、`_mcp_rag_search_chunks` 改为薄包装。
- 更新 `writing_agent/capabilities/__init__.py`：导出 MCP retrieval 能力入口。
- 新增 `tests/unit/test_mcp_retrieval_capability.py`：直接覆盖 citations 缓存 / 注入与 rag URI 组装语义。

### 2026-03-21 第十三阶段验证记录

- 静态检查命令：`.\.venv\Scripts\python -m ruff check writing_agent/capabilities/__init__.py writing_agent/capabilities/mcp_retrieval.py tests/unit/test_mcp_retrieval_capability.py`
- 静态检查结果：通过
- rag / document 定向回归命令：`.\.venv\Scripts\python -m pytest -q tests/unit/test_mcp_retrieval_capability.py tests/test_flow_router_registration.py`
- rag / document 定向回归结果：`4 passed`
- 组合回归命令：`.\.venv\Scripts\python -m pytest -q tests/unit/test_dual_graph_engine.py tests/unit/test_generate_workflow.py tests/unit/test_generate_request_workflow.py tests/unit/test_generate_section_request_workflow.py tests/unit/test_generate_stream_request_workflow.py tests/unit/test_revision_request_workflow.py tests/unit/test_editing_request_workflow.py tests/unit/test_editing_capability.py tests/unit/test_diagramming_capability.py tests/unit/test_fallback_generation_capability.py tests/unit/test_generation_quality_capability.py tests/unit/test_mcp_retrieval_capability.py tests/unit/test_generation_semantic_failover.py tests/unit/test_plan_confirm_flow.py tests/unit/test_inline_context_policy.py tests/test_generation_route_graph.py tests/test_revise_doc_constraints.py tests/test_inline_ai_stream_context_meta.py tests/test_diagram_generate_constraints.py tests/test_generation_fallback_prompt_constraints.py tests/test_flow_router_registration.py tests/integration/test_node_backend_generation_path.py`
- 组合回归结果：`68 passed`

### 2026-03-21 第十三阶段范围结论

- 第十三阶段已将 `MCP citations / RAG 检索` 业务能力迁出 helper runtime。
- `app_v2_generation_helpers_runtime.py` 继续向“运行时装配 / 环境桥接”收敛。
- 当前这份台账中登记的第三批后续演进清单已全部执行完成。



