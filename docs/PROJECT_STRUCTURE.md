# Project Structure Guide

This document defines where code, fixtures, policies, and generated outputs belong.
It is intentionally strict: the repository should stay source-first, while runtime output stays local.

## 1. Top-Level Layout

- `writing_agent/`
  - Main Python application code.
  - Keep business logic here, not in `scripts/`.
- `writing_agent/web/`
  - FastAPI entrypoints, service layer, domain layer, templates, and frontend assets.
- `writing_agent/v2/`
  - Core generation graph, prompt routing, document transformation, and RAG runtime.
- `engine/`
  - Rust workspace for editor and rendering support.
- `gateway/`
  - Node-based AI gateway.
- `scripts/`
  - Guardrails, release tooling, operational checks, and automation entrypoints.
- `tests/`
  - Unit, integration, export, UI, and end-to-end tests.
- `tests/fixtures/`
  - Versioned sample inputs, golden outputs, and small evaluation datasets.
- `security/`
  - Policy-as-code JSON files that drive guards and release checks.
- `docs/`
  - Architecture notes, runbooks, and process documentation.
- `templates/`
  - Prompt templates and reusable writing assets.
- `infra/`
  - Infrastructure definitions such as Terraform.

## 2. Web Layer Boundaries

- `writing_agent/web/app.py`, `writing_agent/web/app_v2.py`
  - Composition roots only.
  - Responsible for route registration, bootstrapping, and runtime wiring.
- `writing_agent/web/api/`
  - Request orchestration and response shaping.
  - Should not own durable business rules.
- `writing_agent/web/services/`
  - Cross-cutting business services used by API flows.
- `writing_agent/web/domains/`
  - Pure domain logic and decision rules.

These layer boundaries are enforced by `security/architecture_boundaries.json` and `scripts/guard_architecture_boundaries.py`.

## 3. What Gets Versioned

Keep these in git:

- Source code.
- Tests and fixtures.
- Policies under `security/`.
- Documentation under `docs/`.
- Stable templates and sample assets that are required to run tests or the product.

Do not keep these in git:

- One-off run outputs.
- Temporary dumps and scratch files.
- Local caches, logs, checkpoints, and metrics.
- Ad hoc exported documents created during debugging.

## 4. Local-Only Output Roots

Generated local output belongs in these ignored locations:

- `.data/`
  - Runtime caches, metrics, checkpoints, audit files, exports, and local state.
- `.data/out/`
  - Default home for generated reports from scripts and preflight tools.
- `artifacts/`
  - Temporary local artifacts when a script explicitly needs a scratch root.
- `tmp/`
  - Disposable investigation dumps.
- `data/`
  - Local-only scratch data, never versioned.

The repository must not track files under `deliverables/`, `artifacts/`, `tmp/`, `data/`, or `_misc_root/`.

## 5. Placement Rules

- If a file is needed by a test or a reproducible evaluation, put it in `tests/fixtures/`.
- If a file is only the result of a run, put it in `.data/out/`.
- If a script is production-facing or used in CI, keep it in `scripts/`.
- If a script is ad hoc, one-off, or machine-specific, do not keep it in the repository unless it is promoted into maintained tooling.
- If a document records process or architecture, keep it in `docs/`.
- If a JSON file acts as policy input to a guard, keep it in `security/`.

## 6. Repository Hygiene Guards

Run these checks before merging structural changes:

```powershell
python scripts/guard_repo_hygiene.py --config security/repo_hygiene_policy.json --root .
python scripts/guard_file_line_limits.py --config security/file_line_limits.json --root .
python scripts/guard_function_complexity.py --config security/function_complexity_limits.json --root .
python scripts/guard_architecture_boundaries.py --config security/architecture_boundaries.json --root .
```

`guard_repo_hygiene.py` is the first line of defense against root clutter and committed generated output.

## 7. Recommended Reading Order

1. `writing_agent/launch.py`
2. `writing_agent/web/app_v2.py`
3. `writing_agent/web/api/`
4. `writing_agent/web/services/`
5. `writing_agent/web/domains/`
6. `writing_agent/v2/graph_runner.py`
7. `writing_agent/document/v2_report_docx.py`
