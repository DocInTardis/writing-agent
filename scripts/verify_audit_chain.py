#!/usr/bin/env python3
"""Verify Audit Chain command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import time
from pathlib import Path
from typing import Any

try:
    from scripts import audit_chain
except Exception:
    _AUDIT_CHAIN_PATH = Path(__file__).with_name("audit_chain.py")
    _AUDIT_SPEC = importlib.util.spec_from_file_location("audit_chain", _AUDIT_CHAIN_PATH)
    if _AUDIT_SPEC is None or _AUDIT_SPEC.loader is None:
        raise
    audit_chain = importlib.util.module_from_spec(_AUDIT_SPEC)
    _AUDIT_SPEC.loader.exec_module(audit_chain)


def _check_row(*, check_id: str, ok: bool, value: Any, expect: str, mode: str = "enforce") -> dict[str, Any]:
    return {
        "id": str(check_id),
        "ok": bool(ok),
        "value": value,
        "expect": str(expect),
        "mode": str(mode or "enforce"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify append-only audit chain integrity and continuity.")
    parser.add_argument("--log", default="")
    parser.add_argument("--state-file", default="")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--require-log", action="store_true")
    parser.add_argument("--require-state", action="store_true")
    parser.add_argument("--max-age-s", type=float, default=0.0)
    parser.add_argument("--no-write-state", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    started = time.time()
    log_path = audit_chain.resolve_log_path(str(args.log or ""))
    state_path = audit_chain.resolve_state_path(str(args.state_file or ""))
    loaded_state = audit_chain.load_state(state_path)

    verification = audit_chain.verify_chain(
        log_path=log_path,
        state=loaded_state,
        require_log=bool(args.require_log),
        require_state=bool(args.require_state),
        strict=bool(args.strict),
        max_age_s=max(0.0, float(args.max_age_s)),
    )
    checks = list(verification.get("checks") if isinstance(verification.get("checks"), list) else [])

    state_written = False
    state_write_error = ""
    if bool(verification.get("ok")) and (not bool(args.no_write_state)):
        try:
            snapshot = audit_chain.build_state_snapshot(log_path=log_path, verification=verification)
            audit_chain.write_state(state_path, snapshot)
            state_written = True
        except Exception as exc:
            state_write_error = f"{exc.__class__.__name__}: {exc}"
    checks.append(
        _check_row(
            check_id="audit_state_write_ok",
            ok=(not state_write_error) or (not bool(args.strict)),
            value={
                "attempted": (not bool(args.no_write_state)),
                "written": state_written,
                "error": state_write_error,
            },
            expect="state snapshot should be writable in strict mode",
            mode="enforce",
        )
    )

    enforce_rows = [row for row in checks if str(row.get("mode") or "enforce") == "enforce"]
    ok = bool(verification.get("ok")) and all(bool(row.get("ok")) for row in enforce_rows)

    ended = time.time()
    report = {
        "ok": bool(ok),
        "started_at": round(started, 3),
        "ended_at": round(ended, 3),
        "duration_s": round(ended - started, 3),
        "log_path": log_path.as_posix(),
        "state_file": state_path.as_posix(),
        "state_loaded": bool(loaded_state),
        "state_written": bool(state_written),
        "strict": bool(args.strict),
        "require_log": bool(args.require_log),
        "require_state": bool(args.require_state),
        "max_age_s": max(0.0, float(args.max_age_s)),
        "entry_count": int(verification.get("entry_count") or 0),
        "last_hash": str(verification.get("last_hash") or ""),
        "last_ts": float(verification.get("last_ts") or 0.0),
        "checks": checks,
    }
    out_default = Path(".data/out") / f"audit_chain_verify_{int(ended)}.json"
    out_path = Path(str(args.out or out_default))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report.get("ok")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
