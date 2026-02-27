"""Release Preflight Runtime command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations


_BIND_SKIP_NAMES = {
    "__builtins__",
    "__cached__",
    "__doc__",
    "__file__",
    "__loader__",
    "__name__",
    "__package__",
    "__spec__",
    "_BIND_SKIP_NAMES",
    "bind",
    "main",
}


def bind(namespace: dict) -> None:
    for key, value in namespace.items():
        if key in _BIND_SKIP_NAMES:
            continue
        globals()[key] = value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Release preflight checks for writing-agent.")
    parser.add_argument("--quick", action="store_true", help="Run reduced checks for faster feedback.")
    parser.add_argument("--skip-pytest", action="store_true")
    parser.add_argument("--skip-frontend", action="store_true")
    parser.add_argument("--skip-rust", action="store_true")
    parser.add_argument("--skip-file-line-limits-guard", action="store_true")
    parser.add_argument("--skip-function-complexity-guard", action="store_true")
    parser.add_argument("--skip-architecture-boundaries-guard", action="store_true")
    parser.add_argument("--skip-deps-audit", action="store_true")
    parser.add_argument("--skip-sbom", action="store_true")
    parser.add_argument("--skip-release-governance", action="store_true")
    parser.add_argument("--skip-release-manifest", action="store_true")
    parser.add_argument("--skip-release-channels", action="store_true")
    parser.add_argument("--skip-release-compat-matrix", action="store_true")
    parser.add_argument("--skip-release-rollout-adapter-contract", action="store_true")
    parser.add_argument("--skip-release-rollout-guard", action="store_true")
    parser.add_argument("--skip-release-rollout-plan", action="store_true")
    parser.add_argument("--skip-rollback-bundle", action="store_true")
    parser.add_argument("--skip-rollback-drill-guard", action="store_true")
    parser.add_argument("--skip-doc-encoding-guard", action="store_true")
    parser.add_argument("--skip-doc-reality-guard", action="store_true")
    parser.add_argument("--skip-slo-guard", action="store_true")
    parser.add_argument("--skip-alert-escalation", action="store_true")
    parser.add_argument("--skip-incident-report", action="store_true")
    parser.add_argument("--skip-correlation-guard", action="store_true")
    parser.add_argument("--skip-incident-notify", action="store_true")
    parser.add_argument("--skip-incident-config-guard", action="store_true")
    parser.add_argument("--skip-sensitive-output-scan", action="store_true")
    parser.add_argument("--skip-data-classification-guard", action="store_true")
    parser.add_argument("--skip-artifact-schema-catalog-guard", action="store_true")
    parser.add_argument("--skip-public-release-guard", action="store_true")
    parser.add_argument("--skip-migration-assistant", action="store_true")
    parser.add_argument("--skip-audit-trail-verify", action="store_true")
    parser.add_argument("--skip-trend-guard", action="store_true")
    parser.add_argument("--skip-long-soak-guard", action="store_true")
    parser.add_argument("--skip-capacity-guard", action="store_true")
    parser.add_argument("--skip-capacity-baseline-refresh", action="store_true")
    parser.add_argument("--skip-capacity-forecast", action="store_true")
    parser.add_argument("--skip-capacity-threshold-suggest", action="store_true")
    parser.add_argument("--skip-capacity-policy-drift-check", action="store_true")
    parser.add_argument("--skip-capacity-policy-patch-validate", action="store_true")
    parser.add_argument("--skip-capacity-stress-gate", action="store_true")
    parser.add_argument("--skip-capacity-failure-diagnostic", action="store_true")
    parser.add_argument("--skip-soak-probe", action="store_true")
    parser.add_argument("--skip-load-probe", action="store_true")
    parser.add_argument("--skip-chaos", action="store_true")
    parser.add_argument("--soak-duration-s", type=float, default=0.0)
    parser.add_argument("--soak-interval-s", type=float, default=None)
    parser.add_argument("--soak-requests-per-window", type=int, default=None)
    parser.add_argument("--soak-concurrency", type=int, default=None)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18130)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    started = time.time()
    steps: list[StepResult] = []

    def append_or_exit(step: StepResult) -> bool:
        steps.append(step)
        return step.ok

    if not args.skip_pytest:
        if not append_or_exit(
            _run_cmd(
                step_id="pytest_citation_verify",
                cmd=[sys.executable, "-m", "pytest", "-q", "tests/test_citation_verify_and_delete.py"],
            )
        ):
            return _finish(started, steps, args.out)
        if not args.quick:
            if not append_or_exit(_run_cmd(step_id="pytest_all", cmd=[sys.executable, "-m", "pytest", "-q"])):
                return _finish(started, steps, args.out)

    if not args.skip_file_line_limits_guard:
        file_line_config = _env_text("WA_FILE_LINE_LIMITS_CONFIG", "security/file_line_limits.json")
        file_line_cmd = [
            sys.executable,
            "scripts/guard_file_line_limits.py",
            "--config",
            file_line_config,
        ]
        if not append_or_exit(_run_cmd(step_id="file_line_limits_guard", cmd=file_line_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_function_complexity_guard:
        complexity_config = _env_text("WA_FUNCTION_COMPLEXITY_CONFIG", "security/function_complexity_limits.json")
        complexity_cmd = [
            sys.executable,
            "scripts/guard_function_complexity.py",
            "--config",
            complexity_config,
        ]
        if not append_or_exit(_run_cmd(step_id="function_complexity_guard", cmd=complexity_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_architecture_boundaries_guard:
        arch_config = _env_text("WA_ARCH_BOUNDARY_POLICY", "security/architecture_boundaries.json")
        arch_cmd = [
            sys.executable,
            "scripts/guard_architecture_boundaries.py",
            "--config",
            arch_config,
        ]
        if not append_or_exit(_run_cmd(step_id="architecture_boundaries_guard", cmd=arch_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_frontend:
        if not append_or_exit(
            _run_cmd(
                step_id="npm_ci_frontend",
                cmd=_npm_cmd(["--prefix", "writing_agent/web/frontend_svelte", "ci"]),
            )
        ):
            return _finish(started, steps, args.out)
        if not append_or_exit(
            _run_cmd(
                step_id="npm_build_frontend",
                cmd=_npm_cmd(["--prefix", "writing_agent/web/frontend_svelte", "run", "build"]),
            )
        ):
            return _finish(started, steps, args.out)

    if not args.skip_deps_audit:
        dep_cmd = [
            sys.executable,
            "scripts/dependency_audit.py",
            "--max-npm-dev-moderate",
            "15" if args.quick else "10",
            "--max-npm-dev-high",
            "0",
            "--max-npm-dev-critical",
            "0",
            "--max-npm-prod-moderate",
            "0",
            "--max-npm-prod-high",
            "0",
            "--max-npm-prod-critical",
            "0",
            "--max-pip-total",
            "0",
        ]
        baseline_path = Path("security/dependency_baseline.json")
        if baseline_path.exists():
            dep_cmd.extend(["--baseline", str(baseline_path.as_posix()), "--fail-on-regression"])
        if args.skip_frontend:
            dep_cmd.append("--skip-npm")
        if _env_flag("WA_PREFLIGHT_REQUIRE_PIP_AUDIT"):
            dep_cmd.append("--require-pip-audit")
        if not append_or_exit(_run_cmd(step_id="dependency_audit", cmd=dep_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_sbom:
        sbom_cmd = [
            sys.executable,
            "scripts/generate_sbom.py",
            "--out-dir",
            ".data/out/sbom",
            "--strict",
        ]
        if args.skip_frontend:
            sbom_cmd.append("--skip-frontend")
        if not append_or_exit(_run_cmd(step_id="generate_sbom", cmd=sbom_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_release_governance:
        gov_cmd = [
            sys.executable,
            "scripts/release_governance_check.py",
        ]
        if _env_flag("WA_RELEASE_GOVERNANCE_STRICT"):
            gov_cmd.append("--strict")
        if _env_flag("WA_RELEASE_REQUIRE_CHANGES_VERSION"):
            gov_cmd.append("--require-changes-version")
        if not append_or_exit(_run_cmd(step_id="release_governance_check", cmd=gov_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_release_manifest:
        manifest_cmd = [
            sys.executable,
            "scripts/generate_release_manifest.py",
        ]
        if _env_flag("WA_RELEASE_REQUIRE_CLEAN_GIT"):
            manifest_cmd.append("--require-clean-git")
        if _env_flag("WA_RELEASE_MANIFEST_REQUIRE_GATE_EVIDENCE"):
            manifest_cmd.append("--require-gate-evidence")
        release_candidate_id = _env_text("WA_RELEASE_CANDIDATE_ID")
        if release_candidate_id:
            manifest_cmd.extend(["--release-candidate-id", release_candidate_id])
        if not append_or_exit(_run_cmd(step_id="generate_release_manifest", cmd=manifest_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_public_release_guard:
        public_release_cmd = [
            sys.executable,
            "scripts/public_release_guard.py",
        ]
        public_release_policy = _env_text("WA_PUBLIC_RELEASE_POLICY_FILE")
        if public_release_policy:
            public_release_cmd.extend(["--policy", public_release_policy])
        public_release_version = _env_text("WA_PUBLIC_RELEASE_VERSION")
        if public_release_version:
            public_release_cmd.extend(["--release-version", public_release_version])
        public_release_changes = _env_text("WA_PUBLIC_RELEASE_CHANGES_FILE")
        if public_release_changes:
            public_release_cmd.extend(["--changes-file", public_release_changes])
        public_release_notes_out = _env_text("WA_PUBLIC_RELEASE_NOTES_OUT")
        if public_release_notes_out:
            public_release_cmd.extend(["--release-notes-out", public_release_notes_out])
        if _env_flag("WA_PUBLIC_RELEASE_WRITE_RELEASE_NOTES"):
            public_release_cmd.append("--write-release-notes")
        if _env_flag("WA_PUBLIC_RELEASE_GUARD_STRICT"):
            public_release_cmd.append("--strict")
        if not append_or_exit(_run_cmd(step_id="public_release_guard", cmd=public_release_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_release_channels:
        channel_cmd = [
            sys.executable,
            "scripts/release_channel_control.py",
            "validate",
        ]
        if _env_flag("WA_RELEASE_CHANNEL_STRICT"):
            channel_cmd.append("--strict")
        if not append_or_exit(_run_cmd(step_id="release_channel_validate", cmd=channel_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_release_compat_matrix:
        compat_cmd = [
            sys.executable,
            "scripts/release_compat_matrix.py",
        ]
        compat_policy = _env_text("WA_RELEASE_COMPAT_POLICY_FILE")
        if compat_policy:
            compat_cmd.extend(["--policy", compat_policy])
        compat_matrix = _env_text("WA_RELEASE_COMPAT_MATRIX_FILE")
        if compat_matrix:
            compat_cmd.extend(["--matrix", compat_matrix])
        if _env_flag("WA_RELEASE_COMPAT_MATRIX_STRICT"):
            compat_cmd.append("--strict")
        if not append_or_exit(_run_cmd(step_id="release_compat_matrix", cmd=compat_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_migration_assistant:
        migration_cmd = [
            sys.executable,
            "scripts/migration_assistant.py",
        ]
        migration_from = _env_text("WA_MIGRATION_FROM_VERSION")
        if migration_from:
            migration_cmd.extend(["--from-version", migration_from])
        migration_to = _env_text("WA_MIGRATION_TO_VERSION")
        if migration_to:
            migration_cmd.extend(["--to-version", migration_to])
        migration_matrix = _env_text("WA_MIGRATION_MATRIX_FILE")
        if migration_matrix:
            migration_cmd.extend(["--matrix", migration_matrix])
        migration_policy = _env_text("WA_MIGRATION_POLICY_FILE")
        if migration_policy:
            migration_cmd.extend(["--policy", migration_policy])
        migration_out_md = _env_text("WA_MIGRATION_OUT_MD")
        if migration_out_md:
            migration_cmd.extend(["--out-md", migration_out_md])
        if _env_flag("WA_MIGRATION_ASSISTANT_STRICT"):
            migration_cmd.append("--strict")
        if not append_or_exit(_run_cmd(step_id="migration_assistant", cmd=migration_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_release_rollout_adapter_contract:
        adapter_cmd = [
            sys.executable,
            "scripts/release_rollout_adapter_contract_check.py",
        ]
        adapter_contract = _env_text("WA_RELEASE_TRAFFIC_ADAPTER_CONTRACT_FILE")
        if adapter_contract:
            adapter_cmd.extend(["--contract", adapter_contract])
        adapter_runtime_command = _env_text("WA_RELEASE_TRAFFIC_APPLY_COMMAND")
        if adapter_runtime_command:
            adapter_cmd.extend(["--command-template", adapter_runtime_command])
        if _env_flag("WA_RELEASE_TRAFFIC_ADAPTER_REQUIRE_RUNTIME_COMMAND"):
            adapter_cmd.append("--require-runtime-command")
        if _env_flag("WA_RELEASE_TRAFFIC_ADAPTER_STRICT"):
            adapter_cmd.append("--strict")
        if not append_or_exit(_run_cmd(step_id="release_rollout_adapter_contract", cmd=adapter_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_release_rollout_guard:
        rollout_cmd = [
            sys.executable,
            "scripts/release_rollout_guard.py",
        ]
        expected_version = _env_text("WA_RELEASE_ROLLOUT_EXPECTED_VERSION")
        if expected_version:
            rollout_cmd.extend(["--expected-version", expected_version])
        rollout_max_history_age = _env_float("WA_RELEASE_ROLLOUT_MAX_HISTORY_AGE_S", -1.0)
        if rollout_max_history_age > 0:
            rollout_cmd.extend(["--max-history-age-s", str(rollout_max_history_age)])
        rollout_min_observe = _env_float("WA_RELEASE_ROLLOUT_MIN_CANARY_OBSERVE_S", -1.0)
        if rollout_min_observe >= 0:
            rollout_cmd.extend(["--min-canary-observe-s", str(rollout_min_observe)])
        if _env_flag("WA_RELEASE_ROLLOUT_ALLOW_DIRECT_STABLE"):
            rollout_cmd.append("--allow-direct-stable")
        if _env_flag("WA_RELEASE_ROLLOUT_STRICT"):
            rollout_cmd.append("--strict")
        if not append_or_exit(_run_cmd(step_id="release_rollout_guard", cmd=rollout_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_rollback_bundle:
        rollback_cmd = [
            sys.executable,
            "scripts/create_rollback_bundle.py",
            "--label",
            "preflight",
            "--recent",
            "2" if args.quick else "4",
        ]
        if not append_or_exit(_run_cmd(step_id="create_rollback_bundle", cmd=rollback_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_rollback_drill_guard:
        drill_cmd = [
            sys.executable,
            "scripts/rollback_drill_guard.py",
        ]
        drill_max_age = _env_float("WA_ROLLBACK_DRILL_MAX_AGE_S", -1.0)
        if drill_max_age > 0:
            drill_cmd.extend(["--max-age-s", str(drill_max_age)])
        drill_history_max_age = _env_float("WA_ROLLBACK_DRILL_HISTORY_MAX_AGE_S", -1.0)
        if drill_history_max_age > 0:
            drill_cmd.extend(["--history-max-age-s", str(drill_history_max_age)])
        drill_min_incident = _env_int("WA_ROLLBACK_DRILL_MIN_INCIDENT_DRILLS", -1)
        if drill_min_incident > 0:
            drill_cmd.extend(["--min-incident-drills", str(drill_min_incident)])
        drill_min_bundles = _env_int("WA_ROLLBACK_DRILL_MIN_ROLLBACK_BUNDLES", -1)
        if drill_min_bundles > 0:
            drill_cmd.extend(["--min-rollback-bundles", str(drill_min_bundles)])
        if _env_flag("WA_ROLLBACK_DRILL_REQUIRE_EMAIL"):
            drill_cmd.append("--require-email-drill")
        if _env_flag("WA_ROLLBACK_DRILL_REQUIRE_HISTORY_ROLLBACK"):
            drill_cmd.append("--require-history-rollback")
        drill_signature_pattern = _env_text("WA_ROLLBACK_DRILL_SIGNATURE_PATTERN")
        if drill_signature_pattern:
            drill_cmd.extend(["--signature-pattern", drill_signature_pattern])
        drill_signature_policy = _env_text("WA_ROLLBACK_DRILL_SIGNATURE_POLICY")
        if drill_signature_policy:
            drill_cmd.extend(["--signature-policy", drill_signature_policy])
        drill_signature_max_age = _env_float("WA_ROLLBACK_DRILL_SIGNATURE_MAX_AGE_S", -1.0)
        if drill_signature_max_age > 0:
            drill_cmd.extend(["--signature-max-age-s", str(drill_signature_max_age)])
        if _env_flag("WA_ROLLBACK_DRILL_REQUIRE_SIGNATURE"):
            drill_cmd.append("--require-signature")
        drill_signing_key = _env_text("WA_ROLLBACK_DRILL_SIGNING_KEY")
        if drill_signing_key:
            drill_cmd.extend(["--signing-key", drill_signing_key])
        if _env_flag("WA_ROLLBACK_DRILL_STRICT"):
            drill_cmd.append("--strict")
        if not append_or_exit(_run_cmd(step_id="rollback_drill_guard", cmd=drill_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_doc_encoding_guard:
        doc_encoding_cmd = [
            sys.executable,
            "scripts/doc_encoding_guard.py",
        ]
        docs_root = _env_text("WA_DOC_ENCODING_GUARD_ROOT")
        if docs_root:
            doc_encoding_cmd.extend(["--docs-root", docs_root])
        max_suspicious = _env_int("WA_DOC_ENCODING_MAX_SUSPICIOUS_FILES", -1)
        if max_suspicious >= 0:
            doc_encoding_cmd.extend(["--max-suspicious-files", str(max_suspicious)])
        min_hint_count = _env_int("WA_DOC_ENCODING_MIN_HINT_COUNT", -1)
        if min_hint_count > 0:
            doc_encoding_cmd.extend(["--min-hint-count", str(min_hint_count)])
        min_hint_ratio = _env_float("WA_DOC_ENCODING_MIN_HINT_RATIO", -1.0)
        if min_hint_ratio >= 0:
            doc_encoding_cmd.extend(["--min-hint-ratio", str(min_hint_ratio)])
        if _env_flag("WA_DOC_ENCODING_GUARD_STRICT"):
            doc_encoding_cmd.append("--strict")
        if not append_or_exit(_run_cmd(step_id="doc_encoding_guard", cmd=doc_encoding_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_doc_reality_guard:
        doc_reality_cmd = [
            sys.executable,
            "scripts/docs_reality_guard.py",
        ]
        doc_reality_policy = _env_text("WA_DOC_REALITY_POLICY_FILE")
        if doc_reality_policy:
            doc_reality_cmd.extend(["--policy", doc_reality_policy])
        max_missing_paths = _env_int("WA_DOC_REALITY_GUARD_MAX_MISSING_PATHS", -1)
        if max_missing_paths >= 0:
            doc_reality_cmd.extend(["--max-missing-paths", str(max_missing_paths)])
        max_command_failures = _env_int("WA_DOC_REALITY_GUARD_MAX_COMMAND_FAILURES", -1)
        if max_command_failures >= 0:
            doc_reality_cmd.extend(["--max-command-failures", str(max_command_failures)])
        if _env_flag("WA_DOC_REALITY_GUARD_REQUIRE_PYTHON_CHECK"):
            doc_reality_cmd.append("--require-python-command-check")
        if _env_flag("WA_DOC_REALITY_GUARD_STRICT"):
            doc_reality_cmd.append("--strict")
        if not append_or_exit(_run_cmd(step_id="doc_reality_guard", cmd=doc_reality_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_artifact_schema_catalog_guard:
        schema_catalog_cmd = [
            sys.executable,
            "scripts/artifact_schema_catalog_guard.py",
        ]
        schema_catalog_file = _env_text("WA_ARTIFACT_SCHEMA_CATALOG_FILE")
        if schema_catalog_file:
            schema_catalog_cmd.extend(["--catalog", schema_catalog_file])
        schema_catalog_policy = _env_text("WA_ARTIFACT_SCHEMA_CATALOG_POLICY_FILE")
        if schema_catalog_policy:
            schema_catalog_cmd.extend(["--policy", schema_catalog_policy])
        if _env_flag("WA_ARTIFACT_SCHEMA_CATALOG_REQUIRE_EVIDENCE"):
            schema_catalog_cmd.append("--require-evidence")
        if _env_flag("WA_ARTIFACT_SCHEMA_CATALOG_STRICT"):
            schema_catalog_cmd.append("--strict")
        if not append_or_exit(_run_cmd(step_id="artifact_schema_catalog_guard", cmd=schema_catalog_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_release_rollout_plan:
        rollout_plan_cmd = [
            sys.executable,
            "scripts/release_rollout_executor.py",
            "--dry-run",
        ]
        rollout_target = _env_text("WA_RELEASE_ROLLOUT_TARGET_VERSION")
        if rollout_target:
            rollout_plan_cmd.extend(["--target-version", rollout_target])
        rollout_actor = _env_text("WA_RELEASE_ROLLOUT_ACTOR")
        if rollout_actor:
            rollout_plan_cmd.extend(["--actor", rollout_actor])
        rollout_reason = _env_text("WA_RELEASE_ROLLOUT_REASON")
        if rollout_reason:
            rollout_plan_cmd.extend(["--reason", rollout_reason])
        if _env_flag("WA_RELEASE_ROLLOUT_PLAN_ALLOW_GATE_FAILURES"):
            rollout_plan_cmd.append("--allow-gate-failures")
        if _env_flag("WA_RELEASE_ROLLOUT_PLAN_STRICT"):
            rollout_plan_cmd.append("--strict")
        if not append_or_exit(_run_cmd(step_id="release_rollout_executor_dry_run", cmd=rollout_plan_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_rust:
        if not append_or_exit(
            _run_cmd(step_id="cargo_test_engine", cmd=["cargo", "test", "--quiet"], cwd="engine")
        ):
            return _finish(started, steps, args.out)

    if not args.skip_load_probe:
        if not append_or_exit(
            _run_load_probe_with_temp_server(host=str(args.host), port=int(args.port), quick=bool(args.quick))
        ):
            return _finish(started, steps, args.out)

    soak_duration, soak_interval, soak_requests, soak_concurrency = _resolve_soak_settings(args)

    if (not args.skip_soak_probe) and (not args.skip_load_probe) and (soak_duration > 0):
        if not append_or_exit(
            _run_soak_with_temp_server(
                host=str(args.host),
                port=int(args.port) + 1,
                quick=bool(args.quick),
                duration_s=soak_duration,
                interval_s=soak_interval,
                requests_per_window=soak_requests,
                concurrency=soak_concurrency,
                timeout_s=6.0,
            )
        ):
            return _finish(started, steps, args.out)

    if not args.skip_slo_guard and not args.skip_load_probe:
        slo_cmd = [
            sys.executable,
            "scripts/slo_guard.py",
        ]
        if bool(args.quick):
            slo_cmd.append("--quick")
        if not append_or_exit(_run_cmd(step_id="slo_guard", cmd=slo_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_capacity_guard and not args.skip_load_probe:
        release_branch = _env_text("WA_CAPACITY_RELEASE_BRANCH") or _env_text("GITHUB_REF_NAME")
        runtime_env = _env_text("WA_RUNTIME_ENV")
        capacity_profile = _env_text("WA_CAPACITY_PROFILE")
        release_tier = _infer_release_tier(
            release_tier=_env_text("WA_CAPACITY_RELEASE_TIER"),
            release_branch=release_branch,
            runtime_env=runtime_env,
        )
        capacity_cmd = [
            sys.executable,
            "scripts/capacity_guard.py",
        ]
        if bool(args.quick):
            capacity_cmd.append("--quick")
        if _env_flag("WA_CAPACITY_GUARD_STRICT"):
            capacity_cmd.append("--strict")
        if _env_flag("WA_CAPACITY_REQUIRE_SOAK"):
            capacity_cmd.append("--require-soak")
        if release_tier:
            capacity_cmd.extend(["--release-tier", release_tier])
        if release_branch:
            capacity_cmd.extend(["--release-branch", release_branch])
        if runtime_env:
            capacity_cmd.extend(["--runtime-env", runtime_env])
        if capacity_profile:
            capacity_cmd.extend(["--capacity-profile", capacity_profile])
        capacity_step = _run_cmd(step_id="capacity_guard", cmd=capacity_cmd)
        steps.append(capacity_step)
        if not capacity_step.ok:
            if not args.skip_capacity_failure_diagnostic:
                diag_cmd = [
                    sys.executable,
                    "scripts/update_capacity_baseline.py",
                    "--dry-run",
                    "--reason",
                    "capacity guard failure diagnostic",
                ]
                if capacity_profile:
                    diag_cmd.extend(["--capacity-profile", capacity_profile])
                if _env_flag("WA_CAPACITY_BASELINE_ALLOW_REGRESSION"):
                    diag_cmd.append("--allow-regression")
                steps.append(
                    _run_cmd(
                        step_id="capacity_baseline_dry_run_on_guard_failure",
                        cmd=diag_cmd,
                    )
                )
            return _finish(started, steps, args.out)

    if not args.skip_capacity_forecast and not args.skip_load_probe:
        capacity_profile = _env_text("WA_CAPACITY_PROFILE")
        forecast_cmd = [
            sys.executable,
            "scripts/capacity_forecast.py",
        ]
        if bool(args.quick):
            forecast_cmd.extend(["--load-window", "8", "--min-samples", "4", "--horizon-days", "14"])
        horizon_days = _env_float("WA_CAPACITY_FORECAST_HORIZON_DAYS", -1.0)
        if horizon_days > 0:
            forecast_cmd.extend(["--horizon-days", str(horizon_days)])
        min_samples = _env_int("WA_CAPACITY_FORECAST_MIN_SAMPLES", -1)
        if min_samples > 1:
            forecast_cmd.extend(["--min-samples", str(min_samples)])
        if capacity_profile:
            forecast_cmd.extend(["--capacity-profile", capacity_profile])
        if _env_flag("WA_CAPACITY_FORECAST_STRICT"):
            forecast_cmd.append("--strict")
        if not append_or_exit(_run_cmd(step_id="capacity_forecast", cmd=forecast_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_capacity_threshold_suggest and not args.skip_load_probe:
        capacity_profile = _env_text("WA_CAPACITY_PROFILE")
        suggest_cmd = [
            sys.executable,
            "scripts/suggest_capacity_alert_thresholds.py",
            "--load-window",
            "4" if args.quick else "8",
            "--soak-window",
            "3" if args.quick else "6",
            "--write-thresholds",
            ".data/out/capacity_alert_thresholds_suggested.json",
        ]
        if capacity_profile:
            suggest_cmd.extend(["--capacity-profile", capacity_profile])
        if _env_flag("WA_CAPACITY_REQUIRE_SOAK"):
            suggest_cmd.append("--prefer-soak")
        if not append_or_exit(_run_cmd(step_id="capacity_alert_threshold_suggest", cmd=suggest_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_capacity_policy_drift_check and not args.skip_load_probe:
        capacity_profile = _env_text("WA_CAPACITY_PROFILE")
        drift_cmd = [
            sys.executable,
            "scripts/capacity_alert_policy_drift.py",
            "--suggested",
            ".data/out/capacity_alert_thresholds_suggested.json",
            "--write-patch",
            ".data/out/capacity_policy_threshold_patch_suggested.json",
        ]
        if capacity_profile:
            drift_cmd.extend(["--capacity-profile", capacity_profile])
        policy_level = _env_text("WA_CAPACITY_POLICY_LEVEL", "critical").lower()
        if policy_level in {"warn", "critical"}:
            drift_cmd.extend(["--policy-level", policy_level])
        max_relative_drift = _env_float("WA_CAPACITY_POLICY_MAX_RELATIVE_DRIFT", -1.0)
        if max_relative_drift > 0:
            drift_cmd.extend(["--max-relative-drift", str(max_relative_drift)])
        min_confidence = _env_float("WA_CAPACITY_POLICY_MIN_CONFIDENCE", -1.0)
        if min_confidence >= 0:
            drift_cmd.extend(["--min-confidence", str(min_confidence)])
        if _env_flag("WA_CAPACITY_POLICY_DRIFT_STRICT"):
            drift_cmd.append("--strict")
        if not append_or_exit(_run_cmd(step_id="capacity_alert_policy_drift_check", cmd=drift_cmd)):
            return _finish(started, steps, args.out)

    if (
        not args.skip_capacity_policy_patch_validate
        and not args.skip_load_probe
        and not args.skip_capacity_policy_drift_check
    ):
        patch_cmd = [
            sys.executable,
            "scripts/apply_capacity_policy_threshold_patch.py",
            "--patch",
            ".data/out/capacity_policy_threshold_patch_suggested.json",
            "--dry-run",
            "--reason",
            "preflight capacity policy patch validation",
        ]
        capacity_profile = _env_text("WA_CAPACITY_PROFILE")
        if capacity_profile:
            patch_cmd.extend(["--capacity-profile", capacity_profile])
        patch_max_exceeded = _env_int("WA_CAPACITY_POLICY_PATCH_MAX_EXCEEDED", -1)
        if patch_max_exceeded >= 0:
            patch_cmd.extend(["--max-exceeded-metrics", str(patch_max_exceeded)])
        patch_min_confidence = _env_float("WA_CAPACITY_POLICY_PATCH_MIN_CONFIDENCE", -1.0)
        if patch_min_confidence >= 0:
            patch_cmd.extend(["--min-confidence", str(patch_min_confidence)])
        if _env_flag("WA_CAPACITY_POLICY_PATCH_ALLOW_RELAX"):
            patch_cmd.append("--allow-relax")
        if _env_flag("WA_CAPACITY_POLICY_PATCH_IGNORE_SOURCE_HASH"):
            patch_cmd.append("--ignore-source-hash")
        if _env_flag("WA_CAPACITY_POLICY_PATCH_STRICT"):
            patch_cmd.append("--strict")
        if not append_or_exit(_run_cmd(step_id="capacity_alert_policy_patch_validate", cmd=patch_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_capacity_baseline_refresh and not args.skip_load_probe:
        capacity_profile = _env_text("WA_CAPACITY_PROFILE")
        baseline_cmd = [
            sys.executable,
            "scripts/update_capacity_baseline.py",
            "--dry-run",
            "--reason",
            "preflight capacity baseline review",
        ]
        if capacity_profile:
            baseline_cmd.extend(["--capacity-profile", capacity_profile])
        if _env_flag("WA_CAPACITY_BASELINE_ALLOW_REGRESSION"):
            baseline_cmd.append("--allow-regression")
        if not append_or_exit(_run_cmd(step_id="capacity_baseline_refresh", cmd=baseline_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_capacity_stress_gate and not args.skip_load_probe:
        stress_cmd = [
            sys.executable,
            "scripts/capacity_stress_gate.py",
        ]
        stress_max_age = _env_float("WA_CAPACITY_STRESS_MAX_AGE_S", -1.0)
        if stress_max_age > 0:
            stress_cmd.extend(["--max-age-s", str(stress_max_age)])
        stress_min_profiles = _env_int("WA_CAPACITY_STRESS_MIN_PROFILES", -1)
        if stress_min_profiles > 0:
            stress_cmd.extend(["--min-profiles", str(stress_min_profiles)])
        stress_max_failed = _env_int("WA_CAPACITY_STRESS_MAX_FAILED_PROFILES", -1)
        if stress_max_failed >= 0:
            stress_cmd.extend(["--max-failed-profiles", str(stress_max_failed)])
        if _env_flag("WA_CAPACITY_STRESS_REQUIRE_SOAK"):
            stress_cmd.append("--require-soak")
        if _env_flag("WA_CAPACITY_STRESS_GATE_STRICT"):
            stress_cmd.append("--strict")
        if not append_or_exit(_run_cmd(step_id="capacity_stress_gate", cmd=stress_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_trend_guard and not args.skip_load_probe:
        trend_cmd = [
            sys.executable,
            "scripts/preflight_trend_guard.py",
        ]
        if bool(args.quick):
            trend_cmd.append("--quick")
        if _env_flag("WA_TREND_GUARD_STRICT"):
            trend_cmd.append("--strict")
        if _env_flag("WA_TREND_REQUIRE_SOAK") or _env_flag("WA_CAPACITY_REQUIRE_SOAK"):
            trend_cmd.append("--require-soak")
        if not append_or_exit(_run_cmd(step_id="preflight_trend_guard", cmd=trend_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_long_soak_guard:
        long_soak_cmd = [
            sys.executable,
            "scripts/citation_verify_long_soak_guard.py",
        ]
        long_soak_policy = _env_text("WA_LONG_SOAK_POLICY_FILE")
        if long_soak_policy:
            long_soak_cmd.extend(["--policy", long_soak_policy])
        long_soak_pattern = _env_text("WA_LONG_SOAK_PATTERN")
        if long_soak_pattern:
            long_soak_cmd.extend(["--pattern", long_soak_pattern])
        long_soak_history = _env_text("WA_LONG_SOAK_HISTORY_FILE")
        if long_soak_history:
            long_soak_cmd.extend(["--history-file", long_soak_history])
        if _env_flag("WA_LONG_SOAK_GUARD_STRICT"):
            long_soak_cmd.append("--strict")
        if not append_or_exit(_run_cmd(step_id="citation_verify_long_soak_guard", cmd=long_soak_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_alert_escalation and not args.skip_load_probe:
        escalation_cmd = [
            sys.executable,
            "scripts/alert_escalation_guard.py",
        ]
        if bool(args.quick):
            escalation_cmd.append("--quick")
        if _env_flag("WA_ALERT_ESCALATION_STRICT"):
            escalation_cmd.append("--strict")
        if not append_or_exit(_run_cmd(step_id="alert_escalation_guard", cmd=escalation_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_incident_report:
        incident_cmd = [
            sys.executable,
            "scripts/create_incident_report.py",
            "--only-when-escalated",
        ]
        if _env_flag("WA_INCIDENT_REPORT_STRICT"):
            incident_cmd.append("--strict")
        if not append_or_exit(_run_cmd(step_id="create_incident_report", cmd=incident_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_correlation_guard:
        correlation_cmd = [
            sys.executable,
            "scripts/correlation_trace_guard.py",
        ]
        if _env_flag("WA_CORRELATION_GUARD_STRICT"):
            correlation_cmd.append("--strict")
        if not append_or_exit(_run_cmd(step_id="correlation_trace_guard", cmd=correlation_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_incident_notify:
        notify_cmd = [
            sys.executable,
            "scripts/incident_notify.py",
            "--only-when-escalated",
        ]
        incident_oncall_roster = _env_text("WA_INCIDENT_ONCALL_ROSTER_FILE")
        if incident_oncall_roster:
            notify_cmd.extend(["--oncall-roster", incident_oncall_roster])
        incident_use_roster = _env_text("WA_INCIDENT_USE_ONCALL_ROSTER")
        if incident_use_roster:
            notify_cmd.extend(["--prefer-oncall-roster", incident_use_roster])
        if _env_flag("WA_INCIDENT_NOTIFY_STRICT"):
            notify_cmd.append("--strict")
        if not append_or_exit(_run_cmd(step_id="incident_notify", cmd=notify_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_incident_config_guard:
        cfg_cmd = [
            sys.executable,
            "scripts/incident_config_guard.py",
        ]
        incident_oncall_roster = _env_text("WA_INCIDENT_ONCALL_ROSTER_FILE")
        if incident_oncall_roster:
            cfg_cmd.extend(["--oncall-roster", incident_oncall_roster])
        if _env_flag("WA_INCIDENT_REQUIRE_ONCALL_ROSTER"):
            cfg_cmd.append("--require-oncall-roster")
        if _env_flag("WA_INCIDENT_CONFIG_STRICT"):
            cfg_cmd.append("--strict")
        if not append_or_exit(_run_cmd(step_id="incident_config_guard", cmd=cfg_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_sensitive_output_scan:
        scan_cmd = [
            sys.executable,
            "scripts/sensitive_output_scan.py",
            "--max-findings",
            "0",
        ]
        if _env_flag("WA_SENSITIVE_OUTPUT_SCAN_STRICT"):
            scan_cmd.append("--strict")
        if not append_or_exit(_run_cmd(step_id="sensitive_output_scan", cmd=scan_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_data_classification_guard:
        class_cmd = [
            sys.executable,
            "scripts/data_classification_guard.py",
        ]
        class_policy = _env_text("WA_DATA_CLASS_POLICY_FILE")
        if class_policy:
            class_cmd.extend(["--policy", class_policy])
        class_max_findings = _env_int("WA_DATA_CLASS_GUARD_MAX_UNMASKED_FINDINGS", -1)
        if class_max_findings >= 0:
            class_cmd.extend(["--max-unmasked-findings", str(class_max_findings)])
        if _env_flag("WA_DATA_CLASS_GUARD_REQUIRE_RULES"):
            class_cmd.append("--require-rules")
        if _env_flag("WA_DATA_CLASS_GUARD_STRICT"):
            class_cmd.append("--strict")
        if not append_or_exit(_run_cmd(step_id="data_classification_guard", cmd=class_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_audit_trail_verify:
        audit_cmd = [
            sys.executable,
            "scripts/verify_audit_chain.py",
        ]
        if _env_flag("WA_AUDIT_CHAIN_STRICT"):
            audit_cmd.append("--strict")
        if _env_flag("WA_AUDIT_CHAIN_REQUIRE_LOG"):
            audit_cmd.append("--require-log")
        if _env_flag("WA_AUDIT_CHAIN_REQUIRE_STATE"):
            audit_cmd.append("--require-state")
        audit_log = _env_text("WA_AUDIT_CHAIN_LOG")
        if audit_log:
            audit_cmd.extend(["--log", audit_log])
        audit_state = _env_text("WA_AUDIT_CHAIN_STATE_FILE")
        if audit_state:
            audit_cmd.extend(["--state-file", audit_state])
        audit_max_age = _env_float("WA_AUDIT_CHAIN_MAX_AGE_S", -1.0)
        if audit_max_age > 0:
            audit_cmd.extend(["--max-age-s", str(audit_max_age)])
        if _env_flag("WA_AUDIT_CHAIN_NO_WRITE_STATE"):
            audit_cmd.append("--no-write-state")
        if not append_or_exit(_run_cmd(step_id="audit_trail_integrity", cmd=audit_cmd)):
            return _finish(started, steps, args.out)

    if not args.skip_chaos:
        if not append_or_exit(
            _run_cmd(
                step_id="alert_webhook_chaos",
                cmd=[
                    sys.executable,
                    "scripts/citation_verify_alert_chaos.py",
                    "--host",
                    str(args.host),
                    "--port",
                    str(int(args.port) + 1),
                    "--webhook-port",
                    str(int(args.port) + 2),
                    "--cooldown-s",
                    "0.8" if args.quick else "1.2",
                ],
            )
        ):
            return _finish(started, steps, args.out)

    return _finish(started, steps, args.out)
