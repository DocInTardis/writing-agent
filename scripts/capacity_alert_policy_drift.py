#!/usr/bin/env python3
"""Capacity Alert Policy Drift command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from copy import deepcopy
from pathlib import Path
from typing import Any


_MAPPINGS: list[dict[str, Any]] = [
    {
        "metric": "latency_p95_ms",
        "policy_field": "max_latency_p95_ms",
        "kind": "max",
        "digits": 1,
        "min_abs_change_to_flag": 25.0,
    },
    {
        "metric": "degraded_rate",
        "policy_field": "max_degraded_rate",
        "kind": "max",
        "digits": 4,
        "min_abs_change_to_flag": 0.002,
    },
    {
        "metric": "success_rate_min",
        "policy_field": "min_success_rate",
        "kind": "min",
        "digits": 4,
        "min_abs_change_to_flag": 0.001,
    },
    {
        "metric": "headroom_ratio_min",
        "policy_field": "required_headroom_ratio",
        "kind": "min",
        "digits": 4,
        "min_abs_change_to_flag": 0.02,
    },
]


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
    return ""


def _sha256_of_text(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


def _stable_json_sha256(payload: dict[str, Any] | None) -> str:
    if not isinstance(payload, dict):
        return ""
    try:
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except Exception:
        return ""
    return _sha256_of_text(text)


def _walk_get(root: dict[str, Any], path_tokens: tuple[str, ...]) -> Any:
    cur: Any = root
    for token in path_tokens:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(token)
    return cur


def _walk_set(root: dict[str, Any], path_tokens: tuple[str, ...], value: Any) -> None:
    cur: dict[str, Any] = root
    for token in path_tokens[:-1]:
        nxt = cur.get(token)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[token] = nxt
        cur = nxt
    cur[path_tokens[-1]] = value


def _relative_delta(current_value: float, next_value: float) -> float:
    base = abs(float(current_value))
    if base > 1e-12:
        return abs(float(next_value) - float(current_value)) / base
    return 0.0 if abs(float(next_value)) <= 1e-12 else 1.0


def _drift_direction(*, kind: str, current_value: float, next_value: float) -> str:
    if abs(float(next_value) - float(current_value)) <= 1e-12:
        return "unchanged"
    is_max = str(kind) == "max"
    if is_max:
        return "relax" if next_value > current_value else "tighten"
    return "relax" if next_value < current_value else "tighten"


def _check_row(*, check_id: str, ok: bool, value: Any, expect: str, mode: str) -> dict[str, Any]:
    return {
        "id": str(check_id),
        "ok": bool(ok),
        "value": value,
        "expect": str(expect),
        "mode": str(mode or "warn"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare suggested capacity thresholds with active capacity policy and emit drift report/patch."
    )
    parser.add_argument("--policy", default="security/capacity_policy.json")
    parser.add_argument("--suggested", default=".data/out/capacity_alert_thresholds_suggested.json")
    parser.add_argument("--capacity-profile", default="")
    parser.add_argument("--policy-level", choices=("warn", "critical"), default="critical")
    parser.add_argument("--max-relative-drift", type=float, default=0.2)
    parser.add_argument("--min-confidence", type=float, default=0.45)
    parser.add_argument("--write-patch", default="")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    started = time.time()
    checks: list[dict[str, Any]] = []

    mode = "enforce" if bool(args.strict) else "warn"
    policy_path = Path(str(args.policy))
    suggested_path = Path(str(args.suggested))
    policy_raw = _load_json(policy_path)
    suggested_raw = _load_json(suggested_path)
    capacity_profile = _resolve_capacity_profile(str(args.capacity_profile))
    capacity_profile_effective = capacity_profile or "default"
    policy_sha256 = _stable_json_sha256(policy_raw if isinstance(policy_raw, dict) else None)
    suggested_sha256 = _stable_json_sha256(suggested_raw if isinstance(suggested_raw, dict) else None)

    checks.append(
        _check_row(
            check_id="capacity_policy_loaded",
            ok=isinstance(policy_raw, dict),
            value=policy_path.as_posix(),
            expect="capacity policy json exists and valid",
            mode=mode,
        )
    )
    checks.append(
        _check_row(
            check_id="suggested_thresholds_loaded",
            ok=isinstance(suggested_raw, dict),
            value=suggested_path.as_posix(),
            expect="suggested thresholds json exists and valid",
            mode=mode,
        )
    )

    recommendation_by_profile = (
        suggested_raw.get("citation_metrics_alerts_by_profile")
        if isinstance(suggested_raw, dict) and isinstance(suggested_raw.get("citation_metrics_alerts_by_profile"), dict)
        else {}
    )
    recommendation_source = "citation_metrics_alerts"
    recommendation = (
        suggested_raw.get("citation_metrics_alerts")
        if isinstance(suggested_raw, dict) and isinstance(suggested_raw.get("citation_metrics_alerts"), dict)
        else {}
    )
    profile_recommendation = (
        recommendation_by_profile.get(capacity_profile)
        if capacity_profile and isinstance(recommendation_by_profile.get(capacity_profile), dict)
        else {}
    )
    if profile_recommendation:
        recommendation = profile_recommendation
        recommendation_source = f"citation_metrics_alerts_by_profile:{capacity_profile}"

    checks.append(
        _check_row(
            check_id="suggested_citation_metrics_alerts_available",
            ok=isinstance(recommendation, dict) and len(recommendation) > 0,
            value={
                "capacity_profile": capacity_profile,
                "capacity_profile_effective": capacity_profile_effective,
                "source": recommendation_source,
                "metrics": sorted(recommendation.keys()) if isinstance(recommendation, dict) else [],
            },
            expect="citation_metrics_alerts in suggested thresholds",
            mode=mode,
        )
    )

    confidence = _safe_float((suggested_raw or {}).get("confidence"), -1.0)
    confidence_ok = confidence < 0.0 or confidence >= float(args.min_confidence)
    checks.append(
        _check_row(
            check_id="suggested_confidence_floor",
            ok=confidence_ok,
            value=round(confidence, 4) if confidence >= 0 else confidence,
            expect=f">={float(args.min_confidence):.2f} or confidence omitted",
            mode=mode,
        )
    )

    candidate_policy = deepcopy(policy_raw) if isinstance(policy_raw, dict) else {}
    drift_rows: list[dict[str, Any]] = []

    for row in _MAPPINGS:
        metric = str(row.get("metric") or "")
        policy_field = str(row.get("policy_field") or "").strip()
        policy_tokens = ("citation_metrics", policy_field)
        if capacity_profile:
            policy_tokens = ("citation_metrics", "profile_overrides", capacity_profile, policy_field)
        kind = str(row.get("kind") or "max")
        digits = int(row.get("digits") or 4)
        min_abs_change = abs(_safe_float(row.get("min_abs_change_to_flag"), 0.0))
        metric_node = recommendation.get(metric) if isinstance(recommendation, dict) and isinstance(recommendation.get(metric), dict) else {}

        current_value = _safe_float(_walk_get(policy_raw or {}, policy_tokens), float("nan"))
        if current_value != current_value:
            fallback_tokens = ("citation_metrics", policy_field)
            current_value = _safe_float(_walk_get(policy_raw or {}, fallback_tokens), float("nan"))
        suggested_value = _safe_float(metric_node.get(str(args.policy_level)), float("nan"))
        has_values = (not (current_value != current_value)) and (not (suggested_value != suggested_value))

        abs_delta = abs(suggested_value - current_value) if has_values else 0.0
        relative_delta = _relative_delta(current_value, suggested_value) if has_values else 0.0
        exceeds = has_values and abs_delta >= min_abs_change and relative_delta > float(args.max_relative_drift)

        if has_values:
            _walk_set(candidate_policy, policy_tokens, round(float(suggested_value), digits))

        drift_row = {
            "metric": metric,
            "kind": kind,
            "policy_path": ".".join(policy_tokens),
            "policy_level": str(args.policy_level),
            "current": round(float(current_value), digits) if has_values else None,
            "suggested": round(float(suggested_value), digits) if has_values else None,
            "abs_delta": round(abs_delta, max(4, digits)) if has_values else None,
            "relative_delta": round(relative_delta, 6) if has_values else None,
            "direction": _drift_direction(kind=kind, current_value=current_value, next_value=suggested_value) if has_values else "missing",
            "min_abs_change_to_flag": min_abs_change,
            "max_relative_drift": float(args.max_relative_drift),
            "exceeds": bool(exceeds),
            "has_values": bool(has_values),
        }
        drift_rows.append(drift_row)
        checks.append(
            _check_row(
                check_id=f"threshold_drift::{metric}",
                ok=(not bool(exceeds)) and bool(has_values),
                value={
                    "exceeds": bool(exceeds),
                    "current": drift_row["current"],
                    "suggested": drift_row["suggested"],
                    "relative_delta": drift_row["relative_delta"],
                },
                expect=f"relative_delta<={float(args.max_relative_drift):.3f} (after min_abs gate {min_abs_change})",
                mode=mode,
            )
        )

    changed_count = sum(1 for row in drift_rows if bool(row.get("has_values")) and abs(_safe_float(row.get("abs_delta"), 0.0)) > 0.0)
    exceeded_count = sum(1 for row in drift_rows if bool(row.get("exceeds")))

    patch_path_text = str(args.write_patch or "").strip()
    patch_path = Path(patch_path_text) if patch_path_text else None
    patch_written = False
    if isinstance(patch_path, Path) and candidate_policy:
        patch_payload = {
            "version": 1,
            "generated_at": round(time.time(), 3),
            "policy_path": policy_path.as_posix(),
            "suggested_path": suggested_path.as_posix(),
            "capacity_profile": capacity_profile_effective,
            "recommendation_source": recommendation_source,
            "source_policy_sha256": policy_sha256,
            "source_suggested_sha256": suggested_sha256,
            "policy_level": str(args.policy_level),
            "strict": bool(args.strict),
            "max_relative_drift": float(args.max_relative_drift),
            "min_confidence": float(args.min_confidence),
            "changes": drift_rows,
            "summary": {
                "mapped_metrics": len(drift_rows),
                "changed_metrics": int(changed_count),
                "exceeded_metrics": int(exceeded_count),
                "confidence": round(confidence, 4) if confidence >= 0 else confidence,
            },
            "candidate_policy": candidate_policy,
        }
        patch_path.parent.mkdir(parents=True, exist_ok=True)
        patch_path.write_text(json.dumps(patch_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        patch_written = True

    if bool(args.apply) and candidate_policy and isinstance(policy_raw, dict):
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        policy_path.write_text(json.dumps(candidate_policy, ensure_ascii=False, indent=2), encoding="utf-8")

    ok = all(bool(row.get("ok")) for row in checks)

    ended = time.time()
    report = {
        "ok": bool(ok),
        "started_at": round(started, 3),
        "ended_at": round(ended, 3),
        "duration_s": round(ended - started, 3),
        "strict": bool(args.strict),
        "policy_path": policy_path.as_posix(),
        "suggested_path": suggested_path.as_posix(),
        "capacity_profile": capacity_profile_effective,
        "recommendation_source": recommendation_source,
        "source_policy_sha256": policy_sha256,
        "source_suggested_sha256": suggested_sha256,
        "policy_level": str(args.policy_level),
        "max_relative_drift": float(args.max_relative_drift),
        "min_confidence": float(args.min_confidence),
        "confidence": round(confidence, 4) if confidence >= 0 else confidence,
        "checks": checks,
        "drift": drift_rows,
        "summary": {
            "mapped_metrics": len(drift_rows),
            "changed_metrics": int(changed_count),
            "exceeded_metrics": int(exceeded_count),
        },
        "write_patch_path": patch_path.as_posix() if isinstance(patch_path, Path) else "",
        "patch_written": bool(patch_written),
        "applied": bool(args.apply),
    }

    out_default = Path(".data/out") / f"capacity_alert_policy_drift_{int(ended)}.json"
    out_path = Path(str(args.out or out_default))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if bool(args.strict):
        return 0 if bool(report.get("ok")) else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
