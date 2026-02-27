# Capacity Model And Guard

This document defines the capacity baseline model and automated guard for `citation_verify`.

## Policy

- `security/capacity_policy.json`

Key fields:

- `target_peak_rps`: expected peak request rate baseline.
- `required_headroom_ratio`: required ratio of measured throughput to `target_peak_rps`.
- `profile_overrides.<profile>`: environment-specific capacity thresholds and target baseline (`dev`/`staging`/`prod`/`default`).
- `quick_relax.required_headroom_ratio`: lower temporary threshold for quick preflight.
- `quick_relax.allow_headroom_history_fallback`: allow quick mode to downgrade latest headroom failure when history window remains healthy.
- `headroom_history.*`: recent load history guard (median and drop-ratio checks).
- `headroom_history.strict_promote_to_enforce`: in `--strict`, promote history checks to enforce mode.
- `headroom_history.promote_when_quick_with_sufficient_history`: optionally promote in quick mode when enough reports exist.
- `headroom_history.mode_by_release_tier`: stage rollout by release tier (e.g. dev/staging/prod).
- `headroom_history.mode_by_runtime_env`: stage rollout by runtime environment.
- `headroom_history.mode_by_branch_pattern`: branch-based mode overrides (supports glob patterns).
- `load_report_max_age_s`: max allowed age for load report.
- `soak_report_max_age_s`: max allowed age for soak report.
- `max_latency_p95_ms`: p95 latency limit during load probe.
- `max_degraded_rate`: degraded response rate limit.
- `min_success_rate`: success rate lower bound.
- `soak.*`: long-run stability thresholds.

## Script

- `scripts/capacity_guard.py`

Typical usage:

```powershell
python scripts/capacity_guard.py
```

Quick mode:

```powershell
python scripts/capacity_guard.py --quick
```

Use explicit history pattern:

```powershell
python scripts/capacity_guard.py --load-pattern ".data/out/citation_verify_load_probe_*.json"
```

Release-context mode override:

```powershell
python scripts/capacity_guard.py --release-tier prod --release-branch main --runtime-env production
```

Require soak evidence:

```powershell
python scripts/capacity_guard.py --strict --require-soak
```

Output artifact:

- `.data/out/capacity_guard_*.json`

## Baseline Refresh

Script:

- `scripts/update_capacity_baseline.py`

Refresh target peak RPS from latest load report:

```powershell
python scripts/update_capacity_baseline.py --capacity-profile prod --reason "capacity baseline refresh (prod)"
```

Suggest alert thresholds from recent load/soak history:

```powershell
python scripts/suggest_capacity_alert_thresholds.py `
  --capacity-profile prod `
  --load-window 8 `
  --soak-window 6 `
  --write-thresholds .data/out/capacity_alert_thresholds_suggested_prod.json
```

Check drift against current `security/capacity_policy.json` and write a candidate patch:

```powershell
python scripts/capacity_alert_policy_drift.py `
  --capacity-profile prod `
  --suggested .data/out/capacity_alert_thresholds_suggested_prod.json `
  --policy-level critical `
  --write-patch .data/out/capacity_policy_threshold_patch_suggested_prod.json
```

Validate/apply candidate patch with safety gates:

```powershell
python scripts/apply_capacity_policy_threshold_patch.py `
  --patch .data/out/capacity_policy_threshold_patch_suggested_prod.json `
  --capacity-profile prod `
  --reason "capacity threshold policy update" `
  --min-confidence 0.45 `
  --max-exceeded-metrics 0 `
  --dry-run
```

Apply for real (writes policy and backup):

```powershell
python scripts/apply_capacity_policy_threshold_patch.py `
  --patch .data/out/capacity_policy_threshold_patch_suggested_prod.json `
  --capacity-profile prod `
  --reason "capacity threshold policy update" `
  --allow-relax `
  --strict
```

Dry-run only (no policy overwrite):

```powershell
python scripts/update_capacity_baseline.py --dry-run --reason "capacity baseline review"
```

Calibrate all profiles continuously in workflow:

- `.github/workflows/capacity-baseline-refresh.yml` runs a matrix over `dev` / `staging` / `prod`.

Allow baseline decrease explicitly:

```powershell
python scripts/update_capacity_baseline.py --allow-regression --reason "hardware downgrade rollback"
```

Artifacts:

- `.data/out/capacity_baseline_refresh_*.json`
- `.data/out/capacity_policy_generated_*.json`

## Capacity Forecast

Generate a growth forecast from recent load history:

```powershell
python scripts/capacity_forecast.py --capacity-profile prod --horizon-days 30 --strict
```

Artifacts:

- `.data/out/capacity_forecast_*.json`
- `.data/out/capacity_forecast_*.md`

## Stress Matrix

Run multi-profile stress matrix (peak/burst/jitter):

```powershell
python scripts/capacity_stress_matrix.py --quick --include-soak
```

Use full matrix for longer evidence:

```powershell
python scripts/capacity_stress_matrix.py --include-soak --soak-duration-s 1800 --strict
```

Gate release with recent stress evidence:

```powershell
python scripts/capacity_stress_gate.py `
  --max-age-s 1209600 `
  --min-profiles 3 `
  --max-failed-profiles 0 `
  --require-soak
```

Artifacts:

- `.data/out/capacity_stress_matrix_*.json`
- `.data/out/capacity_stress_gate_*.json`
- `.data/out/citation_verify_load_probe_stress_*.json`
- `.data/out/citation_verify_soak_stress_*.json`

## Preflight Integration

`scripts/release_preflight.py` includes `capacity_guard` when load probe is enabled.

Controls:

- strict env: `WA_CAPACITY_GUARD_STRICT=1`
- capacity profile env: `WA_CAPACITY_PROFILE=dev|staging|prod|default`
- require soak env: `WA_CAPACITY_REQUIRE_SOAK=1`
- require soak trend env: `WA_TREND_REQUIRE_SOAK=1`
- drift strict env: `WA_CAPACITY_POLICY_DRIFT_STRICT=1`
- drift level env: `WA_CAPACITY_POLICY_LEVEL=critical|warn`
- drift tolerance env: `WA_CAPACITY_POLICY_MAX_RELATIVE_DRIFT=0.2`
- drift confidence env: `WA_CAPACITY_POLICY_MIN_CONFIDENCE=0.45`
- patch strict env: `WA_CAPACITY_POLICY_PATCH_STRICT=1`
- patch allow-relax env: `WA_CAPACITY_POLICY_PATCH_ALLOW_RELAX=1`
- patch max-exceeded env: `WA_CAPACITY_POLICY_PATCH_MAX_EXCEEDED=0`
- patch confidence env: `WA_CAPACITY_POLICY_PATCH_MIN_CONFIDENCE=0.45`
- patch hash-override env: `WA_CAPACITY_POLICY_PATCH_IGNORE_SOURCE_HASH=1`
- stress gate strict env: `WA_CAPACITY_STRESS_GATE_STRICT=1`
- stress gate age env: `WA_CAPACITY_STRESS_MAX_AGE_S=1209600`
- stress gate profile count env: `WA_CAPACITY_STRESS_MIN_PROFILES=3`
- stress gate fail bound env: `WA_CAPACITY_STRESS_MAX_FAILED_PROFILES=0`
- stress gate soak env: `WA_CAPACITY_STRESS_REQUIRE_SOAK=1`
- auto soak env: `WA_PREFLIGHT_SOAK_DURATION_S` (seconds, `>0` to enable in preflight)
- skip flag: `--skip-capacity-guard`
- skip flag: `--skip-capacity-policy-drift-check`
- skip flag: `--skip-capacity-policy-patch-validate`
- skip flag: `--skip-capacity-stress-gate`
- skip soak probe flag: `--skip-soak-probe`
- workflows:
  - `.github/workflows/capacity-baseline-refresh.yml`
  - `.github/workflows/capacity-stress-matrix.yml`
