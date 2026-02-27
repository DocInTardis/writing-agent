# Master Test Content Summary

- Generated at: `2026-02-23 16:15:14`
- Total automated test files: `51`
- Content validation dataset: single-round `70`, multiround `24` (total rounds `96`)
- Persona coverage items: `14` (`tests/ui/PLAYWRIGHT_PERSONA_MATRIX.md`)
- Content-validation run batches with result files: `21`

## 1. Test Asset Structure

| Category | File Count |
|---|---:|
| `UI_Playwright` | 3 |
| `Release_Engineering` | 10 |
| `Capacity_Performance` | 9 |
| `Citation_Observability` | 3 |
| `Security_Compliance` | 4 |
| `Ops_Reliability` | 11 |
| `Engine_Document` | 9 |
| `Export_Docx` | 1 |
| `Other` | 1 |

## 2. Full Automated Test File List

### 2.1 `UI_Playwright` (3)

- `tests/ui/test_workbench.py`
- `tests/ui/test_workbench_svelte.py`
- `tests/ui/test_workbench_svelte_personas.py`

### 2.2 `Release_Engineering` (10)

- `tests/test_generate_release_manifest_gate_map.py`
- `tests/test_generate_release_notes.py`
- `tests/test_public_release_guard.py`
- `tests/test_release_channel_control.py`
- `tests/test_release_compat_matrix.py`
- `tests/test_release_engineering_scripts.py`
- `tests/test_release_preflight.py`
- `tests/test_release_rollout_adapter_contract_check.py`
- `tests/test_release_rollout_executor.py`
- `tests/test_release_rollout_guard.py`

### 2.3 `Capacity_Performance` (9)

- `tests/test_apply_capacity_policy_threshold_patch.py`
- `tests/test_capacity_alert_policy_drift.py`
- `tests/test_capacity_forecast.py`
- `tests/test_capacity_guard.py`
- `tests/test_capacity_stress_gate.py`
- `tests/test_capacity_stress_matrix.py`
- `tests/test_slo_guard.py`
- `tests/test_suggest_capacity_alert_thresholds.py`
- `tests/test_update_capacity_baseline.py`

### 2.4 `Citation_Observability` (3)

- `tests/test_citation_verify_and_delete.py`
- `tests/test_citation_verify_long_soak_guard.py`
- `tests/test_citation_verify_soak.py`

### 2.5 `Security_Compliance` (4)

- `tests/test_data_classification_guard.py`
- `tests/test_dependency_security_scripts.py`
- `tests/test_security_alert_notify.py`
- `tests/test_sensitive_output_scan.py`

### 2.6 `Ops_Reliability` (11)

- `tests/test_alert_escalation_guard.py`
- `tests/test_audit_chain.py`
- `tests/test_correlation_trace_guard.py`
- `tests/test_create_incident_report.py`
- `tests/test_create_rollback_bundle.py`
- `tests/test_incident_config_guard.py`
- `tests/test_incident_notify.py`
- `tests/test_incident_notify_drill.py`
- `tests/test_preflight_trend_guard.py`
- `tests/test_rollback_drill_guard.py`
- `tests/test_sign_rollback_drill_evidence.py`

### 2.7 `Engine_Document` (9)

- `tests/test_block_edit_clean_output.py`
- `tests/test_doc_encoding_guard.py`
- `tests/test_doc_format_heading_glue.py`
- `tests/test_docs_reality_guard.py`
- `tests/test_format_only_guard.py`
- `tests/test_generation_guards.py`
- `tests/test_migration_assistant.py`
- `tests/test_state_engine_v21.py`
- `tests/test_upload_guardrails.py`

### 2.8 `Export_Docx` (1)

- `tests/export/test_docx_export.py`

### 2.9 `Other` (1)

- `tests/test_artifact_schema_catalog_guard.py`

## 3. Content Validation Dataset Coverage

- Single-round cases: `70`
- Multiround cases: `24`
- Total multiround steps: `96`
- Single-round groups: `10`
- Multiround groups: `10`

### 3.1 Single-round Group Distribution

| Group | Cases |
|---|---:|
| `academic_research` | 7 |
| `customer_service` | 7 |
| `enterprise_management` | 7 |
| `finance_literacy` | 7 |
| `government_public` | 7 |
| `healthcare_science` | 7 |
| `inclusive_education` | 7 |
| `legal_compliance` | 7 |
| `marketing_brand` | 7 |
| `technical_manual` | 7 |

### 3.2 Multiround Group Distribution

| Group | Cases |
|---|---:|
| `academic_research` | 3 |
| `customer_service` | 1 |
| `enterprise_management` | 3 |
| `finance_literacy` | 1 |
| `government_public` | 2 |
| `healthcare_science` | 1 |
| `inclusive_education` | 3 |
| `legal_compliance` | 2 |
| `marketing_brand` | 3 |
| `technical_manual` | 5 |

## 4. Frontend Execution History (Playwright Content Validation)

| Run ID | Passed | Total | Failed | Pass Rate |
|---|---:|---:|---:|---:|
| `content_validation_20260222_195838` | 0 | 1 | 1 | 0.0% |
| `content_validation_20260222_200114` | 0 | 1 | 1 | 0.0% |
| `content_validation_20260222_200602` | 0 | 1 | 1 | 0.0% |
| `content_validation_20260222_201202` | 0 | 1 | 1 | 0.0% |
| `content_validation_20260222_201627` | 1 | 1 | 0 | 100.0% |
| `content_validation_20260222_202003` | 8 | 11 | 3 | 72.73% |
| `content_validation_20260222_210626` | 1 | 2 | 1 | 50.0% |
| `content_validation_20260222_212518` | 0 | 1 | 1 | 0.0% |
| `content_validation_20260222_214003` | 0 | 1 | 1 | 0.0% |
| `content_validation_20260222_215121` | 0 | 1 | 1 | 0.0% |
| `content_validation_20260222_220435` | 1 | 1 | 0 | 100.0% |
| `content_validation_20260222_221733` | 1 | 1 | 0 | 100.0% |
| `content_validation_20260222_222355` | 8 | 11 | 3 | 72.73% |
| `content_validation_20260222_231158` | 1 | 3 | 2 | 33.33% |
| `content_validation_20260222_232530` | 3 | 3 | 0 | 100.0% |
| `content_validation_20260222_234017` | 10 | 11 | 1 | 90.91% |
| `content_validation_20260223_002839` | 0 | 1 | 1 | 0.0% |
| `content_validation_20260223_003559` | 1 | 1 | 0 | 100.0% |
| `content_validation_20260223_004303` | 10 | 11 | 1 | 90.91% |
| `content_validation_20260223_012957` | 1 | 1 | 0 | 100.0% |
| `content_validation_20260223_014405` | 11 | 11 | 0 | 100.0% |

## 5. Current Stable Baseline

- Latest fully stable smoke batch: `content_validation_20260223_014405` (`11/11`, `100.0%`).
- Evidence JSON: `.data\out\content_validation_20260223_014405\content_validation_run_20260223_014405.json`
- Evidence Markdown: `.data\out\content_validation_20260223_014405\content_validation_summary_20260223_014405.md`

## 6. Related Test Documents

- `tests/ui/CONTENT_VALIDATION_EXEC_DATASET.md`
- `tests/ui/CONTENT_VALIDATION_EXECUTION_REPORT.md`
- `tests/ui/PLAYWRIGHT_PERSONA_MATRIX.md`

## 7. Notes

- This document summarizes both test assets and executed results found in the workspace.
- The `70 + 24` dataset is executable as a full suite; at least one full-group smoke batch is stabilized.
- For a complete 70+24 pass, run `scripts/ui_content_validation_runner.py --run-all`.

