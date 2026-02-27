#!/usr/bin/env python3
"""Slo Guard command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import json
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


def _latest_report(pattern: str) -> Path | None:
    rows = sorted(Path(".").glob(pattern), key=lambda p: p.stat().st_mtime if p.exists() else 0.0)
    if not rows:
        return None
    return rows[-1]


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return int(default)


def _check_row(check_id: str, ok: bool, value: Any, expect: str, mode: str = "enforce") -> dict[str, Any]:
    return {
        "id": check_id,
        "ok": bool(ok),
        "value": value,
        "expect": expect,
        "mode": mode,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="SLO guard based on load probe report and policy targets.")
    parser.add_argument("--policy", default="security/slo_targets.json")
    parser.add_argument("--load-report", default="")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    policy_path = Path(str(args.policy))
    load_path = Path(str(args.load_report)) if str(args.load_report).strip() else None
    if load_path is None:
        load_path = _latest_report(".data/out/citation_verify_load_probe_*.json")

    started = time.time()
    checks: list[dict[str, Any]] = []
    policy_raw = _load_json(policy_path)
    report_raw = _load_json(load_path) if isinstance(load_path, Path) else None

    if not isinstance(policy_raw, dict):
        checks.append(_check_row("policy_loaded", False, False, "policy json exists and valid"))
        report = {
            "ok": False,
            "started_at": round(started, 3),
            "ended_at": round(time.time(), 3),
            "duration_s": round(time.time() - started, 3),
            "policy_path": str(policy_path.as_posix()),
            "load_report_path": str(load_path.as_posix() if isinstance(load_path, Path) else ""),
            "checks": checks,
        }
        out_path = Path(str(args.out or Path(".data/out") / f"slo_guard_{int(time.time())}.json"))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    if not isinstance(report_raw, dict):
        checks.append(_check_row("load_report_loaded", False, False, "load probe report exists and valid"))
        report = {
            "ok": False,
            "started_at": round(started, 3),
            "ended_at": round(time.time(), 3),
            "duration_s": round(time.time() - started, 3),
            "policy_path": str(policy_path.as_posix()),
            "load_report_path": str(load_path.as_posix() if isinstance(load_path, Path) else ""),
            "checks": checks,
        }
        out_path = Path(str(args.out or Path(".data/out") / f"slo_guard_{int(time.time())}.json"))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    policy = policy_raw.get("citation_metrics") if isinstance(policy_raw.get("citation_metrics"), dict) else {}
    summary = report_raw.get("summary") if isinstance(report_raw.get("summary"), dict) else {}
    latency = summary.get("latency_ms") if isinstance(summary.get("latency_ms"), dict) else {}
    events_probe = report_raw.get("events_probe") if isinstance(report_raw.get("events_probe"), dict) else {}

    min_success = _safe_float(policy.get("success_rate_min"), 0.99)
    max_p95 = _safe_float(policy.get("latency_p95_ms_max"), 1500.0)
    max_degraded = _safe_float(policy.get("degraded_rate_max"), 0.05)
    min_recent_events = _safe_int(policy.get("events_recent_min"), 0)

    if bool(args.quick):
        min_success = min(min_success, 0.99)
        max_p95 = max(max_p95, 2200.0)
        max_degraded = max(max_degraded, 0.05)

    success_rate = _safe_float(summary.get("success_rate"), 0.0)
    p95 = _safe_float(latency.get("p95"), 0.0)
    degraded_rate = _safe_float(summary.get("degraded_rate"), 0.0)
    recent_events = _safe_int(events_probe.get("recent_count"), 0)
    events_ok = bool(events_probe.get("ok"))

    checks.append(
        _check_row(
            "slo_success_rate",
            success_rate >= min_success,
            success_rate,
            f">={min_success:.4f}",
        )
    )
    checks.append(
        _check_row(
            "slo_latency_p95_ms",
            p95 <= max_p95,
            p95,
            f"<={max_p95:.2f}",
        )
    )
    checks.append(
        _check_row(
            "slo_degraded_rate",
            degraded_rate <= max_degraded,
            degraded_rate,
            f"<={max_degraded:.4f}",
        )
    )
    checks.append(
        _check_row(
            "slo_events_probe_ok",
            events_ok,
            events_ok,
            "events probe returns ok=true",
            mode="warn",
        )
    )
    checks.append(
        _check_row(
            "slo_recent_events_min",
            recent_events >= min_recent_events,
            recent_events,
            f">={min_recent_events}",
            mode="warn",
        )
    )

    enforce_rows = [row for row in checks if str(row.get("mode") or "enforce") == "enforce"]
    ended = time.time()
    report = {
        "ok": all(bool(row.get("ok")) for row in enforce_rows),
        "started_at": round(started, 3),
        "ended_at": round(ended, 3),
        "duration_s": round(ended - started, 3),
        "quick": bool(args.quick),
        "policy_path": policy_path.as_posix(),
        "load_report_path": load_path.as_posix() if isinstance(load_path, Path) else "",
        "targets": {
            "success_rate_min": min_success,
            "latency_p95_ms_max": max_p95,
            "degraded_rate_max": max_degraded,
            "events_recent_min": min_recent_events,
        },
        "observed": {
            "success_rate": success_rate,
            "latency_p95_ms": p95,
            "degraded_rate": degraded_rate,
            "events_probe_ok": events_ok,
            "recent_events": recent_events,
        },
        "checks": checks,
    }
    out_path = Path(str(args.out or Path(".data/out") / f"slo_guard_{int(ended)}.json"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report.get("ok")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
