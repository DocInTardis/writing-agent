#!/usr/bin/env python3
"""Preflight Trend Guard command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    return None


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _check_row(*, check_id: str, ok: bool, value: Any, expect: str, mode: str = "enforce") -> dict[str, Any]:
    return {
        "id": str(check_id),
        "ok": bool(ok),
        "value": value,
        "expect": str(expect),
        "mode": str(mode or "enforce"),
    }


def _extract_load_rows(pattern: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(Path(".").glob(pattern), key=lambda p: p.stat().st_mtime if p.exists() else 0.0):
        raw = _load_json(path)
        if not isinstance(raw, dict):
            continue
        summary = raw.get("summary") if isinstance(raw.get("summary"), dict) else {}
        latency = summary.get("latency_ms") if isinstance(summary.get("latency_ms"), dict) else {}
        ts = _safe_float(raw.get("ts"), 0.0)
        if ts <= 0:
            ts = _safe_float(path.stat().st_mtime if path.exists() else 0.0, 0.0)
        rows.append(
            {
                "path": path.as_posix(),
                "ts": ts,
                "success_rate": _safe_float(summary.get("success_rate"), 0.0),
                "p95_ms": _safe_float(latency.get("p95"), 0.0),
                "degraded_rate": _safe_float(summary.get("degraded_rate"), 0.0),
            }
        )
    rows.sort(key=lambda row: _safe_float(row.get("ts"), 0.0))
    return rows


def _extract_soak_rows(pattern: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(Path(".").glob(pattern), key=lambda p: p.stat().st_mtime if p.exists() else 0.0):
        raw = _load_json(path)
        if not isinstance(raw, dict):
            continue
        aggregate = raw.get("aggregate") if isinstance(raw.get("aggregate"), dict) else {}
        ts = _safe_float(raw.get("ended_at"), 0.0)
        if ts <= 0:
            ts = _safe_float(raw.get("started_at"), 0.0)
        if ts <= 0:
            ts = _safe_float(path.stat().st_mtime if path.exists() else 0.0, 0.0)
        rows.append(
            {
                "path": path.as_posix(),
                "ts": ts,
                "success_rate": _safe_float(aggregate.get("success_rate"), 0.0),
                "p95_ms": _safe_float(aggregate.get("latency_p95_ms"), 0.0),
                "degraded_rate": _safe_float(aggregate.get("degraded_rate"), 0.0),
                "duration_s": _safe_float(raw.get("duration_s"), 0.0),
                "window_count": _safe_int(aggregate.get("window_count"), 0),
            }
        )
    rows.sort(key=lambda row: _safe_float(row.get("ts"), 0.0))
    return rows


def _pair_worsen(
    *,
    prev: dict[str, Any],
    cur: dict[str, Any],
    p95_increase_ratio_min: float,
    success_rate_drop_min: float,
    degraded_rate_increase_min: float,
) -> dict[str, Any]:
    prev_p95 = max(0.001, _safe_float(prev.get("p95_ms"), 0.0))
    cur_p95 = max(0.0, _safe_float(cur.get("p95_ms"), 0.0))
    p95_ratio = cur_p95 / prev_p95
    success_drop = _safe_float(prev.get("success_rate"), 0.0) - _safe_float(cur.get("success_rate"), 0.0)
    degraded_increase = _safe_float(cur.get("degraded_rate"), 0.0) - _safe_float(prev.get("degraded_rate"), 0.0)
    worsen_by: list[str] = []
    if (p95_ratio - 1.0) >= p95_increase_ratio_min:
        worsen_by.append("p95_ratio")
    if success_drop >= success_rate_drop_min:
        worsen_by.append("success_drop")
    if degraded_increase >= degraded_rate_increase_min:
        worsen_by.append("degraded_increase")
    return {
        "prev_path": str(prev.get("path") or ""),
        "cur_path": str(cur.get("path") or ""),
        "p95_ratio": round(p95_ratio, 6),
        "success_drop": round(success_drop, 6),
        "degraded_increase": round(degraded_increase, 6),
        "worsen": len(worsen_by) > 0,
        "worsen_by": worsen_by,
    }


def _tail_consecutive_worsen(transitions: list[dict[str, Any]]) -> int:
    count = 0
    for row in reversed(transitions):
        if bool(row.get("worsen")):
            count += 1
        else:
            break
    return count


def _median(values: list[float]) -> float:
    rows = [float(x) for x in values if float(x) >= 0.0]
    if not rows:
        return 0.0
    return float(statistics.median(rows))


def _analyze_trend(
    *,
    check_prefix: str,
    rows: list[dict[str, Any]],
    mode: str,
    min_required_runs: int,
    allow_insufficient: bool,
    allow_insufficient_when_enforced: bool,
    consecutive_limit: int,
    p95_increase_ratio_min: float,
    success_rate_drop_min: float,
    degraded_rate_increase_min: float,
    max_p95_ratio_to_window_median: float,
    min_success_rate_delta_to_window_median: float,
    max_degraded_rate_delta_to_window_median: float,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    effective_mode = str(mode or "warn")
    relaxed_history = bool(allow_insufficient) and (
        allow_insufficient_when_enforced or effective_mode != "enforce"
    )
    has_required_history = len(rows) >= int(min_required_runs)
    checks.append(
        _check_row(
            check_id=f"{check_prefix}_reports_available",
            ok=has_required_history or relaxed_history,
            value={
                "available": len(rows),
                "required": int(min_required_runs),
                "allow_insufficient_history": bool(allow_insufficient),
                "relaxed_for_mode": bool(relaxed_history),
            },
            expect="enough reports for trend analysis",
            mode=effective_mode,
        )
    )

    transitions: list[dict[str, Any]] = []
    if len(rows) >= 2:
        for idx in range(1, len(rows)):
            transitions.append(
                _pair_worsen(
                    prev=rows[idx - 1],
                    cur=rows[idx],
                    p95_increase_ratio_min=p95_increase_ratio_min,
                    success_rate_drop_min=success_rate_drop_min,
                    degraded_rate_increase_min=degraded_rate_increase_min,
                )
            )

    consecutive_tail = _tail_consecutive_worsen(transitions)
    history_guard_ok = consecutive_tail < int(consecutive_limit)
    if not has_required_history and relaxed_history:
        history_guard_ok = True
    checks.append(
        _check_row(
            check_id=f"{check_prefix}_consecutive_worsen_limit",
            ok=history_guard_ok,
            value={"tail_consecutive_worsen": consecutive_tail, "limit": int(consecutive_limit)},
            expect=f"<{int(consecutive_limit)}",
            mode=effective_mode,
        )
    )

    latest = rows[-1] if rows else {}
    history = rows[:-1] if len(rows) > 1 else []
    p95_median = _median([_safe_float(row.get("p95_ms"), 0.0) for row in history])
    success_median = _median([_safe_float(row.get("success_rate"), 0.0) for row in history])
    degraded_median = _median([_safe_float(row.get("degraded_rate"), 0.0) for row in history])

    latest_p95_ratio = (_safe_float(latest.get("p95_ms"), 0.0) / max(0.001, p95_median)) if history else 1.0
    latest_success_delta = (_safe_float(latest.get("success_rate"), 0.0) - success_median) if history else 0.0
    latest_degraded_delta = (_safe_float(latest.get("degraded_rate"), 0.0) - degraded_median) if history else 0.0

    def _latest_check_ok(raw_ok: bool) -> bool:
        if raw_ok:
            return True
        return (not has_required_history) and relaxed_history

    checks.append(
        _check_row(
            check_id=f"{check_prefix}_latest_vs_median_p95",
            ok=_latest_check_ok(latest_p95_ratio <= max_p95_ratio_to_window_median),
            value=round(latest_p95_ratio, 6),
            expect=f"<={max_p95_ratio_to_window_median:.4f}",
            mode=effective_mode,
        )
    )
    checks.append(
        _check_row(
            check_id=f"{check_prefix}_latest_vs_median_success_rate",
            ok=_latest_check_ok(latest_success_delta >= min_success_rate_delta_to_window_median),
            value=round(latest_success_delta, 6),
            expect=f">={min_success_rate_delta_to_window_median:.6f}",
            mode=effective_mode,
        )
    )
    checks.append(
        _check_row(
            check_id=f"{check_prefix}_latest_vs_median_degraded_rate",
            ok=_latest_check_ok(latest_degraded_delta <= max_degraded_rate_delta_to_window_median),
            value=round(latest_degraded_delta, 6),
            expect=f"<={max_degraded_rate_delta_to_window_median:.6f}",
            mode=effective_mode,
        )
    )

    return checks, {
        "reports_considered": rows,
        "transitions": transitions,
        "tail_consecutive_worsen": consecutive_tail,
        "latest_vs_median": {
            "p95_ratio": round(latest_p95_ratio, 6),
            "success_rate_delta": round(latest_success_delta, 6),
            "degraded_rate_delta": round(latest_degraded_delta, 6),
            "history_count": len(history),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detect consecutive performance degradation trends across load probe and soak reports."
    )
    parser.add_argument("--policy", default="security/performance_trend_policy.json")
    parser.add_argument("--load-pattern", default=".data/out/citation_verify_load_probe_*.json")
    parser.add_argument("--soak-pattern", default=".data/out/citation_verify_soak_*.json")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--skip-soak", action="store_true")
    parser.add_argument("--require-soak", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    started = time.time()
    checks: list[dict[str, Any]] = []

    policy_path = Path(str(args.policy))
    policy_raw = _load_json(policy_path)
    checks.append(
        _check_row(
            check_id="trend_policy_loaded",
            ok=isinstance(policy_raw, dict),
            value=policy_path.as_posix(),
            expect="performance trend policy exists and valid",
        )
    )
    if not isinstance(policy_raw, dict):
        ended = time.time()
        report = {
            "ok": False,
            "started_at": round(started, 3),
            "ended_at": round(ended, 3),
            "duration_s": round(ended - started, 3),
            "checks": checks,
            "trend": {},
        }
        out_path = Path(str(args.out or Path(".data/out") / f"preflight_trend_guard_{int(ended)}.json"))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    node = policy_raw.get("citation_verify") if isinstance(policy_raw.get("citation_verify"), dict) else {}
    worsen_cfg = node.get("worsen") if isinstance(node.get("worsen"), dict) else {}
    latest_guard_cfg = node.get("latest_guard") if isinstance(node.get("latest_guard"), dict) else {}
    soak_node = node.get("soak_trend") if isinstance(node.get("soak_trend"), dict) else {}

    window_runs = max(3, _safe_int(node.get("window_runs"), 6))
    min_required_runs = max(2, _safe_int(node.get("min_required_runs"), 4))
    allow_insufficient = bool(node.get("allow_insufficient_history", True))
    consecutive_limit = max(2, _safe_int(node.get("consecutive_worsen_limit"), 3))
    if bool(args.quick):
        window_runs = min(window_runs, 4)
        min_required_runs = min(min_required_runs, 3)
        consecutive_limit = min(consecutive_limit, 2)

    p95_increase_ratio_min = max(0.0, _safe_float(worsen_cfg.get("p95_increase_ratio_min"), 0.08))
    success_rate_drop_min = max(0.0, _safe_float(worsen_cfg.get("success_rate_drop_min"), 0.002))
    degraded_rate_increase_min = max(0.0, _safe_float(worsen_cfg.get("degraded_rate_increase_min"), 0.003))

    max_p95_ratio_to_window_median = max(
        1.0,
        _safe_float(latest_guard_cfg.get("max_p95_ratio_to_window_median"), 1.35),
    )
    min_success_rate_delta_to_window_median = _safe_float(
        latest_guard_cfg.get("min_success_rate_delta_to_window_median"),
        -0.01,
    )
    max_degraded_rate_delta_to_window_median = _safe_float(
        latest_guard_cfg.get("max_degraded_rate_delta_to_window_median"),
        0.01,
    )

    load_rows = _extract_load_rows(str(args.load_pattern))[-window_runs:]
    load_checks, load_trend = _analyze_trend(
        check_prefix="trend",
        rows=load_rows,
        mode="enforce" if bool(args.strict) else "warn",
        min_required_runs=min_required_runs,
        allow_insufficient=allow_insufficient,
        allow_insufficient_when_enforced=True,
        consecutive_limit=consecutive_limit,
        p95_increase_ratio_min=p95_increase_ratio_min,
        success_rate_drop_min=success_rate_drop_min,
        degraded_rate_increase_min=degraded_rate_increase_min,
        max_p95_ratio_to_window_median=max_p95_ratio_to_window_median,
        min_success_rate_delta_to_window_median=min_success_rate_delta_to_window_median,
        max_degraded_rate_delta_to_window_median=max_degraded_rate_delta_to_window_median,
    )
    checks.extend(load_checks)

    soak_enabled = bool(soak_node.get("enabled", True))
    soak_required_in_strict = bool(soak_node.get("required_in_strict", False))
    soak_window_runs = max(3, _safe_int(soak_node.get("window_runs"), 5))
    soak_min_required_runs = max(2, _safe_int(soak_node.get("min_required_runs"), 3))
    soak_allow_insufficient = bool(soak_node.get("allow_insufficient_history", True))
    soak_consecutive_limit = max(2, _safe_int(soak_node.get("consecutive_worsen_limit"), 2))
    if bool(args.quick):
        soak_window_runs = min(soak_window_runs, 4)
        soak_min_required_runs = min(soak_min_required_runs, 3)
        soak_consecutive_limit = min(soak_consecutive_limit, 2)

    soak_worsen_cfg = soak_node.get("worsen") if isinstance(soak_node.get("worsen"), dict) else {}
    soak_latest_guard_cfg = soak_node.get("latest_guard") if isinstance(soak_node.get("latest_guard"), dict) else {}
    soak_p95_increase_ratio_min = max(0.0, _safe_float(soak_worsen_cfg.get("p95_increase_ratio_min"), 0.1))
    soak_success_rate_drop_min = max(0.0, _safe_float(soak_worsen_cfg.get("success_rate_drop_min"), 0.002))
    soak_degraded_rate_increase_min = max(0.0, _safe_float(soak_worsen_cfg.get("degraded_rate_increase_min"), 0.003))
    soak_max_p95_ratio_to_window_median = max(
        1.0,
        _safe_float(soak_latest_guard_cfg.get("max_p95_ratio_to_window_median"), 1.3),
    )
    soak_min_success_rate_delta_to_window_median = _safe_float(
        soak_latest_guard_cfg.get("min_success_rate_delta_to_window_median"),
        -0.005,
    )
    soak_max_degraded_rate_delta_to_window_median = _safe_float(
        soak_latest_guard_cfg.get("max_degraded_rate_delta_to_window_median"),
        0.01,
    )

    soak_mode = (
        "enforce"
        if bool(args.require_soak) or (bool(args.strict) and soak_required_in_strict)
        else "warn"
    )
    soak_trend: dict[str, Any] = {
        "enabled": soak_enabled and (not bool(args.skip_soak)),
        "skipped": bool(args.skip_soak) or (not soak_enabled),
        "reports_considered": [],
        "transitions": [],
        "tail_consecutive_worsen": 0,
        "latest_vs_median": {
            "p95_ratio": 1.0,
            "success_rate_delta": 0.0,
            "degraded_rate_delta": 0.0,
            "history_count": 0,
        },
    }
    if bool(args.skip_soak):
        checks.append(
            _check_row(
                check_id="soak_trend_skipped",
                ok=True,
                value="skip-soak",
                expect="soak trend not required",
                mode="warn",
            )
        )
    elif not soak_enabled:
        checks.append(
            _check_row(
                check_id="soak_trend_disabled",
                ok=True,
                value=False,
                expect="policy soak trend disabled",
                mode="warn",
            )
        )
    else:
        soak_rows = _extract_soak_rows(str(args.soak_pattern))[-soak_window_runs:]
        soak_checks, soak_trend = _analyze_trend(
            check_prefix="soak_trend",
            rows=soak_rows,
            mode=soak_mode,
            min_required_runs=soak_min_required_runs,
            allow_insufficient=soak_allow_insufficient,
            allow_insufficient_when_enforced=False,
            consecutive_limit=soak_consecutive_limit,
            p95_increase_ratio_min=soak_p95_increase_ratio_min,
            success_rate_drop_min=soak_success_rate_drop_min,
            degraded_rate_increase_min=soak_degraded_rate_increase_min,
            max_p95_ratio_to_window_median=soak_max_p95_ratio_to_window_median,
            min_success_rate_delta_to_window_median=soak_min_success_rate_delta_to_window_median,
            max_degraded_rate_delta_to_window_median=soak_max_degraded_rate_delta_to_window_median,
        )
        checks.extend(soak_checks)

    enforce_rows = [row for row in checks if str(row.get("mode") or "enforce") == "enforce"]
    ok = all(bool(row.get("ok")) for row in enforce_rows)

    ended = time.time()
    report = {
        "ok": bool(ok),
        "started_at": round(started, 3),
        "ended_at": round(ended, 3),
        "duration_s": round(ended - started, 3),
        "quick": bool(args.quick),
        "strict": bool(args.strict),
        "require_soak": bool(args.require_soak),
        "policy_path": policy_path.as_posix(),
        "load_pattern": str(args.load_pattern),
        "soak_pattern": str(args.soak_pattern),
        "settings": {
            "load": {
                "window_runs": window_runs,
                "min_required_runs": min_required_runs,
                "allow_insufficient_history": allow_insufficient,
                "consecutive_worsen_limit": consecutive_limit,
                "worsen": {
                    "p95_increase_ratio_min": p95_increase_ratio_min,
                    "success_rate_drop_min": success_rate_drop_min,
                    "degraded_rate_increase_min": degraded_rate_increase_min,
                },
                "latest_guard": {
                    "max_p95_ratio_to_window_median": max_p95_ratio_to_window_median,
                    "min_success_rate_delta_to_window_median": min_success_rate_delta_to_window_median,
                    "max_degraded_rate_delta_to_window_median": max_degraded_rate_delta_to_window_median,
                },
            },
            "soak": {
                "enabled": soak_enabled,
                "required_in_strict": soak_required_in_strict,
                "mode": soak_mode,
                "window_runs": soak_window_runs,
                "min_required_runs": soak_min_required_runs,
                "allow_insufficient_history": soak_allow_insufficient,
                "consecutive_worsen_limit": soak_consecutive_limit,
                "worsen": {
                    "p95_increase_ratio_min": soak_p95_increase_ratio_min,
                    "success_rate_drop_min": soak_success_rate_drop_min,
                    "degraded_rate_increase_min": soak_degraded_rate_increase_min,
                },
                "latest_guard": {
                    "max_p95_ratio_to_window_median": soak_max_p95_ratio_to_window_median,
                    "min_success_rate_delta_to_window_median": soak_min_success_rate_delta_to_window_median,
                    "max_degraded_rate_delta_to_window_median": soak_max_degraded_rate_delta_to_window_median,
                },
            },
        },
        "checks": checks,
        "trend": {
            "reports_considered": load_trend.get("reports_considered", []),
            "transitions": load_trend.get("transitions", []),
            "tail_consecutive_worsen": load_trend.get("tail_consecutive_worsen", 0),
            "latest_vs_median": load_trend.get("latest_vs_median", {}),
            "load": load_trend,
            "soak": soak_trend,
        },
    }
    out_path = Path(str(args.out or Path(".data/out") / f"preflight_trend_guard_{int(ended)}.json"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report.get("ok")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
