from __future__ import annotations

from scripts import citation_verify_soak


def test_percentile_interpolation() -> None:
    values = [10.0, 20.0, 30.0, 40.0]
    assert citation_verify_soak._percentile(values, 0.5) == 25.0
    assert citation_verify_soak._percentile(values, 0.0) == 10.0
    assert citation_verify_soak._percentile(values, 1.0) == 40.0


def test_window_summary_metrics() -> None:
    rows = [
        {"ok": True, "elapsed_ms": 100.0, "degraded": False},
        {"ok": True, "elapsed_ms": 200.0, "degraded": True},
        {"ok": False, "elapsed_ms": 300.0, "degraded": False},
    ]
    summary = citation_verify_soak._window_summary(rows)
    assert summary["requests"] == 3
    assert summary["success"] == 2
    assert summary["failed"] == 1
    assert summary["success_rate"] == 0.666667
    assert summary["degraded_rate"] == 0.333333
    assert summary["latency_ms"]["p95"] >= 200.0


def test_aggregate_windows_metrics() -> None:
    windows = [
        {"summary": {"requests": 4, "success": 4, "failed": 0, "degraded_count": 0, "latency_ms": {"p95": 120.0}}},
        {"summary": {"requests": 6, "success": 5, "failed": 1, "degraded_count": 1, "latency_ms": {"p95": 240.0}}},
    ]
    agg = citation_verify_soak._aggregate_windows(windows)
    assert agg["requests"] == 10
    assert agg["success"] == 9
    assert agg["failed"] == 1
    assert agg["success_rate"] == 0.9
    assert agg["degraded_rate"] == 0.1
    assert agg["max_window_p95_ms"] == 240.0
