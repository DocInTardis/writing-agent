#!/usr/bin/env python3
"""Sign Rollback Drill Evidence command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from typing import Any


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _latest_paths(pattern: str, *, limit: int) -> list[Path]:
    rows = sorted((Path(p) for p in glob.glob(pattern)), key=lambda p: p.stat().st_mtime if p.exists() else 0.0)
    take = max(0, int(limit))
    if take <= 0:
        return []
    return rows[-take:]


def _check_row(*, check_id: str, ok: bool, value: Any, expect: str, mode: str = "warn") -> dict[str, Any]:
    return {
        "id": str(check_id),
        "ok": bool(ok),
        "value": value,
        "expect": str(expect),
        "mode": str(mode or "warn"),
    }


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sign(payload_text: str, key: str) -> str:
    return hmac.new(str(key).encode("utf-8"), payload_text.encode("utf-8"), hashlib.sha256).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Sign rollback drill evidence reports with HMAC-SHA256.")
    parser.add_argument("--incident-drill-pattern", default=".data/out/incident_notify_drill_*.json")
    parser.add_argument("--rollback-bundle-pattern", default=".data/out/rollback_bundle_report_*.json")
    parser.add_argument("--incident-report-pattern", default=".data/out/incident_report_drill_*.json")
    parser.add_argument("--recent", type=int, default=4)
    parser.add_argument("--signing-key", default=os.environ.get("WA_ROLLBACK_DRILL_SIGNING_KEY", ""))
    parser.add_argument("--key-id", default=os.environ.get("WA_ROLLBACK_DRILL_SIGNING_KEY_ID", "default"))
    parser.add_argument("--require-key", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    started = time.time()
    mode = "enforce" if bool(args.strict) else "warn"
    checks: list[dict[str, Any]] = []

    recent = max(1, _safe_int(args.recent, 4))
    incident_paths = _latest_paths(str(args.incident_drill_pattern), limit=recent)
    rollback_paths = _latest_paths(str(args.rollback_bundle_pattern), limit=recent)
    incident_report_paths = _latest_paths(str(args.incident_report_pattern), limit=recent)

    artifacts: list[dict[str, Any]] = []
    for path in [*incident_paths, *rollback_paths, *incident_report_paths]:
        if not path.exists() or not path.is_file():
            continue
        stat = path.stat()
        artifacts.append(
            {
                "path": path.as_posix(),
                "size": int(stat.st_size),
                "mtime": round(float(stat.st_mtime), 3),
                "sha256": _sha256(path),
            }
        )

    checks.append(
        _check_row(
            check_id="drill_evidence_artifacts_found",
            ok=len(artifacts) > 0,
            value={"artifacts": len(artifacts), "recent": recent},
            expect="at least one drill evidence artifact exists",
            mode=mode,
        )
    )
    checks.append(
        _check_row(
            check_id="drill_evidence_has_incident_and_rollback",
            ok=len(incident_paths) > 0 and len(rollback_paths) > 0,
            value={"incident_reports": len(incident_paths), "rollback_reports": len(rollback_paths)},
            expect="at least one incident drill report and one rollback bundle report",
            mode=mode,
        )
    )

    signing_key = str(args.signing_key or "").strip()
    key_required = bool(args.require_key)
    checks.append(
        _check_row(
            check_id="drill_signature_key_available",
            ok=(not key_required) or bool(signing_key),
            value={"require_key": key_required, "available": bool(signing_key)},
            expect="signing key available when required",
            mode=mode,
        )
    )

    payload = {
        "version": 1,
        "signed_at": round(time.time(), 3),
        "algorithm": "hmac-sha256",
        "key_id": str(args.key_id or "default"),
        "artifact_patterns": {
            "incident_drill_pattern": str(args.incident_drill_pattern),
            "rollback_bundle_pattern": str(args.rollback_bundle_pattern),
            "incident_report_pattern": str(args.incident_report_pattern),
        },
        "artifacts": artifacts,
    }
    payload_text = _canonical_json(payload)

    signature = ""
    if signing_key:
        signature = _sign(payload_text, signing_key)
    checks.append(
        _check_row(
            check_id="drill_signature_created",
            ok=bool(signature) or (not key_required),
            value={"signature_present": bool(signature)},
            expect="signature generated when key required",
            mode=mode,
        )
    )

    enforce_rows = [row for row in checks if str(row.get("mode") or "warn") == "enforce"]
    ok = all(bool(row.get("ok")) for row in enforce_rows)
    ended = time.time()
    report = {
        "ok": bool(ok),
        "started_at": round(started, 3),
        "ended_at": round(ended, 3),
        "duration_s": round(ended - started, 3),
        "strict": bool(args.strict),
        "settings": {
            "recent": recent,
            "require_key": key_required,
            "key_id": str(args.key_id or "default"),
            "incident_drill_pattern": str(args.incident_drill_pattern),
            "rollback_bundle_pattern": str(args.rollback_bundle_pattern),
            "incident_report_pattern": str(args.incident_report_pattern),
        },
        "checks": checks,
        "payload": payload,
        "payload_canonical_json": payload_text,
        "signature": signature,
    }
    out_default = Path(".data/out") / f"rollback_drill_signature_{int(ended)}.json"
    out_path = Path(str(args.out or out_default))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if bool(args.strict):
        return 0 if bool(ok) else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
