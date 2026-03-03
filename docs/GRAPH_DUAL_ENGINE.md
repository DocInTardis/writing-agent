# Graph Dual Engine

Implemented runtime components:

- `writing_agent/state_engine/graph_contracts.py`
- `writing_agent/state_engine/dual_engine.py`
- `writing_agent/state_engine/checkpoint_store.py`
- `writing_agent/state_engine/replay.py`
- `writing_agent/v2/graph_runner.py::run_generate_graph_dual_engine`

Capabilities:

- Explicit node/edge/route contracts
- Typed state with schema version
- chapter-level checkpoint save/resume
- deterministic replay from event log
- trace/span/node metadata per node event
- human-in-the-loop interrupt hook per node
- route entries for compose_mode/resume_sections/format_only
- route-driven entry branching (qa-only / writer-start / planner-full)
- optional LangGraph backend (`WRITING_AGENT_GRAPH_ENGINE=langgraph|dual|auto`)
- route observability metadata (`trace_id` / `engine` / `route_id` / `route_entry`) returned as `graph_meta` on route-graph API path
- workbench diagnostics chip and thought log consume `graph_meta` for online route tracing
- route/fallback metrics (JSONL): `WRITING_AGENT_ROUTE_GRAPH_METRICS_ENABLE`, `WRITING_AGENT_ROUTE_GRAPH_METRICS_PATH`
- failure injection switches (test-only): `WRITING_AGENT_FAIL_INJECT_ROUTE_GRAPH`, `WRITING_AGENT_FAIL_INJECT_ROUTE_GRAPH_PHASES`, `WRITING_AGENT_FAIL_INJECT_SELECTED_REVISION_REFINE`
