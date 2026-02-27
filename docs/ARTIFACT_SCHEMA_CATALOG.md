# Artifact Schema Catalog

This catalog is the central index for key JSON artifacts and their required fields.

Validation guard:

- script: `scripts/artifact_schema_catalog_guard.py`
- policy: `security/artifact_schema_catalog_policy.json`

## release_preflight

- artifact glob: `.data/out/release_preflight_*.json`
- required fields:
  - `ok`
  - `started_at`
  - `ended_at`
  - `steps`

## release_rollout_executor

- artifact glob: `.data/out/release_rollout_executor_*.json`
- required fields:
  - `ok`
  - `plan`
  - `apply_result`
  - `checks`
  - `correlation`

## incident_notify

- artifact glob: `.data/out/incident_notify_*.json`
- required fields:
  - `ok`
  - `incident_report`
  - `channels`
  - `routed_channels`

## audit_chain_verify

- artifact glob: `.data/out/audit_chain_verify_*.json`
- required fields:
  - `ok`
  - `log_path`
  - `entry_count`
  - `checks`

## data_classification_guard

- artifact glob: `.data/out/data_classification_guard_*.json`
- required fields:
  - `ok`
  - `policy_file`
  - `findings`
  - `retention_violations`
  - `checks`

## docs_reality_guard

- artifact glob: `.data/out/docs_reality_guard_*.json`
- required fields:
  - `ok`
  - `policy_file`
  - `missing_paths`
  - `checks`

## public_release_guard

- artifact glob: `.data/out/public_release_guard_*.json`
- required fields:
  - `ok`
  - `release_version`
  - `checks`

## migration_assistant

- artifact glob: `.data/out/migration_assistant_*.json`
- required fields:
  - `ok`
  - `from_version`
  - `to_version`
  - `plan`
  - `checks`
