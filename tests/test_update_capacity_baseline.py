from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts import update_capacity_baseline


def test_candidate_target_peak_rps() -> None:
    out = update_capacity_baseline._candidate_target_peak_rps(
        effective_rps=40.0,
        required_headroom_ratio=1.25,
        reserve_ratio=0.9,
        min_target_peak_rps=1.0,
    )
    assert out == 28.8


def test_main_updates_policy_with_reason(monkeypatch, tmp_path: Path) -> None:
    policy = tmp_path / "capacity_policy.json"
    policy.write_text(
        json.dumps({"citation_metrics": {"target_peak_rps": 10.0, "required_headroom_ratio": 1.2}}),
        encoding="utf-8",
    )
    load = tmp_path / "load.json"
    load.write_text(
        json.dumps(
            {
                "summary": {
                    "requests": 120,
                    "duration_s": 3.0,
                    "success_rate": 1.0,
                    "degraded_rate": 0.0,
                    "latency_ms": {"p95": 300.0},
                }
            }
        ),
        encoding="utf-8",
    )
    out_path = tmp_path / "refresh_report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "update_capacity_baseline.py",
            "--policy",
            policy.as_posix(),
            "--load-report",
            load.as_posix(),
            "--reason",
            "refresh from stable perf run",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = update_capacity_baseline.main()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    updated = json.loads(policy.read_text(encoding="utf-8"))
    assert code == 0
    assert report["ok"] is True
    assert float(updated["citation_metrics"]["target_peak_rps"]) > 10.0
    assert str(updated["citation_metrics"]["baseline_meta"]["direction"]) == "increase"


def test_main_fails_decrease_without_allow_regression(monkeypatch, tmp_path: Path) -> None:
    policy = tmp_path / "capacity_policy.json"
    policy.write_text(
        json.dumps({"citation_metrics": {"target_peak_rps": 50.0, "required_headroom_ratio": 1.2}}),
        encoding="utf-8",
    )
    load = tmp_path / "load.json"
    load.write_text(
        json.dumps(
            {
                "summary": {
                    "requests": 60,
                    "duration_s": 3.0,
                    "success_rate": 1.0,
                    "degraded_rate": 0.0,
                    "latency_ms": {"p95": 300.0},
                }
            }
        ),
        encoding="utf-8",
    )
    out_path = tmp_path / "refresh_report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "update_capacity_baseline.py",
            "--policy",
            policy.as_posix(),
            "--load-report",
            load.as_posix(),
            "--reason",
            "downshift capacity",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = update_capacity_baseline.main()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 2
    assert report["ok"] is False
    assert report["guard_reason"] == "capacity_baseline_decrease_requires_allow_regression"


def test_main_dry_run_allows_decrease_without_allow_regression(monkeypatch, tmp_path: Path) -> None:
    policy = tmp_path / "capacity_policy.json"
    policy.write_text(
        json.dumps({"citation_metrics": {"target_peak_rps": 50.0, "required_headroom_ratio": 1.2}}),
        encoding="utf-8",
    )
    load = tmp_path / "load.json"
    load.write_text(
        json.dumps(
            {
                "summary": {
                    "requests": 60,
                    "duration_s": 3.0,
                    "success_rate": 1.0,
                    "degraded_rate": 0.0,
                    "latency_ms": {"p95": 300.0},
                }
            }
        ),
        encoding="utf-8",
    )
    out_path = tmp_path / "refresh_report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "update_capacity_baseline.py",
            "--policy",
            policy.as_posix(),
            "--load-report",
            load.as_posix(),
            "--reason",
            "dry run downshift review",
            "--dry-run",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = update_capacity_baseline.main()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 0
    assert report["ok"] is True


def test_main_fails_change_without_reason(monkeypatch, tmp_path: Path) -> None:
    policy = tmp_path / "capacity_policy.json"
    policy.write_text(
        json.dumps({"citation_metrics": {"target_peak_rps": 10.0, "required_headroom_ratio": 1.2}}),
        encoding="utf-8",
    )
    load = tmp_path / "load.json"
    load.write_text(
        json.dumps(
            {
                "summary": {
                    "requests": 120,
                    "duration_s": 3.0,
                    "success_rate": 1.0,
                    "degraded_rate": 0.0,
                    "latency_ms": {"p95": 300.0},
                }
            }
        ),
        encoding="utf-8",
    )
    out_path = tmp_path / "refresh_report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "update_capacity_baseline.py",
            "--policy",
            policy.as_posix(),
            "--load-report",
            load.as_posix(),
            "--out",
            out_path.as_posix(),
        ],
    )
    code = update_capacity_baseline.main()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 2
    assert report["ok"] is False
    assert report["guard_reason"] == "capacity_baseline_change_requires_reason"


def test_main_updates_profile_override_baseline(monkeypatch, tmp_path: Path) -> None:
    policy = tmp_path / "capacity_policy.json"
    policy.write_text(
        json.dumps(
            {
                "citation_metrics": {
                    "target_peak_rps": 12.0,
                    "required_headroom_ratio": 1.2,
                    "profile_overrides": {
                        "prod": {
                            "target_peak_rps": 30.0,
                            "required_headroom_ratio": 1.3,
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    load = tmp_path / "load.json"
    load.write_text(
        json.dumps(
            {
                "summary": {
                    "requests": 200,
                    "duration_s": 4.0,
                    "success_rate": 1.0,
                    "degraded_rate": 0.0,
                    "latency_ms": {"p95": 300.0},
                }
            }
        ),
        encoding="utf-8",
    )
    out_path = tmp_path / "refresh_report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "update_capacity_baseline.py",
            "--policy",
            policy.as_posix(),
            "--load-report",
            load.as_posix(),
            "--capacity-profile",
            "prod",
            "--reason",
            "prod baseline refresh",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = update_capacity_baseline.main()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    updated = json.loads(policy.read_text(encoding="utf-8"))
    prod_node = ((updated.get("citation_metrics") or {}).get("profile_overrides") or {}).get("prod") or {}
    assert code == 0
    assert report["ok"] is True
    assert report["capacity_profile"] == "prod"
    assert float(prod_node.get("target_peak_rps") or 0.0) > 30.0
    assert str(((prod_node.get("baseline_meta") or {}).get("capacity_profile") or "")) == "prod"
