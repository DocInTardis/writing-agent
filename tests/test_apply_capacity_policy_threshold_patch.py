from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts import apply_capacity_policy_threshold_patch
from scripts import capacity_alert_policy_drift


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _policy_payload() -> dict:
    return {
        "version": 1,
        "citation_metrics": {
            "target_peak_rps": 20.0,
            "required_headroom_ratio": 1.2,
            "max_latency_p95_ms": 1200.0,
            "max_degraded_rate": 0.05,
            "min_success_rate": 0.99,
        },
    }


def _build_patch(policy: Path, suggested: Path, patch: Path, report: Path) -> None:
    sys.argv = [
        "capacity_alert_policy_drift.py",
        "--policy",
        policy.as_posix(),
        "--suggested",
        suggested.as_posix(),
        "--policy-level",
        "critical",
        "--max-relative-drift",
        "0.25",
        "--write-patch",
        patch.as_posix(),
        "--out",
        report.as_posix(),
    ]
    code = capacity_alert_policy_drift.main()
    assert code == 0


def test_apply_patch_dry_run_requires_reason_and_keeps_policy(monkeypatch, tmp_path: Path) -> None:
    policy = tmp_path / "capacity_policy.json"
    suggested = tmp_path / "suggested.json"
    drift_report = tmp_path / "drift_report.json"
    patch = tmp_path / "patch.json"
    apply_report = tmp_path / "apply_report.json"
    _write_json(policy, _policy_payload())
    _write_json(
        suggested,
        {
            "version": 1,
            "confidence": 0.91,
            "citation_metrics_alerts": {
                "latency_p95_ms": {"warn": 1100.0, "critical": 1160.0},
                "degraded_rate": {"warn": 0.04, "critical": 0.048},
                "success_rate_min": {"warn": 0.991, "critical": 0.992},
                "headroom_ratio_min": {"warn": 1.21, "critical": 1.22},
            },
        },
    )
    _build_patch(policy, suggested, patch, drift_report)

    baseline_text = policy.read_text(encoding="utf-8")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "apply_capacity_policy_threshold_patch.py",
            "--patch",
            patch.as_posix(),
            "--dry-run",
            "--reason",
            "validate threshold patch",
            "--out",
            apply_report.as_posix(),
        ],
    )
    code = apply_capacity_policy_threshold_patch.main()
    body = json.loads(apply_report.read_text(encoding="utf-8"))
    assert code == 0
    assert body["ok"] is True
    assert body["applied"] is False
    assert policy.read_text(encoding="utf-8") == baseline_text


def test_apply_patch_strict_fails_without_allow_relax(monkeypatch, tmp_path: Path) -> None:
    policy = tmp_path / "capacity_policy.json"
    suggested = tmp_path / "suggested.json"
    drift_report = tmp_path / "drift_report.json"
    patch = tmp_path / "patch.json"
    apply_report = tmp_path / "apply_report.json"
    _write_json(policy, _policy_payload())
    _write_json(
        suggested,
        {
            "version": 1,
            "confidence": 0.95,
            "citation_metrics_alerts": {
                "latency_p95_ms": {"warn": 1300.0, "critical": 1400.0},
                "degraded_rate": {"warn": 0.06, "critical": 0.07},
                "success_rate_min": {"warn": 0.985, "critical": 0.98},
                "headroom_ratio_min": {"warn": 1.1, "critical": 1.05},
            },
        },
    )
    _build_patch(policy, suggested, patch, drift_report)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "apply_capacity_policy_threshold_patch.py",
            "--patch",
            patch.as_posix(),
            "--reason",
            "strict apply should fail on relax",
            "--strict",
            "--out",
            apply_report.as_posix(),
        ],
    )
    code = apply_capacity_policy_threshold_patch.main()
    body = json.loads(apply_report.read_text(encoding="utf-8"))
    assert code == 2
    assert body["ok"] is False


def test_apply_patch_writes_policy_with_allow_relax(monkeypatch, tmp_path: Path) -> None:
    policy = tmp_path / "capacity_policy.json"
    suggested = tmp_path / "suggested.json"
    drift_report = tmp_path / "drift_report.json"
    patch = tmp_path / "patch.json"
    apply_report = tmp_path / "apply_report.json"
    _write_json(policy, _policy_payload())
    _write_json(
        suggested,
        {
            "version": 1,
            "confidence": 0.9,
            "citation_metrics_alerts": {
                "latency_p95_ms": {"warn": 1120.0, "critical": 1180.0},
                "degraded_rate": {"warn": 0.045, "critical": 0.049},
                "success_rate_min": {"warn": 0.991, "critical": 0.992},
                "headroom_ratio_min": {"warn": 1.19, "critical": 1.18},
            },
        },
    )
    _build_patch(policy, suggested, patch, drift_report)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "apply_capacity_policy_threshold_patch.py",
            "--patch",
            patch.as_posix(),
            "--reason",
            "apply refreshed thresholds",
            "--allow-relax",
            "--strict",
            "--out",
            apply_report.as_posix(),
        ],
    )
    code = apply_capacity_policy_threshold_patch.main()
    body = json.loads(apply_report.read_text(encoding="utf-8"))
    updated = json.loads(policy.read_text(encoding="utf-8"))
    assert code == 0
    assert body["ok"] is True
    assert body["applied"] is True
    citation_metrics = updated.get("citation_metrics", {})
    assert abs(float(citation_metrics.get("max_latency_p95_ms") or 0.0) - 1180.0) < 1e-9
    assert "threshold_patch_meta" in citation_metrics


def test_apply_patch_hash_mismatch_requires_override(monkeypatch, tmp_path: Path) -> None:
    policy = tmp_path / "capacity_policy.json"
    suggested = tmp_path / "suggested.json"
    drift_report = tmp_path / "drift_report.json"
    patch = tmp_path / "patch.json"
    apply_report = tmp_path / "apply_report.json"
    _write_json(policy, _policy_payload())
    _write_json(
        suggested,
        {
            "version": 1,
            "confidence": 0.9,
            "citation_metrics_alerts": {
                "latency_p95_ms": {"warn": 1120.0, "critical": 1180.0},
                "degraded_rate": {"warn": 0.045, "critical": 0.049},
                "success_rate_min": {"warn": 0.991, "critical": 0.992},
                "headroom_ratio_min": {"warn": 1.19, "critical": 1.18},
            },
        },
    )
    _build_patch(policy, suggested, patch, drift_report)
    current = json.loads(policy.read_text(encoding="utf-8"))
    current["citation_metrics"]["target_peak_rps"] = 33.0
    _write_json(policy, current)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "apply_capacity_policy_threshold_patch.py",
            "--patch",
            patch.as_posix(),
            "--reason",
            "hash mismatch should fail",
            "--strict",
            "--out",
            apply_report.as_posix(),
        ],
    )
    code = apply_capacity_policy_threshold_patch.main()
    body = json.loads(apply_report.read_text(encoding="utf-8"))
    assert code == 2
    assert body["ok"] is False


def test_apply_patch_strict_fails_on_capacity_profile_mismatch(monkeypatch, tmp_path: Path) -> None:
    policy = tmp_path / "capacity_policy.json"
    suggested = tmp_path / "suggested.json"
    drift_report = tmp_path / "drift_report.json"
    patch = tmp_path / "patch.json"
    apply_report = tmp_path / "apply_report.json"
    _write_json(policy, _policy_payload())
    _write_json(
        suggested,
        {
            "version": 1,
            "confidence": 0.91,
            "citation_metrics_alerts_by_profile": {
                "prod": {
                    "latency_p95_ms": {"warn": 1120.0, "critical": 1180.0},
                    "degraded_rate": {"warn": 0.045, "critical": 0.049},
                    "success_rate_min": {"warn": 0.991, "critical": 0.992},
                    "headroom_ratio_min": {"warn": 1.19, "critical": 1.18},
                }
            },
            "citation_metrics_alerts": {
                "latency_p95_ms": {"warn": 1120.0, "critical": 1180.0},
                "degraded_rate": {"warn": 0.045, "critical": 0.049},
                "success_rate_min": {"warn": 0.991, "critical": 0.992},
                "headroom_ratio_min": {"warn": 1.19, "critical": 1.18},
            },
        },
    )
    sys.argv = [
        "capacity_alert_policy_drift.py",
        "--policy",
        policy.as_posix(),
        "--suggested",
        suggested.as_posix(),
        "--capacity-profile",
        "prod",
        "--write-patch",
        patch.as_posix(),
        "--out",
        drift_report.as_posix(),
    ]
    code = capacity_alert_policy_drift.main()
    assert code == 0

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "apply_capacity_policy_threshold_patch.py",
            "--patch",
            patch.as_posix(),
            "--capacity-profile",
            "staging",
            "--reason",
            "profile mismatch should fail",
            "--strict",
            "--out",
            apply_report.as_posix(),
        ],
    )
    code = apply_capacity_policy_threshold_patch.main()
    body = json.loads(apply_report.read_text(encoding="utf-8"))
    assert code == 2
    assert body["ok"] is False
