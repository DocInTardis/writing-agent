# Dependency Baseline Policy

This document defines how `security/dependency_baseline.json` is maintained.

## Goal

- Prevent accidental risk growth in dependency vulnerabilities.
- Keep baseline updates auditable and intentional.
- Ensure dependency gates remain strict in CI and release preflight.

## Baseline Update Command

Use the refresh script instead of editing the baseline JSON manually:

```powershell
python scripts/update_dependency_baseline.py --reason "why baseline changed"
```

The script will:

- Run `scripts/dependency_audit.py` with current policy thresholds.
- Generate a fresh baseline snapshot in `.data/out/`.
- Compare against existing baseline.
- Refuse to overwrite baseline if risk regresses, unless explicitly allowed.
- Write a refresh report under `.data/out/dependency_baseline_refresh_*.json`.

## Regression Guard

By default, baseline refresh blocks any increase in:

- `critical`
- `high`
- `moderate`
- `total`

across:

- `npm_prod`
- `npm_dev`
- `pip`

If regression must be accepted temporarily:

```powershell
python scripts/update_dependency_baseline.py --allow-regression --reason "temporary accepted risk"
```

Without `--reason`, `--allow-regression` still fails.

## PR Requirements for Baseline Changes

When `security/dependency_baseline.json` changes, include:

- The output report path from `.data/out/dependency_baseline_refresh_*.json`
- A concise risk statement in the PR description
- Mitigation/rollback plan and expected remediation ETA for any accepted regression

## CI Integration Notes

- `dependency-security` workflow enforces baseline regression checks.
- `release-preflight` also enforces dependency audit and SBOM generation.
- If either audit or SBOM fails, workflow can notify webhook and open a GitHub issue.
