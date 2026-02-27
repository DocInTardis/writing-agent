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
- optional LangGraph backend (`WRITING_AGENT_GRAPH_ENGINE=langgraph|dual|auto`)
