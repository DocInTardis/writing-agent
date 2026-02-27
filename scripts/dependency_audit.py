#!/usr/bin/env python3
"""Dependency Audit command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


def _npm_cmd(args: list[str]) -> list[str]:
    if os.name == "nt":
        return ["cmd", "/c", "npm", *args]
    return ["npm", *args]


def _run(cmd: list[str], *, cwd: str = ".") -> dict[str, Any]:
    started = time.perf_counter()
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    elapsed = time.perf_counter() - started
    return {
        "cmd": cmd,
        "cwd": cwd,
        "code": int(proc.returncode),
        "stdout": str(proc.stdout or ""),
        "stderr": str(proc.stderr or ""),
        "duration_s": round(float(elapsed), 3),
    }


def _extract_json(text: str) -> dict[str, Any] | list[Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if isinstance(data, (dict, list)):
            return data
    except Exception:
        pass
    # Try to recover from prefixed logs by trimming to first/last json token.
    left_obj = raw.find("{")
    right_obj = raw.rfind("}")
    if left_obj >= 0 and right_obj > left_obj:
        chunk = raw[left_obj : right_obj + 1]
        try:
            data = json.loads(chunk)
            if isinstance(data, (dict, list)):
                return data
        except Exception:
            pass
    left_arr = raw.find("[")
    right_arr = raw.rfind("]")
    if left_arr >= 0 and right_arr > left_arr:
        chunk = raw[left_arr : right_arr + 1]
        try:
            data = json.loads(chunk)
            if isinstance(data, (dict, list)):
                return data
        except Exception:
            pass
    return None


def _empty_levels() -> dict[str, int]:
    return {"info": 0, "low": 0, "moderate": 0, "high": 0, "critical": 0, "unknown": 0, "total": 0}


def _normalize_level(raw: Any) -> str:
    v = str(raw or "").strip().lower()
    if v in {"info", "low", "moderate", "high", "critical"}:
        return v
    return "unknown"


def _npm_levels(data: dict[str, Any] | None) -> dict[str, int]:
    out = _empty_levels()
    row = data if isinstance(data, dict) else {}
    meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    vul = meta.get("vulnerabilities") if isinstance(meta.get("vulnerabilities"), dict) else {}
    if vul:
        for key in ("info", "low", "moderate", "high", "critical"):
            out[key] = int(vul.get(key) or 0)
        out["total"] = int(sum(out[k] for k in ("info", "low", "moderate", "high", "critical")))
        return out
    details = row.get("vulnerabilities") if isinstance(row.get("vulnerabilities"), dict) else {}
    for _, item in details.items():
        if not isinstance(item, dict):
            continue
        lvl = _normalize_level(item.get("severity"))
        out[lvl] += 1
        out["total"] += 1
    return out


def _pip_levels(data: dict[str, Any] | list[Any] | None) -> dict[str, int]:
    out = _empty_levels()
    deps: list[dict[str, Any]] = []
    if isinstance(data, dict):
        if isinstance(data.get("dependencies"), list):
            deps = [row for row in data.get("dependencies") if isinstance(row, dict)]
        elif isinstance(data.get("results"), list):
            deps = [row for row in data.get("results") if isinstance(row, dict)]
    elif isinstance(data, list):
        deps = [row for row in data if isinstance(row, dict)]

    for dep in deps:
        vulns = dep.get("vulns") if isinstance(dep.get("vulns"), list) else []
        for v in vulns:
            if not isinstance(v, dict):
                continue
            lvl = _normalize_level(v.get("severity"))
            out[lvl] += 1
            out["total"] += 1
    return out


def _ok(condition: bool, *, check_id: str, value: Any, expect: str, mode: str = "enforce") -> dict[str, Any]:
    return {"id": check_id, "ok": bool(condition), "value": value, "expect": expect, "mode": mode}


def _load_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(raw, dict):
        return raw
    return None


def _baseline_levels(raw: dict[str, Any] | None) -> dict[str, dict[str, int]]:
    data = raw if isinstance(raw, dict) else {}
    levels = data.get("levels") if isinstance(data.get("levels"), dict) else {}
    out = {
        "npm_prod": _empty_levels(),
        "npm_dev": _empty_levels(),
        "pip": _empty_levels(),
    }
    for key in ("npm_prod", "npm_dev", "pip"):
        row = levels.get(key) if isinstance(levels.get(key), dict) else {}
        for sev in ("info", "low", "moderate", "high", "critical", "unknown", "total"):
            out[key][sev] = int(row.get(sev) or 0)
    return out


def _regression_rows(
    *,
    current: dict[str, dict[str, int]],
    baseline: dict[str, dict[str, int]],
    mode: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in ("npm_prod", "npm_dev", "pip"):
        curr = current.get(key) or _empty_levels()
        base = baseline.get(key) or _empty_levels()
        for sev in ("critical", "high", "moderate", "total"):
            cid = f"{key}_{sev}_regression"
            now = int(curr.get(sev) or 0)
            old = int(base.get(sev) or 0)
            rows.append(
                _ok(
                    now <= old,
                    check_id=cid,
                    value={"current": now, "baseline": old, "delta": now - old},
                    expect="current<=baseline",
                    mode=mode,
                )
            )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Dependency security audit (npm + pip-audit) with policy thresholds.")
    parser.add_argument("--frontend-dir", default="writing_agent/web/frontend_svelte")
    parser.add_argument("--requirements", default="requirements.txt")
    parser.add_argument("--skip-npm", action="store_true")
    parser.add_argument("--skip-pip", action="store_true")
    parser.add_argument("--require-pip-audit", action="store_true")
    parser.add_argument("--baseline", default="")
    parser.add_argument("--write-baseline", default="")
    parser.add_argument("--fail-on-regression", action="store_true")
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
    checks: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "ok": False,
        "started_at": round(started, 3),
        "npm": {"skipped": bool(args.skip_npm)},
        "pip": {"skipped": bool(args.skip_pip)},
        "baseline": {"enabled": bool(str(args.baseline or "").strip()), "path": str(args.baseline or "").strip()},
        "checks": checks,
    }
    current_levels = {
        "npm_prod": _empty_levels(),
        "npm_dev": _empty_levels(),
        "pip": _empty_levels(),
    }

    if not args.skip_npm:
        frontend_dir = str(args.frontend_dir)
        prod_run = _run(_npm_cmd(["--prefix", frontend_dir, "audit", "--json", "--omit=optional", "--omit=dev"]))
        dev_run = _run(_npm_cmd(["--prefix", frontend_dir, "audit", "--json", "--omit=optional"]))
        prod_json = _extract_json(prod_run.get("stdout") or prod_run.get("stderr") or "")
        dev_json = _extract_json(dev_run.get("stdout") or dev_run.get("stderr") or "")
        prod_levels = _npm_levels(prod_json if isinstance(prod_json, dict) else None)
        dev_levels = _npm_levels(dev_json if isinstance(dev_json, dict) else None)
        current_levels["npm_prod"] = dict(prod_levels)
        current_levels["npm_dev"] = dict(dev_levels)
        report["npm"] = {
            "prod": {"run": {k: v for k, v in prod_run.items() if k not in {"stdout", "stderr"}}, "levels": prod_levels},
            "dev": {"run": {k: v for k, v in dev_run.items() if k not in {"stdout", "stderr"}}, "levels": dev_levels},
        }
        checks.append(
            _ok(
                prod_levels["critical"] <= int(args.max_npm_prod_critical),
                check_id="npm_prod_critical",
                value=prod_levels["critical"],
                expect=f"<={int(args.max_npm_prod_critical)}",
            )
        )
        checks.append(
            _ok(
                prod_levels["high"] <= int(args.max_npm_prod_high),
                check_id="npm_prod_high",
                value=prod_levels["high"],
                expect=f"<={int(args.max_npm_prod_high)}",
            )
        )
        checks.append(
            _ok(
                prod_levels["moderate"] <= int(args.max_npm_prod_moderate),
                check_id="npm_prod_moderate",
                value=prod_levels["moderate"],
                expect=f"<={int(args.max_npm_prod_moderate)}",
            )
        )
        checks.append(
            _ok(
                dev_levels["critical"] <= int(args.max_npm_dev_critical),
                check_id="npm_dev_critical",
                value=dev_levels["critical"],
                expect=f"<={int(args.max_npm_dev_critical)}",
            )
        )
        checks.append(
            _ok(
                dev_levels["high"] <= int(args.max_npm_dev_high),
                check_id="npm_dev_high",
                value=dev_levels["high"],
                expect=f"<={int(args.max_npm_dev_high)}",
            )
        )
        checks.append(
            _ok(
                dev_levels["moderate"] <= int(args.max_npm_dev_moderate),
                check_id="npm_dev_moderate",
                value=dev_levels["moderate"],
                expect=f"<={int(args.max_npm_dev_moderate)}",
            )
        )

    if not args.skip_pip:
        req = str(args.requirements)
        pip_run = _run([sys.executable, "-m", "pip_audit", "-r", req, "--format", "json"])
        pip_json = _extract_json(pip_run.get("stdout") or "")
        pip_missing = False
        if pip_run["code"] != 0 and not pip_json:
            err_text = f"{pip_run.get('stdout','')} {pip_run.get('stderr','')}".lower()
            pip_missing = "no module named" in err_text and "pip_audit" in err_text
        pip_levels = _pip_levels(pip_json)
        current_levels["pip"] = dict(pip_levels)
        report["pip"] = {
            "run": {k: v for k, v in pip_run.items() if k not in {"stdout", "stderr"}},
            "levels": pip_levels,
            "tool_missing": pip_missing,
        }
        if pip_missing and not args.require_pip_audit:
            checks.append(
                _ok(
                    True,
                    check_id="pip_audit_tool_present",
                    value=False,
                    expect="tool present or allowed missing",
                    mode="warn",
                )
            )
        elif pip_missing and args.require_pip_audit:
            checks.append(
                _ok(
                    False,
                    check_id="pip_audit_tool_present",
                    value=False,
                    expect="tool present",
                )
            )
        else:
            checks.append(
                _ok(
                    pip_levels["total"] <= int(args.max_pip_total),
                    check_id="pip_total_vulns",
                    value=pip_levels["total"],
                    expect=f"<={int(args.max_pip_total)}",
                )
            )

    baseline_path = Path(str(args.baseline or "").strip()) if str(args.baseline or "").strip() else None
    if baseline_path is not None:
        baseline_raw = _load_json_file(baseline_path)
        baseline_loaded = baseline_raw is not None
        report["baseline"]["loaded"] = bool(baseline_loaded)
        if not baseline_loaded:
            checks.append(
                _ok(
                    not bool(args.fail_on_regression),
                    check_id="baseline_loaded",
                    value=False,
                    expect="baseline file exists and is valid json",
                    mode="enforce" if bool(args.fail_on_regression) else "warn",
                )
            )
        else:
            baseline_levels = _baseline_levels(baseline_raw)
            report["baseline"]["levels"] = baseline_levels
            mode = "enforce" if bool(args.fail_on_regression) else "warn"
            checks.extend(_regression_rows(current=current_levels, baseline=baseline_levels, mode=mode))

    write_baseline_path = Path(str(args.write_baseline or "").strip()) if str(args.write_baseline or "").strip() else None
    if write_baseline_path is not None:
        out_base = {
            "version": 1,
            "generated_at": round(time.time(), 3),
            "levels": current_levels,
        }
        write_baseline_path.parent.mkdir(parents=True, exist_ok=True)
        write_baseline_path.write_text(json.dumps(out_base, ensure_ascii=False, indent=2), encoding="utf-8")
        report["baseline"]["written"] = str(write_baseline_path)

    enforce_rows = [row for row in checks if str(row.get("mode") or "enforce") == "enforce"]
    report["ok"] = all(bool(row.get("ok")) for row in enforce_rows)
    report["ended_at"] = round(time.time(), 3)
    report["duration_s"] = round(report["ended_at"] - report["started_at"], 3)  # type: ignore[operator]

    out_default = Path(".data/out") / f"dependency_audit_{int(report['ended_at'])}.json"
    out_path = Path(str(args.out or out_default))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report.get("ok")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
