# Release Engineering

This document defines the release-governance and compatibility checks for productized delivery.

## Objectives

- Keep release artifacts versioned and traceable.
- Prevent accidental schema/version drift.
- Ensure rollback is possible with known compatible runtime data.

## Local Commands

Run governance checks:

```powershell
python scripts/release_governance_check.py --strict
```

Generate release manifest:

```powershell
python scripts/generate_release_manifest.py
```

Release manifest now includes immutable gate evidence mapping:

- key: `release_candidate_id`
- value: gate artifact map + `evidence_sha256`
- optional strict check:
  - `python scripts/generate_release_manifest.py --require-gate-evidence`

Run integrated preflight:

```powershell
python scripts/release_preflight.py --quick
```

## Policy Source

- Policy file: `security/release_policy.json`
- Includes:
  - `app_version`
  - current state schema
  - backward compatible schema list
  - runtime data file contract
- Ops RBAC policy:
  - `security/ops_rbac_policy.json`
- Rollback drill signature policy:
  - `security/rollback_drill_signature_policy.json`
- Related rollout adapter contract:
  - `security/release_traffic_adapter_contract.json`
- Audit trail integrity:
  - `docs/AUDIT_TRAIL_INTEGRITY.md`

When version/schema changes, update policy in the same PR.

## CI Integration

- Workflow: `.github/workflows/release-preflight.yml`
- Nightly soak workflow: `.github/workflows/citation-soak.yml`
- Long-soak governance workflow: `.github/workflows/citation-soak-long.yml`
- Capacity baseline refresh workflow: `.github/workflows/capacity-baseline-refresh.yml`
- Capacity stress matrix workflow: `.github/workflows/capacity-stress-matrix.yml`
- Release drill evidence workflow: `.github/workflows/release-drill-evidence.yml`
- Release compatibility matrix workflow: `.github/workflows/release-compat-matrix.yml`
- Release rollout automation workflow: `.github/workflows/release-rollout-automation.yml`
- Public release workflow: `.github/workflows/public-release.yml`
- Enforced env:
  - `WA_PREFLIGHT_REQUIRE_PIP_AUDIT=1`
  - `WA_RELEASE_GOVERNANCE_STRICT=1`
  - `WA_RELEASE_REQUIRE_CHANGES_VERSION=1`
  - `WA_RELEASE_COMPAT_MATRIX_STRICT=1`
  - `WA_RELEASE_TRAFFIC_ADAPTER_STRICT=1`
  - `WA_RELEASE_ROLLOUT_STRICT=1`
  - `WA_RELEASE_ROLLOUT_PLAN_STRICT=1`
  - `WA_DOC_ENCODING_GUARD_STRICT=1`
  - `WA_DOC_REALITY_POLICY_FILE`
  - `WA_DOC_REALITY_GUARD_STRICT=1`
  - `WA_DOC_REALITY_GUARD_REQUIRE_PYTHON_CHECK=1`
  - `WA_DOC_REALITY_GUARD_MAX_MISSING_PATHS=0`
  - `WA_DOC_REALITY_GUARD_MAX_COMMAND_FAILURES=0`
  - `WA_ALERT_ESCALATION_STRICT=1`
  - `WA_CORRELATION_GUARD_STRICT=1`
  - `WA_TREND_GUARD_STRICT=1`
  - `WA_TREND_REQUIRE_SOAK=1` (for soak-enabled preflight runs)
  - `WA_LONG_SOAK_POLICY_FILE` / `WA_LONG_SOAK_HISTORY_FILE`
  - `WA_LONG_SOAK_GUARD_STRICT=1` (recommended for tagged release preflight)
  - `WA_INCIDENT_ONCALL_ROSTER_FILE=security/oncall_roster.json`
  - `WA_INCIDENT_REQUIRE_ONCALL_ROSTER=1`
  - `WA_INCIDENT_USE_ONCALL_ROSTER=1`
  - `WA_INCIDENT_CONFIG_STRICT=1`
  - `WA_SENSITIVE_OUTPUT_SCAN_STRICT=1`
  - `WA_DATA_CLASS_POLICY_FILE`
  - `WA_DATA_CLASS_GUARD_STRICT=1`
  - `WA_DATA_CLASS_GUARD_MAX_UNMASKED_FINDINGS`
  - `WA_ARTIFACT_SCHEMA_CATALOG_FILE`
  - `WA_ARTIFACT_SCHEMA_CATALOG_POLICY_FILE`
  - `WA_ARTIFACT_SCHEMA_CATALOG_STRICT=1`
  - `WA_PUBLIC_RELEASE_POLICY_FILE`
  - `WA_PUBLIC_RELEASE_VERSION`
  - `WA_PUBLIC_RELEASE_WRITE_RELEASE_NOTES=1`
  - `WA_PUBLIC_RELEASE_GUARD_STRICT=1`
  - `WA_MIGRATION_MATRIX_FILE`
  - `WA_MIGRATION_POLICY_FILE`
  - `WA_MIGRATION_ASSISTANT_STRICT=1`
  - `WA_AUDIT_CHAIN_STRICT=1`
  - `WA_AUDIT_CHAIN_REQUIRE_LOG=1`
  - `WA_AUDIT_CHAIN_LOG` / `WA_AUDIT_CHAIN_STATE_FILE`
  - `WA_AUDIT_CHAIN_MAX_AGE_S`
  - `WA_CAPACITY_GUARD_STRICT=1`
  - `WA_CAPACITY_PROFILE=dev|staging|prod|default`
  - `WA_CAPACITY_FORECAST_STRICT=1`
  - `WA_CAPACITY_RELEASE_TIER` / `WA_CAPACITY_RELEASE_BRANCH` / `WA_RUNTIME_ENV` for staged headroom-history mode rollout
- Uploaded artifacts now include:
  - `release_governance_*.json`
  - `release_manifest_*.json`
  - `release_compat_matrix_*.json`
  - `release_rollout_adapter_contract_*.json`
  - `release_rollout_guard_*.json`
  - `release_rollout_executor_*.json`
  - `rollback_drill_guard_*.json`
  - `rollback_drill_signature_*.json`
  - `doc_encoding_guard_*.json`
  - `docs_reality_guard_*.json`
  - `preflight_trend_guard_*.json`
  - `citation_verify_long_soak_guard_*.json`
  - `alert_escalation_*.json`
  - `correlation_trace_guard_*.json`
  - `incident_report_*.json`
  - `incident_report_*.md`
  - `incident_notify_*.json`
  - `incident_notify_drill_*.json`
  - `incident_notify_drill_notify_*.json`
  - `incident_report_drill_*.json`
  - `incident_config_guard_*.json`
  - `sensitive_output_scan_*.json`
  - `data_classification_guard_*.json`
  - `artifact_schema_catalog_guard_*.json`
  - `public_release_guard_*.json`
  - `migration_assistant_*.json`
  - `migration_assistant_*.md`
  - `release_notes_*.md`
  - `audit_chain_verify_*.json`
  - `.data/audit/operations_audit_chain.ndjson`
  - `.data/audit/operations_audit_chain_state.json`
  - `capacity_guard_*.json`
  - `capacity_forecast_*.json`
  - `capacity_forecast_*.md`
  - `capacity_baseline_refresh_*.json`
  - `capacity_policy_generated_*.json`
  - `capacity_alert_threshold_suggest_*.json`
  - `capacity_alert_thresholds_suggested.json`
  - `capacity_alert_policy_drift_*.json`
  - `capacity_policy_threshold_patch_suggested.json`
  - `capacity_policy_patch_apply_*.json`
  - `capacity_stress_gate_*.json`
  - `capacity_stress_matrix_*.json`
  - dependency audit and SBOM outputs

## Failure Diagnostics

When `capacity_guard` fails in preflight, the pipeline now runs an automatic dry-run baseline analysis:

- step id: `capacity_baseline_dry_run_on_guard_failure`
- command: `python scripts/update_capacity_baseline.py --dry-run --reason "capacity guard failure diagnostic"`

This does not overwrite policy, but emits candidate baseline artifacts for triage.
Disable this behavior only when needed via `--skip-capacity-failure-diagnostic`.

Preflight now also runs threshold suggestion on successful capacity gate:

- step id: `capacity_alert_threshold_suggest`
- command: `python scripts/suggest_capacity_alert_thresholds.py ...`
- artifacts:
  - `.data/out/capacity_alert_threshold_suggest_*.json`
  - `.data/out/capacity_alert_thresholds_suggested.json`

Then it runs policy-drift check (warn mode by default):

- step id: `capacity_alert_policy_drift_check`
- command: `python scripts/capacity_alert_policy_drift.py ...`
- strict mode env (optional): `WA_CAPACITY_POLICY_DRIFT_STRICT=1`
- candidate patch artifact:
  - `.data/out/capacity_policy_threshold_patch_suggested.json`

Then preflight validates patch applicability in dry-run mode:

- step id: `capacity_alert_policy_patch_validate`
- command: `python scripts/apply_capacity_policy_threshold_patch.py --dry-run ...`
- strict env (optional): `WA_CAPACITY_POLICY_PATCH_STRICT=1`
- gate env:
  - `WA_CAPACITY_POLICY_PATCH_MAX_EXCEEDED`
  - `WA_CAPACITY_POLICY_PATCH_MIN_CONFIDENCE`
  - `WA_CAPACITY_POLICY_PATCH_ALLOW_RELAX`
  - `WA_CAPACITY_POLICY_PATCH_IGNORE_SOURCE_HASH`
- artifact:
  - `.data/out/capacity_policy_patch_apply_*.json`

Then preflight checks stress evidence freshness and quality in gate mode:

- step id: `capacity_stress_gate`
- command: `python scripts/capacity_stress_gate.py ...`
- strict env (optional): `WA_CAPACITY_STRESS_GATE_STRICT=1`
- gate env:
  - `WA_CAPACITY_STRESS_MAX_AGE_S`
  - `WA_CAPACITY_STRESS_MIN_PROFILES`
  - `WA_CAPACITY_STRESS_MAX_FAILED_PROFILES`
  - `WA_CAPACITY_STRESS_REQUIRE_SOAK`
- artifact:
  - `.data/out/capacity_stress_gate_*.json`

Then preflight validates release rollout strategy using channel history and policy:

- step id: `release_rollout_guard`
- command: `python scripts/release_rollout_guard.py ...`
- strict env (optional): `WA_RELEASE_ROLLOUT_STRICT=1`
- gate env:
  - `WA_RELEASE_ROLLOUT_EXPECTED_VERSION`
  - `WA_RELEASE_ROLLOUT_MAX_HISTORY_AGE_S`
  - `WA_RELEASE_ROLLOUT_MIN_CANARY_OBSERVE_S`
  - `WA_RELEASE_ROLLOUT_ALLOW_DIRECT_STABLE`
- policy source:
  - `security/release_rollout_policy.json`
- artifact:
  - `.data/out/release_rollout_guard_*.json`

Then preflight runs compatibility matrix for upgrade/rollback regression:

- step id: `release_compat_matrix`
- command: `python scripts/release_compat_matrix.py ...`
- strict env (optional): `WA_RELEASE_COMPAT_MATRIX_STRICT=1`
- config:
  - `security/release_compat_matrix.json`
- required coverage rules can now enforce:
  - N-1 -> N upgrade case
  - N -> N+1 upgrade case
  - N+1 -> N rollback case
  - at least one expected failure-mode case (`expect_readable=false`)
- negative case fixtures may define `expected_failed_checks` for deterministic failure assertions.
- artifact:
  - `.data/out/release_compat_matrix_*.json`

Then preflight validates rollout traffic adapter contract and command templates:

- step id: `release_rollout_adapter_contract`
- command: `python scripts/release_rollout_adapter_contract_check.py ...`
- strict env (optional): `WA_RELEASE_TRAFFIC_ADAPTER_STRICT=1`
- optional env:
  - `WA_RELEASE_TRAFFIC_ADAPTER_CONTRACT_FILE`
  - `WA_RELEASE_TRAFFIC_APPLY_COMMAND`
  - `WA_RELEASE_TRAFFIC_ADAPTER_REQUIRE_RUNTIME_COMMAND`
- contract source:
  - `security/release_traffic_adapter_contract.json`
- artifact:
  - `.data/out/release_rollout_adapter_contract_*.json`

Then preflight checks rollback drill evidence freshness and completeness:

- step id: `rollback_drill_guard`
- command: `python scripts/rollback_drill_guard.py ...`
- strict env (optional): `WA_ROLLBACK_DRILL_STRICT=1`
- gate env:
  - `WA_ROLLBACK_DRILL_MAX_AGE_S`
  - `WA_ROLLBACK_DRILL_HISTORY_MAX_AGE_S`
  - `WA_ROLLBACK_DRILL_MIN_INCIDENT_DRILLS`
  - `WA_ROLLBACK_DRILL_MIN_ROLLBACK_BUNDLES`
  - `WA_ROLLBACK_DRILL_REQUIRE_EMAIL`
  - `WA_ROLLBACK_DRILL_REQUIRE_HISTORY_ROLLBACK`
  - `WA_ROLLBACK_DRILL_REQUIRE_SIGNATURE`
  - `WA_ROLLBACK_DRILL_SIGNATURE_PATTERN`
  - `WA_ROLLBACK_DRILL_SIGNATURE_POLICY`
  - `WA_ROLLBACK_DRILL_SIGNATURE_MAX_AGE_S`
  - `WA_ROLLBACK_DRILL_SIGNING_KEY`
- artifact:
  - `.data/out/rollback_drill_guard_*.json`
  - `.data/out/rollback_drill_signature_*.json`

Then preflight validates documentation encoding quality:

- step id: `doc_encoding_guard`
- command: `python scripts/doc_encoding_guard.py ...`
- optional env:
  - `WA_DOC_ENCODING_GUARD_ROOT`
  - `WA_DOC_ENCODING_MAX_SUSPICIOUS_FILES`
  - `WA_DOC_ENCODING_MIN_HINT_COUNT`
  - `WA_DOC_ENCODING_MIN_HINT_RATIO`
- strict env (optional):
  - `WA_DOC_ENCODING_GUARD_STRICT=1`
- artifact:
  - `.data/out/doc_encoding_guard_*.json`

Then preflight validates documented paths and script commands are real:

- step id: `doc_reality_guard`
- command: `python scripts/docs_reality_guard.py ...`
- optional env:
  - `WA_DOC_REALITY_POLICY_FILE`
  - `WA_DOC_REALITY_GUARD_MAX_MISSING_PATHS`
  - `WA_DOC_REALITY_GUARD_MAX_COMMAND_FAILURES`
  - `WA_DOC_REALITY_GUARD_REQUIRE_PYTHON_CHECK`
- strict env (optional):
  - `WA_DOC_REALITY_GUARD_STRICT=1`
- artifact:
  - `.data/out/docs_reality_guard_*.json`

Then preflight executes rollout plan in dry-run mode:

- step id: `release_rollout_executor_dry_run`
- command: `python scripts/release_rollout_executor.py --dry-run ...`
- strict env (optional): `WA_RELEASE_ROLLOUT_PLAN_STRICT=1`
- rollout env:
  - `WA_RELEASE_ROLLOUT_TARGET_VERSION`
  - `WA_RELEASE_ROLLOUT_ACTOR`
  - `WA_RELEASE_ROLLOUT_REASON`
  - `WA_RELEASE_ROLLOUT_PLAN_ALLOW_GATE_FAILURES`
- artifact:
  - `.data/out/release_rollout_executor_*.json`

Then preflight validates correlation IDs across rollout/alert/incident artifacts:

- step id: `correlation_trace_guard`
- command: `python scripts/correlation_trace_guard.py ...`
- strict env (optional): `WA_CORRELATION_GUARD_STRICT=1`
- artifact:
  - `.data/out/correlation_trace_guard_*.json`

Then preflight validates tamper-evident audit chain integrity:

- step id: `audit_trail_integrity`
- command: `python scripts/verify_audit_chain.py ...`
- strict env (optional):
  - `WA_AUDIT_CHAIN_STRICT=1`
  - `WA_AUDIT_CHAIN_REQUIRE_LOG=1`
  - `WA_AUDIT_CHAIN_MAX_AGE_S`
- optional env:
  - `WA_AUDIT_CHAIN_LOG`
  - `WA_AUDIT_CHAIN_STATE_FILE`
  - `WA_AUDIT_CHAIN_REQUIRE_STATE`
  - `WA_AUDIT_CHAIN_NO_WRITE_STATE`
- artifact:
  - `.data/out/audit_chain_verify_*.json`

Then preflight validates data-classification and retention policy:

- step id: `data_classification_guard`
- command: `python scripts/data_classification_guard.py ...`
- optional env:
  - `WA_DATA_CLASS_POLICY_FILE`
  - `WA_DATA_CLASS_GUARD_MAX_UNMASKED_FINDINGS`
  - `WA_DATA_CLASS_GUARD_REQUIRE_RULES`
- strict env (optional):
  - `WA_DATA_CLASS_GUARD_STRICT=1`
- artifact:
  - `.data/out/data_classification_guard_*.json`

Then preflight validates schema catalog coverage:

- step id: `artifact_schema_catalog_guard`
- command: `python scripts/artifact_schema_catalog_guard.py ...`
- optional env:
  - `WA_ARTIFACT_SCHEMA_CATALOG_FILE`
  - `WA_ARTIFACT_SCHEMA_CATALOG_POLICY_FILE`
  - `WA_ARTIFACT_SCHEMA_CATALOG_REQUIRE_EVIDENCE`
- strict env (optional):
  - `WA_ARTIFACT_SCHEMA_CATALOG_STRICT=1`
- artifact:
  - `.data/out/artifact_schema_catalog_guard_*.json`

Then preflight validates public release publication contract:

- step id: `public_release_guard`
- command: `python scripts/public_release_guard.py ...`
- optional env:
  - `WA_PUBLIC_RELEASE_POLICY_FILE`
  - `WA_PUBLIC_RELEASE_VERSION`
  - `WA_PUBLIC_RELEASE_CHANGES_FILE`
  - `WA_PUBLIC_RELEASE_NOTES_OUT`
  - `WA_PUBLIC_RELEASE_WRITE_RELEASE_NOTES`
- strict env (optional):
  - `WA_PUBLIC_RELEASE_GUARD_STRICT=1`
- artifact:
  - `.data/out/public_release_guard_*.json`
  - `.data/out/release_notes_*.md`

Then preflight generates migration readiness plan:

- step id: `migration_assistant`
- command: `python scripts/migration_assistant.py ...`
- optional env:
  - `WA_MIGRATION_FROM_VERSION`
  - `WA_MIGRATION_TO_VERSION`
  - `WA_MIGRATION_MATRIX_FILE`
  - `WA_MIGRATION_POLICY_FILE`
  - `WA_MIGRATION_OUT_MD`
- strict env (optional):
  - `WA_MIGRATION_ASSISTANT_STRICT=1`
- artifact:
  - `.data/out/migration_assistant_*.json`
  - `.data/out/migration_assistant_*.md`

Then preflight verifies long-soak evidence retention and regression baseline:

- step id: `citation_verify_long_soak_guard`
- command: `python scripts/citation_verify_long_soak_guard.py ...`
- optional env:
  - `WA_LONG_SOAK_POLICY_FILE`
  - `WA_LONG_SOAK_PATTERN`
  - `WA_LONG_SOAK_HISTORY_FILE`
- strict env (optional):
  - `WA_LONG_SOAK_GUARD_STRICT=1`
- policy source:
  - `security/long_soak_policy.json`
- artifact:
  - `.data/out/citation_verify_long_soak_guard_*.json`

For apply mode outside preflight, rollout executor now supports an optional real-traffic command adapter:

- `--traffic-apply-command "<command template>"`
- `--traffic-apply-required`
- `--traffic-apply-timeout-s`

Apply mode behavior:

- If command succeeds: rollout state change is committed.
- If command fails: rollout state change is reverted and reported.
