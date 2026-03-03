# API Schema And Error Codes

Canonical schema models are defined in:

- `writing_agent/web/contracts.py`

Error code enum:

- `BAD_REQUEST`
- `NOT_FOUND`
- `CONFLICT`
- `FORBIDDEN`
- `INTERNAL_ERROR`
- `TIMEOUT`

All new v1 endpoints should return `ok` + typed payload or `APIError`.

## Generate Response Contract

Applies to:

- `POST /api/doc/{doc_id}/generate`
- `POST /api/doc/{doc_id}/generate/section`
- `POST /api/doc/{doc_id}/generate/stream` final event payload

Core fields:

- `ok: 1`
- `text: string`
- `problems: string[]`
- `doc_ir: object`

Optional diagnostic fields:

- `revision_meta: object`
  - Present when selected-text revision flow is evaluated (including miss + fallback diagnostics).
- `graph_meta: object`
  - Present only when route-graph path is used (`WRITING_AGENT_USE_ROUTE_GRAPH=1` and dual-engine path is taken).
  - Omitted on legacy graph and shortcut branches to avoid false positives.

`graph_meta` shape:

- `path: "route_graph"`
- `trace_id: string`
- `engine: string` (`native` / `langgraph` / `fallback`)
- `route_id: string` (`format_only` / `resume_sections` / `compose_mode` / `default`)
- `route_entry: string` (`qa` / `writer` / `planner` / empty)

Compatibility rule:

- Consumers must treat `graph_meta` as optional and non-breaking.
- Missing `graph_meta` means either legacy path or non-route shortcut path, not an API error.
