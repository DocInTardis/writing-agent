#!/usr/bin/env python3
"""Correlation Trace Guard command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _latest_report(pattern: str) -> Path | None:
    rows = sorted(Path(".").glob(pattern), key=lambda p: p.stat().st_mtime if p.exists() else 0.0)
    if not rows:
        return None
    return rows[-1]


def _extract_correlation(raw: dict[str, Any]) -> dict[str, str]:
    node = raw if isinstance(raw, dict) else {}
    corr = node.get("correlation") if isinstance(node.get("correlation"), dict) else {}
    incident = node.get("incident") if isinstance(node.get("incident"), dict) else {}
    observed = node.get("observed") if isinstance(node.get("observed"), dict) else {}
    last_event = observed.get("last_event") if isinstance(observed.get("last_event"), dict) else {}
    correlation_id = str(
        corr.get("correlation_id")
        or incident.get("correlation_id")
        or last_event.get("correlation_id")
        or ""
    ).strip()
    release_candidate_id = str(
        corr.get("release_candidate_id")
        or incident.get("release_candidate_id")
        or last_event.get("release_candidate_id")
        or ""
    ).strip()
    if not release_candidate_id and correlation_id:
        release_candidate_id = correlation_id
    if not correlation_id and release_candidate_id:
        correlation_id = release_candidate_id
    return {
        "correlation_id": correlation_id,
        "release_candidate_id": release_candidate_id,
    }


def _check_row(*, check_id: str, ok: bool, value: Any, expect: str, mode: str = "enforce") -> dict[str, Any]:
    return {
        "id": str(check_id),
        "ok": bool(ok),
        "value": value,
        "expect": str(expect),
        "mode": str(mode or "enforce"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate correlation IDs across rollout/alert/incident artifacts.")
    parser.add_argument("--rollout-report", default="")
    parser.add_argument("--alert-report", default="")
    parser.add_argument("--incident-report", default="")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    started = time.time()
    checks: list[dict[str, Any]] = []

    rollout_path = (
        Path(str(args.rollout_report))
        if str(args.rollout_report).strip()
        else _latest_report(".data/out/release_rollout_executor_*.json")
    )
    alert_path = (
        Path(str(args.alert_report))
        if str(args.alert_report).strip()
        else _latest_report(".data/out/alert_escalation_*.json")
    )
    incident_path = (
        Path(str(args.incident_report))
        if str(args.incident_report).strip()
        else _latest_report(".data/out/incident_report_[0-9]*.json")
    )

    rollout_raw = _load_json(rollout_path) if isinstance(rollout_path, Path) else {}
    alert_raw = _load_json(alert_path) if isinstance(alert_path, Path) else {}
    incident_raw = _load_json(incident_path) if isinstance(incident_path, Path) else {}

    checks.append(
        _check_row(
            check_id="rollout_report_loaded",
            ok=isinstance(rollout_path, Path) and bool(rollout_raw),
            value=rollout_path.as_posix() if isinstance(rollout_path, Path) else "",
            expect="rollout executor report exists",
            mode="warn",
        )
    )
    checks.append(
        _check_row(
            check_id="alert_report_loaded",
            ok=isinstance(alert_path, Path) and bool(alert_raw),
            value=alert_path.as_posix() if isinstance(alert_path, Path) else "",
            expect="alert escalation report exists",
            mode="warn",
        )
    )
    checks.append(
        _check_row(
            check_id="incident_report_loaded",
            ok=isinstance(incident_path, Path) and bool(incident_raw),
            value=incident_path.as_posix() if isinstance(incident_path, Path) else "",
            expect="incident report exists",
            mode="warn",
        )
    )

    rollout_corr = _extract_correlation(rollout_raw)
    alert_corr = _extract_correlation(alert_raw)
    incident_corr = _extract_correlation(incident_raw)

    checks.append(
        _check_row(
            check_id="rollout_correlation_id_present",
            ok=bool(rollout_corr.get("correlation_id")),
            value=rollout_corr,
            expect="rollout report should contain correlation_id",
            mode="enforce" if bool(args.strict) else "warn",
        )
    )
    checks.append(
        _check_row(
            check_id="rollout_release_candidate_id_present",
            ok=bool(rollout_corr.get("release_candidate_id")),
            value=rollout_corr,
            expect="rollout report should contain release_candidate_id",
            mode="enforce" if bool(args.strict) else "warn",
        )
    )

    correlation_values = [
        value
        for value in [
            rollout_corr.get("correlation_id"),
            alert_corr.get("correlation_id"),
            incident_corr.get("correlation_id"),
        ]
        if str(value or "").strip()
    ]
    release_candidate_values = [
        value
        for value in [
            rollout_corr.get("release_candidate_id"),
            alert_corr.get("release_candidate_id"),
            incident_corr.get("release_candidate_id"),
        ]
        if str(value or "").strip()
    ]

    checks.append(
        _check_row(
            check_id="correlation_id_consistent",
            ok=(len(set(correlation_values)) <= 1),
            value={"values": correlation_values},
            expect="correlation_id values should match across available artifacts",
            mode="enforce" if bool(args.strict and len(correlation_values) >= 2) else "warn",
        )
    )
    checks.append(
        _check_row(
            check_id="release_candidate_id_consistent",
            ok=(len(set(release_candidate_values)) <= 1),
            value={"values": release_candidate_values},
            expect="release_candidate_id values should match across available artifacts",
            mode="enforce" if bool(args.strict and len(release_candidate_values) >= 2) else "warn",
        )
    )

    enforce_rows = [row for row in checks if str(row.get("mode") or "enforce") == "enforce"]
    ok = all(bool(row.get("ok")) for row in enforce_rows)
    ended = time.time()
    report = {
        "ok": bool(ok),
        "started_at": round(started, 3),
        "ended_at": round(ended, 3),
        "duration_s": round(ended - started, 3),
        "strict": bool(args.strict),
        "paths": {
            "rollout_report": rollout_path.as_posix() if isinstance(rollout_path, Path) else "",
            "alert_report": alert_path.as_posix() if isinstance(alert_path, Path) else "",
            "incident_report": incident_path.as_posix() if isinstance(incident_path, Path) else "",
        },
        "correlation": {
            "rollout": rollout_corr,
            "alert": alert_corr,
            "incident": incident_corr,
        },
        "checks": checks,
    }
    out_default = Path(".data/out") / f"correlation_trace_guard_{int(ended)}.json"
    out_path = Path(str(args.out or out_default))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report.get("ok")) else 2


if __name__ == "__main__":
    raise SystemExit(main())

