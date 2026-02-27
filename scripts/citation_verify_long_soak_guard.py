#!/usr/bin/env python3
"""Citation Verify Long Soak Guard command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any


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


def _check_row(*, check_id: str, ok: bool, value: Any, expect: str, mode: str = "warn") -> dict[str, Any]:
    return {
        "id": str(check_id),
        "ok": bool(ok),
        "value": value,
        "expect": str(expect),
        "mode": str(mode or "warn"),
    }


def _median(values: list[float]) -> float:
    rows = [float(x) for x in values]
    if not rows:
        return 0.0
    return float(statistics.median(rows))


def _normalize_entry(raw: dict[str, Any], *, source: str) -> dict[str, Any]:
    ts = _safe_float(raw.get("ts"), 0.0)
    ended_at = _safe_float(raw.get("ended_at"), 0.0)
    started_at = _safe_float(raw.get("started_at"), 0.0)
    if ended_at <= 0 and ts > 0:
        ended_at = ts
    if started_at <= 0 and ended_at > 0:
        started_at = max(0.0, ended_at - _safe_float(raw.get("duration_s"), 0.0))
    duration_s = _safe_float(raw.get("duration_s"), max(0.0, ended_at - started_at))
    label = str(raw.get("label") or "").strip()
    return {
        "source": str(source),
        "path": str(raw.get("path") or ""),
        "label": label,
        "ts": ended_at if ended_at > 0 else ts,
        "started_at": started_at,
        "ended_at": ended_at if ended_at > 0 else ts,
        "duration_s": max(0.0, duration_s),
        "success_rate": _safe_float(raw.get("success_rate"), 0.0),
        "p95_ms": _safe_float(raw.get("p95_ms"), 0.0),
        "degraded_rate": _safe_float(raw.get("degraded_rate"), 0.0),
        "requests": _safe_int(raw.get("requests"), 0),
        "window_count": _safe_int(raw.get("window_count"), 0),
    }


def _entry_key(row: dict[str, Any]) -> str:
    return "|".join(
        [
            f"{_safe_float(row.get('ended_at'), 0.0):.3f}",
            f"{_safe_float(row.get('duration_s'), 0.0):.3f}",
            f"{_safe_float(row.get('success_rate'), 0.0):.6f}",
            f"{_safe_float(row.get('p95_ms'), 0.0):.3f}",
            f"{_safe_float(row.get('degraded_rate'), 0.0):.6f}",
            str(row.get("label") or ""),
            str(row.get("path") or ""),
        ]
    )


def _read_soak_reports(pattern: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(Path(".").glob(pattern), key=lambda p: p.stat().st_mtime if p.exists() else 0.0):
        raw = _load_json(path)
        if not isinstance(raw, dict):
            continue
        aggregate = raw.get("aggregate") if isinstance(raw.get("aggregate"), dict) else {}
        row = _normalize_entry(
            {
                "path": path.as_posix(),
                "label": raw.get("label"),
                "started_at": raw.get("started_at"),
                "ended_at": raw.get("ended_at"),
                "duration_s": raw.get("duration_s"),
                "success_rate": aggregate.get("success_rate"),
                "p95_ms": aggregate.get("latency_p95_ms"),
                "degraded_rate": aggregate.get("degraded_rate"),
                "requests": aggregate.get("requests"),
                "window_count": aggregate.get("window_count"),
            },
            source="report",
        )
        if _safe_float(row.get("ts"), 0.0) <= 0:
            row["ts"] = _safe_float(path.stat().st_mtime if path.exists() else 0.0, 0.0)
            row["ended_at"] = _safe_float(row.get("ts"), 0.0)
        rows.append(row)
    rows.sort(key=lambda row: _safe_float(row.get("ts"), 0.0))
    return rows


def _read_history(path: Path) -> list[dict[str, Any]]:
    raw = _load_json(path)
    if isinstance(raw, dict):
        entries = raw.get("entries") if isinstance(raw.get("entries"), list) else []
        rows: list[dict[str, Any]] = []
        for entry in entries:
            if isinstance(entry, dict):
                rows.append(_normalize_entry(entry, source="history"))
        rows.sort(key=lambda row: _safe_float(row.get("ts"), 0.0))
        return rows
    if isinstance(raw, list):
        rows = []
        for entry in raw:
            if isinstance(entry, dict):
                rows.append(_normalize_entry(entry, source="history"))
        rows.sort(key=lambda row: _safe_float(row.get("ts"), 0.0))
        return rows
    return []


def _merge_history(
    *,
    history_rows: list[dict[str, Any]],
    current_rows: list[dict[str, Any]],
    now_ts: float,
    retention_days: float,
    max_records: int,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in [*history_rows, *current_rows]:
        key = _entry_key(row)
        if key in seen:
            continue
        seen.add(key)
        merged.append(dict(row))
    merged.sort(key=lambda item: _safe_float(item.get("ts"), 0.0))

    if retention_days > 0:
        min_ts = float(now_ts) - float(retention_days) * 24.0 * 3600.0
        merged = [row for row in merged if _safe_float(row.get("ts"), 0.0) >= min_ts]
    if max_records > 0 and len(merged) > int(max_records):
        merged = merged[-int(max_records) :]
    return merged


def _profile_coverage(
    *,
    rows: list[dict[str, Any]],
    profile_id: str,
    min_duration_s: float,
    required_count: int,
    window_days: float,
    now_ts: float,
) -> dict[str, Any]:
    min_duration = max(0.0, float(min_duration_s))
    window_s = max(0.0, float(window_days) * 24.0 * 3600.0)
    window_start = float(now_ts) - window_s if window_s > 0 else 0.0
    matched = [
        row
        for row in rows
        if _safe_float(row.get("duration_s"), 0.0) >= min_duration
        and (_safe_float(row.get("ts"), 0.0) >= window_start if window_s > 0 else True)
    ]
    return {
        "profile_id": str(profile_id),
        "min_duration_s": min_duration,
        "required_count": max(0, int(required_count)),
        "window_days": max(0.0, float(window_days)),
        "actual_count": len(matched),
        "matched_reports": matched,
        "ok": len(matched) >= max(0, int(required_count)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate citation long-soak evidence retention and regression guard."
    )
    parser.add_argument("--policy", default="security/long_soak_policy.json")
    parser.add_argument("--pattern", default=".data/out/citation_verify_soak_*.json")
    parser.add_argument("--history-file", default=".data/perf/citation_verify_long_soak_history.json")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    started = time.time()
    checks: list[dict[str, Any]] = []
    mode = "enforce" if bool(args.strict) else "warn"

    policy_path = Path(str(args.policy))
    policy_raw = _load_json(policy_path)
    checks.append(
        _check_row(
            check_id="long_soak_policy_loaded",
            ok=isinstance(policy_raw, dict),
            value=policy_path.as_posix(),
            expect="long soak policy exists and valid",
            mode="enforce",
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
            "history": {"path": str(args.history_file), "entries": []},
        }
        out_default = Path(".data/out") / f"citation_verify_long_soak_guard_{int(ended)}.json"
        out_path = Path(str(args.out or out_default))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    history_cfg = policy_raw.get("history") if isinstance(policy_raw.get("history"), dict) else {}
    gate_cfg = policy_raw.get("gate") if isinstance(policy_raw.get("gate"), dict) else {}
    regression_cfg = policy_raw.get("regression") if isinstance(policy_raw.get("regression"), dict) else {}
    profiles_cfg = policy_raw.get("profiles") if isinstance(policy_raw.get("profiles"), list) else []

    history_retention_days = max(1.0, _safe_float(history_cfg.get("retention_days"), 120.0))
    history_max_records = max(10, _safe_int(history_cfg.get("max_records"), 180))
    min_reports = max(1, _safe_int(gate_cfg.get("min_reports"), 6))
    max_report_age_s = max(60.0, _safe_float(gate_cfg.get("max_report_age_s"), 14 * 24 * 3600.0))

    now_ts = time.time()
    history_path = Path(str(args.history_file))
    history_rows = _read_history(history_path)
    current_rows = _read_soak_reports(str(args.pattern))
    merged_rows = _merge_history(
        history_rows=history_rows,
        current_rows=current_rows,
        now_ts=now_ts,
        retention_days=history_retention_days,
        max_records=history_max_records,
    )

    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_payload = {
        "version": 1,
        "updated_at": round(now_ts, 3),
        "policy_path": policy_path.as_posix(),
        "entries": merged_rows,
    }
    history_path.write_text(json.dumps(history_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    checks.append(
        _check_row(
            check_id="long_soak_history_min_reports",
            ok=len(merged_rows) >= min_reports,
            value={"count": len(merged_rows), "required": min_reports},
            expect="history reports count >= min_reports",
            mode=mode,
        )
    )

    latest = merged_rows[-1] if merged_rows else {}
    latest_age_s = (
        max(0.0, now_ts - _safe_float(latest.get("ts"), 0.0)) if _safe_float(latest.get("ts"), 0.0) > 0 else float("inf")
    )
    checks.append(
        _check_row(
            check_id="long_soak_latest_report_fresh",
            ok=latest_age_s <= max_report_age_s,
            value=round(latest_age_s, 3) if latest_age_s != float("inf") else "inf",
            expect=f"<={max_report_age_s:.1f}s",
            mode=mode,
        )
    )

    profile_results: list[dict[str, Any]] = []
    for profile_raw in profiles_cfg:
        if not isinstance(profile_raw, dict):
            continue
        profile_id = str(profile_raw.get("id") or "").strip()
        if not profile_id:
            continue
        profile_result = _profile_coverage(
            rows=merged_rows,
            profile_id=profile_id,
            min_duration_s=_safe_float(profile_raw.get("min_duration_s"), 0.0),
            required_count=_safe_int(profile_raw.get("required_count"), 0),
            window_days=_safe_float(profile_raw.get("window_days"), 0.0),
            now_ts=now_ts,
        )
        profile_results.append(profile_result)
        checks.append(
            _check_row(
                check_id=f"profile_{profile_id}_coverage",
                ok=bool(profile_result.get("ok")),
                value={
                    "actual_count": profile_result.get("actual_count"),
                    "required_count": profile_result.get("required_count"),
                    "window_days": profile_result.get("window_days"),
                    "min_duration_s": profile_result.get("min_duration_s"),
                },
                expect="actual_count >= required_count",
                mode=mode,
            )
        )

    regression_window_runs = max(3, _safe_int(regression_cfg.get("window_runs"), 12))
    regression_min_required = max(2, _safe_int(regression_cfg.get("min_required_runs"), 5))
    regression_min_duration_s = max(0.0, _safe_float(regression_cfg.get("min_duration_s"), 12 * 3600.0))
    max_p95_ratio_to_median = max(1.0, _safe_float(regression_cfg.get("max_p95_ratio_to_median"), 1.25))
    min_success_rate_delta_to_median = _safe_float(
        regression_cfg.get("min_success_rate_delta_to_median"),
        -0.005,
    )
    max_degraded_rate_delta_to_median = _safe_float(
        regression_cfg.get("max_degraded_rate_delta_to_median"),
        0.01,
    )

    regression_rows = [
        row for row in merged_rows if _safe_float(row.get("duration_s"), 0.0) >= regression_min_duration_s
    ]
    regression_rows = regression_rows[-regression_window_runs:]

    checks.append(
        _check_row(
            check_id="long_soak_regression_reports_available",
            ok=len(regression_rows) >= regression_min_required,
            value={"available": len(regression_rows), "required": regression_min_required},
            expect="enough long soak reports for regression check",
            mode=mode,
        )
    )

    latest_vs_median = {
        "p95_ratio": 1.0,
        "success_rate_delta": 0.0,
        "degraded_rate_delta": 0.0,
        "history_count": max(0, len(regression_rows) - 1),
    }
    if len(regression_rows) >= 2:
        regression_latest = regression_rows[-1]
        regression_history = regression_rows[:-1]
        p95_median = _median([_safe_float(row.get("p95_ms"), 0.0) for row in regression_history])
        success_median = _median([_safe_float(row.get("success_rate"), 0.0) for row in regression_history])
        degraded_median = _median([_safe_float(row.get("degraded_rate"), 0.0) for row in regression_history])
        p95_ratio = _safe_float(regression_latest.get("p95_ms"), 0.0) / max(0.001, p95_median)
        success_delta = _safe_float(regression_latest.get("success_rate"), 0.0) - success_median
        degraded_delta = _safe_float(regression_latest.get("degraded_rate"), 0.0) - degraded_median
        latest_vs_median = {
            "p95_ratio": round(p95_ratio, 6),
            "success_rate_delta": round(success_delta, 6),
            "degraded_rate_delta": round(degraded_delta, 6),
            "history_count": len(regression_history),
        }
        checks.extend(
            [
                _check_row(
                    check_id="long_soak_regression_latest_p95_ratio",
                    ok=p95_ratio <= max_p95_ratio_to_median,
                    value=round(p95_ratio, 6),
                    expect=f"<={max_p95_ratio_to_median:.6f}",
                    mode=mode,
                ),
                _check_row(
                    check_id="long_soak_regression_latest_success_rate_delta",
                    ok=success_delta >= min_success_rate_delta_to_median,
                    value=round(success_delta, 6),
                    expect=f">={min_success_rate_delta_to_median:.6f}",
                    mode=mode,
                ),
                _check_row(
                    check_id="long_soak_regression_latest_degraded_rate_delta",
                    ok=degraded_delta <= max_degraded_rate_delta_to_median,
                    value=round(degraded_delta, 6),
                    expect=f"<={max_degraded_rate_delta_to_median:.6f}",
                    mode=mode,
                ),
            ]
        )

    enforce_rows = [row for row in checks if str(row.get("mode") or "warn") == "enforce"]
    ok = all(bool(row.get("ok")) for row in enforce_rows)
    ended = time.time()
    report = {
        "ok": bool(ok),
        "started_at": round(started, 3),
        "ended_at": round(ended, 3),
        "duration_s": round(ended - started, 3),
        "strict": bool(args.strict),
        "policy_path": policy_path.as_posix(),
        "pattern": str(args.pattern),
        "history_file": history_path.as_posix(),
        "checks": checks,
        "summary": {
            "history_count": len(merged_rows),
            "latest_report": latest,
            "profile_coverage": profile_results,
            "regression": {
                "window_runs": regression_window_runs,
                "min_required_runs": regression_min_required,
                "min_duration_s": regression_min_duration_s,
                "reports_considered": regression_rows,
                "latest_vs_median": latest_vs_median,
            },
        },
    }
    out_default = Path(".data/out") / f"citation_verify_long_soak_guard_{int(ended)}.json"
    out_path = Path(str(args.out or out_default))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if bool(args.strict):
        return 0 if bool(ok) else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
