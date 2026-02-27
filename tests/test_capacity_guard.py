from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from scripts import capacity_guard


def test_calc_effective_rps() -> None:
    assert capacity_guard._calc_effective_rps({"requests": 100, "duration_s": 4}) == 25.0
    assert capacity_guard._calc_effective_rps({"requests": 0, "duration_s": 4}) == 0.0
    assert capacity_guard._calc_effective_rps({"requests": 100, "duration_s": 0}) == 0.0


def test_capacity_profile_override_resolution() -> None:
    policy = {
        "citation_metrics": {
            "target_peak_rps": 20.0,
            "required_headroom_ratio": 1.2,
            "quick_relax": {"required_headroom_ratio": 1.15},
            "profile_overrides": {
                "prod": {
                    "target_peak_rps": 45.0,
                    "required_headroom_ratio": 1.35,
                    "quick_relax": {"required_headroom_ratio": 1.25},
                }
            },
        }
    }
    merged, info = capacity_guard._resolve_citation_metrics_for_profile(
        policy_raw=policy,
        capacity_profile="prod",
        release_context={"release_tier": "", "release_branch": "", "runtime_env": ""},
    )
    assert info["resolved"] == "prod"
    assert info["override_applied"] is True
    assert float(merged["target_peak_rps"]) == 45.0
    assert float(merged["required_headroom_ratio"]) == 1.35
    assert float((merged.get("quick_relax") or {}).get("required_headroom_ratio")) == 1.25


def test_load_targets_quick_relax() -> None:
    policy = {
        "citation_metrics": {
            "target_peak_rps": 20.0,
            "required_headroom_ratio": 1.2,
            "max_latency_p95_ms": 1000.0,
            "max_degraded_rate": 0.04,
            "min_success_rate": 0.99,
            "quick_relax": {
                "required_headroom_ratio": 1.15,
                "allow_headroom_history_fallback": True,
                "max_latency_p95_ms": 2200.0,
                "max_degraded_rate": 0.08,
            },
        }
    }
    normal = capacity_guard._load_targets(policy, quick=False)
    quick = capacity_guard._load_targets(policy, quick=True)
    assert normal["required_headroom_ratio"] == 1.2
    assert quick["required_headroom_ratio"] == 1.15
    assert normal["quick_allow_headroom_history_fallback"] is False
    assert quick["quick_allow_headroom_history_fallback"] is True
    assert normal["max_latency_p95_ms"] == 1000.0
    assert quick["max_latency_p95_ms"] == 2200.0
    assert quick["max_degraded_rate"] == 0.08


def test_load_soak_targets_quick_relax() -> None:
    policy = {
        "citation_metrics": {
            "soak": {
                "min_duration_s": 1200.0,
                "min_window_count": 10,
                "min_success_rate": 0.995,
                "max_latency_p95_ms": 2000.0,
                "quick_relax": {
                    "min_duration_s": 300.0,
                    "min_window_count": 5,
                    "min_success_rate": 0.99,
                    "max_latency_p95_ms": 2500.0,
                },
            }
        }
    }
    full = capacity_guard._load_soak_targets(policy, quick=False)
    quick = capacity_guard._load_soak_targets(policy, quick=True)
    assert full["min_duration_s"] == 1200.0
    assert quick["min_duration_s"] == 300.0
    assert quick["min_window_count"] == 5.0
    assert quick["min_success_rate"] == 0.99
    assert quick["max_latency_p95_ms"] == 2500.0


def test_load_headroom_history_targets_quick_relax() -> None:
    policy = {
        "citation_metrics": {
            "headroom_history": {
                "enabled": True,
                "mode": "enforce",
                "strict_promote_to_enforce": True,
                "promote_when_quick_with_sufficient_history": True,
                "window_runs": 6,
                "min_required_runs": 4,
                "allow_insufficient_history": False,
                "max_latest_drop_ratio_to_window_median": 0.08,
                "quick_relax": {
                    "mode": "warn",
                    "strict_promote_to_enforce": False,
                    "promote_when_quick_with_sufficient_history": False,
                    "window_runs": 4,
                    "min_required_runs": 3,
                    "allow_insufficient_history": True,
                    "max_latest_drop_ratio_to_window_median": 0.2,
                },
            }
        }
    }
    full = capacity_guard._load_headroom_history_targets(
        policy,
        quick=False,
        release_context={"release_tier": "", "release_branch": "", "runtime_env": ""},
    )
    quick = capacity_guard._load_headroom_history_targets(
        policy,
        quick=True,
        release_context={"release_tier": "", "release_branch": "", "runtime_env": ""},
    )
    assert full["mode"] == "enforce"
    assert full["strict_promote_to_enforce"] is True
    assert full["promote_when_quick_with_sufficient_history"] is True
    assert full["window_runs"] == 6
    assert full["min_required_runs"] == 4
    assert full["allow_insufficient_history"] is False
    assert full["max_latest_drop_ratio_to_window_median"] == 0.08
    assert quick["mode"] == "warn"
    assert quick["strict_promote_to_enforce"] is False
    assert quick["promote_when_quick_with_sufficient_history"] is False
    assert quick["window_runs"] == 4
    assert quick["min_required_runs"] == 3
    assert quick["allow_insufficient_history"] is True
    assert quick["max_latest_drop_ratio_to_window_median"] == 0.2


def test_load_headroom_history_targets_mode_override_by_release_context() -> None:
    policy = {
        "citation_metrics": {
            "headroom_history": {
                "mode": "warn",
                "mode_by_release_tier": {"prod": "enforce"},
                "mode_by_runtime_env": {"production": "enforce"},
                "mode_by_branch_pattern": [{"pattern": "release/*", "mode": "enforce"}],
                "quick_relax": {"mode": "warn"},
            }
        }
    }
    prod = capacity_guard._load_headroom_history_targets(
        policy,
        quick=True,
        release_context={"release_tier": "prod", "release_branch": "feature/a", "runtime_env": "dev"},
    )
    assert prod["mode"] == "enforce"
    assert prod["mode_override_source"] == "mode_by_release_tier:prod"

    rel = capacity_guard._load_headroom_history_targets(
        policy,
        quick=True,
        release_context={"release_tier": "", "release_branch": "release/1.0.0", "runtime_env": ""},
    )
    assert rel["mode"] == "enforce"
    assert rel["mode_override_source"] == "mode_by_branch_pattern:release/*"


def test_extract_load_history_reads_reports(tmp_path: Path, monkeypatch) -> None:
    report = tmp_path / ".data/out/citation_verify_load_probe_1.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        json.dumps(
            {
                "ts": 1000.0,
                "summary": {
                    "requests": 120,
                    "duration_s": 4.0,
                    "success_rate": 1.0,
                    "degraded_rate": 0.0,
                    "latency_ms": {"p95": 350.0},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    rows = capacity_guard._extract_load_history(".data/out/citation_verify_load_probe_*.json")
    assert len(rows) == 1
    assert rows[0]["effective_rps"] == 30.0
    assert rows[0]["p95_ms"] == 350.0


def test_report_age_prefers_report_timestamp(tmp_path: Path) -> None:
    row = tmp_path / "report.json"
    row.write_text("{}", encoding="utf-8")
    now_ts = 1000.0
    age = capacity_guard._report_age_s(
        report_path=row,
        report_raw={"ts": 900.0},
        now_ts=now_ts,
    )
    assert age == 100.0


def test_main_passes_with_valid_reports(monkeypatch, tmp_path: Path) -> None:
    policy = tmp_path / "capacity_policy.json"
    policy.write_text(
        json.dumps(
            {
                "citation_metrics": {
                    "target_peak_rps": 20.0,
                    "required_headroom_ratio": 1.2,
                    "max_latency_p95_ms": 1000.0,
                    "max_degraded_rate": 0.05,
                    "min_success_rate": 0.99,
                    "headroom_history": {"enabled": False},
                    "soak": {
                        "min_duration_s": 600.0,
                        "min_window_count": 6,
                        "min_success_rate": 0.99,
                        "max_latency_p95_ms": 1500.0,
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
                    "requests": 120,
                    "duration_s": 3.0,
                    "success_rate": 1.0,
                    "degraded_rate": 0.0,
                    "latency_ms": {"p95": 400.0},
                }
            }
        ),
        encoding="utf-8",
    )
    soak = tmp_path / "soak.json"
    soak.write_text(
        json.dumps(
            {
                "duration_s": 900.0,
                "aggregate": {"window_count": 8, "success_rate": 0.995, "latency_p95_ms": 900.0},
            }
        ),
        encoding="utf-8",
    )
    out_path = tmp_path / "capacity_guard.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capacity_guard.py",
            "--policy",
            policy.as_posix(),
            "--load-report",
            load.as_posix(),
            "--soak-report",
            soak.as_posix(),
            "--strict",
            "--require-soak",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = capacity_guard.main()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 0
    assert report["ok"] is True


def test_main_fails_headroom(monkeypatch, tmp_path: Path) -> None:
    policy = tmp_path / "capacity_policy.json"
    policy.write_text(
        json.dumps(
            {
                "citation_metrics": {
                    "target_peak_rps": 100.0,
                    "required_headroom_ratio": 1.5,
                    "max_latency_p95_ms": 1000.0,
                    "max_degraded_rate": 0.05,
                    "min_success_rate": 0.99,
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
                    "requests": 50,
                    "duration_s": 5.0,
                    "success_rate": 1.0,
                    "degraded_rate": 0.0,
                    "latency_ms": {"p95": 300.0},
                }
            }
        ),
        encoding="utf-8",
    )
    out_path = tmp_path / "capacity_guard.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capacity_guard.py",
            "--policy",
            policy.as_posix(),
            "--load-report",
            load.as_posix(),
            "--out",
            out_path.as_posix(),
        ],
    )
    code = capacity_guard.main()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 2
    assert report["ok"] is False


def test_main_quick_relax_headroom_can_pass_borderline(monkeypatch, tmp_path: Path) -> None:
    policy = tmp_path / "capacity_policy.json"
    policy.write_text(
        json.dumps(
            {
                "citation_metrics": {
                    "target_peak_rps": 20.0,
                    "required_headroom_ratio": 1.2,
                    "max_latency_p95_ms": 1000.0,
                    "max_degraded_rate": 0.05,
                    "min_success_rate": 0.99,
                    "quick_relax": {
                        "required_headroom_ratio": 1.15,
                        "max_latency_p95_ms": 2200.0,
                        "max_degraded_rate": 0.08,
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
                    "requests": 120,
                    "duration_s": 5.04,
                    "success_rate": 1.0,
                    "degraded_rate": 0.0,
                    "latency_ms": {"p95": 300.0},
                }
            }
        ),
        encoding="utf-8",
    )
    out_path = tmp_path / "capacity_guard.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capacity_guard.py",
            "--policy",
            policy.as_posix(),
            "--load-report",
            load.as_posix(),
            "--quick",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = capacity_guard.main()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 0
    assert report["ok"] is True


def test_main_quick_can_fallback_to_history_for_headroom(monkeypatch, tmp_path: Path) -> None:
    now = time.time()
    policy = tmp_path / "capacity_policy.json"
    policy.write_text(
        json.dumps(
            {
                "citation_metrics": {
                    "target_peak_rps": 20.0,
                    "required_headroom_ratio": 1.2,
                    "max_latency_p95_ms": 1000.0,
                    "max_degraded_rate": 0.05,
                    "min_success_rate": 0.99,
                    "quick_relax": {
                        "required_headroom_ratio": 1.2,
                        "allow_headroom_history_fallback": True,
                    },
                    "headroom_history": {
                        "enabled": True,
                        "mode": "warn",
                        "window_runs": 3,
                        "min_required_runs": 3,
                        "allow_insufficient_history": False,
                        "max_latest_drop_ratio_to_window_median": 0.2,
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / ".data/out"
    out_dir.mkdir(parents=True, exist_ok=True)

    def _write_load(path: Path, ts: float, effective_rps: float) -> None:
        path.write_text(
            json.dumps(
                {
                    "ts": ts,
                    "summary": {
                        "requests": effective_rps * 4.0,
                        "duration_s": 4.0,
                        "success_rate": 1.0,
                        "degraded_rate": 0.0,
                        "latency_ms": {"p95": 300.0},
                    },
                }
            ),
            encoding="utf-8",
        )

    first = out_dir / "citation_verify_load_probe_1.json"
    second = out_dir / "citation_verify_load_probe_2.json"
    third = out_dir / "citation_verify_load_probe_3.json"
    _write_load(first, now - 120.0, 25.0)  # ratio 1.25
    _write_load(second, now - 80.0, 24.0)  # ratio 1.2
    _write_load(third, now - 40.0, 21.0)   # ratio 1.05, fallback candidate

    out_path = tmp_path / "capacity_guard.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capacity_guard.py",
            "--policy",
            policy.name,
            "--load-report",
            third.as_posix(),
            "--load-pattern",
            ".data/out/citation_verify_load_probe_*.json",
            "--quick",
            "--out",
            out_path.name,
        ],
    )
    code = capacity_guard.main()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 0
    headroom_rows = [row for row in report["checks"] if row.get("id") == "capacity_headroom_ratio"]
    assert headroom_rows
    assert headroom_rows[0]["ok"] is False
    assert headroom_rows[0]["mode"] == "warn"
    assert headroom_rows[0]["fallback"] == "headroom_history"
    fallback_rows = [row for row in report["checks"] if row.get("id") == "capacity_headroom_history_fallback"]
    assert fallback_rows
    assert fallback_rows[0]["ok"] is True
    assert fallback_rows[0]["value"]["applied"] is True


def test_main_fails_when_headroom_history_drop_exceeds_limit(monkeypatch, tmp_path: Path) -> None:
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
                    "headroom_history": {
                        "enabled": True,
                        "mode": "enforce",
                        "window_runs": 3,
                        "min_required_runs": 3,
                        "allow_insufficient_history": False,
                        "max_latest_drop_ratio_to_window_median": 0.1,
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / ".data/out"
    out_dir.mkdir(parents=True, exist_ok=True)

    def _write_load(path: Path, ts: float, effective_rps: float) -> None:
        path.write_text(
            json.dumps(
                {
                    "ts": ts,
                    "summary": {
                        "requests": effective_rps * 4.0,
                        "duration_s": 4.0,
                        "success_rate": 1.0,
                        "degraded_rate": 0.0,
                        "latency_ms": {"p95": 300.0},
                    },
                }
            ),
            encoding="utf-8",
        )

    first = out_dir / "citation_verify_load_probe_1.json"
    second = out_dir / "citation_verify_load_probe_2.json"
    third = out_dir / "citation_verify_load_probe_3.json"
    _write_load(first, now - 120.0, 30.0)   # ratio 1.5
    _write_load(second, now - 80.0, 28.0)   # ratio 1.4
    _write_load(third, now - 40.0, 24.0)    # ratio 1.2 (passes base threshold)

    out_path = tmp_path / "capacity_guard.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capacity_guard.py",
            "--policy",
            policy.name,
            "--load-report",
            third.as_posix(),
            "--load-pattern",
            ".data/out/citation_verify_load_probe_*.json",
            "--out",
            out_path.name,
        ],
    )
    code = capacity_guard.main()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 2
    rows = [row for row in report["checks"] if row.get("id") == "capacity_headroom_recent_drop_ratio"]
    assert rows
    assert rows[0]["ok"] is False
    assert rows[0]["mode"] == "enforce"


def test_main_strict_promotes_headroom_history_mode_when_not_quick(monkeypatch, tmp_path: Path) -> None:
    now = time.time()
    policy = tmp_path / "capacity_policy.json"
    policy.write_text(
        json.dumps(
            {
                "citation_metrics": {
                    "target_peak_rps": 10.0,
                    "required_headroom_ratio": 1.0,
                    "max_latency_p95_ms": 1200.0,
                    "max_degraded_rate": 0.05,
                    "min_success_rate": 0.99,
                    "headroom_history": {
                        "enabled": True,
                        "mode": "warn",
                        "strict_promote_to_enforce": True,
                        "promote_when_quick_with_sufficient_history": False,
                        "window_runs": 3,
                        "min_required_runs": 2,
                        "allow_insufficient_history": True,
                        "max_latest_drop_ratio_to_window_median": 0.2,
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / ".data/out"
    out_dir.mkdir(parents=True, exist_ok=True)
    for idx, rps in enumerate([12.0, 11.5], start=1):
        (out_dir / f"citation_verify_load_probe_{idx}.json").write_text(
            json.dumps(
                {
                    "ts": now - 120.0 + idx * 10.0,
                    "summary": {
                        "requests": rps * 4.0,
                        "duration_s": 4.0,
                        "success_rate": 1.0,
                        "degraded_rate": 0.0,
                        "latency_ms": {"p95": 300.0},
                    },
                }
            ),
            encoding="utf-8",
        )
    load = out_dir / "citation_verify_load_probe_2.json"
    out_path = tmp_path / "capacity_guard.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capacity_guard.py",
            "--policy",
            policy.name,
            "--load-report",
            load.as_posix(),
            "--load-pattern",
            ".data/out/citation_verify_load_probe_*.json",
            "--strict",
            "--out",
            out_path.name,
        ],
    )
    code = capacity_guard.main()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 0
    mode_rows = [row for row in report["checks"] if row.get("id") == "capacity_headroom_history_mode"]
    assert mode_rows
    assert mode_rows[0]["value"]["effective"] == "enforce"
    assert mode_rows[0]["value"]["promoted"] is True
    reports_rows = [row for row in report["checks"] if row.get("id") == "capacity_headroom_history_reports_available"]
    assert reports_rows
    assert reports_rows[0]["mode"] == "enforce"


def test_main_quick_strict_keeps_headroom_history_warn_by_default(monkeypatch, tmp_path: Path) -> None:
    now = time.time()
    policy = tmp_path / "capacity_policy.json"
    policy.write_text(
        json.dumps(
            {
                "citation_metrics": {
                    "target_peak_rps": 10.0,
                    "required_headroom_ratio": 1.0,
                    "max_latency_p95_ms": 1200.0,
                    "max_degraded_rate": 0.05,
                    "min_success_rate": 0.99,
                    "quick_relax": {
                        "required_headroom_ratio": 1.0,
                        "allow_headroom_history_fallback": False,
                    },
                    "headroom_history": {
                        "enabled": True,
                        "mode": "warn",
                        "strict_promote_to_enforce": True,
                        "promote_when_quick_with_sufficient_history": False,
                        "window_runs": 3,
                        "min_required_runs": 2,
                        "allow_insufficient_history": True,
                        "max_latest_drop_ratio_to_window_median": 0.2,
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / ".data/out"
    out_dir.mkdir(parents=True, exist_ok=True)
    for idx, rps in enumerate([12.0, 11.8], start=1):
        (out_dir / f"citation_verify_load_probe_{idx}.json").write_text(
            json.dumps(
                {
                    "ts": now - 120.0 + idx * 10.0,
                    "summary": {
                        "requests": rps * 4.0,
                        "duration_s": 4.0,
                        "success_rate": 1.0,
                        "degraded_rate": 0.0,
                        "latency_ms": {"p95": 300.0},
                    },
                }
            ),
            encoding="utf-8",
        )
    load = out_dir / "citation_verify_load_probe_2.json"
    out_path = tmp_path / "capacity_guard.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capacity_guard.py",
            "--policy",
            policy.name,
            "--load-report",
            load.as_posix(),
            "--load-pattern",
            ".data/out/citation_verify_load_probe_*.json",
            "--quick",
            "--strict",
            "--out",
            out_path.name,
        ],
    )
    code = capacity_guard.main()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 0
    mode_rows = [row for row in report["checks"] if row.get("id") == "capacity_headroom_history_mode"]
    assert mode_rows
    assert mode_rows[0]["value"]["effective"] == "warn"
    assert mode_rows[0]["value"]["promoted"] is False


def test_main_release_tier_override_sets_history_mode(monkeypatch, tmp_path: Path) -> None:
    now = time.time()
    policy = tmp_path / "capacity_policy.json"
    policy.write_text(
        json.dumps(
            {
                "citation_metrics": {
                    "target_peak_rps": 10.0,
                    "required_headroom_ratio": 1.0,
                    "max_latency_p95_ms": 1200.0,
                    "max_degraded_rate": 0.05,
                    "min_success_rate": 0.99,
                    "headroom_history": {
                        "enabled": True,
                        "mode": "warn",
                        "mode_by_release_tier": {"prod": "enforce"},
                        "strict_promote_to_enforce": False,
                        "window_runs": 3,
                        "min_required_runs": 2,
                        "allow_insufficient_history": True,
                        "max_latest_drop_ratio_to_window_median": 0.2,
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / ".data/out"
    out_dir.mkdir(parents=True, exist_ok=True)
    for idx, rps in enumerate([12.0, 11.8], start=1):
        (out_dir / f"citation_verify_load_probe_{idx}.json").write_text(
            json.dumps(
                {
                    "ts": now - 120.0 + idx * 10.0,
                    "summary": {
                        "requests": rps * 4.0,
                        "duration_s": 4.0,
                        "success_rate": 1.0,
                        "degraded_rate": 0.0,
                        "latency_ms": {"p95": 300.0},
                    },
                }
            ),
            encoding="utf-8",
        )
    load = out_dir / "citation_verify_load_probe_2.json"
    out_path = tmp_path / "capacity_guard.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capacity_guard.py",
            "--policy",
            policy.name,
            "--load-report",
            load.as_posix(),
            "--load-pattern",
            ".data/out/citation_verify_load_probe_*.json",
            "--release-tier",
            "prod",
            "--out",
            out_path.name,
        ],
    )
    code = capacity_guard.main()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 0
    mode_rows = [row for row in report["checks"] if row.get("id") == "capacity_headroom_history_mode"]
    assert mode_rows
    assert mode_rows[0]["value"]["configured"] == "enforce"
    assert mode_rows[0]["value"]["override_source"] == "mode_by_release_tier:prod"


def test_main_strict_without_require_soak_allows_missing_soak(monkeypatch, tmp_path: Path) -> None:
    policy = tmp_path / "capacity_policy.json"
    policy.write_text(
        json.dumps(
            {
                "citation_metrics": {
                    "target_peak_rps": 10.0,
                    "required_headroom_ratio": 1.0,
                    "max_latency_p95_ms": 1000.0,
                    "max_degraded_rate": 0.05,
                    "min_success_rate": 0.99,
                    "headroom_history": {"enabled": False},
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
    out_path = tmp_path / "capacity_guard.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capacity_guard.py",
            "--policy",
            policy.as_posix(),
            "--load-report",
            load.as_posix(),
            "--soak-report",
            (tmp_path / "missing_soak.json").as_posix(),
            "--strict",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = capacity_guard.main()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 0
    assert report["ok"] is True
    mode_rows = [row for row in report["checks"] if row.get("id") == "capacity_soak_report_loaded"]
    assert mode_rows
    assert mode_rows[0]["mode"] == "warn"


def test_main_fails_when_load_report_is_stale(monkeypatch, tmp_path: Path) -> None:
    now = time.time()
    policy = tmp_path / "capacity_policy.json"
    policy.write_text(
        json.dumps(
            {
                "citation_metrics": {
                    "target_peak_rps": 10.0,
                    "required_headroom_ratio": 1.0,
                    "load_report_max_age_s": 1.0,
                    "max_latency_p95_ms": 1000.0,
                    "max_degraded_rate": 0.05,
                    "min_success_rate": 0.99,
                }
            }
        ),
        encoding="utf-8",
    )
    load = tmp_path / "load.json"
    load.write_text(
        json.dumps(
            {
                "ts": now - 3600.0,
                "summary": {
                    "requests": 120,
                    "duration_s": 3.0,
                    "success_rate": 1.0,
                    "degraded_rate": 0.0,
                    "latency_ms": {"p95": 300.0},
                },
            }
        ),
        encoding="utf-8",
    )
    out_path = tmp_path / "capacity_guard.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capacity_guard.py",
            "--policy",
            policy.as_posix(),
            "--load-report",
            load.as_posix(),
            "--out",
            out_path.as_posix(),
        ],
    )
    code = capacity_guard.main()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 2
    assert report["ok"] is False
    stale_rows = [row for row in report["checks"] if row.get("id") == "capacity_load_report_fresh"]
    assert stale_rows
    assert stale_rows[0]["ok"] is False
