#!/usr/bin/env python3
"""Capacity Stress Gate command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


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


def _check_row(*, check_id: str, ok: bool, value: Any, expect: str, mode: str = "warn") -> dict[str, Any]:
    return {
        "id": str(check_id),
        "ok": bool(ok),
        "value": value,
        "expect": str(expect),
        "mode": str(mode or "warn"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Gate release by recent capacity stress matrix evidence.")
    parser.add_argument("--report", default="")
    parser.add_argument("--pattern", default=".data/out/capacity_stress_matrix_*.json")
    parser.add_argument("--max-age-s", type=float, default=7 * 24 * 3600.0)
    parser.add_argument("--min-profiles", type=int, default=3)
    parser.add_argument("--max-failed-profiles", type=int, default=0)
    parser.add_argument("--require-soak", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    started = time.time()
    checks: list[dict[str, Any]] = []
    mode = "enforce" if bool(args.strict) else "warn"

    report_path = Path(str(args.report)) if str(args.report).strip() else _latest_report(str(args.pattern))
    report_raw = _load_json(report_path) if isinstance(report_path, Path) else None
    checks.append(
        _check_row(
            check_id="stress_report_loaded",
            ok=isinstance(report_raw, dict),
            value=report_path.as_posix() if isinstance(report_path, Path) else "",
            expect="stress matrix report exists and valid",
            mode=mode,
        )
    )

    if isinstance(report_raw, dict):
        ended_at = _safe_float(report_raw.get("ended_at"), 0.0)
        age_s = max(0.0, started - ended_at) if ended_at > 0 else float("inf")
        checks.append(
            _check_row(
                check_id="stress_report_fresh",
                ok=age_s <= float(args.max_age_s),
                value=round(age_s, 3) if age_s != float("inf") else "inf",
                expect=f"<={float(args.max_age_s):.1f}s",
                mode=mode,
            )
        )

        summary = report_raw.get("summary") if isinstance(report_raw.get("summary"), dict) else {}
        profiles_total = _safe_int(summary.get("profiles_total"), 0)
        profiles_fail = _safe_int(summary.get("profiles_fail"), 0)
        checks.append(
            _check_row(
                check_id="stress_profiles_min_count",
                ok=profiles_total >= max(1, int(args.min_profiles)),
                value={"profiles_total": profiles_total, "min_profiles": max(1, int(args.min_profiles))},
                expect="profiles_total >= min_profiles",
                mode=mode,
            )
        )
        checks.append(
            _check_row(
                check_id="stress_profiles_fail_bound",
                ok=profiles_fail <= max(0, int(args.max_failed_profiles)),
                value={"profiles_fail": profiles_fail, "max_failed_profiles": max(0, int(args.max_failed_profiles))},
                expect="profiles_fail <= max_failed_profiles",
                mode=mode,
            )
        )
        if bool(args.require_soak):
            soak = report_raw.get("soak") if isinstance(report_raw.get("soak"), dict) else {}
            checks.append(
                _check_row(
                    check_id="stress_soak_required",
                    ok=bool(soak.get("ok")) and bool(soak.get("report_ok")),
                    value={"ok": bool(soak.get("ok")), "report_ok": bool(soak.get("report_ok"))},
                    expect="soak run exists and passes",
                    mode=mode,
                )
            )

    ok = all(bool(row.get("ok")) for row in checks)

    ended = time.time()
    report = {
        "ok": bool(ok),
        "started_at": round(started, 3),
        "ended_at": round(ended, 3),
        "duration_s": round(ended - started, 3),
        "strict": bool(args.strict),
        "pattern": str(args.pattern),
        "report_path": report_path.as_posix() if isinstance(report_path, Path) else "",
        "checks": checks,
    }
    out_default = Path(".data/out") / f"capacity_stress_gate_{int(ended)}.json"
    out_path = Path(str(args.out or out_default))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if bool(args.strict):
        return 0 if bool(ok) else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
