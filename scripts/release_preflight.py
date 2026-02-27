#!/usr/bin/env python3
"""Release Preflight command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

_TRUTHY_VALUES = {"1", "true", "yes", "on"}


@dataclass
class StepResult:
    id: str
    ok: bool
    return_code: int
    duration_s: float
    command: list[str]
    cwd: str


def _run_cmd(
    *,
    step_id: str,
    cmd: list[str],
    cwd: str = ".",
    env: dict[str, str] | None = None,
) -> StepResult:
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


def _npm_cmd(args: list[str]) -> list[str]:
    if os.name == "nt":
        return ["cmd", "/c", "npm", *args]
    return ["npm", *args]


def _env_flag(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in _TRUTHY_VALUES


def _env_float(name: str, default: float) -> float:
    raw = str(os.environ.get(name, "")).strip()
    if not raw:
        return float(default)
    try:
        return float(raw)
    except Exception:
        return float(default)


def _env_int(name: str, default: int) -> int:
    raw = str(os.environ.get(name, "")).strip()
    if not raw:
        return int(default)
    try:
        return int(raw)
    except Exception:
        return int(default)


def _env_text(name: str, default: str = "") -> str:
    raw = str(os.environ.get(name, "")).strip()
    if raw:
        return raw
    return str(default or "")


def _infer_release_tier(*, release_tier: str, release_branch: str, runtime_env: str) -> str:
    tier = str(release_tier or "").strip().lower()
    if tier:
        return tier

    branch = str(release_branch or "").strip().lower()
    if branch in {"main", "master"} or branch.startswith("release/") or branch.startswith("hotfix/"):
        return "prod"
    if branch.startswith("staging/") or branch.startswith("stage/"):
        return "staging"
    if branch:
        return "dev"

    env_name = str(runtime_env or "").strip().lower()
    if env_name in {"prod", "production"}:
        return "prod"
    if env_name in {"staging", "stage"}:
        return "staging"
    if env_name in {"dev", "development", "local", "test", "ci"}:
        return "dev"
    return ""


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


def _run_load_probe_with_temp_server(
    *,
    host: str,
    port: int,
    quick: bool,
) -> StepResult:
    app_proc: subprocess.Popen | None = None
    try:
        env = os.environ.copy()
        env["WRITING_AGENT_USE_OLLAMA"] = "0"
        env["WRITING_AGENT_CITATION_VERIFY_ALERTS"] = "1"
        env["WRITING_AGENT_CITATION_VERIFY_ALERT_NOTIFY"] = "0"
        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "writing_agent.web.app_v2:app",
            "--host",
            host,
            "--port",
            str(int(port)),
        ]
        app_proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base_url = f"http://{host}:{int(port)}"
        _wait_app_ready(base_url, timeout_s=15.0)
        requests = "120" if quick else "320"
        concurrency = "10" if quick else "24"
        max_p95 = "2200" if quick else "1500"
        run_cmd = [
            sys.executable,
            "scripts/citation_verify_load_probe.py",
            "--base-url",
            base_url,
            "--requests",
            requests,
            "--concurrency",
            concurrency,
            "--timeout-s",
            "6",
            "--min-success-rate",
            "0.99",
            "--max-p95-ms",
            max_p95,
            "--max-degraded-rate",
            "0.05",
        ]
        return _run_cmd(step_id="citation_metrics_load_probe", cmd=run_cmd)
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


def _run_soak_with_temp_server(
    *,
    host: str,
    port: int,
    quick: bool,
    duration_s: float,
    interval_s: float,
    requests_per_window: int,
    concurrency: int,
    timeout_s: float,
) -> StepResult:
    app_proc: subprocess.Popen | None = None
    try:
        env = os.environ.copy()
        env["WRITING_AGENT_USE_OLLAMA"] = "0"
        env["WRITING_AGENT_CITATION_VERIFY_ALERTS"] = "1"
        env["WRITING_AGENT_CITATION_VERIFY_ALERT_NOTIFY"] = "0"
        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "writing_agent.web.app_v2:app",
            "--host",
            host,
            "--port",
            str(int(port)),
        ]
        app_proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base_url = f"http://{host}:{int(port)}"
        _wait_app_ready(base_url, timeout_s=20.0)
        run_cmd = [
            sys.executable,
            "scripts/citation_verify_soak.py",
            "--base-url",
            base_url,
            "--duration-s",
            str(max(5.0, float(duration_s))),
            "--interval-s",
            str(max(2.0, float(interval_s))),
            "--requests-per-window",
            str(max(1, int(requests_per_window))),
            "--concurrency",
            str(max(1, int(concurrency))),
            "--timeout-s",
            str(max(0.2, float(timeout_s))),
            "--min-overall-success-rate",
            "0.99",
            "--max-overall-p95-ms",
            "2500" if quick else "2000",
            "--max-overall-degraded-rate",
            "0.08" if quick else "0.05",
            "--label",
            "release-preflight",
        ]
        return _run_cmd(step_id="citation_metrics_soak_probe", cmd=run_cmd)
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


def _resolve_soak_settings(args: argparse.Namespace) -> tuple[float, float, int, int]:
    duration_s = float(args.soak_duration_s if args.soak_duration_s is not None else 0.0)
    if duration_s <= 0:
        duration_s = _env_float("WA_PREFLIGHT_SOAK_DURATION_S", 0.0)

    if args.soak_interval_s is None:
        interval_s = _env_float("WA_PREFLIGHT_SOAK_INTERVAL_S", 30.0)
    else:
        interval_s = float(args.soak_interval_s)

    if args.soak_requests_per_window is None:
        requests_per_window = _env_int("WA_PREFLIGHT_SOAK_REQUESTS_PER_WINDOW", 24)
    else:
        requests_per_window = int(args.soak_requests_per_window)

    if args.soak_concurrency is None:
        concurrency = _env_int("WA_PREFLIGHT_SOAK_CONCURRENCY", 8)
    else:
        concurrency = int(args.soak_concurrency)

    return (
        max(0.0, float(duration_s)),
        max(2.0, float(interval_s)),
        max(1, int(requests_per_window)),
        max(1, int(concurrency)),
    )


def main(argv: list[str] | None = None) -> int:
    try:
        from scripts import release_preflight_runtime as _runtime
    except Exception:
        runtime_path = Path(__file__).with_name("release_preflight_runtime.py")
        spec = importlib.util.spec_from_file_location("release_preflight_runtime", runtime_path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"failed_to_load_runtime:{runtime_path}")
        _runtime = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_runtime)  # type: ignore[union-attr]

    _runtime.bind(globals())
    return _runtime.main(argv)


def _finish(started: float, steps: list[StepResult], out_override: str) -> int:
    ended = time.time()
    report = {
        "ok": all(step.ok for step in steps),
        "started_at": round(started, 3),
        "ended_at": round(ended, 3),
        "duration_s": round(ended - started, 3),
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
    default_out = Path(".data/out") / f"release_preflight_{int(ended)}.json"
    out_path = Path(str(out_override or default_out))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report.get("ok")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
