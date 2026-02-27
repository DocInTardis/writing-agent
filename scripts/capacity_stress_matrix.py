#!/usr/bin/env python3
"""Capacity Stress Matrix command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


@dataclass
class StepResult:
    id: str
    ok: bool
    return_code: int
    duration_s: float
    command: list[str]
    cwd: str


def _run_cmd(*, step_id: str, cmd: list[str], cwd: str = ".", env: dict[str, str] | None = None) -> StepResult:
    started = time.perf_counter()
    merged_env = os.environ.copy()
    merged_env["PYTHONPATH"] = "."
    if env:
        merged_env.update({str(k): str(v) for k, v in env.items()})
    proc = subprocess.run(cmd, cwd=cwd, env=merged_env)
    elapsed = time.perf_counter() - started
    return StepResult(
        id=step_id,
        ok=int(proc.returncode) == 0,
        return_code=int(proc.returncode),
        duration_s=round(float(elapsed), 3),
        command=list(cmd),
        cwd=str(cwd),
    )


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


def _wait_app_ready(base_url: str, *, timeout_s: float) -> None:
    deadline = time.time() + max(3.0, float(timeout_s))
    url = f"{base_url.rstrip('/')}/api/metrics/citation_verify"
    while time.time() < deadline:
        try:
            req = Request(url, method="GET")
            with urlopen(req, timeout=1.5) as resp:
                status = int(getattr(resp, "status", 0) or resp.getcode() or 0)
            if 200 <= status < 300:
                return
        except Exception:
            pass
        time.sleep(0.25)
    raise RuntimeError("temp_app_not_ready")


def _profile_catalog(*, quick: bool) -> dict[str, dict[str, Any]]:
    if quick:
        return {
            "peak": {
                "requests": 220,
                "concurrency": 16,
                "timeout_s": 6.0,
                "min_success_rate": 0.99,
                "max_p95_ms": 2200.0,
                "max_degraded_rate": 0.05,
            },
            "burst": {
                "requests": 360,
                "concurrency": 24,
                "timeout_s": 6.0,
                "min_success_rate": 0.985,
                "max_p95_ms": 2500.0,
                "max_degraded_rate": 0.08,
            },
            "jitter": {
                "requests": 200,
                "concurrency": 20,
                "timeout_s": 1.8,
                "min_success_rate": 0.94,
                "max_p95_ms": 2800.0,
                "max_degraded_rate": 0.15,
            },
        }
    return {
        "peak": {
            "requests": 900,
            "concurrency": 48,
            "timeout_s": 6.0,
            "min_success_rate": 0.99,
            "max_p95_ms": 1800.0,
            "max_degraded_rate": 0.05,
        },
        "burst": {
            "requests": 1400,
            "concurrency": 64,
            "timeout_s": 6.0,
            "min_success_rate": 0.98,
            "max_p95_ms": 2200.0,
            "max_degraded_rate": 0.08,
        },
        "jitter": {
            "requests": 800,
            "concurrency": 56,
            "timeout_s": 2.2,
            "min_success_rate": 0.9,
            "max_p95_ms": 3000.0,
            "max_degraded_rate": 0.18,
        },
    }


def _parse_profiles(text: str, available: dict[str, dict[str, Any]]) -> list[str]:
    raw = [seg.strip().lower() for seg in str(text or "").split(",")]
    rows = [item for item in raw if item in available]
    if rows:
        return rows
    return list(available.keys())


def main() -> int:
    parser = argparse.ArgumentParser(description="Run capacity stress profile matrix and emit summarized report.")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--profiles", default="peak,burst,jitter")
    parser.add_argument("--include-soak", action="store_true")
    parser.add_argument("--soak-duration-s", type=float, default=0.0)
    parser.add_argument("--soak-interval-s", type=float, default=30.0)
    parser.add_argument("--soak-requests-per-window", type=int, default=24)
    parser.add_argument("--soak-concurrency", type=int, default=8)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18160)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    started = time.time()
    checks: list[dict[str, Any]] = []
    steps: list[StepResult] = []

    profile_map = _profile_catalog(quick=bool(args.quick))
    profile_ids = _parse_profiles(str(args.profiles or ""), profile_map)
    selected_profiles = [profile_map[item] | {"id": item} for item in profile_ids]
    checks.append(
        {
            "id": "profiles_selected",
            "ok": len(selected_profiles) > 0,
            "value": profile_ids,
            "expect": "at least one valid stress profile selected",
            "mode": "enforce",
        }
    )

    app_proc: subprocess.Popen | None = None
    ts = int(started)
    load_rows: list[dict[str, Any]] = []
    soak_row: dict[str, Any] = {}
    try:
        app_env = os.environ.copy()
        app_env["WRITING_AGENT_USE_OLLAMA"] = "0"
        app_env["WRITING_AGENT_CITATION_VERIFY_ALERTS"] = "1"
        app_env["WRITING_AGENT_CITATION_VERIFY_ALERT_NOTIFY"] = "0"
        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "writing_agent.web.app_v2:app",
            "--host",
            str(args.host),
            "--port",
            str(int(args.port)),
        ]
        app_proc = subprocess.Popen(cmd, env=app_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base_url = f"http://{str(args.host)}:{int(args.port)}"
        _wait_app_ready(base_url, timeout_s=20.0)

        for profile in selected_profiles:
            profile_id = str(profile.get("id") or "profile")
            load_out = Path(".data/out") / f"citation_verify_load_probe_stress_{profile_id}_{ts}.json"
            load_cmd = [
                sys.executable,
                "scripts/citation_verify_load_probe.py",
                "--base-url",
                base_url,
                "--requests",
                str(int(profile.get("requests") or 1)),
                "--concurrency",
                str(int(profile.get("concurrency") or 1)),
                "--timeout-s",
                str(float(profile.get("timeout_s") or 6.0)),
                "--min-success-rate",
                str(float(profile.get("min_success_rate") or 0.99)),
                "--max-p95-ms",
                str(float(profile.get("max_p95_ms") or 2000.0)),
                "--max-degraded-rate",
                str(float(profile.get("max_degraded_rate") or 0.05)),
                "--out",
                load_out.as_posix(),
            ]
            step = _run_cmd(step_id=f"load_profile_{profile_id}", cmd=load_cmd)
            steps.append(step)
            load_report = _load_json(load_out)
            load_rows.append(
                {
                    "id": profile_id,
                    "ok": bool(step.ok),
                    "return_code": int(step.return_code),
                    "duration_s": float(step.duration_s),
                    "report_path": load_out.as_posix(),
                    "report_ok": bool(isinstance(load_report, dict) and bool(load_report.get("ok"))),
                    "summary": (load_report.get("summary") if isinstance(load_report, dict) else {}),
                }
            )

        if bool(args.include_soak):
            soak_duration = float(args.soak_duration_s) if float(args.soak_duration_s) > 0 else (300.0 if bool(args.quick) else 1800.0)
            soak_out = Path(".data/out") / f"citation_verify_soak_stress_{ts}.json"
            soak_cmd = [
                sys.executable,
                "scripts/citation_verify_soak.py",
                "--base-url",
                base_url,
                "--duration-s",
                str(max(5.0, soak_duration)),
                "--interval-s",
                str(max(2.0, float(args.soak_interval_s))),
                "--requests-per-window",
                str(max(1, int(args.soak_requests_per_window))),
                "--concurrency",
                str(max(1, int(args.soak_concurrency))),
                "--timeout-s",
                "6",
                "--min-overall-success-rate",
                "0.99" if bool(args.quick) else "0.995",
                "--max-overall-p95-ms",
                "2500" if bool(args.quick) else "2000",
                "--max-overall-degraded-rate",
                "0.08" if bool(args.quick) else "0.05",
                "--label",
                "capacity-stress-matrix",
                "--out",
                soak_out.as_posix(),
            ]
            soak_step = _run_cmd(step_id="stress_soak", cmd=soak_cmd)
            steps.append(soak_step)
            soak_report = _load_json(soak_out)
            soak_row = {
                "ok": bool(soak_step.ok),
                "return_code": int(soak_step.return_code),
                "duration_s": float(soak_step.duration_s),
                "report_path": soak_out.as_posix(),
                "report_ok": bool(isinstance(soak_report, dict) and bool(soak_report.get("ok"))),
                "aggregate": (soak_report.get("aggregate") if isinstance(soak_report, dict) else {}),
            }
    finally:
        if app_proc is not None and app_proc.poll() is None:
            try:
                app_proc.terminate()
            except Exception:
                pass
            try:
                app_proc.wait(timeout=5.0)
            except Exception:
                try:
                    app_proc.kill()
                except Exception:
                    pass

    profile_pass = sum(1 for row in load_rows if bool(row.get("ok")) and bool(row.get("report_ok")))
    profile_fail = max(0, len(load_rows) - profile_pass)
    checks.append(
        {
            "id": "stress_profiles_all_pass",
            "ok": profile_fail == 0,
            "value": {"pass": profile_pass, "fail": profile_fail, "total": len(load_rows)},
            "expect": "all stress profiles pass",
            "mode": "enforce",
        }
    )
    if bool(args.include_soak):
        checks.append(
            {
                "id": "stress_soak_pass",
                "ok": bool(soak_row.get("ok")) and bool(soak_row.get("report_ok")),
                "value": {"ok": bool(soak_row.get("ok")), "report_ok": bool(soak_row.get("report_ok"))},
                "expect": "soak profile passes",
                "mode": "enforce",
            }
        )

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
        "target": {
            "host": str(args.host),
            "port": int(args.port),
            "base_url": f"http://{str(args.host)}:{int(args.port)}",
        },
        "profiles": load_rows,
        "soak": soak_row,
        "checks": checks,
        "summary": {
            "profiles_total": len(load_rows),
            "profiles_pass": profile_pass,
            "profiles_fail": profile_fail,
            "include_soak": bool(args.include_soak),
            "soak_pass": bool(soak_row.get("ok")) and bool(soak_row.get("report_ok")) if bool(args.include_soak) else None,
        },
        "steps": [
            {
                "id": step.id,
                "ok": step.ok,
                "return_code": step.return_code,
                "duration_s": step.duration_s,
                "command": step.command,
                "cwd": step.cwd,
            }
            for step in steps
        ],
    }

    out_default = Path(".data/out") / f"capacity_stress_matrix_{int(ended)}.json"
    out_path = Path(str(args.out or out_default))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if bool(args.strict):
        return 0 if bool(ok) else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
