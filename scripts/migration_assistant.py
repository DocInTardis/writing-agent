#!/usr/bin/env python3
"""Migration Assistant command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any


_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
_VERSION_RE = re.compile(r'__version__\s*=\s*"([^"]+)"')


def _is_semver(value: str) -> bool:
    return bool(_SEMVER_RE.match(str(value or "").strip()))


def _version_key(value: str) -> tuple[int, int, int, str]:
    raw = str(value or "").strip()
    if not _is_semver(raw):
        return (0, 0, 0, raw)
    main = raw.split("-", 1)[0].split("+", 1)[0]
    parts = [int(x) for x in main.split(".")]
    suffix = raw[len(main) :]
    return (parts[0], parts[1], parts[2], suffix)


def _load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _extract_version(path: Path) -> str:
    m = _VERSION_RE.search(_load_text(path))
    return str(m.group(1)).strip() if m else ""


def _load_json_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _check_row(*, check_id: str, ok: bool, value: Any, expect: str, mode: str = "enforce") -> dict[str, Any]:
    return {
        "id": str(check_id),
        "ok": bool(ok),
        "value": value,
        "expect": str(expect),
        "mode": str(mode or "enforce"),
    }


def _infer_from_version(*, cases: list[dict[str, Any]], to_version: str) -> str:
    candidates: list[str] = []
    for row in cases:
        if not isinstance(row, dict):
            continue
        if str(row.get("direction") or "").strip().lower() != "upgrade":
            continue
        if str(row.get("to_version") or "").strip() != str(to_version or "").strip():
            continue
        source = str(row.get("from_version") or "").strip()
        if _is_semver(source):
            candidates.append(source)
    if candidates:
        return sorted(set(candidates), key=_version_key)[0]
    for row in cases:
        if not isinstance(row, dict):
            continue
        source = str(row.get("from_version") or "").strip()
        if _is_semver(source):
            return source
    return str(to_version or "")


def _build_markdown(*, report: dict[str, Any]) -> str:
    checks = report.get("checks") if isinstance(report.get("checks"), list) else []
    failed = [row for row in checks if isinstance(row, dict) and str(row.get("mode") or "enforce") == "enforce" and (not bool(row.get("ok")))]
    lines = [
        "# Migration Assistant Report",
        "",
        f"- from: `{report.get('from_version')}`",
        f"- to: `{report.get('to_version')}`",
        f"- strict: `{bool(report.get('strict'))}`",
        f"- generated_at: `{report.get('ended_at')}`",
        "",
        "## Readiness",
        f"- overall_ok: `{bool(report.get('ok'))}`",
        f"- failed_enforce_checks: `{len(failed)}`",
        "",
        "## Planned Commands",
    ]
    for cmd in report.get("plan", []):
        lines.append(f"- `{cmd}`")
    lines.extend(["", "## Failing Enforce Checks"])
    if failed:
        for row in failed:
            lines.append(f"- `{row.get('id')}`: expected {row.get('expect')}, got {row.get('value')}")
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate guided upgrade/rollback migration plan and readiness report.")
    parser.add_argument("--from-version", default="")
    parser.add_argument("--to-version", default="")
    parser.add_argument("--init-file", default="writing_agent/__init__.py")
    parser.add_argument("--matrix", default="security/release_compat_matrix.json")
    parser.add_argument("--policy", default="security/release_policy.json")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--out", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()

    started = time.time()
    init_path = Path(str(args.init_file))
    matrix_path = Path(str(args.matrix))
    policy_path = Path(str(args.policy))
    init_version = _extract_version(init_path)
    to_version = str(args.to_version or "").strip() or init_version

    matrix = _load_json_dict(matrix_path)
    policy = _load_json_dict(policy_path)
    cases = [row for row in (matrix.get("cases") if isinstance(matrix.get("cases"), list) else []) if isinstance(row, dict)]
    from_version = str(args.from_version or "").strip() or _infer_from_version(cases=cases, to_version=to_version)

    checks: list[dict[str, Any]] = []
    checks.append(
        _check_row(
            check_id="matrix_loaded",
            ok=bool(matrix),
            value=matrix_path.as_posix(),
            expect="compatibility matrix should load",
            mode="enforce",
        )
    )
    checks.append(
        _check_row(
            check_id="policy_loaded",
            ok=bool(policy),
            value=policy_path.as_posix(),
            expect="release policy should load",
            mode="enforce",
        )
    )
    checks.append(
        _check_row(
            check_id="from_version_semver",
            ok=_is_semver(from_version),
            value=from_version,
            expect="from-version should be semantic version",
            mode="enforce",
        )
    )
    checks.append(
        _check_row(
            check_id="to_version_semver",
            ok=_is_semver(to_version),
            value=to_version,
            expect="to-version should be semantic version",
            mode="enforce",
        )
    )
    checks.append(
        _check_row(
            check_id="target_version_matches_init",
            ok=(not init_version) or (init_version == to_version),
            value={"init_version": init_version, "to_version": to_version},
            expect="migration target should match current package version",
            mode="enforce" if bool(args.strict) else "warn",
        )
    )

    upgrade_cases = [
        row
        for row in cases
        if str(row.get("direction") or "").strip().lower() == "upgrade"
        and str(row.get("to_version") or "").strip() == to_version
    ]
    exact_upgrade = [
        row
        for row in upgrade_cases
        if str(row.get("from_version") or "").strip() == from_version
    ]
    rollback_to_target = [
        row
        for row in cases
        if str(row.get("direction") or "").strip().lower() == "rollback"
        and str(row.get("to_version") or "").strip() == to_version
    ]

    checks.append(
        _check_row(
            check_id="upgrade_case_for_target_exists",
            ok=len(upgrade_cases) > 0,
            value={"to_version": to_version, "count": len(upgrade_cases)},
            expect="matrix should have at least one upgrade case for target version",
            mode="enforce",
        )
    )
    checks.append(
        _check_row(
            check_id="upgrade_case_exact_or_equivalent",
            ok=(len(exact_upgrade) > 0) or (from_version == to_version and len(upgrade_cases) > 0),
            value={"from_version": from_version, "to_version": to_version, "exact_count": len(exact_upgrade)},
            expect="matrix should cover exact from/to migration or already-on-target case",
            mode="enforce" if bool(args.strict) else "warn",
        )
    )
    checks.append(
        _check_row(
            check_id="rollback_path_to_target_exists",
            ok=len(rollback_to_target) > 0,
            value={"to_version": to_version, "count": len(rollback_to_target)},
            expect="matrix should provide rollback path landing to target version",
            mode="enforce",
        )
    )

    current_schema = str(
        (
            policy.get("state_schema")
            if isinstance(policy.get("state_schema"), dict)
            else {}
        ).get("current")
        or ""
    ).strip()
    checks.append(
        _check_row(
            check_id="policy_current_schema_present",
            ok=bool(current_schema),
            value=current_schema,
            expect="release policy should define current state schema",
            mode="enforce",
        )
    )

    plan = [
        "python scripts/create_rollback_bundle.py --label migration-pre --strict",
        "python scripts/release_compat_matrix.py --strict",
        "python scripts/release_preflight.py --quick",
        f"python scripts/release_rollout_executor.py --dry-run --target-version {to_version} --strict",
        "python scripts/verify_audit_chain.py --strict --require-log",
    ]
    if from_version != to_version:
        plan.append(f"# apply window: promote from {from_version} to {to_version} via rollout policy")
    else:
        plan.append("# already on target version: keep guardrails green and monitor")

    enforce_rows = [row for row in checks if str(row.get("mode") or "enforce") == "enforce"]
    ok = all(bool(row.get("ok")) for row in enforce_rows)
    ended = time.time()
    report = {
        "ok": bool(ok),
        "started_at": round(started, 3),
        "ended_at": round(ended, 3),
        "duration_s": round(ended - started, 3),
        "strict": bool(args.strict),
        "from_version": from_version,
        "to_version": to_version,
        "init_version": init_version,
        "matrix_file": matrix_path.as_posix(),
        "policy_file": policy_path.as_posix(),
        "current_schema": current_schema,
        "upgrade_case_count": len(upgrade_cases),
        "rollback_to_target_count": len(rollback_to_target),
        "plan": plan,
        "checks": checks,
    }

    out_default = Path(".data/out") / f"migration_assistant_{int(ended)}.json"
    out_path = Path(str(args.out or out_default))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    md_path = Path(str(args.out_md or Path(".data/out") / f"migration_assistant_{int(ended)}.md"))
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(_build_markdown(report=report), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report.get("ok")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
