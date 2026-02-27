# Start Here

This is the single onboarding path for running, validating, and operating `writing-agent`.

## 1) Environment Setup

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt -r requirements-dev.txt
```

Optional frontend dependencies:

```powershell
cmd /c npm --prefix writing_agent/web/frontend_svelte ci
```

## 2) Launch

```powershell
.\.venv\Scripts\python -m writing_agent.launch
```

Open:

- `http://127.0.0.1:8000`

## 3) Baseline Validation

Run core tests:

```powershell
.\.venv\Scripts\python -m pytest -q
```

Run release preflight quick path:

```powershell
.\.venv\Scripts\python scripts/release_preflight.py --quick
```

## 4) Operations Essentials

- Runbook: `docs/OPERATIONS_RUNBOOK.md`
- Decoupling refactor execution plan: `docs/DECOUPLING_REFACTOR_EXECUTION_PLAN_20260225_CN.md`
- Release engineering: `docs/RELEASE_ENGINEERING.md`
- Release and rollback execution: `docs/RELEASE_AND_ROLLBACK.md`
- Privacy and classification controls: `docs/PRIVACY_DATA_CLASSIFICATION.md`
- Audit trail integrity: `docs/AUDIT_TRAIL_INTEGRITY.md`

## 5) Productization Gates

The integrated preflight now includes:

- dependency and SBOM gates
- release governance and manifest
- rollout policy/adapter/compat checks
- rollback drill evidence checks
- docs encoding and docs-reality checks
- trend/capacity guards
- incident routing and sensitive output checks
- audit chain integrity checks
- data classification and retention checks
- schema catalog coverage checks
- public release contract checks
- migration assistant readiness checks

## 6) Release Entry Point

For tag or release candidate readiness:

```powershell
.\.venv\Scripts\python scripts/public_release_guard.py --strict --write-release-notes
```

Then:

```powershell
.\.venv\Scripts\python scripts/migration_assistant.py --strict
```

## 7) If Something Fails

Use:

- `docs/TROUBLESHOOTING_DECISION_TREE.md`

This maps failures to exact scripts, artifacts, and next actions.
