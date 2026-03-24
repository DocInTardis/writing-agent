# Scripts Directory

This directory contains maintained operational tooling only.

## What Belongs Here

- Guardrails and repository hygiene checks.
- Release and rollout tooling.
- Repeatable quality and regression utilities.
- Supported launchers such as `start.ps1` and `start_desktop.ps1`.

## Common Scripts

- `guard_repo_hygiene.py`
  - Prevents generated output roots and scratch files from leaking into the repository.
- `guard_file_line_limits.py`
  - Enforces file size limits for large Python modules.
- `guard_function_complexity.py`
  - Enforces function complexity thresholds.
- `guard_architecture_boundaries.py`
  - Enforces web-layer dependency boundaries.
- `release_preflight.py`
  - Runs the main release readiness checks.
- `run_quality_suite.py`
  - Aggregates key quality checks for local development.

## Placement Rule

Do not keep one-off repair scripts, local debugging helpers, or machine-specific utilities here.
If a script is not maintained, not tested, or not part of a repeatable workflow, it should stay out of the repository.
