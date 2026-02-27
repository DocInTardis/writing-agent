# Contributing Guide

## Development Setup
1. Create a virtual environment: `python -m venv .venv`
2. Install runtime dependencies: `.venv\\Scripts\\pip install -r requirements.txt`
3. Install dev dependencies: `.venv\\Scripts\\pip install -r requirements-dev.txt`
4. Start the app locally: `.venv\\Scripts\\python -m writing_agent.launch`
5. Install pre-commit hooks: `pre-commit install`

## Project Layout
- `writing_agent/`: application code
- `tests/`: automated tests (unit/integration/e2e)
- `scripts/`: CI/preflight/governance and maintenance utilities
- `docs/`: architecture and operational documentation
- `security/`: policy-as-code and guard configurations

## Before Opening a PR
1. Run tests: `python -m pytest -q tests`
2. Run file-size guard: `python scripts/guard_file_line_limits.py --config security/file_line_limits.json --root .`
3. Run complexity guard: `python scripts/guard_function_complexity.py --config security/function_complexity_limits.json --root .`
4. Run boundary guard: `python scripts/guard_architecture_boundaries.py --config security/architecture_boundaries.json --root .`
5. Run pre-commit checks: `pre-commit run --all-files`

## Coding Rules
- Keep modules focused and avoid oversized files.
- Add module docstrings and comments for non-obvious logic.
- Prefer service/domain layering over route-layer business logic.
- Add or update tests for behavior changes.

## Commit Convention
- `feat:` new functionality
- `fix:` bug fix
- `refactor:` structure-only change
- `test:` tests only
- `docs:` documentation only
- `chore:` maintenance
