# writing-agent

`writing-agent` is a report-writing and export platform focused on:
- structured generation flows (`planner` / `writer` / `reviewer` / `qa`)
- citation-aware RAG retrieval and trust checks
- document export pipelines (Markdown and DOCX)
- web workbench with streaming editing
- governance scripts for quality, release, and operations

## Project Layout

```text
.
├── writing_agent/                 # Application source code
├── tests/                         # Unit / integration / e2e tests
│   └── legacy/                    # Historical script-like tests (excluded by default)
├── scripts/                       # Guardrails, release, and ops scripts
│   └── dev/                       # Local developer utility scripts
├── docs/                          # Architecture and operational docs
│   └── archive/                   # Archived milestone documents
├── security/                      # Policy-as-code and quality gate configs
├── templates/                     # Prompt and few-shot assets
├── infra/                         # Terraform and infra resources
├── pyproject.toml                 # Packaging and project metadata
├── requirements.txt               # Runtime dependencies
└── requirements-dev.txt           # Development dependencies
```

## Quick Start

### 1) Install dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\pip install -r requirements-dev.txt
```

### 2) Run application

```powershell
.\.venv\Scripts\python -m writing_agent.launch
```

Default URL: `http://127.0.0.1:8000`

### 3) Run tests

```powershell
python -m pytest -q tests
```

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
$env:WRITING_AGENT_LLM_BACKEND=\"node\"
$env:WRITING_AGENT_NODE_GATEWAY_URL=\"http://127.0.0.1:8787\"
```

## Common Development Commands

If you have `make` installed:

```bash
make test
make build-frontend
make guards
make preflight
```

Equivalent direct commands:

```powershell
python scripts/guard_file_line_limits.py --config security/file_line_limits.json --root .
python scripts/guard_function_complexity.py --config security/function_complexity_limits.json --root .
python scripts/guard_architecture_boundaries.py --config security/architecture_boundaries.json --root .
python scripts/release_preflight.py --quick
```

## Documentation

- Documentation index: `docs/INDEX.md`
- Getting started: `docs/START_HERE.md`
- Structure guide: `docs/PROJECT_STRUCTURE.md`
- Development guide: `docs/DEVELOPMENT.md`
- Operations runbook: `docs/OPERATIONS_RUNBOOK.md`
- Release and rollback: `docs/RELEASE_AND_ROLLBACK.md`
- API versioning: `docs/API_VERSIONING.md`
- Prompt registry: `docs/PROMPT_REGISTRY.md`
- RAG trust guard: `docs/RAG_TRUST_GUARD.md`
- Node gateway protocol: `docs/NODE_AI_GATEWAY_PROTOCOL_20260227_CN.md`
- Node gateway runbook: `docs/NODE_AI_GATEWAY_RUNBOOK_20260227_CN.md`

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
