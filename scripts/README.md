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
- `editor_behavior_matrix.mjs`
  - Uses the installed Edge and the DevTools protocol (no Playwright or bundled
    browser) to verify trusted IME, keyboard, paragraph, pointer-selection, and
    triple-click behavior in an isolated document.
- `product_workflow_smoke.py`
  - Runs generation, human and AI Document V3 commands, block movement, page
    setup, persistence reload, and DOCX/PDF export with a deterministic,
    zero-cost test provider.

## Placement Rule

Do not keep one-off repair scripts, local debugging helpers, or machine-specific utilities here.
If a script is not maintained, not tested, or not part of a repeatable workflow, it should stay out of the repository.
