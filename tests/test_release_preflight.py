from __future__ import annotations

import sys
from pathlib import Path

from scripts import release_preflight


def _ok_step(step_id: str, cmd: list[str] | None = None) -> release_preflight.StepResult:
    return release_preflight.StepResult(
        id=step_id,
        ok=True,
        return_code=0,
        duration_s=0.001,
        command=list(cmd or []),
        cwd=".",
    )


def _base_args(out_path: Path) -> list[str]:
    return [
        "release_preflight.py",
        "--quick",
        "--skip-pytest",
        "--skip-frontend",
        "--skip-rust",
        "--skip-deps-audit",
        "--skip-sbom",
        "--skip-release-governance",
        "--skip-release-manifest",
        "--skip-release-channels",
        "--skip-rollback-bundle",
        "--skip-slo-guard",
        "--skip-alert-escalation",
        "--skip-incident-report",
        "--skip-incident-notify",
        "--skip-incident-config-guard",
        "--skip-sensitive-output-scan",
        "--skip-chaos",
        "--out",
        out_path.as_posix(),
    ]


def test_preflight_env_drives_capacity_and_trend_require_soak(monkeypatch, tmp_path: Path) -> None:
    run_cmd_calls: list[tuple[str, list[str]]] = []
    soak_calls: list[dict[str, object]] = []

    def _fake_run_cmd(*, step_id: str, cmd: list[str], cwd: str = ".", env=None):  # noqa: ANN001
        run_cmd_calls.append((step_id, list(cmd)))
        return _ok_step(step_id, cmd)

    def _fake_load(*, host: str, port: int, quick: bool) -> release_preflight.StepResult:
        assert host == "127.0.0.1"
        assert port == 18130
        assert quick is True
        return _ok_step("citation_metrics_load_probe", ["fake-load"])

    def _fake_soak(
        *,
        host: str,
        port: int,
        quick: bool,
        duration_s: float,
        interval_s: float,
        requests_per_window: int,
        concurrency: int,
        timeout_s: float,
    ) -> release_preflight.StepResult:
        soak_calls.append(
            {
                "host": host,
                "port": port,
                "quick": quick,
                "duration_s": duration_s,
                "interval_s": interval_s,
                "requests_per_window": requests_per_window,
                "concurrency": concurrency,
                "timeout_s": timeout_s,
            }
        )
        return _ok_step("citation_metrics_soak_probe", ["fake-soak"])

    monkeypatch.setattr(release_preflight, "_run_cmd", _fake_run_cmd)
    monkeypatch.setattr(release_preflight, "_run_load_probe_with_temp_server", _fake_load)
    monkeypatch.setattr(release_preflight, "_run_soak_with_temp_server", _fake_soak)

    monkeypatch.setenv("WA_PREFLIGHT_SOAK_DURATION_S", "60")
    monkeypatch.setenv("WA_PREFLIGHT_SOAK_INTERVAL_S", "11")
    monkeypatch.setenv("WA_PREFLIGHT_SOAK_REQUESTS_PER_WINDOW", "7")
    monkeypatch.setenv("WA_PREFLIGHT_SOAK_CONCURRENCY", "3")
    monkeypatch.setenv("WA_CAPACITY_GUARD_STRICT", "1")
    monkeypatch.setenv("WA_CAPACITY_PROFILE", "staging")
    monkeypatch.setenv("WA_CAPACITY_REQUIRE_SOAK", "1")
    monkeypatch.setenv("WA_CAPACITY_BASELINE_ALLOW_REGRESSION", "1")
    monkeypatch.setenv("WA_CAPACITY_POLICY_DRIFT_STRICT", "1")
    monkeypatch.setenv("WA_CAPACITY_POLICY_LEVEL", "warn")
    monkeypatch.setenv("WA_CAPACITY_POLICY_MAX_RELATIVE_DRIFT", "0.33")
    monkeypatch.setenv("WA_CAPACITY_POLICY_MIN_CONFIDENCE", "0.55")
    monkeypatch.setenv("WA_CAPACITY_POLICY_PATCH_STRICT", "1")
    monkeypatch.setenv("WA_CAPACITY_POLICY_PATCH_ALLOW_RELAX", "1")
    monkeypatch.setenv("WA_CAPACITY_POLICY_PATCH_MAX_EXCEEDED", "1")
    monkeypatch.setenv("WA_CAPACITY_POLICY_PATCH_MIN_CONFIDENCE", "0.66")
    monkeypatch.setenv("WA_CAPACITY_POLICY_PATCH_IGNORE_SOURCE_HASH", "1")
    monkeypatch.setenv("WA_CAPACITY_STRESS_GATE_STRICT", "1")
    monkeypatch.setenv("WA_CAPACITY_STRESS_REQUIRE_SOAK", "1")
    monkeypatch.setenv("WA_CAPACITY_STRESS_MAX_AGE_S", "86400")
    monkeypatch.setenv("WA_CAPACITY_STRESS_MIN_PROFILES", "3")
    monkeypatch.setenv("WA_CAPACITY_STRESS_MAX_FAILED_PROFILES", "0")
    monkeypatch.setenv("WA_CAPACITY_FORECAST_STRICT", "1")
    monkeypatch.setenv("WA_CAPACITY_FORECAST_HORIZON_DAYS", "21")
    monkeypatch.setenv("WA_CAPACITY_FORECAST_MIN_SAMPLES", "5")
    monkeypatch.setenv("WA_TREND_GUARD_STRICT", "1")
    monkeypatch.setenv("WA_CAPACITY_RELEASE_TIER", "prod")
    monkeypatch.setenv("WA_CAPACITY_RELEASE_BRANCH", "release/1.0.0")
    monkeypatch.setenv("WA_RUNTIME_ENV", "production")
    monkeypatch.setenv("WA_RELEASE_COMPAT_MATRIX_STRICT", "1")
    monkeypatch.setenv("WA_RELEASE_COMPAT_POLICY_FILE", "security/release_policy.json")
    monkeypatch.setenv("WA_RELEASE_COMPAT_MATRIX_FILE", "security/release_compat_matrix.json")
    monkeypatch.setenv("WA_RELEASE_TRAFFIC_ADAPTER_STRICT", "1")
    monkeypatch.setenv("WA_RELEASE_TRAFFIC_ADAPTER_CONTRACT_FILE", "security/release_traffic_adapter_contract.json")
    monkeypatch.setenv(
        "WA_RELEASE_TRAFFIC_APPLY_COMMAND",
        "rolloutctl --action {action} --to {target_version} --canary {canary_rollout_percent}",
    )
    monkeypatch.setenv("WA_RELEASE_TRAFFIC_ADAPTER_REQUIRE_RUNTIME_COMMAND", "1")
    monkeypatch.setenv("WA_RELEASE_MANIFEST_REQUIRE_GATE_EVIDENCE", "1")
    monkeypatch.setenv("WA_RELEASE_CANDIDATE_ID", "rc-test-001")
    monkeypatch.setenv("WA_RELEASE_ROLLOUT_STRICT", "1")
    monkeypatch.setenv("WA_RELEASE_ROLLOUT_EXPECTED_VERSION", "0.1.0")
    monkeypatch.setenv("WA_RELEASE_ROLLOUT_MAX_HISTORY_AGE_S", "12345")
    monkeypatch.setenv("WA_RELEASE_ROLLOUT_MIN_CANARY_OBSERVE_S", "900")
    monkeypatch.setenv("WA_RELEASE_ROLLOUT_ALLOW_DIRECT_STABLE", "1")
    monkeypatch.setenv("WA_RELEASE_ROLLOUT_PLAN_STRICT", "1")
    monkeypatch.setenv("WA_RELEASE_ROLLOUT_TARGET_VERSION", "0.1.0")
    monkeypatch.setenv("WA_RELEASE_ROLLOUT_ACTOR", "release-bot")
    monkeypatch.setenv("WA_RELEASE_ROLLOUT_REASON", "preflight rollout plan")
    monkeypatch.setenv("WA_RELEASE_ROLLOUT_PLAN_ALLOW_GATE_FAILURES", "1")
    monkeypatch.setenv("WA_ROLLBACK_DRILL_STRICT", "1")
    monkeypatch.setenv("WA_ROLLBACK_DRILL_MAX_AGE_S", "45678")
    monkeypatch.setenv("WA_ROLLBACK_DRILL_HISTORY_MAX_AGE_S", "56789")
    monkeypatch.setenv("WA_ROLLBACK_DRILL_MIN_INCIDENT_DRILLS", "2")
    monkeypatch.setenv("WA_ROLLBACK_DRILL_MIN_ROLLBACK_BUNDLES", "3")
    monkeypatch.setenv("WA_ROLLBACK_DRILL_REQUIRE_EMAIL", "1")
    monkeypatch.setenv("WA_ROLLBACK_DRILL_REQUIRE_HISTORY_ROLLBACK", "1")
    monkeypatch.setenv("WA_ROLLBACK_DRILL_REQUIRE_SIGNATURE", "1")
    monkeypatch.setenv("WA_ROLLBACK_DRILL_SIGNATURE_PATTERN", ".data/out/rollback_drill_signature_*.json")
    monkeypatch.setenv("WA_ROLLBACK_DRILL_SIGNATURE_POLICY", "security/rollback_drill_signature_policy.json")
    monkeypatch.setenv("WA_ROLLBACK_DRILL_SIGNATURE_MAX_AGE_S", "4567")
    monkeypatch.setenv("WA_ROLLBACK_DRILL_SIGNING_KEY", "rollback-sign-key")
    monkeypatch.setenv("WA_CORRELATION_GUARD_STRICT", "1")
    monkeypatch.setenv("WA_LONG_SOAK_GUARD_STRICT", "1")
    monkeypatch.setenv("WA_LONG_SOAK_POLICY_FILE", "security/long_soak_policy.json")
    monkeypatch.setenv("WA_LONG_SOAK_PATTERN", ".data/out/citation_verify_soak_*.json")
    monkeypatch.setenv("WA_LONG_SOAK_HISTORY_FILE", ".data/perf/citation_verify_long_soak_history.json")
    monkeypatch.setenv("WA_DOC_ENCODING_GUARD_STRICT", "1")
    monkeypatch.setenv("WA_DOC_ENCODING_GUARD_ROOT", "docs")
    monkeypatch.setenv("WA_DOC_ENCODING_MAX_SUSPICIOUS_FILES", "0")
    monkeypatch.setenv("WA_DOC_ENCODING_MIN_HINT_COUNT", "6")
    monkeypatch.setenv("WA_DOC_ENCODING_MIN_HINT_RATIO", "0.02")
    monkeypatch.setenv("WA_DOC_REALITY_POLICY_FILE", "security/docs_reality_policy.json")
    monkeypatch.setenv("WA_DOC_REALITY_GUARD_STRICT", "1")
    monkeypatch.setenv("WA_DOC_REALITY_GUARD_REQUIRE_PYTHON_CHECK", "1")
    monkeypatch.setenv("WA_DOC_REALITY_GUARD_MAX_MISSING_PATHS", "0")
    monkeypatch.setenv("WA_DOC_REALITY_GUARD_MAX_COMMAND_FAILURES", "0")
    monkeypatch.setenv("WA_INCIDENT_ONCALL_ROSTER_FILE", "security/oncall_roster.json")
    monkeypatch.setenv("WA_INCIDENT_REQUIRE_ONCALL_ROSTER", "1")
    monkeypatch.setenv("WA_INCIDENT_USE_ONCALL_ROSTER", "0")
    monkeypatch.setenv("WA_DATA_CLASS_POLICY_FILE", "security/data_classification_policy.json")
    monkeypatch.setenv("WA_DATA_CLASS_GUARD_STRICT", "1")
    monkeypatch.setenv("WA_DATA_CLASS_GUARD_REQUIRE_RULES", "1")
    monkeypatch.setenv("WA_DATA_CLASS_GUARD_MAX_UNMASKED_FINDINGS", "0")
    monkeypatch.setenv("WA_ARTIFACT_SCHEMA_CATALOG_FILE", "docs/ARTIFACT_SCHEMA_CATALOG.md")
    monkeypatch.setenv("WA_ARTIFACT_SCHEMA_CATALOG_POLICY_FILE", "security/artifact_schema_catalog_policy.json")
    monkeypatch.setenv("WA_ARTIFACT_SCHEMA_CATALOG_STRICT", "1")
    monkeypatch.setenv("WA_ARTIFACT_SCHEMA_CATALOG_REQUIRE_EVIDENCE", "1")
    monkeypatch.setenv("WA_PUBLIC_RELEASE_POLICY_FILE", "security/public_release_policy.json")
    monkeypatch.setenv("WA_PUBLIC_RELEASE_VERSION", "0.1.0")
    monkeypatch.setenv("WA_PUBLIC_RELEASE_CHANGES_FILE", "CHANGES.md")
    monkeypatch.setenv("WA_PUBLIC_RELEASE_WRITE_RELEASE_NOTES", "1")
    monkeypatch.setenv("WA_PUBLIC_RELEASE_NOTES_OUT", ".data/out/release_notes_preflight.md")
    monkeypatch.setenv("WA_PUBLIC_RELEASE_GUARD_STRICT", "1")
    monkeypatch.setenv("WA_MIGRATION_FROM_VERSION", "0.0.9")
    monkeypatch.setenv("WA_MIGRATION_TO_VERSION", "0.1.0")
    monkeypatch.setenv("WA_MIGRATION_MATRIX_FILE", "security/release_compat_matrix.json")
    monkeypatch.setenv("WA_MIGRATION_POLICY_FILE", "security/release_policy.json")
    monkeypatch.setenv("WA_MIGRATION_OUT_MD", ".data/out/migration_assistant_preflight.md")
    monkeypatch.setenv("WA_MIGRATION_ASSISTANT_STRICT", "1")
    monkeypatch.setenv("WA_AUDIT_CHAIN_STRICT", "1")
    monkeypatch.setenv("WA_AUDIT_CHAIN_REQUIRE_LOG", "1")
    monkeypatch.setenv("WA_AUDIT_CHAIN_REQUIRE_STATE", "1")
    monkeypatch.setenv("WA_AUDIT_CHAIN_MAX_AGE_S", "900")
    monkeypatch.setenv("WA_AUDIT_CHAIN_LOG", ".data/audit/operations_audit_chain.ndjson")
    monkeypatch.setenv("WA_AUDIT_CHAIN_STATE_FILE", ".data/audit/operations_audit_chain_state.json")
    monkeypatch.setenv("WA_AUDIT_CHAIN_NO_WRITE_STATE", "1")

    out_path = tmp_path / "preflight.json"
    argv = _base_args(out_path)
    argv = [item for item in argv if item not in {"--skip-incident-notify", "--skip-incident-config-guard"}]
    monkeypatch.setattr(sys, "argv", argv)
    code = release_preflight.main()

    assert code == 0
    assert len(soak_calls) == 1
    assert soak_calls[0]["duration_s"] == 60.0
    assert soak_calls[0]["interval_s"] == 11.0
    assert soak_calls[0]["requests_per_window"] == 7
    assert soak_calls[0]["concurrency"] == 3

    cmd_map = {step_id: cmd for step_id, cmd in run_cmd_calls}
    assert "file_line_limits_guard" in cmd_map
    assert "scripts/guard_file_line_limits.py" in cmd_map["file_line_limits_guard"]
    assert "--config" in cmd_map["file_line_limits_guard"]
    assert "security/file_line_limits.json" in cmd_map["file_line_limits_guard"]
    assert "function_complexity_guard" in cmd_map
    assert "scripts/guard_function_complexity.py" in cmd_map["function_complexity_guard"]
    assert "--config" in cmd_map["function_complexity_guard"]
    assert "security/function_complexity_limits.json" in cmd_map["function_complexity_guard"]
    assert "architecture_boundaries_guard" in cmd_map
    assert "scripts/guard_architecture_boundaries.py" in cmd_map["architecture_boundaries_guard"]
    assert "--config" in cmd_map["architecture_boundaries_guard"]
    assert "security/architecture_boundaries.json" in cmd_map["architecture_boundaries_guard"]
    assert "--strict" in cmd_map["capacity_guard"]
    assert "--require-soak" in cmd_map["capacity_guard"]
    assert "--release-tier" in cmd_map["capacity_guard"]
    assert "prod" in cmd_map["capacity_guard"]
    assert "--capacity-profile" in cmd_map["capacity_guard"]
    assert "staging" in cmd_map["capacity_guard"]
    assert "--release-branch" in cmd_map["capacity_guard"]
    assert "release/1.0.0" in cmd_map["capacity_guard"]
    assert "--runtime-env" in cmd_map["capacity_guard"]
    assert "production" in cmd_map["capacity_guard"]
    assert "--prefer-soak" in cmd_map["capacity_alert_threshold_suggest"]
    assert "--capacity-profile" in cmd_map["capacity_alert_threshold_suggest"]
    assert "capacity_forecast" in cmd_map
    assert "--capacity-profile" in cmd_map["capacity_forecast"]
    assert "staging" in cmd_map["capacity_forecast"]
    assert "--strict" in cmd_map["capacity_forecast"]
    assert "--horizon-days" in cmd_map["capacity_forecast"]
    assert "21.0" in cmd_map["capacity_forecast"]
    assert "--min-samples" in cmd_map["capacity_forecast"]
    assert "5" in cmd_map["capacity_forecast"]
    assert "--strict" in cmd_map["capacity_alert_policy_drift_check"]
    assert "--capacity-profile" in cmd_map["capacity_alert_policy_drift_check"]
    assert "--policy-level" in cmd_map["capacity_alert_policy_drift_check"]
    assert "warn" in cmd_map["capacity_alert_policy_drift_check"]
    assert "--max-relative-drift" in cmd_map["capacity_alert_policy_drift_check"]
    assert "0.33" in cmd_map["capacity_alert_policy_drift_check"]
    assert "--min-confidence" in cmd_map["capacity_alert_policy_drift_check"]
    assert "0.55" in cmd_map["capacity_alert_policy_drift_check"]
    assert "--strict" in cmd_map["capacity_alert_policy_patch_validate"]
    assert "--capacity-profile" in cmd_map["capacity_alert_policy_patch_validate"]
    assert "--allow-relax" in cmd_map["capacity_alert_policy_patch_validate"]
    assert "--max-exceeded-metrics" in cmd_map["capacity_alert_policy_patch_validate"]
    assert "1" in cmd_map["capacity_alert_policy_patch_validate"]
    assert "--min-confidence" in cmd_map["capacity_alert_policy_patch_validate"]
    assert "0.66" in cmd_map["capacity_alert_policy_patch_validate"]
    assert "--ignore-source-hash" in cmd_map["capacity_alert_policy_patch_validate"]
    assert "--dry-run" in cmd_map["capacity_alert_policy_patch_validate"]
    assert "--strict" in cmd_map["capacity_stress_gate"]
    assert "--require-soak" in cmd_map["capacity_stress_gate"]
    assert "--max-age-s" in cmd_map["capacity_stress_gate"]
    assert "86400.0" in cmd_map["capacity_stress_gate"]
    assert "--min-profiles" in cmd_map["capacity_stress_gate"]
    assert "3" in cmd_map["capacity_stress_gate"]
    assert "--max-failed-profiles" in cmd_map["capacity_stress_gate"]
    assert "0" in cmd_map["capacity_stress_gate"]
    assert "--allow-regression" in cmd_map["capacity_baseline_refresh"]
    assert "--capacity-profile" in cmd_map["capacity_baseline_refresh"]
    assert "--strict" in cmd_map["release_compat_matrix"]
    assert "--policy" in cmd_map["release_compat_matrix"]
    assert "security/release_policy.json" in cmd_map["release_compat_matrix"]
    assert "--matrix" in cmd_map["release_compat_matrix"]
    assert "security/release_compat_matrix.json" in cmd_map["release_compat_matrix"]
    assert "--strict" in cmd_map["release_rollout_adapter_contract"]
    assert "--contract" in cmd_map["release_rollout_adapter_contract"]
    assert "security/release_traffic_adapter_contract.json" in cmd_map["release_rollout_adapter_contract"]
    assert "--command-template" in cmd_map["release_rollout_adapter_contract"]
    assert "rolloutctl --action {action} --to {target_version} --canary {canary_rollout_percent}" in cmd_map[
        "release_rollout_adapter_contract"
    ]
    assert "--require-runtime-command" in cmd_map["release_rollout_adapter_contract"]
    assert "--strict" in cmd_map["release_rollout_guard"]
    assert "--expected-version" in cmd_map["release_rollout_guard"]
    assert "0.1.0" in cmd_map["release_rollout_guard"]
    assert "--max-history-age-s" in cmd_map["release_rollout_guard"]
    assert "12345.0" in cmd_map["release_rollout_guard"]
    assert "--min-canary-observe-s" in cmd_map["release_rollout_guard"]
    assert "900.0" in cmd_map["release_rollout_guard"]
    assert "--allow-direct-stable" in cmd_map["release_rollout_guard"]
    assert "--strict" in cmd_map["rollback_drill_guard"]
    assert "--max-age-s" in cmd_map["rollback_drill_guard"]
    assert "45678.0" in cmd_map["rollback_drill_guard"]
    assert "--history-max-age-s" in cmd_map["rollback_drill_guard"]
    assert "56789.0" in cmd_map["rollback_drill_guard"]
    assert "--min-incident-drills" in cmd_map["rollback_drill_guard"]
    assert "2" in cmd_map["rollback_drill_guard"]
    assert "--min-rollback-bundles" in cmd_map["rollback_drill_guard"]
    assert "3" in cmd_map["rollback_drill_guard"]
    assert "--require-email-drill" in cmd_map["rollback_drill_guard"]
    assert "--require-history-rollback" in cmd_map["rollback_drill_guard"]
    assert "--require-signature" in cmd_map["rollback_drill_guard"]
    assert "--signature-pattern" in cmd_map["rollback_drill_guard"]
    assert ".data/out/rollback_drill_signature_*.json" in cmd_map["rollback_drill_guard"]
    assert "--signature-policy" in cmd_map["rollback_drill_guard"]
    assert "security/rollback_drill_signature_policy.json" in cmd_map["rollback_drill_guard"]
    assert "--signature-max-age-s" in cmd_map["rollback_drill_guard"]
    assert "4567.0" in cmd_map["rollback_drill_guard"]
    assert "--signing-key" in cmd_map["rollback_drill_guard"]
    assert "rollback-sign-key" in cmd_map["rollback_drill_guard"]
    assert "--dry-run" in cmd_map["release_rollout_executor_dry_run"]
    assert "--strict" in cmd_map["release_rollout_executor_dry_run"]
    assert "--target-version" in cmd_map["release_rollout_executor_dry_run"]
    assert "0.1.0" in cmd_map["release_rollout_executor_dry_run"]
    assert "--actor" in cmd_map["release_rollout_executor_dry_run"]
    assert "release-bot" in cmd_map["release_rollout_executor_dry_run"]
    assert "--reason" in cmd_map["release_rollout_executor_dry_run"]
    assert "preflight rollout plan" in cmd_map["release_rollout_executor_dry_run"]
    assert "--allow-gate-failures" in cmd_map["release_rollout_executor_dry_run"]
    assert "--strict" in cmd_map["correlation_trace_guard"]
    assert "--strict" in cmd_map["preflight_trend_guard"]
    assert "--require-soak" in cmd_map["preflight_trend_guard"]
    assert "--strict" in cmd_map["citation_verify_long_soak_guard"]
    assert "--policy" in cmd_map["citation_verify_long_soak_guard"]
    assert "security/long_soak_policy.json" in cmd_map["citation_verify_long_soak_guard"]
    assert "--pattern" in cmd_map["citation_verify_long_soak_guard"]
    assert ".data/out/citation_verify_soak_*.json" in cmd_map["citation_verify_long_soak_guard"]
    assert "--history-file" in cmd_map["citation_verify_long_soak_guard"]
    assert ".data/perf/citation_verify_long_soak_history.json" in cmd_map["citation_verify_long_soak_guard"]
    assert "--strict" in cmd_map["doc_encoding_guard"]
    assert "--docs-root" in cmd_map["doc_encoding_guard"]
    assert "docs" in cmd_map["doc_encoding_guard"]
    assert "--max-suspicious-files" in cmd_map["doc_encoding_guard"]
    assert "0" in cmd_map["doc_encoding_guard"]
    assert "--min-hint-count" in cmd_map["doc_encoding_guard"]
    assert "6" in cmd_map["doc_encoding_guard"]
    assert "--min-hint-ratio" in cmd_map["doc_encoding_guard"]
    assert "0.02" in cmd_map["doc_encoding_guard"]
    assert "--policy" in cmd_map["doc_reality_guard"]
    assert "security/docs_reality_policy.json" in cmd_map["doc_reality_guard"]
    assert "--max-missing-paths" in cmd_map["doc_reality_guard"]
    assert "0" in cmd_map["doc_reality_guard"]
    assert "--max-command-failures" in cmd_map["doc_reality_guard"]
    assert "--require-python-command-check" in cmd_map["doc_reality_guard"]
    assert "--strict" in cmd_map["doc_reality_guard"]
    assert "--oncall-roster" in cmd_map["incident_notify"]
    assert "security/oncall_roster.json" in cmd_map["incident_notify"]
    assert "--prefer-oncall-roster" in cmd_map["incident_notify"]
    assert "0" in cmd_map["incident_notify"]
    assert "--oncall-roster" in cmd_map["incident_config_guard"]
    assert "--require-oncall-roster" in cmd_map["incident_config_guard"]
    assert "public_release_guard" in cmd_map
    assert "scripts/public_release_guard.py" in cmd_map["public_release_guard"]
    assert "--policy" in cmd_map["public_release_guard"]
    assert "security/public_release_policy.json" in cmd_map["public_release_guard"]
    assert "--release-version" in cmd_map["public_release_guard"]
    assert "0.1.0" in cmd_map["public_release_guard"]
    assert "--changes-file" in cmd_map["public_release_guard"]
    assert "CHANGES.md" in cmd_map["public_release_guard"]
    assert "--release-notes-out" in cmd_map["public_release_guard"]
    assert ".data/out/release_notes_preflight.md" in cmd_map["public_release_guard"]
    assert "--write-release-notes" in cmd_map["public_release_guard"]
    assert "--strict" in cmd_map["public_release_guard"]
    assert "migration_assistant" in cmd_map
    assert "scripts/migration_assistant.py" in cmd_map["migration_assistant"]
    assert "--from-version" in cmd_map["migration_assistant"]
    assert "0.0.9" in cmd_map["migration_assistant"]
    assert "--to-version" in cmd_map["migration_assistant"]
    assert "0.1.0" in cmd_map["migration_assistant"]
    assert "--matrix" in cmd_map["migration_assistant"]
    assert "security/release_compat_matrix.json" in cmd_map["migration_assistant"]
    assert "--policy" in cmd_map["migration_assistant"]
    assert "security/release_policy.json" in cmd_map["migration_assistant"]
    assert "--out-md" in cmd_map["migration_assistant"]
    assert ".data/out/migration_assistant_preflight.md" in cmd_map["migration_assistant"]
    assert "--strict" in cmd_map["migration_assistant"]
    assert "artifact_schema_catalog_guard" in cmd_map
    assert "scripts/artifact_schema_catalog_guard.py" in cmd_map["artifact_schema_catalog_guard"]
    assert "--catalog" in cmd_map["artifact_schema_catalog_guard"]
    assert "docs/ARTIFACT_SCHEMA_CATALOG.md" in cmd_map["artifact_schema_catalog_guard"]
    assert "--policy" in cmd_map["artifact_schema_catalog_guard"]
    assert "security/artifact_schema_catalog_policy.json" in cmd_map["artifact_schema_catalog_guard"]
    assert "--require-evidence" in cmd_map["artifact_schema_catalog_guard"]
    assert "--strict" in cmd_map["artifact_schema_catalog_guard"]
    assert "data_classification_guard" in cmd_map
    assert "scripts/data_classification_guard.py" in cmd_map["data_classification_guard"]
    assert "--policy" in cmd_map["data_classification_guard"]
    assert "security/data_classification_policy.json" in cmd_map["data_classification_guard"]
    assert "--max-unmasked-findings" in cmd_map["data_classification_guard"]
    assert "0" in cmd_map["data_classification_guard"]
    assert "--require-rules" in cmd_map["data_classification_guard"]
    assert "--strict" in cmd_map["data_classification_guard"]
    assert "audit_trail_integrity" in cmd_map
    assert "scripts/verify_audit_chain.py" in cmd_map["audit_trail_integrity"]
    assert "--strict" in cmd_map["audit_trail_integrity"]
    assert "--require-log" in cmd_map["audit_trail_integrity"]
    assert "--require-state" in cmd_map["audit_trail_integrity"]
    assert "--log" in cmd_map["audit_trail_integrity"]
    assert ".data/audit/operations_audit_chain.ndjson" in cmd_map["audit_trail_integrity"]
    assert "--state-file" in cmd_map["audit_trail_integrity"]
    assert ".data/audit/operations_audit_chain_state.json" in cmd_map["audit_trail_integrity"]
    assert "--max-age-s" in cmd_map["audit_trail_integrity"]
    assert "900.0" in cmd_map["audit_trail_integrity"]
    assert "--no-write-state" in cmd_map["audit_trail_integrity"]


def test_preflight_cli_soak_args_override_env(monkeypatch, tmp_path: Path) -> None:
    soak_calls: list[dict[str, object]] = []

    def _fake_run_cmd(*, step_id: str, cmd: list[str], cwd: str = ".", env=None):  # noqa: ANN001
        return _ok_step(step_id, cmd)

    def _fake_load(*, host: str, port: int, quick: bool) -> release_preflight.StepResult:
        return _ok_step("citation_metrics_load_probe", ["fake-load"])

    def _fake_soak(
        *,
        host: str,
        port: int,
        quick: bool,
        duration_s: float,
        interval_s: float,
        requests_per_window: int,
        concurrency: int,
        timeout_s: float,
    ) -> release_preflight.StepResult:
        soak_calls.append(
            {
                "duration_s": duration_s,
                "interval_s": interval_s,
                "requests_per_window": requests_per_window,
                "concurrency": concurrency,
            }
        )
        return _ok_step("citation_metrics_soak_probe", ["fake-soak"])

    monkeypatch.setattr(release_preflight, "_run_cmd", _fake_run_cmd)
    monkeypatch.setattr(release_preflight, "_run_load_probe_with_temp_server", _fake_load)
    monkeypatch.setattr(release_preflight, "_run_soak_with_temp_server", _fake_soak)

    monkeypatch.setenv("WA_PREFLIGHT_SOAK_DURATION_S", "99")
    monkeypatch.setenv("WA_PREFLIGHT_SOAK_INTERVAL_S", "99")
    monkeypatch.setenv("WA_PREFLIGHT_SOAK_REQUESTS_PER_WINDOW", "99")
    monkeypatch.setenv("WA_PREFLIGHT_SOAK_CONCURRENCY", "99")

    out_path = tmp_path / "preflight.json"
    argv = _base_args(out_path)
    argv.extend(
        [
            "--skip-capacity-guard",
            "--skip-capacity-baseline-refresh",
            "--skip-trend-guard",
            "--soak-duration-s",
            "12",
            "--soak-interval-s",
            "7",
            "--soak-requests-per-window",
            "5",
            "--soak-concurrency",
            "2",
        ]
    )
    monkeypatch.setattr(sys, "argv", argv)
    code = release_preflight.main()

    assert code == 0
    assert len(soak_calls) == 1
    assert soak_calls[0]["duration_s"] == 12.0
    assert soak_calls[0]["interval_s"] == 7.0
    assert soak_calls[0]["requests_per_window"] == 5
    assert soak_calls[0]["concurrency"] == 2


def test_preflight_runs_capacity_failure_diagnostic(monkeypatch, tmp_path: Path) -> None:
    run_cmd_calls: list[tuple[str, list[str]]] = []

    def _fake_run_cmd(*, step_id: str, cmd: list[str], cwd: str = ".", env=None):  # noqa: ANN001
        run_cmd_calls.append((step_id, list(cmd)))
        if step_id == "capacity_guard":
            return release_preflight.StepResult(
                id=step_id,
                ok=False,
                return_code=2,
                duration_s=0.001,
                command=list(cmd),
                cwd=cwd,
            )
        return _ok_step(step_id, cmd)

    def _fake_load(*, host: str, port: int, quick: bool) -> release_preflight.StepResult:
        return _ok_step("citation_metrics_load_probe", ["fake-load"])

    monkeypatch.setattr(release_preflight, "_run_cmd", _fake_run_cmd)
    monkeypatch.setattr(release_preflight, "_run_load_probe_with_temp_server", _fake_load)
    monkeypatch.setenv("WA_CAPACITY_GUARD_STRICT", "1")
    monkeypatch.setenv("WA_CAPACITY_BASELINE_ALLOW_REGRESSION", "1")

    out_path = tmp_path / "preflight.json"
    argv = _base_args(out_path)
    argv.extend(["--skip-capacity-baseline-refresh", "--skip-trend-guard"])
    monkeypatch.setattr(sys, "argv", argv)
    code = release_preflight.main()

    assert code == 2
    cmd_map = {step_id: cmd for step_id, cmd in run_cmd_calls}
    assert "capacity_guard" in cmd_map
    assert "capacity_baseline_dry_run_on_guard_failure" in cmd_map
    assert "--dry-run" in cmd_map["capacity_baseline_dry_run_on_guard_failure"]
    assert "--allow-regression" in cmd_map["capacity_baseline_dry_run_on_guard_failure"]
    assert "capacity_baseline_refresh" not in cmd_map


def test_infer_release_tier_from_branch_and_env() -> None:
    assert release_preflight._infer_release_tier(release_tier="", release_branch="main", runtime_env="") == "prod"
    assert release_preflight._infer_release_tier(release_tier="", release_branch="main", runtime_env="ci") == "prod"
    assert release_preflight._infer_release_tier(release_tier="", release_branch="feature/demo", runtime_env="") == "dev"
    assert release_preflight._infer_release_tier(release_tier="", release_branch="", runtime_env="staging") == "staging"
    assert release_preflight._infer_release_tier(release_tier="prod", release_branch="feature/x", runtime_env="dev") == "prod"


def test_preflight_runs_capacity_threshold_suggest(monkeypatch, tmp_path: Path) -> None:
    run_cmd_calls: list[tuple[str, list[str]]] = []

    def _fake_run_cmd(*, step_id: str, cmd: list[str], cwd: str = ".", env=None):  # noqa: ANN001
        run_cmd_calls.append((step_id, list(cmd)))
        return _ok_step(step_id, cmd)

    def _fake_load(*, host: str, port: int, quick: bool) -> release_preflight.StepResult:
        return _ok_step("citation_metrics_load_probe", ["fake-load"])

    monkeypatch.setattr(release_preflight, "_run_cmd", _fake_run_cmd)
    monkeypatch.setattr(release_preflight, "_run_load_probe_with_temp_server", _fake_load)
    monkeypatch.setenv("WA_CAPACITY_GUARD_STRICT", "1")

    out_path = tmp_path / "preflight.json"
    argv = _base_args(out_path)
    argv.extend(["--skip-capacity-baseline-refresh", "--skip-trend-guard"])
    monkeypatch.setattr(sys, "argv", argv)
    code = release_preflight.main()

    assert code == 0
    cmd_map = {step_id: cmd for step_id, cmd in run_cmd_calls}
    assert "capacity_alert_threshold_suggest" in cmd_map
    assert "--write-thresholds" in cmd_map["capacity_alert_threshold_suggest"]
    assert "capacity_alert_policy_drift_check" in cmd_map
    assert "--write-patch" in cmd_map["capacity_alert_policy_drift_check"]
    assert "capacity_alert_policy_patch_validate" in cmd_map
    assert "--dry-run" in cmd_map["capacity_alert_policy_patch_validate"]
    assert "capacity_stress_gate" in cmd_map


def test_preflight_manifest_gate_evidence_env(monkeypatch, tmp_path: Path) -> None:
    run_cmd_calls: list[tuple[str, list[str]]] = []

    def _fake_run_cmd(*, step_id: str, cmd: list[str], cwd: str = ".", env=None):  # noqa: ANN001
        run_cmd_calls.append((step_id, list(cmd)))
        return _ok_step(step_id, cmd)

    monkeypatch.setattr(release_preflight, "_run_cmd", _fake_run_cmd)
    out_path = tmp_path / "preflight.json"
    argv = _base_args(out_path)
    argv = [item for item in argv if item != "--skip-release-manifest"]
    monkeypatch.setenv("WA_RELEASE_MANIFEST_REQUIRE_GATE_EVIDENCE", "1")
    monkeypatch.setenv("WA_RELEASE_CANDIDATE_ID", "rc-manifest-1")
    monkeypatch.setattr(sys, "argv", argv)
    code = release_preflight.main()

    assert code == 0
    cmd_map = {step_id: cmd for step_id, cmd in run_cmd_calls}
    assert "generate_release_manifest" in cmd_map
    assert "--require-gate-evidence" in cmd_map["generate_release_manifest"]
    assert "--release-candidate-id" in cmd_map["generate_release_manifest"]
    assert "rc-manifest-1" in cmd_map["generate_release_manifest"]
