#!/usr/bin/env python3
"""Release Compat Matrix command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if not text:
        return bool(default)
    return text in {"1", "true", "yes", "on"}


def _is_semver(text: str) -> bool:
    return bool(SEMVER_RE.match(str(text or "").strip()))


def _schema_tuple(text: str) -> tuple[int, int] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    parts = raw.split(".")
    if len(parts) != 2:
        return None
    try:
        return (int(parts[0]), int(parts[1]))
    except Exception:
        return None


def _schema_compare(left: str, right: str) -> int | None:
    lhs = _schema_tuple(left)
    rhs = _schema_tuple(right)
    if lhs is None or rhs is None:
        return None
    if lhs < rhs:
        return -1
    if lhs > rhs:
        return 1
    return 0


def _load_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    return None


def _check_row(*, check_id: str, ok: bool, value: Any, expect: str, mode: str = "enforce") -> dict[str, Any]:
    return {
        "id": str(check_id),
        "ok": bool(ok),
        "value": value,
        "expect": str(expect),
        "mode": str(mode or "enforce"),
    }


def _default_state_dict(target_schema: str) -> dict[str, Any]:
    return {
        "schema_version": str(target_schema),
        "trace_id": "compat-trace-id",
        "session_id": "compat-session",
        "doc_id": "compat-doc",
        "request_id": "compat-request-id",
        "state": "S02_DOC_READY",
        "state_rev": 0,
        "transition_id": None,
        "last_trigger": None,
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        "request": {
            "source": "compat",
            "instruction_raw": "compat",
            "instruction_normalized": "compat",
            "user_id": None,
            "user_cancelled": False,
        },
        "role": {"role_type": "R04", "confidence": 0.0, "hard_constraints": ["none"], "soft_style_prompt": ""},
        "intent": {"intent_type": "I08", "confidence": 0.0, "reason": ""},
        "scope": {"scope_type": "C07", "target_ids": [], "selection_text": None},
        "routing": {
            "route": "E22",
            "score": {
                "role_weight": 0.0,
                "intent_weight": 0.0,
                "scope_weight": 0.0,
                "final_score": 0.0,
            },
        },
        "locks": {"global_lock": False, "partial_locks": [], "conflict_reason": None, "released": False},
        "streaming": {
            "stream_id": None,
            "section_id": None,
            "section_key": None,
            "cursor": 0,
            "token_usage": {"prompt": 0, "completion": 0},
            "aborted": False,
        },
        "media": {"unresolved_media_count": 0, "items": []},
        "verify": {"checks": [], "has_warning": False, "has_error": False},
        "rollback": {"failed_snapshot_id": None, "stable_snapshot_id": None, "incident_diff_id": None},
        "cleanup": {"lock_release_done": False, "temp_clean_done": False, "log_flush_done": False},
        "error": {"code": None, "message": None, "retryable": False},
        "telemetry": {"retry_count": 0, "latency_ms": 0, "action_seq": 0, "idempotency_key": "compat-idempotency"},
    }


def _merge_dict(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            nested = dict(out.get(key) if isinstance(out.get(key), dict) else {})
            for n_key, n_value in value.items():
                nested[n_key] = n_value
            out[key] = nested
        else:
            out[key] = value
    return out


def _normalize_state_payload(payload: dict[str, Any], *, target_schema: str) -> dict[str, Any]:
    merged = _merge_dict(_default_state_dict(target_schema), payload if isinstance(payload, dict) else {})
    merged["schema_version"] = str(target_schema)
    merged["state_rev"] = _safe_int(merged.get("state_rev"), 0)
    return merged


def _validate_runtime_contract(policy: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    runtime_data = policy.get("runtime_data") if isinstance(policy.get("runtime_data"), dict) else {}
    files = runtime_data.get("files") if isinstance(runtime_data.get("files"), list) else []
    kind_map = {"json_object": dict, "json_array": list}
    for item in files:
        if not isinstance(item, dict):
            continue
        rel_path = str(item.get("path") or "").strip()
        kind = str(item.get("kind") or "").strip()
        required = _safe_bool(item.get("required"), False)
        path = Path(rel_path)
        raw = _load_json(path)
        expected_type = kind_map.get(kind)
        if not path.exists():
            checks.append(
                _check_row(
                    check_id=f"runtime_file_exists::{rel_path}",
                    ok=(not required),
                    value={"exists": False, "required": required},
                    expect="required runtime files must exist",
                    mode="enforce" if required else "warn",
                )
            )
            continue
        if kind == "json_array":
            kind_ok = isinstance(raw, list) or (isinstance(raw, dict) and isinstance(raw.get("events"), list))
            actual_kind = "events_wrapper" if isinstance(raw, dict) else (type(raw).__name__ if raw is not None else "invalid_json")
        else:
            kind_ok = expected_type is None or isinstance(raw, expected_type)
            actual_kind = type(raw).__name__ if raw is not None else "invalid_json"
        checks.append(
            _check_row(
                check_id=f"runtime_file_kind::{rel_path}",
                ok=kind_ok,
                value={"kind": kind, "actual": actual_kind},
                expect=f"runtime file matches {kind}",
                mode="enforce",
            )
        )
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="Run release upgrade/rollback compatibility matrix.")
    parser.add_argument("--policy", default="security/release_policy.json")
    parser.add_argument("--matrix", default="security/release_compat_matrix.json")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    started = time.time()
    checks: list[dict[str, Any]] = []
    case_reports: list[dict[str, Any]] = []

    policy_path = Path(str(args.policy))
    matrix_path = Path(str(args.matrix))
    policy_raw = _load_json(policy_path)
    matrix_raw = _load_json(matrix_path)

    checks.append(
        _check_row(
            check_id="release_policy_loaded",
            ok=isinstance(policy_raw, dict),
            value=policy_path.as_posix(),
            expect="release policy exists and valid",
        )
    )
    checks.append(
        _check_row(
            check_id="release_compat_matrix_loaded",
            ok=isinstance(matrix_raw, dict),
            value=matrix_path.as_posix(),
            expect="compat matrix exists and valid",
        )
    )

    policy = policy_raw if isinstance(policy_raw, dict) else {}
    matrix = matrix_raw if isinstance(matrix_raw, dict) else {}
    state_schema = policy.get("state_schema") if isinstance(policy.get("state_schema"), dict) else {}
    current_schema = str(state_schema.get("current") or "").strip()
    backward = [str(item).strip() for item in (state_schema.get("backward_read_compatible") if isinstance(state_schema.get("backward_read_compatible"), list) else []) if str(item).strip()]
    app_version = str(policy.get("app_version") or "").strip()
    cases = matrix.get("cases") if isinstance(matrix.get("cases"), list) else []
    rules = matrix.get("rules") if isinstance(matrix.get("rules"), dict) else {}

    checks.append(
        _check_row(
            check_id="policy_app_version_semver",
            ok=_is_semver(app_version),
            value=app_version,
            expect="policy app_version is semantic version x.y.z",
        )
    )
    checks.append(
        _check_row(
            check_id="matrix_has_cases",
            ok=len(cases) > 0,
            value={"cases": len(cases)},
            expect="matrix contains at least one case",
        )
    )

    required_fields = {
        "schema_version",
        "trace_id",
        "session_id",
        "doc_id",
        "request_id",
        "state",
        "state_rev",
        "created_at",
        "updated_at",
    }
    coverage_upgrade = False
    coverage_rollback = False
    coverage_n_minus_one_upgrade = False
    coverage_n_plus_one_upgrade = False
    coverage_n_plus_one_rollback = False
    coverage_failure_mode = False

    for index, item in enumerate(cases):
        if not isinstance(item, dict):
            case_reports.append(
                {
                    "id": f"case_{index}",
                    "ok": False,
                    "checks": [
                        _check_row(
                            check_id="case_is_dict",
                            ok=False,
                            value=type(item).__name__,
                            expect="case row must be dict",
                        )
                    ],
                }
            )
            continue

        case_id = str(item.get("id") or f"case_{index}")
        direction = str(item.get("direction") or "upgrade").strip().lower()
        from_version = str(item.get("from_version") or app_version).strip()
        to_version = str(item.get("to_version") or app_version).strip()
        from_schema = str(item.get("from_schema") or current_schema).strip()
        to_schema = str(item.get("to_schema") or current_schema).strip()
        expect_readable = _safe_bool(item.get("expect_readable"), True)
        allow_forward_schema_source = _safe_bool(item.get("allow_forward_schema_source"), False)
        expected_failed_checks = [
            str(node).strip()
            for node in (item.get("expected_failed_checks") if isinstance(item.get("expected_failed_checks"), list) else [])
            if str(node).strip()
        ]
        fixture_path = Path(str(item.get("state_fixture") or "").strip())
        raw_payload = _load_json(fixture_path) if fixture_path.as_posix() else None

        if direction == "upgrade" and to_schema == current_schema:
            coverage_upgrade = True
        if direction == "rollback" and to_schema == current_schema:
            coverage_rollback = True
        from_schema_cmp = _schema_compare(from_schema, current_schema)
        to_schema_cmp = _schema_compare(to_schema, current_schema)
        if direction == "upgrade" and to_schema == current_schema and from_schema_cmp is not None and from_schema_cmp < 0:
            coverage_n_minus_one_upgrade = True
        if direction == "upgrade" and from_schema == current_schema and to_schema_cmp is not None and to_schema_cmp > 0:
            coverage_n_plus_one_upgrade = True
        if direction == "rollback" and to_schema == current_schema and from_schema_cmp is not None and from_schema_cmp > 0:
            coverage_n_plus_one_rollback = True
        if not expect_readable:
            coverage_failure_mode = True

        row_checks: list[dict[str, Any]] = []
        row_checks.append(
            _check_row(
                check_id="direction_valid",
                ok=direction in {"upgrade", "rollback"},
                value=direction,
                expect="direction is upgrade or rollback",
            )
        )
        row_checks.append(
            _check_row(
                check_id="from_version_semver",
                ok=_is_semver(from_version),
                value=from_version,
                expect="semantic version x.y.z",
            )
        )
        row_checks.append(
            _check_row(
                check_id="to_version_semver",
                ok=_is_semver(to_version),
                value=to_version,
                expect="semantic version x.y.z",
            )
        )
        row_checks.append(
            _check_row(
                check_id="fixture_loaded",
                ok=isinstance(raw_payload, dict),
                value=fixture_path.as_posix(),
                expect="state fixture exists and is valid json object",
            )
        )

        schema_known = (from_schema == current_schema) or (from_schema in backward)
        if direction == "rollback" and allow_forward_schema_source and from_schema_cmp is not None and from_schema_cmp > 0:
            schema_known = True
        row_checks.append(
            _check_row(
                check_id="from_schema_backward_compatible",
                ok=schema_known,
                value={
                    "from_schema": from_schema,
                    "current": current_schema,
                    "backward": backward,
                    "allow_forward_schema_source": allow_forward_schema_source,
                },
                expect="source schema should be current or backward compatible",
            )
        )

        normalized: dict[str, Any] = {}
        if isinstance(raw_payload, dict):
            normalized = _normalize_state_payload(raw_payload, target_schema=to_schema)
            missing = sorted([key for key in required_fields if key not in normalized])
            row_checks.append(
                _check_row(
                    check_id="normalized_required_fields_present",
                    ok=len(missing) == 0,
                    value={"missing": missing},
                    expect="normalized payload has required state context fields",
                )
            )
            row_checks.append(
                _check_row(
                    check_id="normalized_schema_matches_target",
                    ok=str(normalized.get("schema_version") or "") == to_schema,
                    value={
                        "normalized_schema": str(normalized.get("schema_version") or ""),
                        "target_schema": to_schema,
                    },
                    expect="normalized schema matches target schema",
                )
            )
            row_checks.append(
                _check_row(
                    check_id="normalized_payload_json_roundtrip",
                    ok=True,
                    value=len(json.dumps(normalized, ensure_ascii=False)),
                    expect="normalized payload should be json serializable",
                )
            )

        if expect_readable:
            row_ok = all(bool(row.get("ok")) for row in row_checks)
        else:
            failed_ids = [str(row.get("id") or "") for row in row_checks if not bool(row.get("ok"))]
            missing_expected = [check_id for check_id in expected_failed_checks if check_id not in failed_ids]
            negative_ok = bool(failed_ids) and (len(missing_expected) == 0)
            row_checks.append(
                _check_row(
                    check_id="negative_case_failure_expectation",
                    ok=negative_ok,
                    value={
                        "failed_checks": failed_ids,
                        "expected_failed_checks": expected_failed_checks,
                        "missing_expected_failed_checks": missing_expected,
                    },
                    expect="negative case should fail and include all expected_failed_checks",
                )
            )
            row_ok = negative_ok
        case_reports.append(
            {
                "id": case_id,
                "direction": direction,
                "from_version": from_version,
                "to_version": to_version,
                "from_schema": from_schema,
                "to_schema": to_schema,
                "expect_readable": expect_readable,
                "allow_forward_schema_source": allow_forward_schema_source,
                "expected_failed_checks": expected_failed_checks,
                "ok": bool(row_ok),
                "checks": row_checks,
                "normalized_preview": {
                    "schema_version": str(normalized.get("schema_version") or ""),
                    "state": str(normalized.get("state") or ""),
                    "state_rev": _safe_int(normalized.get("state_rev"), 0),
                }
                if isinstance(normalized, dict)
                else {},
            }
        )

    checks.append(
        _check_row(
            check_id="matrix_covers_upgrade_current_schema",
            ok=(not _safe_bool(rules.get("require_upgrade_case_for_current_schema"), True)) or coverage_upgrade,
            value={"coverage_upgrade": coverage_upgrade, "current_schema": current_schema},
            expect="matrix includes upgrade case targeting current schema",
        )
    )
    checks.append(
        _check_row(
            check_id="matrix_covers_rollback_current_schema",
            ok=(not _safe_bool(rules.get("require_rollback_case_for_current_schema"), True)) or coverage_rollback,
            value={"coverage_rollback": coverage_rollback, "current_schema": current_schema},
            expect="matrix includes rollback case targeting current schema",
        )
    )
    checks.append(
        _check_row(
            check_id="matrix_covers_n_minus_one_upgrade_case",
            ok=(not _safe_bool(rules.get("require_n_minus_one_upgrade_case"), False)) or coverage_n_minus_one_upgrade,
            value={
                "coverage_n_minus_one_upgrade": coverage_n_minus_one_upgrade,
                "current_schema": current_schema,
            },
            expect="matrix includes upgrade case from N-1 schema to current schema",
        )
    )
    checks.append(
        _check_row(
            check_id="matrix_covers_n_plus_one_upgrade_case",
            ok=(not _safe_bool(rules.get("require_n_plus_one_upgrade_case"), False)) or coverage_n_plus_one_upgrade,
            value={
                "coverage_n_plus_one_upgrade": coverage_n_plus_one_upgrade,
                "current_schema": current_schema,
            },
            expect="matrix includes upgrade case from current schema to N+1 schema",
        )
    )
    checks.append(
        _check_row(
            check_id="matrix_covers_n_plus_one_rollback_case",
            ok=(not _safe_bool(rules.get("require_n_plus_one_rollback_case"), False)) or coverage_n_plus_one_rollback,
            value={
                "coverage_n_plus_one_rollback": coverage_n_plus_one_rollback,
                "current_schema": current_schema,
            },
            expect="matrix includes rollback case from N+1 schema to current schema",
        )
    )
    checks.append(
        _check_row(
            check_id="matrix_covers_failure_mode_case",
            ok=(not _safe_bool(rules.get("require_failure_mode_case"), False)) or coverage_failure_mode,
            value={"coverage_failure_mode": coverage_failure_mode},
            expect="matrix includes at least one expected failure-mode fixture",
        )
    )

    if _safe_bool(rules.get("enforce_runtime_contract"), True):
        checks.extend(_validate_runtime_contract(policy))

    checks.append(
        _check_row(
            check_id="all_matrix_cases_pass",
            ok=all(bool(item.get("ok")) for item in case_reports),
            value={"total_cases": len(case_reports), "passed_cases": sum(1 for item in case_reports if bool(item.get("ok")))},
            expect="all matrix cases should pass",
            mode="enforce",
        )
    )

    enforce_rows = [row for row in checks if str(row.get("mode") or "enforce") == "enforce"]
    if bool(args.strict):
        for item in case_reports:
            if not bool(item.get("ok")):
                enforce_rows.append({"ok": False})
    ok = all(bool(row.get("ok")) for row in enforce_rows)

    ended = time.time()
    report = {
        "ok": bool(ok),
        "started_at": round(started, 3),
        "ended_at": round(ended, 3),
        "duration_s": round(ended - started, 3),
        "strict": bool(args.strict),
        "policy_path": policy_path.as_posix(),
        "matrix_path": matrix_path.as_posix(),
        "policy": {
            "app_version": app_version,
            "state_schema_current": current_schema,
            "backward_read_compatible": backward,
        },
        "checks": checks,
        "cases": case_reports,
    }
    out_default = Path(".data/out") / f"release_compat_matrix_{int(ended)}.json"
    out_path = Path(str(args.out or out_default))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report.get("ok")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
