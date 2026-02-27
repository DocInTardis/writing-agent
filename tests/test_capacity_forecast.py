from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from scripts import capacity_forecast


def test_linear_regression_basic_shape() -> None:
    slope, intercept, r2 = capacity_forecast._linear_regression([0.0, 1.0, 2.0], [10.0, 12.0, 14.0])
    assert slope > 1.9
    assert slope < 2.1
    assert intercept > 9.9
    assert intercept < 10.1
    assert r2 > 0.99


def test_main_generates_forecast_report(monkeypatch, tmp_path: Path) -> None:
    now = time.time()
    policy = tmp_path / "capacity_policy.json"
    policy.write_text(
        json.dumps(
            {
                "citation_metrics": {
                    "target_peak_rps": 10.0,
                    "required_headroom_ratio": 1.1,
                    "profile_overrides": {
                        "prod": {
                            "target_peak_rps": 10.0,
                            "required_headroom_ratio": 1.1,
                        }
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / ".data/out"
    out_dir.mkdir(parents=True, exist_ok=True)
    for idx, rps in enumerate([11.0, 12.0, 13.0, 14.0, 15.0], start=1):
        (out_dir / f"citation_verify_load_probe_{idx}.json").write_text(
            json.dumps(
                {
                    "ts": now - 600.0 + idx * 60.0,
                    "summary": {
                        "requests": rps * 4.0,
                        "duration_s": 4.0,
                        "success_rate": 1.0,
                        "degraded_rate": 0.0,
                        "latency_ms": {"p95": 500.0},
                    },
                }
            ),
            encoding="utf-8",
        )

    report_path = tmp_path / "forecast.json"
    markdown_path = tmp_path / "forecast.md"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capacity_forecast.py",
            "--policy",
            policy.name,
            "--capacity-profile",
            "prod",
            "--load-pattern",
            ".data/out/citation_verify_load_probe_*.json",
            "--load-window",
            "5",
            "--min-samples",
            "4",
            "--horizon-days",
            "14",
            "--markdown-out",
            markdown_path.name,
            "--out",
            report_path.name,
        ],
    )
    code = capacity_forecast.main()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert code == 0
    assert report["ok"] is True
    assert report["capacity_profile"] == "prod"
    assert Path(markdown_path).exists()
    assert str(report["forecast"]["risk"]) in {"ok", "watch"}


def test_main_strict_fails_when_samples_insufficient(monkeypatch, tmp_path: Path) -> None:
    policy = tmp_path / "capacity_policy.json"
    policy.write_text(
        json.dumps({"citation_metrics": {"target_peak_rps": 10.0, "required_headroom_ratio": 1.2}}),
        encoding="utf-8",
    )
    out_dir = tmp_path / ".data/out"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "citation_verify_load_probe_1.json").write_text(
        json.dumps(
            {
                "ts": time.time(),
                "summary": {
                    "requests": 40.0,
                    "duration_s": 4.0,
                    "success_rate": 1.0,
                    "degraded_rate": 0.0,
                    "latency_ms": {"p95": 500.0},
                },
            }
        ),
        encoding="utf-8",
    )

    report_path = tmp_path / "forecast.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capacity_forecast.py",
            "--policy",
            policy.name,
            "--load-pattern",
            ".data/out/citation_verify_load_probe_*.json",
            "--min-samples",
            "3",
            "--strict",
            "--out",
            report_path.name,
        ],
    )
    code = capacity_forecast.main()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert code == 2
    assert report["ok"] is False
