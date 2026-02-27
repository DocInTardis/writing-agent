#!/usr/bin/env python3
"""Rollback Drill Guard command utility.

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


def _safe_float(value: Any, default: float = 0.0) -> float:
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


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _latest_paths(pattern: str, *, limit: int) -> list[Path]:
    rows = sorted((Path(p) for p in glob.glob(pattern)), key=lambda p: p.stat().st_mtime if p.exists() else 0.0)
    take = max(0, int(limit))
    if take <= 0:
        return []
    return rows[-take:]


def _check_row(*, check_id: str, ok: bool, value: Any, expect: str, mode: str) -> dict[str, Any]:
    return {
        "id": str(check_id),
        "ok": bool(ok),
        "value": value,
        "expect": str(expect),
        "mode": str(mode or "warn"),
    }


def _report_ts(raw: dict[str, Any], *, fallback_path: Path, keys: list[str]) -> float:
    for key in keys:
        value = _safe_float(raw.get(key), 0.0)
        if value > 0:
            return value
    try:
        return _safe_float(fallback_path.stat().st_mtime, 0.0)
    except Exception:
        return 0.0


def _normalize_history(path: Path) -> list[dict[str, Any]]:
    raw = _load_json(path)
    if not isinstance(raw, dict):
        return []
    rows = raw.get("history") if isinstance(raw.get("history"), list) else []
    out: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "ts": _safe_float(row.get("ts"), 0.0),
                "action": str(row.get("action") or "").strip().lower(),
                "channel": str(row.get("channel") or "").strip().lower(),
                "from_version": str(row.get("from_version") or "").strip(),
                "to_version": str(row.get("to_version") or "").strip(),
                "reason": str(row.get("reason") or "").strip(),
                "actor": str(row.get("actor") or "").strip(),
            }
        )
    out.sort(key=lambda item: _safe_float(item.get("ts"), 0.0))
    return out


def _contains_keyword(text: str, keywords: list[str]) -> bool:
    value = str(text or "").strip().lower()
    if not value:
        return False
    return any(keyword in value for keyword in keywords)


def _verify_signature_report(raw: dict[str, Any], *, signing_key: str) -> dict[str, Any]:
    payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else {}
    signature = str(raw.get("signature") or "").strip().lower()
    payload_text = _canonical_json(payload if isinstance(payload, dict) else {})
    expected = (
        hmac.new(str(signing_key or "").encode("utf-8"), payload_text.encode("utf-8"), hashlib.sha256).hexdigest()
        if str(signing_key or "").strip()
        else ""
    )
    signature_ok = bool(signature) and bool(expected) and hmac.compare_digest(signature, expected)
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), list) else []
    hash_rows: list[dict[str, Any]] = []
    for item in artifacts:
        if not isinstance(item, dict):
            continue
        path = Path(str(item.get("path") or ""))
        expected_sha = str(item.get("sha256") or "").strip().lower()
        exists = path.exists() and path.is_file()
        actual_sha = _sha256(path).lower() if exists else ""
        hash_rows.append(
            {
                "path": path.as_posix(),
                "exists": bool(exists),
                "expected_sha256": expected_sha,
                "actual_sha256": actual_sha,
                "hash_match": bool(exists and expected_sha and actual_sha and expected_sha == actual_sha),
            }
        )
    hashes_ok = all(bool(row.get("hash_match")) for row in hash_rows) if hash_rows else False
    return {
        "signature_ok": signature_ok,
        "expected_signature": expected,
        "provided_signature": signature,
        "hashes_ok": hashes_ok,
        "hash_rows": hash_rows,
        "payload": payload,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate rollback drill evidence freshness and quality.")
    parser.add_argument("--incident-drill-pattern", default=".data/out/incident_notify_drill_*.json")
    parser.add_argument("--rollback-bundle-pattern", default=".data/out/rollback_bundle_report_*.json")
    parser.add_argument("--signature-pattern", default=".data/out/rollback_drill_signature_*.json")
    parser.add_argument("--signature-policy", default="security/rollback_drill_signature_policy.json")
    parser.add_argument("--channels-file", default="security/release_channels.json")
    parser.add_argument("--max-age-s", type=float, default=30 * 24 * 3600.0)
    parser.add_argument("--history-max-age-s", type=float, default=45 * 24 * 3600.0)
    parser.add_argument("--signature-max-age-s", type=float, default=30 * 24 * 3600.0)
    parser.add_argument("--min-incident-drills", type=int, default=1)
    parser.add_argument("--min-rollback-bundles", type=int, default=1)
    parser.add_argument("--require-email-drill", action="store_true")
    parser.add_argument("--require-history-rollback", action="store_true")
    parser.add_argument("--require-signature", action="store_true")
    parser.add_argument("--signing-key", default=os.environ.get("WA_ROLLBACK_DRILL_SIGNING_KEY", ""))
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    started = time.time()
    checks: list[dict[str, Any]] = []
    mode = "enforce" if bool(args.strict) else "warn"

    min_incident_drills = max(1, _safe_int(args.min_incident_drills, 1))
    min_rollback_bundles = max(1, _safe_int(args.min_rollback_bundles, 1))
    max_age_s = max(1.0, _safe_float(args.max_age_s, 30 * 24 * 3600.0))
    history_max_age_s = max(1.0, _safe_float(args.history_max_age_s, 45 * 24 * 3600.0))
    signature_max_age_s = max(1.0, _safe_float(args.signature_max_age_s, 30 * 24 * 3600.0))

    signature_policy_path = Path(str(args.signature_policy))
    signature_policy_raw = _load_json(signature_policy_path)
    checks.append(
        _check_row(
            check_id="rollback_signature_policy_loaded",
            ok=(not signature_policy_path.exists()) or isinstance(signature_policy_raw, dict),
            value=signature_policy_path.as_posix(),
            expect="rollback signature policy absent or valid json",
            mode=mode,
        )
    )
    signature_policy = signature_policy_raw if isinstance(signature_policy_raw, dict) else {}
    if isinstance(signature_policy, dict):
        if _safe_float(signature_policy.get("max_signature_age_s"), 0.0) > 0:
            signature_max_age_s = max(1.0, _safe_float(signature_policy.get("max_signature_age_s"), signature_max_age_s))

    require_signature = bool(args.require_signature)
    if bool(signature_policy.get("required")):
        require_signature = True
    if bool(args.strict) and bool(signature_policy.get("required_in_strict")):
        require_signature = True
    signing_key_required = bool(signature_policy.get("require_signing_key", True))
    signing_key = str(args.signing_key or "").strip()

    incident_paths = _latest_paths(str(args.incident_drill_pattern), limit=min_incident_drills)
    incident_rows: list[dict[str, Any]] = []
    incident_missing = max(0, min_incident_drills - len(incident_paths))
    checks.append(
        _check_row(
            check_id="incident_drill_reports_count",
            ok=len(incident_paths) >= min_incident_drills,
            value={"found": len(incident_paths), "required": min_incident_drills},
            expect="enough incident drill reports",
            mode=mode,
        )
    )

    for path in incident_paths:
        raw = _load_json(path)
        ts = _report_ts(raw or {}, fallback_path=path, keys=["ended_at", "started_at", "generated_at"])
        age_s = (started - ts) if ts > 0 else float("inf")
        row = {
            "path": path.as_posix(),
            "loaded": isinstance(raw, dict),
            "ok": bool((raw or {}).get("ok")),
            "with_email": bool((raw or {}).get("with_email")),
            "ts": round(ts, 3),
            "age_s": round(age_s, 3) if age_s != float("inf") else "inf",
        }
        incident_rows.append(row)

    checks.append(
        _check_row(
            check_id="incident_drill_reports_loadable",
            ok=all(bool(row.get("loaded")) for row in incident_rows) and incident_missing == 0,
            value={"loaded": sum(1 for row in incident_rows if bool(row.get("loaded"))), "missing": incident_missing},
            expect="all required incident drill reports should be parseable json",
            mode=mode,
        )
    )
    checks.append(
        _check_row(
            check_id="incident_drill_reports_ok",
            ok=all(bool(row.get("ok")) for row in incident_rows) and incident_missing == 0,
            value={"ok_reports": sum(1 for row in incident_rows if bool(row.get("ok"))), "missing": incident_missing},
            expect="incident drill reports should pass",
            mode=mode,
        )
    )
    checks.append(
        _check_row(
            check_id="incident_drill_reports_fresh",
            ok=all(float(row.get("age_s") if row.get("age_s") != "inf" else float("inf")) <= max_age_s for row in incident_rows)
            and incident_missing == 0,
            value={"max_age_s": max_age_s, "rows": incident_rows},
            expect="incident drill evidence should be fresh",
            mode=mode,
        )
    )

    if bool(args.require_email_drill):
        checks.append(
            _check_row(
                check_id="incident_drill_email_covered",
                ok=any(bool(row.get("with_email")) and bool(row.get("ok")) for row in incident_rows),
                value={"require_email_drill": True, "rows": incident_rows},
                expect="at least one passing incident drill includes email channel",
                mode=mode,
            )
        )

    rollback_paths = _latest_paths(str(args.rollback_bundle_pattern), limit=min_rollback_bundles)
    rollback_rows: list[dict[str, Any]] = []
    rollback_missing = max(0, min_rollback_bundles - len(rollback_paths))
    checks.append(
        _check_row(
            check_id="rollback_bundle_reports_count",
            ok=len(rollback_paths) >= min_rollback_bundles,
            value={"found": len(rollback_paths), "required": min_rollback_bundles},
            expect="enough rollback bundle reports",
            mode=mode,
        )
    )

    for path in rollback_paths:
        raw = _load_json(path)
        ts = _report_ts(raw or {}, fallback_path=path, keys=["generated_at", "ended_at", "started_at"])
        age_s = (started - ts) if ts > 0 else float("inf")
        missing_required = (
            (raw or {}).get("missing_required")
            if isinstance((raw or {}).get("missing_required"), list)
            else []
        )
        row = {
            "path": path.as_posix(),
            "loaded": isinstance(raw, dict),
            "ok": bool((raw or {}).get("ok")),
            "missing_required_count": len(missing_required),
            "ts": round(ts, 3),
            "age_s": round(age_s, 3) if age_s != float("inf") else "inf",
        }
        rollback_rows.append(row)

    checks.append(
        _check_row(
            check_id="rollback_bundle_reports_loadable",
            ok=all(bool(row.get("loaded")) for row in rollback_rows) and rollback_missing == 0,
            value={"loaded": sum(1 for row in rollback_rows if bool(row.get("loaded"))), "missing": rollback_missing},
            expect="all required rollback bundle reports should be parseable json",
            mode=mode,
        )
    )
    checks.append(
        _check_row(
            check_id="rollback_bundle_reports_ok",
            ok=all(bool(row.get("ok")) for row in rollback_rows) and rollback_missing == 0,
            value={"ok_reports": sum(1 for row in rollback_rows if bool(row.get("ok"))), "missing": rollback_missing},
            expect="rollback bundle reports should pass",
            mode=mode,
        )
    )
    checks.append(
        _check_row(
            check_id="rollback_bundle_reports_have_required_files",
            ok=all(int(row.get("missing_required_count") or 0) == 0 for row in rollback_rows) and rollback_missing == 0,
            value={"rows": rollback_rows},
            expect="rollback bundle reports should not miss required files",
            mode=mode,
        )
    )
    checks.append(
        _check_row(
            check_id="rollback_bundle_reports_fresh",
            ok=all(float(row.get("age_s") if row.get("age_s") != "inf" else float("inf")) <= max_age_s for row in rollback_rows)
            and rollback_missing == 0,
            value={"max_age_s": max_age_s, "rows": rollback_rows},
            expect="rollback bundle evidence should be fresh",
            mode=mode,
        )
    )

    signature_rows: list[dict[str, Any]] = []
    signature_paths = _latest_paths(str(args.signature_pattern), limit=1)
    signature_missing = 1 - len(signature_paths)
    signature_mode = mode if require_signature else "warn"
    checks.append(
        _check_row(
            check_id="rollback_signature_reports_count",
            ok=(len(signature_paths) >= 1) if require_signature else True,
            value={"found": len(signature_paths), "required": 1 if require_signature else 0},
            expect="signed drill evidence exists when required",
            mode=signature_mode,
        )
    )
    checks.append(
        _check_row(
            check_id="rollback_signature_key_available",
            ok=(not require_signature) or (not signing_key_required) or bool(signing_key),
            value={
                "require_signature": require_signature,
                "require_signing_key": signing_key_required,
                "key_available": bool(signing_key),
            },
            expect="signing key available for signature verification when required",
            mode=signature_mode,
        )
    )

    for path in signature_paths:
        raw = _load_json(path)
        ts = _report_ts(raw or {}, fallback_path=path, keys=["ended_at", "signed_at", "started_at"])
        age_s = (started - ts) if ts > 0 else float("inf")
        verify = _verify_signature_report(raw or {}, signing_key=signing_key) if isinstance(raw, dict) and signing_key else {
            "signature_ok": False,
            "hashes_ok": False,
            "hash_rows": [],
            "payload": {},
        }
        signature_payload = verify.get("payload") if isinstance(verify.get("payload"), dict) else {}
        payload_artifacts = (
            signature_payload.get("artifacts")
            if isinstance(signature_payload.get("artifacts"), list)
            else []
        )
        payload_paths = {
            str(item.get("path") or "").strip()
            for item in payload_artifacts
            if isinstance(item, dict)
        }
        required_paths = {str(row.get("path") or "").strip() for row in [*incident_rows, *rollback_rows] if str(row.get("path") or "").strip()}
        covers_required = (len(required_paths) == 0) or required_paths.issubset(payload_paths)
        signature_rows.append(
            {
                "path": path.as_posix(),
                "loaded": isinstance(raw, dict),
                "ok": bool((raw or {}).get("ok")) if isinstance(raw, dict) else False,
                "ts": round(ts, 3),
                "age_s": round(age_s, 3) if age_s != float("inf") else "inf",
                "signature_ok": bool(verify.get("signature_ok")),
                "hashes_ok": bool(verify.get("hashes_ok")),
                "covers_required_evidence": bool(covers_required),
                "required_paths_count": len(required_paths),
            }
        )

    checks.append(
        _check_row(
            check_id="rollback_signature_reports_loadable",
            ok=(all(bool(row.get("loaded")) for row in signature_rows) and signature_missing <= 0) if require_signature else True,
            value={"loaded": sum(1 for row in signature_rows if bool(row.get("loaded"))), "missing": max(0, signature_missing)},
            expect="signature report is parseable json when required",
            mode=signature_mode,
        )
    )
    checks.append(
        _check_row(
            check_id="rollback_signature_reports_fresh",
            ok=(
                all(
                    float(row.get("age_s") if row.get("age_s") != "inf" else float("inf")) <= signature_max_age_s
                    for row in signature_rows
                )
                and signature_missing <= 0
            )
            if require_signature
            else True,
            value={"max_age_s": signature_max_age_s, "rows": signature_rows},
            expect="signed drill evidence should be fresh when required",
            mode=signature_mode,
        )
    )
    checks.append(
        _check_row(
            check_id="rollback_signature_reports_valid",
            ok=(
                all(
                    bool(row.get("ok"))
                    and bool(row.get("signature_ok"))
                    and bool(row.get("hashes_ok"))
                    and bool(row.get("covers_required_evidence"))
                    for row in signature_rows
                )
                and signature_missing <= 0
            )
            if require_signature
            else True,
            value={"rows": signature_rows},
            expect="signature report validates hmac, hashes, and evidence coverage",
            mode=signature_mode,
        )
    )

    history_rows = _normalize_history(Path(str(args.channels_file)))
    drill_keywords = ["drill", "rehearsal", "exercise", "simulation", "gameday"]
    rollback_drill_rows = [
        row
        for row in history_rows
        if str(row.get("action") or "") == "rollback"
        and _contains_keyword(str(row.get("reason") or ""), drill_keywords)
    ]
    latest_rollback_drill_ts = _safe_float(
        rollback_drill_rows[-1].get("ts") if rollback_drill_rows else 0.0,
        0.0,
    )
    latest_rollback_drill_age_s = (started - latest_rollback_drill_ts) if latest_rollback_drill_ts > 0 else float("inf")
    if bool(args.require_history_rollback):
        checks.append(
            _check_row(
                check_id="history_has_rollback_rehearsal",
                ok=len(rollback_drill_rows) > 0,
                value={
                    "history_entries": len(history_rows),
                    "rollback_drill_entries": len(rollback_drill_rows),
                    "keywords": drill_keywords,
                },
                expect="release channel history contains rollback drill/rehearsal action",
                mode=mode,
            )
        )
        checks.append(
            _check_row(
                check_id="history_rollback_rehearsal_fresh",
                ok=latest_rollback_drill_age_s <= history_max_age_s,
                value=round(latest_rollback_drill_age_s, 3) if latest_rollback_drill_age_s != float("inf") else "inf",
                expect=f"<= {round(history_max_age_s, 3)}s",
                mode=mode,
            )
        )

    next_actions: list[str] = []
    if len(incident_paths) < min_incident_drills:
        next_actions.append("Run incident drill: python scripts/incident_notify_drill.py --with-email")
    if incident_rows and not all(bool(row.get("ok")) for row in incident_rows):
        next_actions.append("Investigate failed incident drill report and re-run incident_notify_drill until report.ok=true.")
    if len(rollback_paths) < min_rollback_bundles:
        next_actions.append("Generate rollback bundle evidence: python scripts/create_rollback_bundle.py --label drill --strict")
    if rollback_rows and not all(bool(row.get("ok")) for row in rollback_rows):
        next_actions.append("Fix rollback bundle missing files and regenerate rollback bundle report.")
    if require_signature and len(signature_paths) <= 0:
        next_actions.append(
            "Generate signed drill evidence: python scripts/sign_rollback_drill_evidence.py --require-key --strict"
        )
    if require_signature and signature_rows and not all(
        bool(row.get("ok"))
        and bool(row.get("signature_ok"))
        and bool(row.get("hashes_ok"))
        and bool(row.get("covers_required_evidence"))
        for row in signature_rows
    ):
        next_actions.append("Regenerate signed drill evidence and verify HMAC key/payload hash consistency.")
    if bool(args.require_history_rollback) and len(rollback_drill_rows) == 0:
        next_actions.append("Record at least one rollback rehearsal action in release channel history with reason containing 'drill'.")
    if bool(args.require_email_drill) and not any(
        bool(row.get("with_email")) and bool(row.get("ok")) for row in incident_rows
    ):
        next_actions.append("Run incident drill with SMTP enabled to validate email notification path.")

    ok = all(bool(row.get("ok")) for row in checks)
    ended = time.time()
    report = {
        "ok": bool(ok),
        "started_at": round(started, 3),
        "ended_at": round(ended, 3),
        "duration_s": round(ended - started, 3),
        "strict": bool(args.strict),
        "settings": {
            "incident_drill_pattern": str(args.incident_drill_pattern),
            "rollback_bundle_pattern": str(args.rollback_bundle_pattern),
            "channels_file": str(args.channels_file),
            "max_age_s": max_age_s,
            "history_max_age_s": history_max_age_s,
            "signature_max_age_s": signature_max_age_s,
            "min_incident_drills": min_incident_drills,
            "min_rollback_bundles": min_rollback_bundles,
            "require_email_drill": bool(args.require_email_drill),
            "require_history_rollback": bool(args.require_history_rollback),
            "require_signature": require_signature,
            "signature_pattern": str(args.signature_pattern),
            "signature_policy": signature_policy_path.as_posix(),
            "signature_signing_key_required": signing_key_required,
        },
        "evidence": {
            "incident_drills": incident_rows,
            "rollback_bundles": rollback_rows,
            "rollback_signatures": signature_rows,
            "rollback_history_drills": rollback_drill_rows[-10:],
            "rollback_history_total_entries": len(history_rows),
        },
        "checks": checks,
        "next_actions": next_actions,
    }

    out_default = Path(".data/out") / f"rollback_drill_guard_{int(ended)}.json"
    out_path = Path(str(args.out or out_default))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if bool(args.strict):
        return 0 if bool(ok) else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
