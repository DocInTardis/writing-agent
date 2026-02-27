# Release Channels And Rollback

This document defines release-channel operations and rollback bundle generation.

## Channel Registry

- File: `security/release_channels.json`
- Channels:
  - `canary` (partial rollout)
  - `stable` (full rollout)

## Commands

Validate channel registry:

```powershell
python scripts/release_channel_control.py validate --strict
```

Show current status:

```powershell
python scripts/release_channel_control.py status
```

Set canary version:

```powershell
python scripts/release_channel_control.py set --channel canary --version 0.1.1 --reason "start canary" --actor release-bot
```

Promote canary to stable:

```powershell
python scripts/release_channel_control.py promote --source canary --target stable --reason "canary healthy 60m" --actor release-bot
```

Emergency rollback:

```powershell
python scripts/release_channel_control.py rollback --channel stable --to-version 0.1.0 --reason "critical regression" --actor oncall
```

Validate rollout strategy guard (history + promotion path):

```powershell
python scripts/release_rollout_guard.py --strict
```

Policy file:

- `security/release_rollout_policy.json`
- controls canary rollout window, stable rollout requirement, history constraints, and minimum canary observation window.

Plan next rollout stage (dry-run):

```powershell
python scripts/release_rollout_executor.py --dry-run --strict
```

Apply one rollout stage:

```powershell
python scripts/release_rollout_executor.py --apply --strict --target-version 0.1.1 --correlation-id rel-20260221-001 --release-candidate-id rc-0.1.1-20260221
```

The executor applies only one stage per run (`set canary`, `rollout canary`, or `promote stable`) and records the operation in channel history.

Apply one rollout stage with real traffic command:

```powershell
python scripts/release_rollout_executor.py --apply --strict --target-version 0.1.1 --traffic-apply-required --traffic-apply-command "rolloutctl --action {action} --to {target_version} --canary {canary_rollout_percent} --stable {stable_rollout_percent}"
```

If traffic command execution fails, local channel changes are reverted automatically.

Supported placeholders in `--traffic-apply-command`:

- `{action}`
- `{target_version}`
- `{from_version}`
- `{to_version}`
- `{correlation_id}`
- `{release_candidate_id}`
- `{from_rollout_percent}`
- `{to_rollout_percent}`
- `{canary_rollout_percent}`
- `{stable_rollout_percent}`
- `{canary_version}`
- `{stable_version}`

Validate adapter contract and command templates:

```powershell
python scripts/release_rollout_adapter_contract_check.py --strict
```

Validate one runtime command template before apply:

```powershell
python scripts/release_rollout_adapter_contract_check.py --strict --require-runtime-command --command-template "rolloutctl --action {action} --to {target_version} --canary {canary_rollout_percent} --stable {stable_rollout_percent} --corr {correlation_id} --rc {release_candidate_id}"
```

Reference adapter contract:

- `security/release_traffic_adapter_contract.json`
- `docs/RELEASE_TRAFFIC_ADAPTERS.md`

## Rollback Bundle

Create rollback bundle with key runtime and release artifacts:

```powershell
python scripts/create_rollback_bundle.py --label emergency --strict
```

Bundle outputs:

- `.data/out/rollback_bundle_<ts>_<label>/...`
- `.data/out/rollback_bundle_report_<ts>_<label>.json`

This bundle is intended for incident triage and rollback traceability.

## Rollback Drill Evidence

Validate recent drill evidence:

```powershell
python scripts/rollback_drill_guard.py
```

Strict gate with email drill and history rollback rehearsal:

```powershell
python scripts/rollback_drill_guard.py --strict --require-email-drill --require-history-rollback
```

Generate signed drill evidence (HMAC-SHA256):

```powershell
python scripts/sign_rollback_drill_evidence.py --require-key --strict
```

Validate drill evidence with signature requirement:

```powershell
python scripts/rollback_drill_guard.py --strict --require-email-drill --require-history-rollback --require-signature --signing-key "<key>"
```

Signature policy:

- `security/rollback_drill_signature_policy.json`

Automated drill workflow:

- `.github/workflows/release-drill-evidence.yml`

Automated rollout workflow:

- `.github/workflows/release-rollout-automation.yml`
