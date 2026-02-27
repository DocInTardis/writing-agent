#!/usr/bin/env python3
"""Capacity Forecast command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None


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


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_profile(value: Any) -> str:
    text = _normalize_text(value).lower()
    alias = {
        "production": "prod",
        "stage": "staging",
        "development": "dev",
    }
    return alias.get(text, text)


def _resolve_capacity_profile(raw: str) -> str:
    explicit = _normalize_profile(raw)
    if explicit:
        return explicit
    env_profile = _normalize_profile(os.environ.get("WA_CAPACITY_PROFILE"))
    if env_profile:
        return env_profile
    return "default"


def _calc_effective_rps(summary: dict[str, Any]) -> float:
    requests = _safe_float(summary.get("requests"), 0.0)
    duration_s = _safe_float(summary.get("duration_s"), 0.0)
    if requests <= 0 or duration_s <= 0:
        return 0.0
    return requests / duration_s


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
            ts = _safe_float(raw.get("ended_at"), 0.0)
        if ts <= 0 and path.exists():
            ts = _safe_float(path.stat().st_mtime, 0.0)
        rows.append(
            {
                "path": path.as_posix(),
                "ts": ts,
                "effective_rps": _calc_effective_rps(summary),
                "success_rate": _safe_float(summary.get("success_rate"), 0.0),
                "degraded_rate": _safe_float(summary.get("degraded_rate"), 0.0),
                "p95_ms": _safe_float(latency.get("p95"), 0.0),
            }
        )
    rows.sort(key=lambda row: _safe_float(row.get("ts"), 0.0))
    return rows


def _linear_regression(xs: list[float], ys: list[float]) -> tuple[float, float, float]:
    n = min(len(xs), len(ys))
    if n < 2:
        return 0.0, (_safe_float(ys[0], 0.0) if n == 1 else 0.0), 0.0
    x_rows = [float(v) for v in xs[:n]]
    y_rows = [float(v) for v in ys[:n]]
    mean_x = statistics.mean(x_rows)
    mean_y = statistics.mean(y_rows)
    denom = sum((x - mean_x) ** 2 for x in x_rows)
    if denom <= 1e-12:
        return 0.0, float(mean_y), 0.0
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_rows, y_rows)) / denom
    intercept = mean_y - slope * mean_x

    ss_tot = sum((y - mean_y) ** 2 for y in y_rows)
    if ss_tot <= 1e-12:
        return float(slope), float(intercept), 1.0
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(x_rows, y_rows))
    r2 = max(0.0, min(1.0, 1.0 - (ss_res / ss_tot)))
    return float(slope), float(intercept), float(r2)


def _resolve_policy_for_profile(*, policy_raw: dict[str, Any], capacity_profile: str) -> tuple[dict[str, Any], str]:
    root = policy_raw.get("citation_metrics") if isinstance(policy_raw.get("citation_metrics"), dict) else {}
    profile_overrides = root.get("profile_overrides") if isinstance(root.get("profile_overrides"), dict) else {}
    profile_node = (
        profile_overrides.get(capacity_profile)
        if isinstance(profile_overrides.get(capacity_profile), dict)
        else {}
    )
    source = f"profile_overrides:{capacity_profile}" if profile_node else "citation_metrics"
    return (profile_node if profile_node else root), source


def _check_row(*, check_id: str, ok: bool, value: Any, expect: str, mode: str = "enforce") -> dict[str, Any]:
    return {
        "id": str(check_id),
        "ok": bool(ok),
        "value": value,
        "expect": str(expect),
        "mode": str(mode or "enforce"),
    }


def _forecast_risk(*, projected_headroom_ratio: float, required_headroom_ratio: float) -> str:
    required = max(0.0, float(required_headroom_ratio))
    ratio = max(0.0, float(projected_headroom_ratio))
    if ratio < required:
        return "breach"
    if ratio < (required * 1.1):
        return "watch"
    return "ok"


def _to_markdown(
    *,
    report: dict[str, Any],
) -> str:
    forecast = report.get("forecast") if isinstance(report.get("forecast"), dict) else {}
    policy = report.get("policy") if isinstance(report.get("policy"), dict) else {}
    checks = report.get("checks") if isinstance(report.get("checks"), list) else []
    lines: list[str] = []
    lines.append("# Capacity Forecast Report")
    lines.append("")
    lines.append(f"- generated_at: {report.get('ended_at')}")
    lines.append(f"- capacity_profile: {report.get('capacity_profile')}")
    lines.append(f"- policy_source: {report.get('policy_source')}")
    lines.append(f"- load_samples: {((report.get('windows') or {}).get('load_samples'))}")
    lines.append("")
    lines.append("## Forecast")
    lines.append("")
    lines.append(f"- horizon_days: {forecast.get('horizon_days')}")
    lines.append(f"- current_rps: {forecast.get('current_rps')}")
    lines.append(f"- projected_rps: {forecast.get('projected_rps')}")
    lines.append(f"- slope_rps_per_day: {forecast.get('slope_rps_per_day')}")
    lines.append(f"- r2: {forecast.get('r2')}")
    lines.append(f"- projected_headroom_ratio: {forecast.get('projected_headroom_ratio')}")
    lines.append(f"- required_headroom_ratio: {policy.get('required_headroom_ratio')}")
    lines.append(f"- risk: {forecast.get('risk')}")
    lines.append("")
    lines.append("## Checks")
    lines.append("")
    lines.append("| id | ok | mode | value |")
    lines.append("|---|---|---|---|")
    for row in checks:
        if not isinstance(row, dict):
            continue
        lines.append(
            f"| {row.get('id')} | {bool(row.get('ok'))} | {row.get('mode')} | {json.dumps(row.get('value'), ensure_ascii=False)} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate capacity growth forecast from recent load probe history.")
    parser.add_argument("--policy", default="security/capacity_policy.json")
    parser.add_argument("--load-pattern", default=".data/out/citation_verify_load_probe_*.json")
    parser.add_argument("--load-window", type=int, default=16)
    parser.add_argument("--min-samples", type=int, default=6)
    parser.add_argument("--horizon-days", type=float, default=30.0)
    parser.add_argument("--capacity-profile", default="")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--markdown-out", default="")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    started = time.time()
    checks: list[dict[str, Any]] = []
    mode = "enforce" if bool(args.strict) else "warn"

    policy_path = Path(str(args.policy))
    policy_raw = _load_json(policy_path)
    checks.append(
        _check_row(
            check_id="capacity_policy_loaded",
            ok=isinstance(policy_raw, dict),
            value=policy_path.as_posix(),
            expect="capacity policy exists and valid",
            mode=mode,
        )
    )

    load_rows = _extract_load_rows(str(args.load_pattern))
    load_recent = load_rows[-max(1, int(args.load_window)) :]
    min_samples = max(2, int(args.min_samples))
    checks.append(
        _check_row(
            check_id="capacity_forecast_samples_available",
            ok=len(load_recent) >= min_samples,
            value={"available": len(load_recent), "required": min_samples},
            expect="sufficient load samples for forecast",
            mode=mode,
        )
    )

    capacity_profile = _resolve_capacity_profile(str(args.capacity_profile))
    policy_node, policy_source = _resolve_policy_for_profile(
        policy_raw=policy_raw if isinstance(policy_raw, dict) else {},
        capacity_profile=capacity_profile,
    )
    target_peak_rps = _safe_float(policy_node.get("target_peak_rps"), 20.0)
    required_headroom_ratio = _safe_float(policy_node.get("required_headroom_ratio"), 1.2)

    horizon_days = max(1.0, float(args.horizon_days))
    xs: list[float] = []
    ys: list[float] = []
    if load_recent:
        base_ts = _safe_float(load_recent[0].get("ts"), 0.0)
        for row in load_recent:
            ts = _safe_float(row.get("ts"), 0.0)
            x_days = max(0.0, (ts - base_ts) / 86400.0)
            xs.append(x_days)
            ys.append(_safe_float(row.get("effective_rps"), 0.0))
    slope, intercept, r2 = _linear_regression(xs, ys)
    current_rps = _safe_float(statistics.median(ys[-min(len(ys), 3) :]) if ys else 0.0, 0.0)
    projected_rps = max(0.0, intercept + slope * horizon_days)
    projected_headroom_ratio = (projected_rps / target_peak_rps) if target_peak_rps > 0 else 0.0
    risk = _forecast_risk(
        projected_headroom_ratio=projected_headroom_ratio,
        required_headroom_ratio=required_headroom_ratio,
    )
    checks.append(
        _check_row(
            check_id="capacity_forecast_headroom_risk",
            ok=str(risk) != "breach",
            value={
                "risk": risk,
                "projected_headroom_ratio": round(projected_headroom_ratio, 6),
                "required_headroom_ratio": round(required_headroom_ratio, 6),
            },
            expect="projected headroom does not breach required ratio",
            mode=mode,
        )
    )

    enforce_rows = [row for row in checks if str(row.get("mode") or "enforce") == "enforce"]
    ended = time.time()
    report = {
        "ok": all(bool(row.get("ok")) for row in enforce_rows),
        "started_at": round(started, 3),
        "ended_at": round(ended, 3),
        "duration_s": round(ended - started, 3),
        "strict": bool(args.strict),
        "capacity_profile": capacity_profile,
        "policy_source": policy_source,
        "paths": {
            "policy": policy_path.as_posix(),
            "load_pattern": str(args.load_pattern),
        },
        "windows": {
            "load_window": max(1, int(args.load_window)),
            "load_samples": len(load_recent),
            "min_samples": min_samples,
        },
        "policy": {
            "target_peak_rps": round(target_peak_rps, 6),
            "required_headroom_ratio": round(required_headroom_ratio, 6),
        },
        "forecast": {
            "horizon_days": round(horizon_days, 3),
            "slope_rps_per_day": round(slope, 6),
            "intercept_rps": round(intercept, 6),
            "r2": round(r2, 6),
            "current_rps": round(current_rps, 6),
            "projected_rps": round(projected_rps, 6),
            "projected_headroom_ratio": round(projected_headroom_ratio, 6),
            "risk": risk,
        },
        "checks": checks,
    }

    out_default = Path(".data/out") / f"capacity_forecast_{int(ended)}.json"
    out_path = Path(str(args.out or out_default))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    markdown_default = out_path.with_suffix(".md")
    markdown_path = Path(str(args.markdown_out or markdown_default))
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(_to_markdown(report=report), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report.get("ok")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
