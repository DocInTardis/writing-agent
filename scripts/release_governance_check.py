#!/usr/bin/env python3
"""Release Governance Check command utility.

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
SCHEMA_RE = re.compile(r"^\d+\.\d+$")
VERSION_RE = re.compile(r'__version__\s*=\s*"([^"]+)"')
SCHEMA_FIELD_RE = re.compile(r'schema_version\s*=\s*"([^"]+)"')


def _ok(*, check_id: str, ok: bool, value: Any, expect: str, mode: str = "enforce") -> dict[str, Any]:
    return {
        "id": str(check_id),
        "ok": bool(ok),
        "value": value,
        "expect": str(expect),
        "mode": str(mode or "enforce"),
    }


def _load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


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


def _extract_app_version(init_text: str) -> str:
    m = VERSION_RE.search(str(init_text or ""))
    return str(m.group(1)).strip() if m else ""


def _extract_schema_version(context_text: str) -> str:
    m = SCHEMA_FIELD_RE.search(str(context_text or ""))
    return str(m.group(1)).strip() if m else ""


def _is_semver(text: str) -> bool:
    return bool(SEMVER_RE.match(str(text or "").strip()))


def _is_schema_version(text: str) -> bool:
    return bool(SCHEMA_RE.match(str(text or "").strip()))


def _empty_levels() -> dict[str, int]:
    return {"info": 0, "low": 0, "moderate": 0, "high": 0, "critical": 0, "unknown": 0, "total": 0}


def _validate_dependency_baseline(raw: dict[str, Any] | None) -> bool:
    row = raw if isinstance(raw, dict) else {}
    if int(row.get("version") or 0) < 1:
        return False
    levels = row.get("levels") if isinstance(row.get("levels"), dict) else {}
    for key in ("npm_prod", "npm_dev", "pip"):
        item = levels.get(key) if isinstance(levels.get(key), dict) else None
        if not isinstance(item, dict):
            return False
        expected = _empty_levels()
        for sev in expected.keys():
            _ = int(item.get(sev) or 0)
    return True


def _runtime_json_checks(*, data_dir: Path, strict: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    targets = [
        (data_dir / "citation_verify_alerts_config.json", "dict", False),
        (data_dir / "citation_verify_alert_events.json", "events", False),
        (data_dir / "citation_verify_metrics_trends.json", "dict", False),
    ]
    for path, kind, required in targets:
        data = _load_json(path)
        exists = path.exists()
        if required and not exists:
            rows.append(
                _ok(
                    check_id=f"runtime_file_exists::{path.name}",
                    ok=False,
                    value=False,
                    expect="required file exists",
                    mode="enforce",
                )
            )
            continue
        if not exists:
            rows.append(
                _ok(
                    check_id=f"runtime_file_optional::{path.name}",
                    ok=True,
                    value=False,
                    expect="optional",
                    mode="warn",
                )
            )
            continue
        if kind == "events":
            kind_ok = isinstance(data, list) or (
                isinstance(data, dict) and isinstance(data.get("events"), list)
            )
            value_name = "events_list" if kind_ok else (type(data).__name__ if data is not None else "invalid_json")
            expect = "list or {events:list}"
        else:
            expect_kind = dict if kind == "dict" else list
            kind_ok = isinstance(data, expect_kind)
            value_name = type(data).__name__ if data is not None else "invalid_json"
            expect = kind
        rows.append(
            _ok(
                check_id=f"runtime_file_json::{path.name}",
                ok=kind_ok,
                value=value_name,
                expect=expect,
                mode="enforce" if strict else "warn",
            )
        )
    return rows


def _policy_file_checks(
    *,
    alert_policy_path: Path,
    trend_policy_path: Path,
    capacity_policy_path: Path,
    rollback_signature_policy_path: Path,
    oncall_roster_path: Path,
    ops_rbac_policy_path: Path,
    rollout_policy_path: Path,
    rollout_adapter_contract_path: Path,
    compat_matrix_path: Path,
    strict: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    mode = "enforce" if strict else "warn"
    alert_raw = _load_json(alert_policy_path)
    trend_raw = _load_json(trend_policy_path)
    capacity_raw = _load_json(capacity_policy_path)
    rollback_signature_raw = _load_json(rollback_signature_policy_path)
    oncall_roster_raw = _load_json(oncall_roster_path)
    ops_rbac_raw = _load_json(ops_rbac_policy_path)
    rollout_raw = _load_json(rollout_policy_path)
    rollout_adapter_raw = _load_json(rollout_adapter_contract_path)
    compat_raw = _load_json(compat_matrix_path)
    rows.append(
        _ok(
            check_id="alert_escalation_policy_loaded",
            ok=isinstance(alert_raw, dict),
            value=alert_policy_path.as_posix(),
            expect="alert escalation policy json exists and valid",
            mode=mode,
        )
    )
    rows.append(
        _ok(
            check_id="performance_trend_policy_loaded",
            ok=isinstance(trend_raw, dict),
            value=trend_policy_path.as_posix(),
            expect="performance trend policy json exists and valid",
            mode=mode,
        )
    )
    rows.append(
        _ok(
            check_id="capacity_policy_loaded",
            ok=isinstance(capacity_raw, dict),
            value=capacity_policy_path.as_posix(),
            expect="capacity policy json exists and valid",
            mode=mode,
        )
    )
    rows.append(
        _ok(
            check_id="rollback_signature_policy_loaded",
            ok=isinstance(rollback_signature_raw, dict),
            value=rollback_signature_policy_path.as_posix(),
            expect="rollback drill signature policy json exists and valid",
            mode=mode,
        )
    )
    rows.append(
        _ok(
            check_id="oncall_roster_loaded",
            ok=isinstance(oncall_roster_raw, dict),
            value=oncall_roster_path.as_posix(),
            expect="on-call roster json exists and valid",
            mode=mode,
        )
    )
    rows.append(
        _ok(
            check_id="ops_rbac_policy_loaded",
            ok=isinstance(ops_rbac_raw, dict),
            value=ops_rbac_policy_path.as_posix(),
            expect="ops rbac policy json exists and valid",
            mode=mode,
        )
    )
    rows.append(
        _ok(
            check_id="release_rollout_policy_loaded",
            ok=isinstance(rollout_raw, dict),
            value=rollout_policy_path.as_posix(),
            expect="release rollout policy json exists and valid",
            mode=mode,
        )
    )
    rows.append(
        _ok(
            check_id="release_rollout_adapter_contract_loaded",
            ok=isinstance(rollout_adapter_raw, dict),
            value=rollout_adapter_contract_path.as_posix(),
            expect="release rollout adapter contract json exists and valid",
            mode=mode,
        )
    )
    rows.append(
        _ok(
            check_id="release_compat_matrix_loaded",
            ok=isinstance(compat_raw, dict),
            value=compat_matrix_path.as_posix(),
            expect="release compatibility matrix json exists and valid",
            mode=mode,
        )
    )
    return rows


def _policy_checks(
    *,
    policy_raw: dict[str, Any] | None,
    app_version: str,
    schema_version: str,
    strict: bool,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    loaded = isinstance(policy_raw, dict)
    rows.append(_ok(check_id="release_policy_loaded", ok=loaded, value=loaded, expect="policy json loaded"))
    if not loaded:
        return rows

    policy = policy_raw if isinstance(policy_raw, dict) else {}
    pv = str(policy.get("app_version") or "")
    ps = str(((policy.get("state_schema") if isinstance(policy.get("state_schema"), dict) else {}) or {}).get("current") or "")

    mode = "enforce" if strict else "warn"
    rows.append(
        _ok(
            check_id="release_policy_app_version_match",
            ok=(pv == app_version and bool(pv)),
            value={"policy": pv, "code": app_version},
            expect="policy app_version equals code __version__",
            mode=mode,
        )
    )
    rows.append(
        _ok(
            check_id="release_policy_schema_match",
            ok=(ps == schema_version and bool(ps)),
            value={"policy": ps, "code": schema_version},
            expect="policy state_schema.current equals code schema_version",
            mode=mode,
        )
    )
    backward = (
        policy.get("state_schema").get("backward_read_compatible", [])
        if isinstance(policy.get("state_schema"), dict)
        else []
    )
    backward_ok = isinstance(backward, list) and schema_version in [str(x) for x in backward]
    rows.append(
        _ok(
            check_id="release_policy_backward_compat_contains_current",
            ok=bool(backward_ok),
            value=backward if isinstance(backward, list) else [],
            expect="current schema included in backward_read_compatible",
            mode=mode,
        )
    )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Release governance checks: versioning, schema compatibility, runtime data.")
    parser.add_argument("--init-file", default="writing_agent/__init__.py")
    parser.add_argument("--state-context-file", default="writing_agent/state_engine/context.py")
    parser.add_argument("--baseline", default="security/dependency_baseline.json")
    parser.add_argument("--policy", default="security/release_policy.json")
    parser.add_argument("--changes-file", default="CHANGES.md")
    parser.add_argument("--release-doc", default="docs/RELEASE_AND_ROLLBACK.md")
    parser.add_argument("--alert-policy", default="security/alert_escalation_policy.json")
    parser.add_argument("--trend-policy", default="security/performance_trend_policy.json")
    parser.add_argument("--capacity-policy", default="security/capacity_policy.json")
    parser.add_argument("--rollback-signature-policy", default="security/rollback_drill_signature_policy.json")
    parser.add_argument("--oncall-roster", default="security/oncall_roster.json")
    parser.add_argument("--ops-rbac-policy", default="security/ops_rbac_policy.json")
    parser.add_argument("--rollout-policy", default="security/release_rollout_policy.json")
    parser.add_argument("--rollout-adapter-contract", default="security/release_traffic_adapter_contract.json")
    parser.add_argument("--compat-matrix", default="security/release_compat_matrix.json")
    parser.add_argument("--data-dir", default=".data")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--require-changes-version", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    started = time.time()
    checks: list[dict[str, Any]] = []

    init_path = Path(str(args.init_file))
    state_path = Path(str(args.state_context_file))
    baseline_path = Path(str(args.baseline))
    policy_path = Path(str(args.policy))
    changes_path = Path(str(args.changes_file))
    release_doc_path = Path(str(args.release_doc))
    alert_policy_path = Path(str(args.alert_policy))
    trend_policy_path = Path(str(args.trend_policy))
    capacity_policy_path = Path(str(args.capacity_policy))
    rollback_signature_policy_path = Path(str(args.rollback_signature_policy))
    oncall_roster_path = Path(str(args.oncall_roster))
    ops_rbac_policy_path = Path(str(args.ops_rbac_policy))
    rollout_policy_path = Path(str(args.rollout_policy))
    rollout_adapter_contract_path = Path(str(args.rollout_adapter_contract))
    compat_matrix_path = Path(str(args.compat_matrix))
    data_dir = Path(str(args.data_dir))

    app_version = _extract_app_version(_load_text(init_path))
    schema_version = _extract_schema_version(_load_text(state_path))

    checks.append(
        _ok(
            check_id="app_version_semver",
            ok=_is_semver(app_version),
            value=app_version,
            expect="semantic version x.y.z",
        )
    )
    checks.append(
        _ok(
            check_id="state_schema_version_format",
            ok=_is_schema_version(schema_version),
            value=schema_version,
            expect="schema version x.y",
        )
    )

    policy_raw = _load_json(policy_path)
    checks.extend(
        _policy_checks(
            policy_raw=policy_raw if isinstance(policy_raw, dict) else None,
            app_version=app_version,
            schema_version=schema_version,
            strict=bool(args.strict),
        )
    )

    baseline_raw = _load_json(baseline_path)
    checks.append(
        _ok(
            check_id="dependency_baseline_valid",
            ok=_validate_dependency_baseline(baseline_raw if isinstance(baseline_raw, dict) else None),
            value=bool(isinstance(baseline_raw, dict)),
            expect="baseline json valid with levels",
        )
    )

    checks.extend(_runtime_json_checks(data_dir=data_dir, strict=bool(args.strict)))
    checks.extend(
        _policy_file_checks(
            alert_policy_path=alert_policy_path,
            trend_policy_path=trend_policy_path,
            capacity_policy_path=capacity_policy_path,
            rollback_signature_policy_path=rollback_signature_policy_path,
            oncall_roster_path=oncall_roster_path,
            ops_rbac_policy_path=ops_rbac_policy_path,
            rollout_policy_path=rollout_policy_path,
            rollout_adapter_contract_path=rollout_adapter_contract_path,
            compat_matrix_path=compat_matrix_path,
            strict=bool(args.strict),
        )
    )

    checks.append(
        _ok(
            check_id="release_doc_exists",
            ok=release_doc_path.exists(),
            value=release_doc_path.as_posix(),
            expect="docs/RELEASE_AND_ROLLBACK.md exists",
        )
    )
    checks.append(
        _ok(
            check_id="changes_doc_exists",
            ok=changes_path.exists(),
            value=changes_path.as_posix(),
            expect="changes doc exists",
            mode="warn",
        )
    )
    has_version_note = False
    if changes_path.exists():
        text = _load_text(changes_path)
        has_version_note = app_version in text if app_version else False
    checks.append(
        _ok(
            check_id="changes_mentions_current_version",
            ok=bool(has_version_note),
            value={"app_version": app_version, "matched": has_version_note},
            expect="changes doc mentions current app version",
            mode="enforce" if bool(args.require_changes_version) else "warn",
        )
    )

    enforce_rows = [row for row in checks if str(row.get("mode") or "enforce") == "enforce"]
    ended = time.time()
    report = {
        "ok": all(bool(row.get("ok")) for row in enforce_rows),
        "started_at": round(started, 3),
        "ended_at": round(ended, 3),
        "duration_s": round(ended - started, 3),
        "strict": bool(args.strict),
        "versions": {
            "app_version": app_version,
            "state_schema_version": schema_version,
        },
        "paths": {
            "init_file": init_path.as_posix(),
            "state_context_file": state_path.as_posix(),
            "baseline": baseline_path.as_posix(),
            "policy": policy_path.as_posix(),
            "changes_file": changes_path.as_posix(),
            "release_doc": release_doc_path.as_posix(),
            "alert_policy": alert_policy_path.as_posix(),
            "trend_policy": trend_policy_path.as_posix(),
            "capacity_policy": capacity_policy_path.as_posix(),
            "rollback_signature_policy": rollback_signature_policy_path.as_posix(),
            "oncall_roster": oncall_roster_path.as_posix(),
            "ops_rbac_policy": ops_rbac_policy_path.as_posix(),
            "rollout_policy": rollout_policy_path.as_posix(),
            "rollout_adapter_contract": rollout_adapter_contract_path.as_posix(),
            "compat_matrix": compat_matrix_path.as_posix(),
            "data_dir": data_dir.as_posix(),
        },
        "checks": checks,
    }
    out_default = Path(".data/out") / f"release_governance_{int(ended)}.json"
    out_path = Path(str(args.out or out_default))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report.get("ok")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
