#!/usr/bin/env python3
"""Update Dependency Baseline command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


SEVERITY_KEYS = ("critical", "high", "moderate", "total")
LEVEL_GROUPS = ("npm_prod", "npm_dev", "pip")


def _empty_levels() -> dict[str, int]:
    return {"info": 0, "low": 0, "moderate": 0, "high": 0, "critical": 0, "unknown": 0, "total": 0}


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None


def _normalize_levels(raw: dict[str, Any] | None) -> dict[str, dict[str, int]]:
    data = raw if isinstance(raw, dict) else {}
    levels = data.get("levels") if isinstance(data.get("levels"), dict) else {}
    out = {key: _empty_levels() for key in LEVEL_GROUPS}
    for key in LEVEL_GROUPS:
        row = levels.get(key) if isinstance(levels.get(key), dict) else {}
        for sev in ("info", "low", "moderate", "high", "critical", "unknown", "total"):
            out[key][sev] = int(row.get(sev) or 0)
    return out


def _find_regressions(
    *,
    current: dict[str, dict[str, int]],
    baseline: dict[str, dict[str, int]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group in LEVEL_GROUPS:
        now = current.get(group) or _empty_levels()
        old = baseline.get(group) or _empty_levels()
        for sev in SEVERITY_KEYS:
            curr = int(now.get(sev) or 0)
            prev = int(old.get(sev) or 0)
            if curr > prev:
                rows.append(
                    {
                        "group": group,
                        "severity": sev,
                        "current": curr,
                        "baseline": prev,
                        "delta": curr - prev,
                    }
                )
    return rows


def _run_audit(args: argparse.Namespace, *, baseline_out: Path, report_out: Path) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        "scripts/dependency_audit.py",
        "--frontend-dir",
        str(args.frontend_dir),
        "--requirements",
        str(args.requirements),
        "--write-baseline",
        str(baseline_out.as_posix()),
        "--out",
        str(report_out.as_posix()),
        "--max-npm-prod-critical",
        str(int(args.max_npm_prod_critical)),
        "--max-npm-prod-high",
        str(int(args.max_npm_prod_high)),
        "--max-npm-prod-moderate",
        str(int(args.max_npm_prod_moderate)),
        "--max-npm-dev-critical",
        str(int(args.max_npm_dev_critical)),
        "--max-npm-dev-high",
        str(int(args.max_npm_dev_high)),
        "--max-npm-dev-moderate",
        str(int(args.max_npm_dev_moderate)),
        "--max-pip-total",
        str(int(args.max_pip_total)),
    ]
    if args.skip_npm:
        cmd.append("--skip-npm")
    if args.skip_pip:
        cmd.append("--skip-pip")
    if args.require_pip_audit:
        cmd.append("--require-pip-audit")
    return subprocess.run(cmd, capture_output=True, text=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Refresh security/dependency_baseline.json from current audit with regression safeguards."
    )
    parser.add_argument("--baseline", default="security/dependency_baseline.json")
    parser.add_argument("--frontend-dir", default="writing_agent/web/frontend_svelte")
    parser.add_argument("--requirements", default="requirements.txt")
    parser.add_argument("--skip-npm", action="store_true")
    parser.add_argument("--skip-pip", action="store_true")
    parser.add_argument("--require-pip-audit", action="store_true")
    parser.add_argument("--allow-regression", action="store_true")
    parser.add_argument("--reason", default="")
    parser.add_argument("--max-npm-prod-high", type=int, default=0)
    parser.add_argument("--max-npm-prod-critical", type=int, default=0)
    parser.add_argument("--max-npm-prod-moderate", type=int, default=0)
    parser.add_argument("--max-npm-dev-high", type=int, default=0)
    parser.add_argument("--max-npm-dev-critical", type=int, default=0)
    parser.add_argument("--max-npm-dev-moderate", type=int, default=10)
    parser.add_argument("--max-pip-total", type=int, default=0)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    started = time.time()
    ts = int(started)
    out_dir = Path(".data/out")
    out_dir.mkdir(parents=True, exist_ok=True)
    generated_baseline_path = out_dir / f"dependency_baseline_generated_{ts}.json"
    audit_report_path = out_dir / f"dependency_audit_baseline_refresh_{ts}.json"
    baseline_path = Path(str(args.baseline))
    baseline_path.parent.mkdir(parents=True, exist_ok=True)

    audit_run = _run_audit(args, baseline_out=generated_baseline_path, report_out=audit_report_path)
    audit_ok = int(audit_run.returncode) == 0
    generated_raw = _load_json(generated_baseline_path)
    generated_levels = _normalize_levels(generated_raw)
    previous_raw = _load_json(baseline_path)
    previous_levels = _normalize_levels(previous_raw)
    regressions = _find_regressions(current=generated_levels, baseline=previous_levels)
    reason = str(args.reason or "").strip()

    guard_ok = True
    guard_reason = ""
    if regressions and not bool(args.allow_regression):
        guard_ok = False
        guard_reason = "regression_detected_requires_allow_regression"
    elif regressions and bool(args.allow_regression) and not reason:
        guard_ok = False
        guard_reason = "regression_requires_reason"

    ok = bool(audit_ok and guard_ok and generated_raw is not None)
    if ok:
        baseline_path.write_text(json.dumps(generated_raw, ensure_ascii=False, indent=2), encoding="utf-8")

    ended = time.time()
    report = {
        "ok": ok,
        "started_at": round(started, 3),
        "ended_at": round(ended, 3),
        "duration_s": round(ended - started, 3),
        "baseline_path": str(baseline_path.as_posix()),
        "generated_baseline_path": str(generated_baseline_path.as_posix()),
        "audit_report_path": str(audit_report_path.as_posix()),
        "audit_ok": audit_ok,
        "audit_return_code": int(audit_run.returncode),
        "audit_stderr_tail": str(audit_run.stderr or "")[-1200:],
        "audit_stdout_tail": str(audit_run.stdout or "")[-1200:],
        "previous_levels": previous_levels,
        "generated_levels": generated_levels,
        "regressions": regressions,
        "allow_regression": bool(args.allow_regression),
        "reason": reason,
        "guard_ok": guard_ok,
        "guard_reason": guard_reason,
    }
    out_default = out_dir / f"dependency_baseline_refresh_{ts}.json"
    out_path = Path(str(args.out or out_default))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
