# Scripts Directory

This directory contains maintained local tooling only.

## What Belongs Here

- Repeatable local quality, data, and regression utilities.
- Supported launchers such as `start.ps1` and `start_desktop.ps1`.

## Common Scripts

- `run_quality_suite.py`
  - Aggregates key quality checks for local development.
- `start.ps1` / `start_desktop.ps1`
  - Supported launchers for the web and desktop entrypoints.

## Placement Rule

Do not keep one-off repair scripts, local debugging helpers, or machine-specific utilities here.
If a script is not maintained, not tested, or not part of a repeatable workflow, it should stay out of the repository.
