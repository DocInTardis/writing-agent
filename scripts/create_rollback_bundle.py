#!/usr/bin/env python3
"""Create Rollback Bundle command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import time
from pathlib import Path
from typing import Any

try:
    from scripts import audit_chain
except Exception:
    _AUDIT_CHAIN_PATH = Path(__file__).with_name("audit_chain.py")
    _AUDIT_SPEC = importlib.util.spec_from_file_location("audit_chain", _AUDIT_CHAIN_PATH)
    if _AUDIT_SPEC is None or _AUDIT_SPEC.loader is None:
        raise
    audit_chain = importlib.util.module_from_spec(_AUDIT_SPEC)
    _AUDIT_SPEC.loader.exec_module(audit_chain)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _safe_rel(path: Path) -> str:
    if not path.is_absolute():
        return path.as_posix()
    raw = path.as_posix()
    drive = str(path.drive or "").replace(":", "").replace("/", "").replace("\\", "")
    suffix = raw[len(path.drive) :] if path.drive else raw
    suffix = suffix.lstrip("/\\")
    if drive:
        return f"_abs/{drive}/{suffix}"
    return f"_abs/{suffix}"


def _copy_entry(src: Path, dst_root: Path) -> dict[str, Any]:
    rel = _safe_rel(src)
    dst = dst_root / rel
    row: dict[str, Any] = {
        "path": rel,
        "exists": src.exists(),
        "copied": False,
        "size": 0,
        "sha256": "",
    }
    if not src.exists():
        return row
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    row["copied"] = True
    row["size"] = int(src.stat().st_size)
    row["sha256"] = _sha256(src)
    return row


def _glob_recent(pattern: str, *, keep: int) -> list[Path]:
    rows = sorted(Path(".").glob(pattern), key=lambda p: p.stat().st_mtime if p.exists() else 0.0)
    return rows[-max(0, int(keep)) :]


def _latest_json(pattern: str) -> tuple[Path | None, dict[str, Any]]:
    rows = sorted(Path(".").glob(pattern), key=lambda p: p.stat().st_mtime if p.exists() else 0.0)
    if not rows:
        return (None, {})
    path = rows[-1]
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return (path, {})
    return (path, raw if isinstance(raw, dict) else {})


def _extract_correlation(raw: dict[str, Any]) -> dict[str, str]:
    node = raw if isinstance(raw, dict) else {}
    corr = node.get("correlation") if isinstance(node.get("correlation"), dict) else {}
    incident = node.get("incident") if isinstance(node.get("incident"), dict) else {}
    observed = node.get("observed") if isinstance(node.get("observed"), dict) else {}
    last_event = observed.get("last_event") if isinstance(observed.get("last_event"), dict) else {}
    correlation_id = str(
        corr.get("correlation_id")
        or incident.get("correlation_id")
        or last_event.get("correlation_id")
        or ""
    ).strip()
    release_candidate_id = str(
        corr.get("release_candidate_id")
        or incident.get("release_candidate_id")
        or last_event.get("release_candidate_id")
        or ""
    ).strip()
    if not release_candidate_id and correlation_id:
        release_candidate_id = correlation_id
    if not correlation_id and release_candidate_id:
        correlation_id = release_candidate_id
    return {
        "correlation_id": correlation_id,
        "release_candidate_id": release_candidate_id,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create rollback bundle with runtime state and recent release artifacts.")
    parser.add_argument("--out-dir", default=".data/out")
    parser.add_argument("--label", default="")
    parser.add_argument("--recent", type=int, default=2, help="Number of recent report files to include per pattern.")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--audit-log", default="")
    parser.add_argument("--audit-state-file", default="")
    parser.add_argument("--audit-actor", default="")
    parser.add_argument("--skip-audit-log", action="store_true")
    parser.add_argument("--audit-strict", action="store_true")
    args = parser.parse_args()

    ts = int(time.time())
    label = str(args.label or "").strip()
    suffix = f"_{label}" if label else ""
    bundle_root = Path(str(args.out_dir)) / f"rollback_bundle_{ts}{suffix}"
    bundle_root.mkdir(parents=True, exist_ok=True)

    required = [
        Path("security/release_policy.json"),
        Path("security/release_rollout_policy.json"),
        Path("security/release_traffic_adapter_contract.json"),
        Path("security/ops_rbac_policy.json"),
        Path("security/dependency_baseline.json"),
        Path("security/release_channels.json"),
        Path("security/alert_escalation_policy.json"),
        Path("security/performance_trend_policy.json"),
        Path("security/rollback_drill_signature_policy.json"),
        Path("security/incident_routing.json"),
        Path("security/oncall_roster.json"),
        Path("security/capacity_policy.json"),
        Path("security/data_classification_policy.json"),
        Path("security/artifact_schema_catalog_policy.json"),
        Path("security/docs_reality_policy.json"),
        Path("security/public_release_policy.json"),
        Path("writing_agent/__init__.py"),
        Path("writing_agent/state_engine/context.py"),
    ]
    optional = [
        Path(".data/citation_verify_alerts_config.json"),
        Path(".data/citation_verify_alert_events.json"),
        Path(".data/citation_verify_metrics_trends.json"),
        Path("docs/RELEASE_AND_ROLLBACK.md"),
    ]
    for pattern in [
        ".data/out/release_preflight_*.json",
        ".data/out/release_manifest_*.json",
        ".data/out/release_governance_*.json",
        ".data/out/release_compat_matrix_*.json",
        ".data/out/release_rollout_adapter_contract_*.json",
        ".data/out/release_rollout_guard_*.json",
        ".data/out/release_rollout_executor_*.json",
        ".data/out/rollback_drill_guard_*.json",
        ".data/out/rollback_drill_signature_*.json",
        ".data/out/dependency_audit_*.json",
        ".data/out/security_alert_notify_*.json",
        ".data/out/preflight_trend_guard_*.json",
        ".data/out/docs_reality_guard_*.json",
        ".data/out/citation_verify_long_soak_guard_*.json",
        ".data/out/alert_escalation_*.json",
        ".data/out/correlation_trace_guard_*.json",
        ".data/out/incident_report_*.json",
        ".data/out/incident_report_*.md",
        ".data/out/incident_notify_*.json",
        ".data/out/incident_notify_drill_*.json",
        ".data/out/incident_notify_drill_notify_*.json",
        ".data/out/incident_report_drill_*.json",
        ".data/out/oncall_roster_drill_*.json",
        ".data/out/incident_config_guard_*.json",
        ".data/out/sensitive_output_scan_*.json",
        ".data/out/data_classification_guard_*.json",
        ".data/out/artifact_schema_catalog_guard_*.json",
        ".data/out/public_release_guard_*.json",
        ".data/out/migration_assistant_*.json",
        ".data/out/migration_assistant_*.md",
        ".data/out/release_notes_*.md",
        ".data/out/audit_chain_verify_*.json",
        ".data/audit/operations_audit_chain.ndjson",
        ".data/audit/operations_audit_chain_state.json",
        ".data/out/citation_verify_soak_*.json",
        ".data/out/capacity_guard_*.json",
        ".data/out/capacity_forecast_*.json",
        ".data/out/capacity_forecast_*.md",
        ".data/out/capacity_baseline_refresh_*.json",
        ".data/out/capacity_policy_generated_*.json",
        ".data/out/capacity_alert_threshold_suggest_*.json",
        ".data/out/capacity_alert_thresholds_suggested.json",
        ".data/out/capacity_alert_policy_drift_*.json",
        ".data/out/capacity_policy_threshold_patch_suggested.json",
        ".data/out/capacity_policy_patch_apply_*.json",
        ".data/out/capacity_policy_backup_*.json",
        ".data/out/capacity_stress_matrix_*.json",
        ".data/out/capacity_stress_gate_*.json",
        ".data/out/citation_verify_load_probe_stress_*.json",
        ".data/out/citation_verify_soak_stress_*.json",
    ]:
        optional.extend(_glob_recent(pattern, keep=int(args.recent)))

    rows: list[dict[str, Any]] = []
    rows.extend(_copy_entry(p, bundle_root) for p in required)
    required_keys = {p.as_posix() for p in required}
    seen_optional: set[str] = set()
    dedup_optional: list[Path] = []
    for item in optional:
        key = item.as_posix()
        if key in required_keys or key in seen_optional:
            continue
        seen_optional.add(key)
        dedup_optional.append(item)
    rows.extend(_copy_entry(p, bundle_root) for p in dedup_optional)

    missing_required = [row.get("path") for row in rows if row.get("path") in [p.as_posix() for p in required] and not bool(row.get("exists"))]
    rollout_report_path, rollout_report = _latest_json(".data/out/release_rollout_executor_*.json")
    alert_report_path, alert_report = _latest_json(".data/out/alert_escalation_*.json")
    incident_report_path, incident_report = _latest_json(".data/out/incident_report_[0-9]*.json")
    rollout_corr = _extract_correlation(rollout_report)
    alert_corr = _extract_correlation(alert_report)
    incident_corr = _extract_correlation(incident_report)
    correlation_values = [
        value
        for value in [
            rollout_corr.get("correlation_id"),
            alert_corr.get("correlation_id"),
            incident_corr.get("correlation_id"),
        ]
        if str(value or "").strip()
    ]
    release_candidate_values = [
        value
        for value in [
            rollout_corr.get("release_candidate_id"),
            alert_corr.get("release_candidate_id"),
            incident_corr.get("release_candidate_id"),
        ]
        if str(value or "").strip()
    ]
    correlation_consistent = len(set(correlation_values)) <= 1
    release_candidate_consistent = len(set(release_candidate_values)) <= 1
    correlation_checks = [
        {
            "id": "correlation_id_consistent",
            "ok": bool(correlation_consistent),
            "value": {
                "values": correlation_values,
                "rollout_report": rollout_report_path.as_posix() if isinstance(rollout_report_path, Path) else "",
                "alert_report": alert_report_path.as_posix() if isinstance(alert_report_path, Path) else "",
                "incident_report": incident_report_path.as_posix() if isinstance(incident_report_path, Path) else "",
            },
            "expect": "shared correlation_id is consistent across rollout/alert/incident artifacts when present",
            "mode": "enforce" if bool(args.strict and len(correlation_values) >= 2) else "warn",
        },
        {
            "id": "release_candidate_id_consistent",
            "ok": bool(release_candidate_consistent),
            "value": {
                "values": release_candidate_values,
                "rollout_report": rollout_report_path.as_posix() if isinstance(rollout_report_path, Path) else "",
                "alert_report": alert_report_path.as_posix() if isinstance(alert_report_path, Path) else "",
                "incident_report": incident_report_path.as_posix() if isinstance(incident_report_path, Path) else "",
            },
            "expect": "shared release_candidate_id is consistent across rollout/alert/incident artifacts when present",
            "mode": "enforce" if bool(args.strict and len(release_candidate_values) >= 2) else "warn",
        },
    ]
    ok = len(missing_required) == 0
    if args.strict and missing_required:
        ok = False
    if args.strict and len(correlation_values) >= 2 and (not correlation_consistent):
        ok = False
    if args.strict and len(release_candidate_values) >= 2 and (not release_candidate_consistent):
        ok = False

    report = {
        "ok": bool(ok),
        "generated_at": round(time.time(), 3),
        "bundle_root": bundle_root.as_posix(),
        "label": label,
        "missing_required": missing_required,
        "correlation": {
            "rollout": rollout_corr,
            "alert_escalation": alert_corr,
            "incident_report": incident_corr,
            "checks": correlation_checks,
        },
        "files": rows,
    }
    audit_result: dict[str, Any] = {"ok": True, "skipped": True}
    if not bool(args.skip_audit_log):
        audit_actor = str(args.audit_actor or "").strip() or "release-bot"
        audit_result = audit_chain.record_operation(
            action="rollback_bundle_create",
            actor=audit_actor,
            source="create_rollback_bundle",
            status="ok" if bool(report.get("ok")) else "failed",
            context={
                "bundle_root": bundle_root.as_posix(),
                "label": label,
                "strict": bool(args.strict),
                "missing_required_count": len(missing_required),
                "file_count": len(rows),
            },
            log_path=str(args.audit_log or ""),
            state_path=str(args.audit_state_file or ""),
            strict=False,
        )
    report["audit"] = audit_result
    if bool(args.audit_strict) and (not bool(audit_result.get("ok"))):
        report["ok"] = False
    report_path = Path(str(args.out_dir)) / f"rollback_bundle_report_{ts}{suffix}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report.get("ok")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
