# Development Guide

## Environment

1. Create virtual environment:
`python -m venv .venv`
2. Install dependencies:
`.\.venv\Scripts\pip install -r requirements.txt`
`.\.venv\Scripts\pip install -r requirements-dev.txt`

## Pre-commit

Install pre-commit:
`pip install pre-commit`

Enable hooks:
`pre-commit install`

Run hooks manually:
`pre-commit run --all-files`

## Local Verification

Run tests:
`python -m pytest -q tests`

Run frontend build:
`npm --prefix writing_agent/web/frontend_svelte run build`

Run node gateway tests:
`npm --prefix gateway/node_ai_gateway test`

Run guardrails:
- `python scripts/guard_file_line_limits.py --config security/file_line_limits.json --root .`
- `python scripts/guard_function_complexity.py --config security/function_complexity_limits.json --root .`
- `python scripts/guard_architecture_boundaries.py --config security/architecture_boundaries.json --root .`

## Suggested PR Flow

1. Create branch from latest main.
2. Implement changes with tests and docs updates.
3. Run local verification commands.
4. Open PR using `.github/PULL_REQUEST_TEMPLATE.md`.
5. Ensure CI is green before merge.
