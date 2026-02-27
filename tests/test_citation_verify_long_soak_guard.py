from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from scripts import citation_verify_long_soak_guard


def _write_soak_report(
    path: Path,
    *,
    ended_at: float,
    duration_s: float,
    success_rate: float,
    p95_ms: float,
    degraded_rate: float,
    label: str = "",
) -> None:
    payload = {
        "started_at": float(ended_at - duration_s),
        "ended_at": float(ended_at),
        "duration_s": float(duration_s),
        "label": str(label),
        "aggregate": {
            "requests": 1000,
            "window_count": 16,
            "success_rate": float(success_rate),
            "latency_p95_ms": float(p95_ms),
            "degraded_rate": float(degraded_rate),
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_main_strict_passes_with_profile_coverage_and_regression_history(
    monkeypatch,
    tmp_path: Path,
) -> None:
    policy_path = tmp_path / "long_soak_policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "history": {"retention_days": 30, "max_records": 20},
                "gate": {"min_reports": 4, "max_report_age_s": 1000000},
                "profiles": [
                    {"id": "long_12h", "min_duration_s": 120, "required_count": 2, "window_days": 10},
                    {"id": "long_24h", "min_duration_s": 240, "required_count": 1, "window_days": 10},
                ],
                "regression": {
                    "window_runs": 8,
                    "min_required_runs": 4,
                    "min_duration_s": 120,
                    "max_p95_ratio_to_median": 1.4,
                    "min_success_rate_delta_to_median": -0.01,
                    "max_degraded_rate_delta_to_median": 0.02,
                },
            }
        ),
        encoding="utf-8",
    )

    out_dir = tmp_path / ".data/out"
    out_dir.mkdir(parents=True, exist_ok=True)
    base_now = time.time()
    for idx, (duration_s, success_rate, p95_ms, degraded_rate) in enumerate(
        [
            (120.0, 0.998, 1200.0, 0.010),
            (120.0, 0.997, 1210.0, 0.011),
            (240.0, 0.998, 1220.0, 0.010),
            (240.0, 0.997, 1230.0, 0.012),
        ],
        start=1,
    ):
        _write_soak_report(
            out_dir / f"citation_verify_soak_{idx}.json",
            ended_at=base_now - (600.0 - idx * 120.0),
            duration_s=duration_s,
            success_rate=success_rate,
            p95_ms=p95_ms,
            degraded_rate=degraded_rate,
            label="long-soak",
        )

    out_report = tmp_path / "long_soak_guard_report.json"
    history_file = tmp_path / ".data/perf/history.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "citation_verify_long_soak_guard.py",
            "--policy",
            policy_path.name,
            "--pattern",
            ".data/out/citation_verify_soak_*.json",
            "--history-file",
            history_file.as_posix(),
            "--strict",
            "--out",
            out_report.as_posix(),
        ],
    )
    code = citation_verify_long_soak_guard.main()
    report = json.loads(out_report.read_text(encoding="utf-8"))
    saved_history = json.loads(history_file.read_text(encoding="utf-8"))

    assert code == 0
    assert report["ok"] is True
    assert len(saved_history["entries"]) == 4


def test_main_strict_fails_when_required_24h_profile_missing(monkeypatch, tmp_path: Path) -> None:
    policy_path = tmp_path / "long_soak_policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "history": {"retention_days": 30, "max_records": 20},
                "gate": {"min_reports": 3, "max_report_age_s": 1000000},
                "profiles": [
                    {"id": "long_12h", "min_duration_s": 120, "required_count": 1, "window_days": 10},
                    {"id": "long_24h", "min_duration_s": 240, "required_count": 1, "window_days": 10},
                ],
                "regression": {
                    "window_runs": 6,
                    "min_required_runs": 3,
                    "min_duration_s": 120,
                },
            }
        ),
        encoding="utf-8",
    )

    out_dir = tmp_path / ".data/out"
    out_dir.mkdir(parents=True, exist_ok=True)
    base_now = time.time()
    for idx in range(1, 4):
        _write_soak_report(
            out_dir / f"citation_verify_soak_{idx}.json",
            ended_at=base_now - (480.0 - idx * 120.0),
            duration_s=120.0,
            success_rate=0.998,
            p95_ms=1200.0 + idx,
            degraded_rate=0.010,
            label="long-soak",
        )

    out_report = tmp_path / "long_soak_guard_report.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "citation_verify_long_soak_guard.py",
            "--policy",
            policy_path.name,
            "--strict",
            "--out",
            out_report.name,
        ],
    )
    code = citation_verify_long_soak_guard.main()
    report = json.loads(out_report.read_text(encoding="utf-8"))

    assert code == 2
    row = [entry for entry in report["checks"] if entry["id"] == "profile_long_24h_coverage"][0]
    assert row["ok"] is False


def test_main_strict_fails_on_regression_threshold(monkeypatch, tmp_path: Path) -> None:
    policy_path = tmp_path / "long_soak_policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "history": {"retention_days": 30, "max_records": 20},
                "gate": {"min_reports": 4, "max_report_age_s": 1000000},
                "profiles": [],
                "regression": {
                    "window_runs": 6,
                    "min_required_runs": 4,
                    "min_duration_s": 120,
                    "max_p95_ratio_to_median": 1.1,
                    "min_success_rate_delta_to_median": -0.003,
                    "max_degraded_rate_delta_to_median": 0.003,
                },
            }
        ),
        encoding="utf-8",
    )

    out_dir = tmp_path / ".data/out"
    out_dir.mkdir(parents=True, exist_ok=True)
    base_now = time.time()
    rows = [
        (120.0, 0.999, 1000.0, 0.010),
        (120.0, 0.998, 1010.0, 0.011),
        (120.0, 0.998, 1020.0, 0.011),
        (120.0, 0.992, 1400.0, 0.020),
    ]
    for idx, row in enumerate(rows, start=1):
        _write_soak_report(
            out_dir / f"citation_verify_soak_{idx}.json",
            ended_at=base_now - (720.0 - idx * 180.0),
            duration_s=row[0],
            success_rate=row[1],
            p95_ms=row[2],
            degraded_rate=row[3],
        )

    out_report = tmp_path / "long_soak_guard_report.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "citation_verify_long_soak_guard.py",
            "--policy",
            policy_path.name,
            "--strict",
            "--out",
            out_report.name,
        ],
    )
    code = citation_verify_long_soak_guard.main()
    report = json.loads(out_report.read_text(encoding="utf-8"))

    assert code == 2
    row = [entry for entry in report["checks"] if entry["id"] == "long_soak_regression_latest_p95_ratio"][0]
    assert row["ok"] is False
