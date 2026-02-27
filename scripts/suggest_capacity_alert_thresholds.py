#!/usr/bin/env python3
"""Suggest Capacity Alert Thresholds command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import json
import math
import os
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


def _percentile(values: list[float], q: float) -> float:
    rows = sorted(float(x) for x in values)
    if not rows:
        return 0.0
    if len(rows) == 1:
        return rows[0]
    qv = min(1.0, max(0.0, float(q)))
    pos = qv * (len(rows) - 1)
    low = int(math.floor(pos))
    high = int(math.ceil(pos))
    if low == high:
        return rows[low]
    frac = pos - float(low)
    return rows[low] * (1.0 - frac) + rows[high] * frac


def _round_step(value: float, step: float, digits: int = 3) -> float:
    sv = max(0.000001, float(step))
    return round(round(float(value) / sv) * sv, int(digits))


def _extract_load_rows(pattern: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(Path(".").glob(pattern), key=lambda p: p.stat().st_mtime if p.exists() else 0.0):
        raw = _load_json(path)
        if not isinstance(raw, dict):
            continue
        summary = raw.get("summary") if isinstance(raw.get("summary"), dict) else {}
        latency = summary.get("latency_ms") if isinstance(summary.get("latency_ms"), dict) else {}
        requests = _safe_float(summary.get("requests"), 0.0)
        duration_s = _safe_float(summary.get("duration_s"), 0.0)
        effective_rps = (requests / duration_s) if requests > 0 and duration_s > 0 else 0.0
        ts = _safe_float(raw.get("ts"), 0.0)
        if ts <= 0 and path.exists():
            ts = _safe_float(path.stat().st_mtime, 0.0)
        rows.append(
            {
                "path": path.as_posix(),
                "ts": ts,
                "effective_rps": effective_rps,
                "success_rate": _safe_float(summary.get("success_rate"), 0.0),
                "degraded_rate": _safe_float(summary.get("degraded_rate"), 0.0),
                "p95_ms": _safe_float(latency.get("p95"), 0.0),
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
        if ts <= 0 and path.exists():
            ts = _safe_float(path.stat().st_mtime, 0.0)
        rows.append(
            {
                "path": path.as_posix(),
                "ts": ts,
                "success_rate": _safe_float(aggregate.get("success_rate"), 0.0),
                "degraded_rate": _safe_float(aggregate.get("degraded_rate"), 0.0),
                "p95_ms": _safe_float(aggregate.get("latency_p95_ms"), 0.0),
                "window_count": _safe_int(aggregate.get("window_count"), 0),
                "duration_s": _safe_float(raw.get("duration_s"), 0.0),
            }
        )
    rows.sort(key=lambda row: _safe_float(row.get("ts"), 0.0))
    return rows


def _check(check_id: str, ok: bool, value: Any, expect: str) -> dict[str, Any]:
    return {
        "id": str(check_id),
        "ok": bool(ok),
        "value": value,
        "expect": str(expect),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Suggest capacity alert thresholds from recent load/soak reports.")
    parser.add_argument("--policy", default="security/capacity_policy.json")
    parser.add_argument("--load-pattern", default=".data/out/citation_verify_load_probe_*.json")
    parser.add_argument("--soak-pattern", default=".data/out/citation_verify_soak_*.json")
    parser.add_argument("--load-window", type=int, default=8)
    parser.add_argument("--soak-window", type=int, default=6)
    parser.add_argument("--min-load-samples", type=int, default=3)
    parser.add_argument("--min-soak-samples", type=int, default=2)
    parser.add_argument("--capacity-profile", default="")
    parser.add_argument("--prefer-soak", action="store_true")
    parser.add_argument("--write-thresholds", default="")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    started = time.time()
    checks: list[dict[str, Any]] = []

    policy_path = Path(str(args.policy))
    policy_raw = _load_json(policy_path)
    checks.append(
        _check(
            "capacity_policy_loaded",
            isinstance(policy_raw, dict),
            policy_path.as_posix(),
            "capacity policy json exists and valid",
        )
    )

    citation_metrics = (
        policy_raw.get("citation_metrics")
        if isinstance(policy_raw, dict) and isinstance(policy_raw.get("citation_metrics"), dict)
        else {}
    )
    capacity_profile = _resolve_capacity_profile(str(args.capacity_profile))
    profile_overrides = (
        citation_metrics.get("profile_overrides")
        if isinstance(citation_metrics.get("profile_overrides"), dict)
        else {}
    )
    profile_node = (
        profile_overrides.get(capacity_profile)
        if isinstance(profile_overrides.get(capacity_profile), dict)
        else {}
    )
    profile_source = (
        f"profile_overrides:{capacity_profile}" if isinstance(profile_node, dict) and profile_node else "citation_metrics"
    )
    checks.append(
        _check(
            "capacity_profile_override_available",
            bool(profile_node) or capacity_profile == "default",
            {"capacity_profile": capacity_profile, "profile_source": profile_source},
            "profile override present or default profile in use",
        )
    )

    target_peak_rps = _safe_float(
        profile_node.get("target_peak_rps", citation_metrics.get("target_peak_rps"))
        if isinstance(profile_node, dict)
        else citation_metrics.get("target_peak_rps"),
        20.0,
    )
    required_headroom_ratio = _safe_float(
        profile_node.get("required_headroom_ratio", citation_metrics.get("required_headroom_ratio"))
        if isinstance(profile_node, dict)
        else citation_metrics.get("required_headroom_ratio"),
        1.2,
    )
    policy_p95 = _safe_float(
        profile_node.get("max_latency_p95_ms", citation_metrics.get("max_latency_p95_ms"))
        if isinstance(profile_node, dict)
        else citation_metrics.get("max_latency_p95_ms"),
        1200.0,
    )
    policy_degraded = _safe_float(
        profile_node.get("max_degraded_rate", citation_metrics.get("max_degraded_rate"))
        if isinstance(profile_node, dict)
        else citation_metrics.get("max_degraded_rate"),
        0.05,
    )
    policy_success = _safe_float(
        profile_node.get("min_success_rate", citation_metrics.get("min_success_rate"))
        if isinstance(profile_node, dict)
        else citation_metrics.get("min_success_rate"),
        0.99,
    )

    load_rows = _extract_load_rows(str(args.load_pattern))
    soak_rows = _extract_soak_rows(str(args.soak_pattern))
    load_recent = load_rows[-max(1, int(args.load_window)) :]
    soak_recent = soak_rows[-max(1, int(args.soak_window)) :]

    checks.append(
        _check(
            "load_samples_available",
            len(load_recent) >= max(1, int(args.min_load_samples)),
            {"available": len(load_recent), "required": max(1, int(args.min_load_samples))},
            "enough recent load samples",
        )
    )
    checks.append(
        _check(
            "soak_samples_available",
            len(soak_recent) >= max(0, int(args.min_soak_samples)),
            {"available": len(soak_recent), "required": max(0, int(args.min_soak_samples))},
            "enough recent soak samples",
        )
    )

    load_p95_values = [_safe_float(row.get("p95_ms"), 0.0) for row in load_recent if _safe_float(row.get("p95_ms"), 0.0) > 0]
    soak_p95_values = [_safe_float(row.get("p95_ms"), 0.0) for row in soak_recent if _safe_float(row.get("p95_ms"), 0.0) > 0]
    load_degraded_values = [_safe_float(row.get("degraded_rate"), 0.0) for row in load_recent]
    soak_degraded_values = [_safe_float(row.get("degraded_rate"), 0.0) for row in soak_recent]
    load_success_values = [_safe_float(row.get("success_rate"), 0.0) for row in load_recent]
    soak_success_values = [_safe_float(row.get("success_rate"), 0.0) for row in soak_recent]
    load_headroom_values = [
        (_safe_float(row.get("effective_rps"), 0.0) / target_peak_rps) if target_peak_rps > 0 else 0.0
        for row in load_recent
    ]

    p95_pool = list(load_p95_values)
    degraded_pool = list(load_degraded_values)
    success_pool = list(load_success_values)
    if bool(args.prefer_soak) and soak_p95_values:
        p95_pool = soak_p95_values
    else:
        p95_pool.extend(soak_p95_values)
    if bool(args.prefer_soak) and soak_degraded_values:
        degraded_pool = soak_degraded_values
    else:
        degraded_pool.extend(soak_degraded_values)
    if bool(args.prefer_soak) and soak_success_values:
        success_pool = soak_success_values
    else:
        success_pool.extend(soak_success_values)

    p95_p75 = _percentile(p95_pool, 0.75)
    p95_p90 = _percentile(p95_pool, 0.9)
    p95_p95 = _percentile(p95_pool, 0.95)

    degraded_p90 = _percentile(degraded_pool, 0.9)
    degraded_p95 = _percentile(degraded_pool, 0.95)

    success_p10 = _percentile(success_pool, 0.1)
    success_p05 = _percentile(success_pool, 0.05)
    headroom_median = _percentile(load_headroom_values, 0.5)

    warn_p95 = _round_step(max(policy_p95 * 0.85, p95_p75 * 1.15, 300.0), 25.0, digits=1)
    critical_p95 = _round_step(max(policy_p95, p95_p95 * 1.25, warn_p95 * 1.1), 25.0, digits=1)

    warn_degraded = round(min(0.5, max(policy_degraded * 0.8, degraded_p90 * 1.3, 0.005)), 4)
    critical_degraded = round(min(0.8, max(policy_degraded, degraded_p95 * 1.6, warn_degraded * 1.5)), 4)

    warn_success_min = round(max(0.9, min(policy_success, success_p10 - 0.001)), 4)
    critical_success_min = round(max(0.85, min(warn_success_min, success_p05 - 0.003)), 4)

    warn_headroom_min = round(max(0.6, min(required_headroom_ratio, headroom_median * 0.95 or required_headroom_ratio)), 4)
    critical_headroom_min = round(max(0.5, min(warn_headroom_min, required_headroom_ratio * 0.9, headroom_median * 0.85 or warn_headroom_min)), 4)

    confidence = min(
        1.0,
        max(
            0.0,
            (len(load_recent) / max(1.0, float(max(1, int(args.load_window))))) * 0.6
            + (len(soak_recent) / max(1.0, float(max(1, int(args.soak_window))))) * 0.4,
        ),
    )
    confidence = round(confidence, 4)

    recommendation = {
        "latency_p95_ms": {"warn": warn_p95, "critical": critical_p95},
        "degraded_rate": {"warn": warn_degraded, "critical": critical_degraded},
        "success_rate_min": {"warn": warn_success_min, "critical": critical_success_min},
        "headroom_ratio_min": {"warn": warn_headroom_min, "critical": critical_headroom_min},
    }

    thresholds_payload = {
        "version": 1,
        "generated_at": round(time.time(), 3),
        "capacity_profile": capacity_profile,
        "capacity_profile_source": profile_source,
        "source": {
            "policy": policy_path.as_posix(),
            "load_pattern": str(args.load_pattern),
            "soak_pattern": str(args.soak_pattern),
            "load_window": int(args.load_window),
            "soak_window": int(args.soak_window),
        },
        "confidence": confidence,
        "citation_metrics_alerts": recommendation,
        "citation_metrics_alerts_by_profile": {
            capacity_profile: recommendation,
        },
    }

    write_path_text = str(args.write_thresholds or "").strip()
    write_path = Path(write_path_text) if write_path_text else None
    if isinstance(write_path, Path):
        write_path.parent.mkdir(parents=True, exist_ok=True)
        write_path.write_text(json.dumps(thresholds_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    enough_load = len(load_recent) >= max(1, int(args.min_load_samples))
    enough_soak = len(soak_recent) >= max(0, int(args.min_soak_samples))
    ok = bool(isinstance(policy_raw, dict) and enough_load and (enough_soak or not bool(args.prefer_soak)))

    ended = time.time()
    report = {
        "ok": ok,
        "started_at": round(started, 3),
        "ended_at": round(ended, 3),
        "duration_s": round(ended - started, 3),
        "policy_path": policy_path.as_posix(),
        "capacity_profile": capacity_profile,
        "capacity_profile_source": profile_source,
        "load_pattern": str(args.load_pattern),
        "soak_pattern": str(args.soak_pattern),
        "windows": {
            "load_window": int(args.load_window),
            "soak_window": int(args.soak_window),
            "load_samples": len(load_recent),
            "soak_samples": len(soak_recent),
        },
        "checks": checks,
        "observed": {
            "p95_ms": {"p75": round(p95_p75, 3), "p90": round(p95_p90, 3), "p95": round(p95_p95, 3)},
            "degraded_rate": {"p90": round(degraded_p90, 6), "p95": round(degraded_p95, 6)},
            "success_rate": {"p10": round(success_p10, 6), "p05": round(success_p05, 6)},
            "headroom_ratio_median": round(headroom_median, 6),
        },
        "recommendation": recommendation,
        "confidence": confidence,
        "write_thresholds_path": write_path.as_posix() if isinstance(write_path, Path) else "",
    }
    out_path = Path(str(args.out or Path(".data/out") / f"capacity_alert_threshold_suggest_{int(ended)}.json"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
