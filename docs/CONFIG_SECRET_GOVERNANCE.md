# Config And Secret Governance

This document describes release-time governance for incident notification config and secret leakage prevention.

## Scripts

- `scripts/incident_config_guard.py`
- `scripts/sensitive_output_scan.py`

## Incident config guard

Checks:

- At least one incident channel is configured (webhook/slack/feishu/email).
- If email config is present, `email_to + email_from + smtp_host` are complete.
- Routing policy JSON exists and only contains supported channels.

Run:

```powershell
python scripts/incident_config_guard.py --strict
```

Artifact:

- `.data/out/incident_config_guard_*.json`

## Sensitive output scan

Scans output artifacts for common secret/token signatures:

- OpenAI-like keys (`sk-...`)
- AWS access key id (`AKIA...`)
- private key markers
- generic `token/secret/password/api_key` assignments
- bearer tokens

Run:

```powershell
python scripts/sensitive_output_scan.py --strict --max-findings 0
```

Artifact:

- `.data/out/sensitive_output_scan_*.json`

## Release preflight integration

`scripts/release_preflight.py` runs both checks by default.

Strict env flags:

- `WA_INCIDENT_CONFIG_STRICT=1`
- `WA_SENSITIVE_OUTPUT_SCAN_STRICT=1`

Skip flags:

- `--skip-incident-config-guard`
- `--skip-sensitive-output-scan`
