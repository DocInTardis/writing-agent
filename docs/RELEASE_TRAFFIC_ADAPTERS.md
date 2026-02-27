# Release Traffic Adapter Contract

This document defines the standard contract for real traffic rollout command templates.

## Contract File

- Path: `security/release_traffic_adapter_contract.json`
- Validator:
  - `python scripts/release_rollout_adapter_contract_check.py --strict`

## Placeholder Contract

Placeholders are rendered by `scripts/release_rollout_executor.py` in apply mode.

- Required placeholders:
  - `action`
  - `target_version`
- Recommended placeholders:
  - `correlation_id`
  - `release_candidate_id`
  - `canary_rollout_percent`
  - `stable_rollout_percent`

## Example Adapter Types

- Ingress (Nginx canary weight)
  - kind: `ingress-nginx`
  - use `{canary_rollout_percent}` with correlation metadata labels/annotations.
- Service mesh (Istio VirtualService)
  - kind: `service-mesh-istio`
  - update canary/stable route weights with `{canary_rollout_percent}` and `{stable_rollout_percent}`.
- API gateway (stage split)
  - kind: `api-gateway`
  - update gateway split using `{to_rollout_percent}` and target version.

## Runtime Validation

To validate a runtime command before rollout apply:

```powershell
python scripts/release_rollout_adapter_contract_check.py --strict --require-runtime-command --command-template "rolloutctl --action {action} --to {target_version} --canary {canary_rollout_percent} --stable {stable_rollout_percent} --corr {correlation_id} --rc {release_candidate_id}"
```

If the command contains unknown placeholders or malformed braces, validation fails before rollout apply.

