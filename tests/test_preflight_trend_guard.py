from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts import preflight_trend_guard


def test_pair_worsen_detects_p95_and_success_drop() -> None:
    prev = {"path": "a", "p95_ms": 100.0, "success_rate": 0.999, "degraded_rate": 0.001}
    cur = {"path": "b", "p95_ms": 120.0, "success_rate": 0.995, "degraded_rate": 0.001}
    row = preflight_trend_guard._pair_worsen(
        prev=prev,
        cur=cur,
        p95_increase_ratio_min=0.08,
        success_rate_drop_min=0.002,
        degraded_rate_increase_min=0.003,
    )
    assert row["worsen"] is True
    assert "p95_ratio" in row["worsen_by"]
    assert "success_drop" in row["worsen_by"]


def test_tail_consecutive_worsen_counts_from_tail() -> None:
    rows = [{"worsen": False}, {"worsen": True}, {"worsen": True}]
    assert preflight_trend_guard._tail_consecutive_worsen(rows) == 2
    assert preflight_trend_guard._tail_consecutive_worsen([{"worsen": False}]) == 0


def test_median_handles_empty() -> None:
    assert preflight_trend_guard._median([]) == 0.0
    assert preflight_trend_guard._median([1.0, 3.0, 2.0]) == 2.0


def test_extract_soak_rows_reads_aggregate(tmp_path: Path, monkeypatch) -> None:
    report = tmp_path / ".data/out/citation_verify_soak_1.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(
            {
                "ended_at": 1234.0,
                "duration_s": 600.0,
                "aggregate": {
                    "success_rate": 0.995,
                    "degraded_rate": 0.004,
                    "latency_p95_ms": 1800.0,
                    "window_count": 20,
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    rows = preflight_trend_guard._extract_soak_rows(".data/out/citation_verify_soak_*.json")
    assert len(rows) == 1
    assert rows[0]["success_rate"] == 0.995
    assert rows[0]["p95_ms"] == 1800.0
    assert rows[0]["window_count"] == 20


def test_main_require_soak_fails_without_soak_history(monkeypatch, tmp_path: Path) -> None:
    policy = tmp_path / "performance_trend_policy.json"
    policy.write_text(
        json.dumps(
            {
                "citation_verify": {
                    "window_runs": 6,
                    "min_required_runs": 4,
                    "allow_insufficient_history": True,
                    "consecutive_worsen_limit": 3,
                    "worsen": {
                        "p95_increase_ratio_min": 0.08,
                        "success_rate_drop_min": 0.002,
                        "degraded_rate_increase_min": 0.003,
                    },
                    "latest_guard": {
                        "max_p95_ratio_to_window_median": 1.35,
                        "min_success_rate_delta_to_window_median": -0.01,
                        "max_degraded_rate_delta_to_window_median": 0.01,
                    },
                    "soak_trend": {
                        "enabled": True,
                        "required_in_strict": False,
                        "window_runs": 5,
                        "min_required_runs": 3,
                        "allow_insufficient_history": True,
                        "consecutive_worsen_limit": 2,
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "trend_report.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "preflight_trend_guard.py",
            "--policy",
            policy.name,
            "--load-pattern",
            ".data/out/citation_verify_load_probe_*.json",
            "--soak-pattern",
            ".data/out/citation_verify_soak_*.json",
            "--strict",
            "--require-soak",
            "--out",
            out.name,
        ],
    )
    code = preflight_trend_guard.main()
    report = json.loads(out.read_text(encoding="utf-8"))
    assert code == 2
    rows = [row for row in report["checks"] if row.get("id") == "soak_trend_reports_available"]
    assert rows
    assert rows[0]["ok"] is False
    assert rows[0]["mode"] == "enforce"


def test_main_require_soak_detects_consecutive_worsen(monkeypatch, tmp_path: Path) -> None:
    policy = tmp_path / "performance_trend_policy.json"
    policy.write_text(
        json.dumps(
            {
                "citation_verify": {
                    "window_runs": 6,
                    "min_required_runs": 4,
                    "allow_insufficient_history": True,
                    "consecutive_worsen_limit": 3,
                    "worsen": {
                        "p95_increase_ratio_min": 0.08,
                        "success_rate_drop_min": 0.002,
                        "degraded_rate_increase_min": 0.003,
                    },
                    "latest_guard": {
                        "max_p95_ratio_to_window_median": 1.35,
                        "min_success_rate_delta_to_window_median": -0.01,
                        "max_degraded_rate_delta_to_window_median": 0.01,
                    },
                    "soak_trend": {
                        "enabled": True,
                        "required_in_strict": False,
                        "window_runs": 3,
                        "min_required_runs": 3,
                        "allow_insufficient_history": False,
                        "consecutive_worsen_limit": 2,
                        "worsen": {
                            "p95_increase_ratio_min": 0.05,
                            "success_rate_drop_min": 0.001,
                            "degraded_rate_increase_min": 0.001,
                        },
                        "latest_guard": {
                            "max_p95_ratio_to_window_median": 1.5,
                            "min_success_rate_delta_to_window_median": -0.02,
                            "max_degraded_rate_delta_to_window_median": 0.02,
                        },
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "trend_report.json"
    soak_dir = tmp_path / ".data/out"
    soak_dir.mkdir(parents=True, exist_ok=True)
    for idx, (p95, success_rate, degraded_rate) in enumerate(
        [
            (100.0, 0.999, 0.001),
            (125.0, 0.996, 0.003),
            (160.0, 0.993, 0.006),
        ],
        start=1,
    ):
        row = soak_dir / f"citation_verify_soak_{idx}.json"
        row.write_text(
            json.dumps(
                {
                    "started_at": 1000.0 + idx * 100.0,
                    "ended_at": 1000.0 + idx * 100.0 + 30.0,
                    "duration_s": 600.0,
                    "aggregate": {
                        "success_rate": success_rate,
                        "degraded_rate": degraded_rate,
                        "latency_p95_ms": p95,
                        "window_count": 20,
                    },
                }
            ),
            encoding="utf-8",
        )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "preflight_trend_guard.py",
            "--policy",
            policy.name,
            "--load-pattern",
            ".data/out/citation_verify_load_probe_*.json",
            "--soak-pattern",
            ".data/out/citation_verify_soak_*.json",
            "--strict",
            "--require-soak",
            "--out",
            out.name,
        ],
    )
    code = preflight_trend_guard.main()
    report = json.loads(out.read_text(encoding="utf-8"))
    assert code == 2
    rows = [row for row in report["checks"] if row.get("id") == "soak_trend_consecutive_worsen_limit"]
    assert rows
    assert rows[0]["ok"] is False
