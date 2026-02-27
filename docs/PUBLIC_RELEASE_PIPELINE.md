# Public Release Pipeline

This document defines the productized public release contract (`PROD-001`).

## Guard Script

- script: `scripts/public_release_guard.py`
- policy: `security/public_release_policy.json`

Validates:

- release version format and package version alignment
- required docs/workflows/scripts presence
- changelog source presence
- release notes generation automation

## Release Notes

- generator: `scripts/generate_release_notes.py`
- output: `.data/out/release_notes_*.md`

## Workflow

- workflow file: `.github/workflows/public-release.yml`
- trigger: tag `v*` and manual dispatch
- actions:
  - run public release guard
  - run migration assistant report
  - upload release notes and readiness artifacts

## Local Command

```powershell
python scripts/public_release_guard.py --strict --write-release-notes
```
