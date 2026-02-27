from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from scripts import suggest_capacity_alert_thresholds


def test_percentile_interpolation() -> None:
    values = [10.0, 20.0, 30.0, 40.0]
    assert suggest_capacity_alert_thresholds._percentile(values, 0.0) == 10.0
    assert suggest_capacity_alert_thresholds._percentile(values, 0.5) == 25.0
    assert suggest_capacity_alert_thresholds._percentile(values, 1.0) == 40.0


def test_main_generates_threshold_suggestions(monkeypatch, tmp_path: Path) -> None:
    now = time.time()
    policy = tmp_path / "capacity_policy.json"
    policy.write_text(
        json.dumps(
            {
                "citation_metrics": {
                    "target_peak_rps": 20.0,
                    "required_headroom_ratio": 1.2,
                    "max_latency_p95_ms": 1200.0,
                    "max_degraded_rate": 0.05,
                    "min_success_rate": 0.99,
                }
            }
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / ".data/out"
    out_dir.mkdir(parents=True, exist_ok=True)
    for idx, (p95, degraded, success, rps) in enumerate(
        [(500.0, 0.01, 1.0, 24.0), (520.0, 0.015, 0.999, 23.0), (560.0, 0.02, 0.998, 22.0)],
        start=1,
    ):
        (out_dir / f"citation_verify_load_probe_{idx}.json").write_text(
            json.dumps(
                {
                    "ts": now - 100.0 + idx,
                    "summary": {
                        "requests": rps * 4.0,
                        "duration_s": 4.0,
                        "success_rate": success,
                        "degraded_rate": degraded,
                        "latency_ms": {"p95": p95},
                    },
                }
            ),
            encoding="utf-8",
        )
    for idx, (p95, degraded, success) in enumerate(
        [(600.0, 0.02, 0.998), (640.0, 0.025, 0.997)],
        start=1,
    ):
        (out_dir / f"citation_verify_soak_{idx}.json").write_text(
            json.dumps(
                {
                    "ended_at": now - 50.0 + idx,
                    "duration_s": 1200.0,
                    "aggregate": {
                        "success_rate": success,
                        "degraded_rate": degraded,
                        "latency_p95_ms": p95,
                        "window_count": 10,
                    },
                }
            ),
            encoding="utf-8",
        )

    report_path = tmp_path / "suggest_report.json"
    thresholds_path = tmp_path / "thresholds.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "suggest_capacity_alert_thresholds.py",
            "--policy",
            policy.name,
            "--load-pattern",
            ".data/out/citation_verify_load_probe_*.json",
            "--soak-pattern",
            ".data/out/citation_verify_soak_*.json",
            "--load-window",
            "3",
            "--soak-window",
            "2",
            "--write-thresholds",
            thresholds_path.name,
            "--out",
            report_path.name,
        ],
    )
    code = suggest_capacity_alert_thresholds.main()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    thresholds = json.loads(thresholds_path.read_text(encoding="utf-8"))
    assert code == 0
    assert report["ok"] is True
    assert report["recommendation"]["latency_p95_ms"]["critical"] >= report["recommendation"]["latency_p95_ms"]["warn"]
    assert thresholds["citation_metrics_alerts"]["degraded_rate"]["critical"] >= thresholds["citation_metrics_alerts"]["degraded_rate"]["warn"]


def test_main_with_insufficient_history_returns_report(monkeypatch, tmp_path: Path) -> None:
    policy = tmp_path / "capacity_policy.json"
    policy.write_text(
        json.dumps(
            {
                "citation_metrics": {
                    "target_peak_rps": 20.0,
                    "required_headroom_ratio": 1.2,
                    "max_latency_p95_ms": 1200.0,
                    "max_degraded_rate": 0.05,
                    "min_success_rate": 0.99,
                }
            }
        ),
        encoding="utf-8",
    )
    report_path = tmp_path / "suggest_report.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "suggest_capacity_alert_thresholds.py",
            "--policy",
            policy.name,
            "--load-pattern",
            ".data/out/citation_verify_load_probe_*.json",
            "--soak-pattern",
            ".data/out/citation_verify_soak_*.json",
            "--out",
            report_path.name,
        ],
    )
    code = suggest_capacity_alert_thresholds.main()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert code == 0
    assert report["ok"] is False
    assert "recommendation" in report


def test_main_uses_profile_override_when_requested(monkeypatch, tmp_path: Path) -> None:
    now = time.time()
    policy = tmp_path / "capacity_policy.json"
    policy.write_text(
        json.dumps(
            {
                "citation_metrics": {
                    "target_peak_rps": 20.0,
                    "required_headroom_ratio": 1.2,
                    "max_latency_p95_ms": 1200.0,
                    "max_degraded_rate": 0.05,
                    "min_success_rate": 0.99,
                    "profile_overrides": {
                        "prod": {
                            "target_peak_rps": 40.0,
                            "required_headroom_ratio": 1.4,
                            "max_latency_p95_ms": 1000.0,
                            "max_degraded_rate": 0.04,
                            "min_success_rate": 0.995,
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / ".data/out"
    out_dir.mkdir(parents=True, exist_ok=True)
    for idx in range(1, 4):
        (out_dir / f"citation_verify_load_probe_{idx}.json").write_text(
            json.dumps(
                {
                    "ts": now - 60.0 + idx,
                    "summary": {
                        "requests": 80.0,
                        "duration_s": 4.0,
                        "success_rate": 0.999,
                        "degraded_rate": 0.01,
                        "latency_ms": {"p95": 520.0},
                    },
                }
            ),
            encoding="utf-8",
        )

    report_path = tmp_path / "suggest_report.json"
    thresholds_path = tmp_path / "thresholds.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "suggest_capacity_alert_thresholds.py",
            "--policy",
            policy.name,
            "--capacity-profile",
            "prod",
            "--load-pattern",
            ".data/out/citation_verify_load_probe_*.json",
            "--load-window",
            "3",
            "--soak-window",
            "1",
            "--min-soak-samples",
            "0",
            "--write-thresholds",
            thresholds_path.name,
            "--out",
            report_path.name,
        ],
    )
    code = suggest_capacity_alert_thresholds.main()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    thresholds = json.loads(thresholds_path.read_text(encoding="utf-8"))
    assert code == 0
    assert report["ok"] is True
    assert report["capacity_profile"] == "prod"
    assert report["capacity_profile_source"] == "profile_overrides:prod"
    assert float(report["recommendation"]["headroom_ratio_min"]["warn"]) == 0.6
    assert "prod" in (thresholds.get("citation_metrics_alerts_by_profile") or {})
