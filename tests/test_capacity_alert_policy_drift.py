from __future__ import annotations

import json
import sys
from pathlib import Path

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


def test_main_generates_patch_when_drift_within_tolerance(monkeypatch, tmp_path: Path) -> None:
    policy = tmp_path / "capacity_policy.json"
    suggested = tmp_path / "suggested.json"
    report = tmp_path / "drift_report.json"
    patch = tmp_path / "patch.json"
    _write_json(policy, _policy_payload())
    _write_json(
        suggested,
        {
            "version": 1,
            "confidence": 0.88,
            "citation_metrics_alerts": {
                "latency_p95_ms": {"warn": 1150.0, "critical": 1250.0},
                "degraded_rate": {"warn": 0.04, "critical": 0.055},
                "success_rate_min": {"warn": 0.99, "critical": 0.988},
                "headroom_ratio_min": {"warn": 1.2, "critical": 1.15},
            },
        },
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capacity_alert_policy_drift.py",
            "--policy",
            policy.as_posix(),
            "--suggested",
            suggested.as_posix(),
            "--policy-level",
            "critical",
            "--max-relative-drift",
            "0.2",
            "--strict",
            "--write-patch",
            patch.as_posix(),
            "--out",
            report.as_posix(),
        ],
    )
    code = capacity_alert_policy_drift.main()
    body = json.loads(report.read_text(encoding="utf-8"))
    patch_body = json.loads(patch.read_text(encoding="utf-8"))

    assert code == 0
    assert body["ok"] is True
    assert body["summary"]["changed_metrics"] == 4
    assert body["summary"]["exceeded_metrics"] == 0
    assert isinstance(body.get("source_policy_sha256"), str) and body["source_policy_sha256"]
    assert isinstance(body.get("source_suggested_sha256"), str) and body["source_suggested_sha256"]
    assert isinstance(patch_body.get("source_policy_sha256"), str) and patch_body["source_policy_sha256"]
    assert isinstance(patch_body.get("source_suggested_sha256"), str) and patch_body["source_suggested_sha256"]
    candidate = patch_body["candidate_policy"]["citation_metrics"]
    assert float(candidate["max_latency_p95_ms"]) == 1250.0
    assert abs(float(candidate["max_degraded_rate"]) - 0.055) < 1e-9
    assert abs(float(candidate["min_success_rate"]) - 0.988) < 1e-9
    assert abs(float(candidate["required_headroom_ratio"]) - 1.15) < 1e-9


def test_main_strict_fails_when_drift_exceeds_threshold(monkeypatch, tmp_path: Path) -> None:
    policy = tmp_path / "capacity_policy.json"
    suggested = tmp_path / "suggested.json"
    report = tmp_path / "drift_report.json"
    _write_json(policy, _policy_payload())
    _write_json(
        suggested,
        {
            "version": 1,
            "confidence": 0.9,
            "citation_metrics_alerts": {
                "latency_p95_ms": {"warn": 1300.0, "critical": 1900.0},
                "degraded_rate": {"warn": 0.06, "critical": 0.12},
                "success_rate_min": {"warn": 0.97, "critical": 0.9},
                "headroom_ratio_min": {"warn": 1.0, "critical": 0.6},
            },
        },
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capacity_alert_policy_drift.py",
            "--policy",
            policy.as_posix(),
            "--suggested",
            suggested.as_posix(),
            "--policy-level",
            "critical",
            "--max-relative-drift",
            "0.2",
            "--strict",
            "--out",
            report.as_posix(),
        ],
    )
    code = capacity_alert_policy_drift.main()
    body = json.loads(report.read_text(encoding="utf-8"))

    assert code == 2
    assert body["ok"] is False
    assert int(body["summary"]["exceeded_metrics"]) >= 2


def test_main_non_strict_keeps_exit_zero_when_suggestion_missing(monkeypatch, tmp_path: Path) -> None:
    policy = tmp_path / "capacity_policy.json"
    report = tmp_path / "drift_report.json"
    _write_json(policy, _policy_payload())

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capacity_alert_policy_drift.py",
            "--policy",
            policy.as_posix(),
            "--suggested",
            (tmp_path / "missing.json").as_posix(),
            "--out",
            report.as_posix(),
        ],
    )
    code = capacity_alert_policy_drift.main()
    body = json.loads(report.read_text(encoding="utf-8"))

    assert code == 0
    assert body["ok"] is False


def test_main_profile_mode_updates_profile_override_path(monkeypatch, tmp_path: Path) -> None:
    policy = tmp_path / "capacity_policy.json"
    suggested = tmp_path / "suggested.json"
    report = tmp_path / "drift_report.json"
    patch = tmp_path / "patch.json"
    _write_json(
        policy,
        {
            "version": 1,
            "citation_metrics": {
                "target_peak_rps": 20.0,
                "required_headroom_ratio": 1.2,
                "max_latency_p95_ms": 1200.0,
                "max_degraded_rate": 0.05,
                "min_success_rate": 0.99,
                "profile_overrides": {
                    "prod": {
                        "required_headroom_ratio": 1.3,
                        "max_latency_p95_ms": 1000.0,
                        "max_degraded_rate": 0.04,
                        "min_success_rate": 0.995,
                    }
                },
            },
        },
    )
    _write_json(
        suggested,
        {
            "version": 1,
            "confidence": 0.9,
            "citation_metrics_alerts_by_profile": {
                "prod": {
                    "latency_p95_ms": {"warn": 1050.0, "critical": 1100.0},
                    "degraded_rate": {"warn": 0.03, "critical": 0.045},
                    "success_rate_min": {"warn": 0.994, "critical": 0.993},
                    "headroom_ratio_min": {"warn": 1.25, "critical": 1.24},
                }
            },
            "citation_metrics_alerts": {
                "latency_p95_ms": {"warn": 1150.0, "critical": 1250.0},
                "degraded_rate": {"warn": 0.04, "critical": 0.055},
                "success_rate_min": {"warn": 0.99, "critical": 0.988},
                "headroom_ratio_min": {"warn": 1.2, "critical": 1.15},
            },
        },
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capacity_alert_policy_drift.py",
            "--policy",
            policy.as_posix(),
            "--suggested",
            suggested.as_posix(),
            "--capacity-profile",
            "prod",
            "--policy-level",
            "critical",
            "--max-relative-drift",
            "0.3",
            "--write-patch",
            patch.as_posix(),
            "--out",
            report.as_posix(),
        ],
    )
    code = capacity_alert_policy_drift.main()
    body = json.loads(report.read_text(encoding="utf-8"))
    patch_body = json.loads(patch.read_text(encoding="utf-8"))
    prod_node = ((patch_body.get("candidate_policy") or {}).get("citation_metrics") or {}).get("profile_overrides", {}).get("prod", {})

    assert code == 0
    assert body["ok"] is True
    assert body["capacity_profile"] == "prod"
    assert body["recommendation_source"] == "citation_metrics_alerts_by_profile:prod"
    assert abs(float(prod_node.get("max_latency_p95_ms") or 0.0) - 1100.0) < 1e-9
    assert abs(float(prod_node.get("required_headroom_ratio") or 0.0) - 1.24) < 1e-9
