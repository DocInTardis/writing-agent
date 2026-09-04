# writing-agent

`writing-agent` is a report-writing and export platform focused on:
- structured generation flows (`planner` / `writer` / `reviewer` / `qa`)
- citation-aware RAG retrieval and trust checks
- document export pipelines (Markdown and DOCX)
- desktop workbench with streaming editing (currently an embedded local interface)
- persistent workspace dashboard and lifecycle management
- local workspace management and regression tests for the maintained product paths

## Project Layout

```text
.
|- writing_agent/                       # Python application and web backend
|  |- web/                              # FastAPI app + templates + frontend assets
|  |- v2/                               # Graph pipeline and generation runtime
|  |- llm/                              # LLM provider abstraction layer
|  |- state_engine/                     # State/route/replay runtime modules
|- engine/                              # Rust editor/render core workspace
|- gateway/                             # Node AI gateway
|- tests/                               # Unit / integration / export tests
|  `- fixtures/                         # Versioned sample inputs and golden fixtures
|- scripts/                             # Launchers, data tools, and maintained utilities
|- docs/                                # Architecture and runbooks
|- security/                            # Policy-as-code configs
|- templates/                           # Prompt and few-shot assets
|- infra/                               # Terraform resources
|- .data/                               # Local-only runtime outputs (ignored)
|- pyproject.toml                       # Python packaging metadata
|- requirements.txt                     # Runtime dependencies
`- requirements-dev.txt                 # Development dependencies
```

Local hygiene rules:
- Generated run outputs belong in `.data/out/`.
- Versioned evaluation inputs belong in `tests/fixtures/`.
- Temporary scratch roots such as `deliverables/`, `artifacts/`, `tmp/`, and `data/` are local-only and must not be committed.

## Quick Start

### 1) Install dependencies

For everyday use, run `scripts/start_desktop.ps1` (or double-click `start.bat`). It creates one `.venv` on first use;
later launches reuse it without invoking pip. The product direction is a lightweight
desktop app; the current desktop shell still reuses the local service and frontend.
Node and Rust are only needed when building or testing their respective components.
See [storage and runtime scope](docs/LOCAL_RUNTIME.md).

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

For the same dependency versions used by CI, install `requirements-pinned.txt` instead.

### LLM defaults

By default, the app now uses an OpenAI-compatible GPT model for generation. Set your API key before starting:

```powershell
$env:WRITING_AGENT_LLM_PROVIDER="openai"
$env:WRITING_AGENT_OPENAI_API_KEY="<your-openai-api-key>"
$env:WRITING_AGENT_OPENAI_MODEL="gpt-4o-mini"
```

Quota or billing errors do not switch to local Ollama by default. The legacy fallback is opt-in via `WRITING_AGENT_OPENAI_QUOTA_FALLBACK=1`; otherwise the selected API's error is reported.

### 2) Run application

```powershell
.\.venv\Scripts\python -m writing_agent.launch
```

This opens the desktop window. First install desktop dependencies using
`scripts/start_desktop.ps1`. Missing desktop dependencies produce an error, not a
browser fallback. Startup does not launch Ollama or download a model.

Developer-only local HTTP service: `python -m writing_agent.launch --web`
(or `scripts/start.ps1`), at `http://127.0.0.1:8000` by default.

Default product entrypoints:
- `/` -> product home with recent workspaces and system status
- `/new` -> create a fresh workspace and open the workbench
- `/latest` -> jump back to the latest active workspace

### 3) Run tests

```powershell
.\.venv\Scripts\python -m pip install --no-cache-dir -r requirements-dev.txt
.\.venv\Scripts\python -m pytest -q tests
```

The browser automation test chain has been retired; no separate test browser download
is required. Desktop interaction testing still needs to be rebuilt during consolidation.

## Productization Baseline

Current execution checklist: [lightweight desktop refactor](docs/REFACTOR_CHECKLIST.md).

- Product target: `docs/PRODUCTIZATION_TARGET.md`
- Local workspace persistence: `.data/workspaces/`
- Health endpoint: `GET /healthz`
- System status endpoint: `GET /api/system/status`
- Workspace API: list/create/update/duplicate/archive/restore under `GET/POST /api/workspaces...`
- Home dashboard extras: saved views, batch actions, batch label editing, owner/priority/due-date fields, due-soon/unassigned/no-due-date/no-priority/overdue filters, dashboard field editor, trash recovery, search/filter/sort, due-date sorting, trash-expiry sorting, top-label quick filters, pin/unpin, quick-start templates, resume-latest
- Activity stream: `GET /api/workspaces/activity`
- Workspace summary: `GET /api/workspaces/summary`
- Workspace status updates: `POST /api/workspaces/{doc_id}/status`
- Workspace labels: `POST /api/workspaces/{doc_id}/update` with `labels`, filterable from `GET /api/workspaces` and `GET /api/docs/list`
- Workspace trash lifecycle: `POST /api/workspaces/{doc_id}/trash`, `POST /api/workspaces/{doc_id}/untrash`, `POST /api/workspaces/{doc_id}/purge`
- Workspace batch actions: `POST /api/workspaces/batch` for pin/unpin/archive/restore/trash/untrash/purge/status/label edits/owner updates/priority updates/due-date updates
- Workspace trash cleanup: expired trashed workspaces are automatically purged during startup and dashboard/API reads
- Saved views API: `GET /api/workspace-views`, `POST /api/workspace-views/create`, `POST /api/workspace-views/{view_id}/delete`
- Workspace custom fields: `owner`, `priority`, `due_at` are available in workspace detail, list APIs, saved views, dashboard cards, and batch actions

### 4) Build frontend

```powershell
npm --prefix writing_agent/web/frontend_svelte run build
```

### 5) Run Node AI Gateway (incremental backend)

```powershell
cd gateway/node_ai_gateway
npm install
npm test
npm start
```

Then set:

```powershell
$env:WRITING_AGENT_LLM_BACKEND="node"
$env:WRITING_AGENT_NODE_GATEWAY_URL="http://127.0.0.1:8787"
```

## Common Development Commands

If you have `make` installed:

```bash
make test
make build-frontend
make test-gateway
make test-engine
make check
```

Equivalent direct commands for the maintained local path:

```powershell
python -m pytest -q tests
npm --prefix writing_agent/web/frontend_svelte run build
npm --prefix gateway/node_ai_gateway test
cargo test --workspace --manifest-path engine/Cargo.toml
```

## Idempotency Cache Settings

Generation endpoints use a local file-based idempotency cache at `.data/idempotency`.

- `WRITING_AGENT_IDEMPOTENCY_TTL_S`: expiration window in seconds (default `21600`)
- `WRITING_AGENT_IDEMPOTENCY_MAX_ENTRIES`: max cache entries to retain (default `2000`)
- `WRITING_AGENT_IDEMPOTENCY_SWEEP_INTERVAL_S`: active cleanup interval in seconds (default `60`)

Behavior:
- Lazy expiration on read (`get`)
- Active sweep after writes (`put`)
- Oldest-entry eviction when over capacity

## Edit Intent Parser Settings

Edit instructions now use schema-first plan parsing with rule fallback.

- `WRITING_AGENT_EDIT_PLAN_ENABLE`: enable schema parser path (default `1`)
- `WRITING_AGENT_EDIT_PLAN_MODEL`: optional dedicated parser model (default fallback to revise/default model)
- `WRITING_AGENT_EDIT_PLAN_TIMEOUT_S`: parser model timeout in seconds (default `20`)
- `WRITING_AGENT_EDIT_REQUIRE_CONFIRM_HIGH`: require explicit `确认执行` for high-risk plans (default `1`)
- `WRITING_AGENT_EDIT_PLAN_METRICS_ENABLE`: write parser/apply metrics to local file only (default `1`)
- `WRITING_AGENT_EDIT_PLAN_METRICS_PATH`: local metrics JSONL path (default `.data/metrics/edit_plan_events.jsonl`)
- `WRITING_AGENT_EDIT_PLAN_METRICS_MAX_BYTES`: max local metrics file size before trim (default `2097152`)

High-risk confirmation uses backend response fields (`requires_confirmation`, `confirmation_reason`, `confirmation_action`) so frontend can render explicit confirm/cancel buttons without parsing note text.
Parser metrics are local silent logs only and are not exposed in user-facing UI/API.

## Documentation

- Documentation index: `docs/INDEX.md`
- Feature and implementation map: `docs/FEATURES_AND_IMPLEMENTATION.md`
- Code reading guide: `docs/READING_GUIDE.md`
- Getting started: `docs/START_HERE.md`
- Structure guide: `docs/PROJECT_STRUCTURE.md`
- Development guide: `docs/DEVELOPMENT.md`
- Obsolete archived plans have been removed; their history remains available in Git.
- API versioning: `docs/API_VERSIONING.md`
- Prompt registry: `docs/PROMPT_REGISTRY.md`
- RAG trust guard: `docs/RAG_TRUST_GUARD.md`
- Optional Node gateway: `gateway/node_ai_gateway/README.md`

## Community and Governance

- Contributing guide: `CONTRIBUTING.md`
- Code of conduct: `CODE_OF_CONDUCT.md`
- Security policy: `SECURITY.md`
- Support policy: `SUPPORT.md`
- Changelog: `CHANGELOG.md` and `CHANGES.md`

## Maintainer Tooling

- Pre-commit config: `.pre-commit-config.yaml`
- CODEOWNERS: `.github/CODEOWNERS`
- Issue templates: `.github/ISSUE_TEMPLATE/`
- PR template: `.github/PULL_REQUEST_TEMPLATE.md`
- Dependabot config: `.github/dependabot.yml`
