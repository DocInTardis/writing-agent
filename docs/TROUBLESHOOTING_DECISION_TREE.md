# Troubleshooting Decision Tree

Use this decision map to move from symptom to root-cause evidence quickly.

## Entry

1. Did `scripts/release_preflight.py` fail?
- Yes: inspect latest `.data/out/release_preflight_*.json` and find failing `steps[].id`.
- No: go to the specific subsystem branch below.

## A) Dependency/SBOM Failures

- Step ids:
  - `dependency_audit`
  - `generate_sbom`
- Evidence:
  - `.data/out/dependency_audit_*.json`
  - `.data/out/sbom/**`
- Actions:
  - patch vulnerable dependencies
  - refresh baseline with `scripts/update_dependency_baseline.py --reason "..."`

## B) Release Governance / Compatibility Failures

- Step ids:
  - `release_governance_check`
  - `release_compat_matrix`
  - `release_rollout_guard`
  - `release_rollout_adapter_contract`
- Evidence:
  - `.data/out/release_governance_*.json`
  - `.data/out/release_compat_matrix_*.json`
  - `.data/out/release_rollout_guard_*.json`
  - `.data/out/release_rollout_adapter_contract_*.json`
- Actions:
  - align `security/release_policy.json`
  - fix matrix fixtures in `security/release_compat_matrix.json`
  - verify adapter command placeholders

## C) Capacity / Performance Failures

- Step ids:
  - `capacity_guard`
  - `capacity_forecast`
  - `capacity_stress_gate`
  - `preflight_trend_guard`
- Evidence:
  - `.data/out/capacity_guard_*.json`
  - `.data/out/capacity_forecast_*.json`
  - `.data/out/capacity_stress_gate_*.json`
  - `.data/out/preflight_trend_guard_*.json`
- Actions:
  - run diagnostic baseline refresh:
    - `python scripts/update_capacity_baseline.py --dry-run --reason "capacity guard failure diagnostic"`
  - re-run load/soak probes
  - update capacity policy only with evidence

## D) Incident / Alert / Correlation Failures

- Step ids:
  - `alert_escalation_guard`
  - `create_incident_report`
  - `incident_notify`
  - `incident_config_guard`
  - `correlation_trace_guard`
- Evidence:
  - `.data/out/alert_escalation_*.json`
  - `.data/out/incident_report_*.json`
  - `.data/out/incident_notify_*.json`
  - `.data/out/incident_config_guard_*.json`
  - `.data/out/correlation_trace_guard_*.json`
- Actions:
  - validate routing policy and on-call roster
  - verify shared correlation IDs across artifacts
  - replay dead letters if notify failed

## E) Security / Privacy Failures

- Step ids:
  - `sensitive_output_scan`
  - `data_classification_guard`
  - `audit_trail_integrity`
- Evidence:
  - `.data/out/sensitive_output_scan_*.json`
  - `.data/out/data_classification_guard_*.json`
  - `.data/out/audit_chain_verify_*.json`
  - `.data/audit/operations_audit_chain.ndjson`
- Actions:
  - remove or mask leaked secrets and regenerate artifacts
  - enforce retention policy with `security/data_classification_policy.json`
  - stop rollout if audit chain integrity is broken

## F) Docs / Schema Catalog Failures

- Step ids:
  - `doc_encoding_guard`
  - `doc_reality_guard`
  - `artifact_schema_catalog_guard`
- Evidence:
  - `.data/out/doc_encoding_guard_*.json`
  - `.data/out/docs_reality_guard_*.json`
  - `.data/out/artifact_schema_catalog_guard_*.json`
- Actions:
  - fix encoding anomalies in `docs/`
  - remove or correct doc references to missing files/scripts
  - ensure documented `python scripts/*.py ...` commands are callable
  - synchronize `docs/ARTIFACT_SCHEMA_CATALOG.md` with policy

## G) Public Release / Migration Failures

- Step ids:
  - `public_release_guard`
  - `migration_assistant`
- Evidence:
  - `.data/out/public_release_guard_*.json`
  - `.data/out/migration_assistant_*.json`
  - `.data/out/migration_assistant_*.md`
  - `.data/out/release_notes_*.md`
- Actions:
  - align release version with `writing_agent/__init__.py`
  - regenerate release notes
  - ensure compatibility path coverage before rollout
