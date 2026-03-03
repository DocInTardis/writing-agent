# 提交前整理清单（2026-03-03）

## 1. 当前状态

本轮改动覆盖三条主线：

1. route-driven graph 分流与可观测性（`graph_meta`）全链路落地。
2. selected revision / inline AI 的结构化约束与上下文策略强化。
3. legacy `/studio` 流式链路的 strict JSON + fail-closed 收口。

已完成全量回归：

- `python -m pytest -q tests` -> `429 passed, 1 skipped`
- 前端构建：`cmd /c npm --prefix writing_agent\web\frontend_svelte run -s build` -> pass

## 2. 推荐提交策略

### 方案 A（推荐）：1 个整合提交

适用场景：当前改动跨多个核心文件，部分文件同时承载多条主线（例如 `generation_service.py`、`app_v2_generate_stream_runtime.py`），单提交能避免拆分时遗漏依赖。

建议 commit message：

```text
feat: land route-driven branching, constrained revision flows, and legacy studio fail-closed guards
```

建议 body：

```text
- implement route-driven entry branching in dual engine and wire generate/generate-stream/section through route graph switch
- return graph_meta (trace_id/engine/route_id/route_entry) on route-graph path and surface it in Svelte workbench diagnostics
- harden selected revision and inline-ai flows with tagged prompts, strict JSON parsing, retry-once, and context policy propagation
- harden legacy /studio stream worker/aggregator with strict JSON retry and fail-closed fallback; fix h2 split regex boundary bug
- add regression coverage for route graph fallback/shortcut semantics, graph_meta visibility, selected-revision diagnostics, and studio stream constraints
- update architecture/API docs to reflect new contracts and rollout plan
```

### 方案 B：按主题拆成 3 个提交

适用场景：你希望后续回滚粒度更细。

提交 1（route graph 主线）：

```text
feat(route-graph): add route-driven execution and graph_meta observability across generate flows
```

提交 2（selected revision / inline-ai 约束）：

```text
feat(revision): enforce structured selected-edit and inline-ai context-policy guards
```

提交 3（legacy studio 收口）：

```text
fix(studio): enforce strict-json fail-closed behavior in legacy stream pipeline
```

## 3. 关键文件分组（供 git add 参考）

### route graph + graph_meta

- `docs/API_SCHEMA_AND_ERRORS.md`
- `docs/GRAPH_DUAL_ENGINE.md`
- `docs/INDEX.md`
- `docs/ROUTE_DRIVEN_BRANCHING_IMPLEMENTATION_20260303_CN.md`
- `writing_agent/state_engine/graph_contracts.py`
- `writing_agent/state_engine/dual_engine.py`
- `writing_agent/v2/graph_runner.py`
- `writing_agent/web/app_v2.py`
- `writing_agent/web/app_v2_generate_stream_runtime.py`
- `writing_agent/web/services/generation_service.py`
- `writing_agent/web/contracts.py`
- `writing_agent/web/frontend_svelte/src/AppWorkbench.svelte`
- `writing_agent/web/static/v2_svelte/main.js`
- `tests/unit/test_dual_graph_engine.py`
- `tests/test_generation_route_graph.py`
- `tests/ui/test_workbench_svelte.py`

### selected revision + inline-ai

- `docs/SELECTED_TEXT_EDIT_OPTIMIZATION_STRATEGY_20260301_CN.md`
- `writing_agent/web/domains/revision_edit_runtime_domain.py`
- `writing_agent/web/app_v2_textops_runtime_part1.py`
- `writing_agent/web/api/editing_flow.py`
- `writing_agent/v2/inline_ai.py`
- `writing_agent/web/static/v2_legacy_runtime.js`
- `tests/test_inline_ai_parameter_passthrough.py`
- `tests/test_inline_ai_stream_context_meta.py`
- `tests/test_revise_doc_constraints.py`
- `tests/test_selected_revision_error_reporting.py`
- `tests/test_selected_revision_payload_flow.py`
- `tests/unit/test_dynamic_questions_constraints.py`
- `tests/unit/test_inline_ai_guard.py`
- `tests/unit/test_inline_context_policy.py`
- `tests/unit/test_selected_revision_metrics.py`
- `tests/unit/test_selected_revision_strategy.py`

### legacy /studio hardening

- `writing_agent/agents/document_edit.py`
- `writing_agent/web/app.py`
- `tests/unit/test_document_edit_agent_constraints.py`
- `tests/test_studio_stream_constraints.py`

## 4. 执行命令模板

整合提交（方案 A）：

```powershell
git add docs writing_agent tests
git commit -m "feat: land route-driven branching, constrained revision flows, and legacy studio fail-closed guards"
```

按主题拆分（方案 B）示例：

```powershell
# commit 1
git add docs/API_SCHEMA_AND_ERRORS.md docs/GRAPH_DUAL_ENGINE.md docs/INDEX.md docs/ROUTE_DRIVEN_BRANCHING_IMPLEMENTATION_20260303_CN.md
git add writing_agent/state_engine/graph_contracts.py writing_agent/state_engine/dual_engine.py writing_agent/v2/graph_runner.py
git add writing_agent/web/app_v2.py writing_agent/web/app_v2_generate_stream_runtime.py writing_agent/web/services/generation_service.py writing_agent/web/contracts.py
git add writing_agent/web/frontend_svelte/src/AppWorkbench.svelte writing_agent/web/static/v2_svelte/main.js
git add tests/unit/test_dual_graph_engine.py tests/test_generation_route_graph.py tests/ui/test_workbench_svelte.py
git commit -m "feat(route-graph): add route-driven execution and graph_meta observability across generate flows"

# commit 2
git add docs/SELECTED_TEXT_EDIT_OPTIMIZATION_STRATEGY_20260301_CN.md
git add writing_agent/web/domains/revision_edit_runtime_domain.py writing_agent/web/app_v2_textops_runtime_part1.py writing_agent/web/api/editing_flow.py writing_agent/v2/inline_ai.py writing_agent/web/static/v2_legacy_runtime.js
git add tests/test_inline_ai_parameter_passthrough.py tests/test_inline_ai_stream_context_meta.py tests/test_revise_doc_constraints.py tests/test_selected_revision_error_reporting.py tests/test_selected_revision_payload_flow.py
git add tests/unit/test_dynamic_questions_constraints.py tests/unit/test_inline_ai_guard.py tests/unit/test_inline_context_policy.py tests/unit/test_selected_revision_metrics.py tests/unit/test_selected_revision_strategy.py
git commit -m "feat(revision): enforce structured selected-edit and inline-ai context-policy guards"

# commit 3
git add writing_agent/agents/document_edit.py writing_agent/web/app.py tests/unit/test_document_edit_agent_constraints.py tests/test_studio_stream_constraints.py
git commit -m "fix(studio): enforce strict-json fail-closed behavior in legacy stream pipeline"
```
