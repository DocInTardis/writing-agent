#!/usr/bin/env python3
"""Generate Sbom command utility.

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
        "cmd": list(cmd),
        "cwd": str(cwd),
        "code": int(proc.returncode),
        "stdout": str(proc.stdout or ""),
        "stderr": str(proc.stderr or ""),
        "duration_s": round(float(elapsed), 3),
    }


def _extract_json(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    left = raw.find("{")
    right = raw.rfind("}")
    if left >= 0 and right > left:
        chunk = raw[left : right + 1]
        try:
            data = json.loads(chunk)
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return None


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _entry(path: Path, kind: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "path": str(path.as_posix()),
        "size": int(path.stat().st_size if path.exists() else 0),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate SBOM artifacts for Python and frontend dependencies.")
    parser.add_argument("--requirements", default="requirements.txt")
    parser.add_argument("--frontend-dir", default="writing_agent/web/frontend_svelte")
    parser.add_argument("--out-dir", default=".data/out/sbom")
    parser.add_argument("--skip-python", action="store_true")
    parser.add_argument("--skip-frontend", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    started = time.time()
    out_dir = Path(str(args.out_dir))
    out_dir.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "ok": True,
        "started_at": round(started, 3),
        "out_dir": str(out_dir.as_posix()),
        "artifacts": [],
        "steps": {},
    }
    errors: list[str] = []

    if not args.skip_python:
        run = _run([sys.executable, "-m", "pip_audit", "-r", str(args.requirements), "--format", "cyclonedx-json"])
        payload = _extract_json(str(run.get("stdout") or ""))
        if isinstance(payload, dict):
            out_path = out_dir / "python-sbom.cyclonedx.json"
            _write_json(out_path, payload)
            report["artifacts"].append(_entry(out_path, "python"))
        else:
            errors.append("python_sbom_parse_failed")
        report["steps"]["python"] = {k: v for k, v in run.items() if k not in {"stdout", "stderr"}}

    if not args.skip_frontend:
        frontend = str(args.frontend_dir)
        prod_run = _run(
            _npm_cmd(
                [
                    "--prefix",
                    frontend,
                    "sbom",
                    "--sbom-format",
                    "cyclonedx",
                    "--omit=optional",
                    "--omit=dev",
                ]
            )
        )
        prod_payload = _extract_json(str(prod_run.get("stdout") or prod_run.get("stderr") or ""))
        if isinstance(prod_payload, dict):
            out_prod = out_dir / "frontend-sbom-prod.cyclonedx.json"
            _write_json(out_prod, prod_payload)
            report["artifacts"].append(_entry(out_prod, "frontend_prod"))
        else:
            errors.append("frontend_prod_sbom_parse_failed")

        full_run = _run(
            _npm_cmd(
                [
                    "--prefix",
                    frontend,
                    "sbom",
                    "--sbom-format",
                    "cyclonedx",
                    "--omit=optional",
                ]
            )
        )
        full_payload = _extract_json(str(full_run.get("stdout") or full_run.get("stderr") or ""))
        if isinstance(full_payload, dict):
            out_full = out_dir / "frontend-sbom-full.cyclonedx.json"
            _write_json(out_full, full_payload)
            report["artifacts"].append(_entry(out_full, "frontend_full"))
        else:
            errors.append("frontend_full_sbom_parse_failed")

        report["steps"]["frontend_prod"] = {k: v for k, v in prod_run.items() if k not in {"stdout", "stderr"}}
        report["steps"]["frontend_full"] = {k: v for k, v in full_run.items() if k not in {"stdout", "stderr"}}

    manifest = {
        "generated_at": round(time.time(), 3),
        "artifacts": report["artifacts"],
    }
    manifest_path = out_dir / "sbom-manifest.json"
    _write_json(manifest_path, manifest)
    report["manifest"] = str(manifest_path.as_posix())

    report["errors"] = errors
    if errors and args.strict:
        report["ok"] = False
    if not report["artifacts"]:
        report["ok"] = False
    report["ended_at"] = round(time.time(), 3)
    report["duration_s"] = round(report["ended_at"] - report["started_at"], 3)  # type: ignore[operator]

    report_path = out_dir / f"sbom_report_{int(report['ended_at'])}.json"
    _write_json(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report.get("ok")) else 2


if __name__ == "__main__":
    raise SystemExit(main())

