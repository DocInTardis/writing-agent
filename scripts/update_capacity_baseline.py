#!/usr/bin/env python3
"""Update Capacity Baseline command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import json
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


def _latest_report(pattern: str) -> Path | None:
    rows = sorted(Path(".").glob(pattern), key=lambda p: p.stat().st_mtime if p.exists() else 0.0)
    if not rows:
        return None
    return rows[-1]


def _calc_effective_rps(summary: dict[str, Any]) -> float:
    requests = _safe_float(summary.get("requests"), 0.0)
    duration_s = _safe_float(summary.get("duration_s"), 0.0)
    if requests <= 0 or duration_s <= 0:
        return 0.0
    return requests / duration_s


def _candidate_target_peak_rps(
    *,
    effective_rps: float,
    required_headroom_ratio: float,
    reserve_ratio: float,
    min_target_peak_rps: float,
) -> float:
    eff = max(0.0, float(effective_rps))
    req = max(0.001, float(required_headroom_ratio))
    reserve = min(1.0, max(0.05, float(reserve_ratio)))
    minimum = max(0.1, float(min_target_peak_rps))
    candidate = (eff / req) * reserve
    return round(max(minimum, candidate), 3)


def _quality_gate(
    *,
    summary: dict[str, Any],
    min_success_rate: float,
    max_degraded_rate: float,
    max_latency_p95_ms: float,
) -> tuple[bool, list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    success_rate = _safe_float(summary.get("success_rate"), 0.0)
    degraded_rate = _safe_float(summary.get("degraded_rate"), 1.0)
    latency = summary.get("latency_ms") if isinstance(summary.get("latency_ms"), dict) else {}
    p95 = _safe_float(latency.get("p95"), float("inf"))
    checks.append(
        {
            "id": "quality_success_rate",
            "ok": success_rate >= float(min_success_rate),
            "value": round(success_rate, 6),
            "expect": f">={float(min_success_rate):.4f}",
        }
    )
    checks.append(
        {
            "id": "quality_degraded_rate",
            "ok": degraded_rate <= float(max_degraded_rate),
            "value": round(degraded_rate, 6),
            "expect": f"<={float(max_degraded_rate):.4f}",
        }
    )
    checks.append(
        {
            "id": "quality_latency_p95_ms",
            "ok": p95 <= float(max_latency_p95_ms),
            "value": round(p95, 3),
            "expect": f"<={float(max_latency_p95_ms):.2f}",
        }
    )
    return all(bool(row.get("ok")) for row in checks), checks


def main() -> int:
    parser = argparse.ArgumentParser(description="Update security/capacity_policy.json from latest load probe baseline.")
    parser.add_argument("--policy", default="security/capacity_policy.json")
    parser.add_argument("--load-report", default="")
    parser.add_argument("--reserve-ratio", type=float, default=0.9)
    parser.add_argument("--min-target-peak-rps", type=float, default=1.0)
    parser.add_argument("--min-success-rate", type=float, default=0.99)
    parser.add_argument("--max-degraded-rate", type=float, default=0.05)
    parser.add_argument("--max-latency-p95-ms", type=float, default=2200.0)
    parser.add_argument("--capacity-profile", default="")
    parser.add_argument("--allow-regression", action="store_true")
    parser.add_argument("--reason", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    started = time.time()
    ts = int(started)
    out_dir = Path(".data/out")
    out_dir.mkdir(parents=True, exist_ok=True)
    report_out_default = out_dir / f"capacity_baseline_refresh_{ts}.json"
    generated_policy_default = out_dir / f"capacity_policy_generated_{ts}.json"

    policy_path = Path(str(args.policy))
    load_path = Path(str(args.load_report)) if str(args.load_report).strip() else _latest_report(".data/out/citation_verify_load_probe_*.json")

    checks: list[dict[str, Any]] = []
    capacity_profile = _resolve_capacity_profile(str(args.capacity_profile))
    policy_raw = _load_json(policy_path)
    checks.append(
        {
            "id": "policy_loaded",
            "ok": isinstance(policy_raw, dict),
            "value": policy_path.as_posix(),
            "expect": "capacity policy json exists and valid",
        }
    )
    load_raw = _load_json(load_path) if isinstance(load_path, Path) else None
    checks.append(
        {
            "id": "load_report_loaded",
            "ok": isinstance(load_raw, dict),
            "value": load_path.as_posix() if isinstance(load_path, Path) else "",
            "expect": "load report exists and valid",
        }
    )

    guard_ok = all(bool(row.get("ok")) for row in checks)
    guard_reason = ""
    generated_policy: dict[str, Any] = {}
    direction = "unchanged"
    previous_target_peak_rps = 0.0
    candidate_target_peak_rps = 0.0
    effective_rps = 0.0

    if guard_ok:
        assert isinstance(policy_raw, dict)
        assert isinstance(load_raw, dict)
        root = policy_raw.get("citation_metrics") if isinstance(policy_raw.get("citation_metrics"), dict) else {}
        profile_overrides = root.get("profile_overrides") if isinstance(root.get("profile_overrides"), dict) else {}
        profile_node = (
            profile_overrides.get(capacity_profile)
            if isinstance(profile_overrides.get(capacity_profile), dict)
            else {}
        )
        summary = load_raw.get("summary") if isinstance(load_raw.get("summary"), dict) else {}
        quality_ok, quality_checks = _quality_gate(
            summary=summary,
            min_success_rate=float(args.min_success_rate),
            max_degraded_rate=float(args.max_degraded_rate),
            max_latency_p95_ms=float(args.max_latency_p95_ms),
        )
        checks.extend(quality_checks)
        if not quality_ok:
            guard_ok = False
            guard_reason = "load_report_quality_gate_failed"

        required_headroom_ratio = _safe_float(
            profile_node.get("required_headroom_ratio", root.get("required_headroom_ratio"))
            if isinstance(profile_node, dict)
            else root.get("required_headroom_ratio"),
            1.2,
        )
        previous_target_peak_rps = _safe_float(
            profile_node.get("target_peak_rps", root.get("target_peak_rps"))
            if isinstance(profile_node, dict)
            else root.get("target_peak_rps"),
            20.0,
        )
        effective_rps = _calc_effective_rps(summary)
        candidate_target_peak_rps = _candidate_target_peak_rps(
            effective_rps=effective_rps,
            required_headroom_ratio=required_headroom_ratio,
            reserve_ratio=float(args.reserve_ratio),
            min_target_peak_rps=float(args.min_target_peak_rps),
        )
        if candidate_target_peak_rps > previous_target_peak_rps + 1e-9:
            direction = "increase"
        elif candidate_target_peak_rps < previous_target_peak_rps - 1e-9:
            direction = "decrease"
        else:
            direction = "unchanged"

        reason = str(args.reason or "").strip()
        if direction != "unchanged" and not reason:
            guard_ok = False
            guard_reason = "capacity_baseline_change_requires_reason"
        elif direction == "decrease" and not bool(args.allow_regression) and (not bool(args.dry_run)):
            guard_ok = False
            guard_reason = "capacity_baseline_decrease_requires_allow_regression"

        generated_policy = json.loads(json.dumps(policy_raw))
        node = generated_policy.get("citation_metrics") if isinstance(generated_policy.get("citation_metrics"), dict) else {}
        node["target_peak_rps"] = round(candidate_target_peak_rps, 3)
        baseline_meta = node.get("baseline_meta") if isinstance(node.get("baseline_meta"), dict) else {}
        baseline_meta.update(
            {
                "updated_at": round(time.time(), 3),
                "updated_by": "scripts/update_capacity_baseline.py",
                "source_load_report": load_path.as_posix() if isinstance(load_path, Path) else "",
                "effective_rps": round(effective_rps, 6),
                "required_headroom_ratio": round(required_headroom_ratio, 6),
                "reserve_ratio": round(float(args.reserve_ratio), 6),
                "previous_target_peak_rps": round(previous_target_peak_rps, 3),
                "candidate_target_peak_rps": round(candidate_target_peak_rps, 3),
                "direction": direction,
                "allow_regression": bool(args.allow_regression),
                "reason": reason,
            }
        )
        node["baseline_meta"] = baseline_meta

        profile_overrides_generated = (
            node.get("profile_overrides")
            if isinstance(node.get("profile_overrides"), dict)
            else {}
        )
        profile_entry = (
            profile_overrides_generated.get(capacity_profile)
            if isinstance(profile_overrides_generated.get(capacity_profile), dict)
            else {}
        )
        profile_entry["target_peak_rps"] = round(candidate_target_peak_rps, 3)
        profile_entry["required_headroom_ratio"] = round(required_headroom_ratio, 6)
        profile_baseline_meta = (
            profile_entry.get("baseline_meta") if isinstance(profile_entry.get("baseline_meta"), dict) else {}
        )
        profile_baseline_meta.update(baseline_meta)
        profile_baseline_meta["capacity_profile"] = capacity_profile
        profile_entry["baseline_meta"] = profile_baseline_meta
        profile_overrides_generated[capacity_profile] = profile_entry
        node["profile_overrides"] = profile_overrides_generated
        generated_policy["citation_metrics"] = node

    write_ok = bool(guard_ok and generated_policy)
    generated_policy_path = Path(str(generated_policy_default))
    if generated_policy:
        generated_policy_path.write_text(json.dumps(generated_policy, ensure_ascii=False, indent=2), encoding="utf-8")
    if write_ok and not bool(args.dry_run):
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        policy_path.write_text(json.dumps(generated_policy, ensure_ascii=False, indent=2), encoding="utf-8")

    ended = time.time()
    report = {
        "ok": bool(write_ok),
        "started_at": round(started, 3),
        "ended_at": round(ended, 3),
        "duration_s": round(ended - started, 3),
        "policy_path": policy_path.as_posix(),
        "load_report_path": load_path.as_posix() if isinstance(load_path, Path) else "",
        "generated_policy_path": generated_policy_path.as_posix() if generated_policy else "",
        "dry_run": bool(args.dry_run),
        "capacity_profile": capacity_profile,
        "guard_ok": bool(guard_ok),
        "guard_reason": str(guard_reason),
        "direction": direction,
        "previous_target_peak_rps": round(previous_target_peak_rps, 3),
        "candidate_target_peak_rps": round(candidate_target_peak_rps, 3),
        "effective_rps": round(effective_rps, 6),
        "allow_regression": bool(args.allow_regression),
        "reason": str(args.reason or "").strip(),
        "checks": checks,
    }
    out_path = Path(str(args.out or report_out_default))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report.get("ok")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
