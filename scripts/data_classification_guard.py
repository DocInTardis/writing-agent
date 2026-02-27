#!/usr/bin/env python3
"""Data Classification Guard command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
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


def _mask(value: str) -> str:
    text = str(value or "")
    if len(text) <= 4:
        return "***"
    if len(text) <= 8:
        return text[:1] + "***" + text[-1:]
    return text[:3] + "***" + text[-2:]


def _check_row(*, check_id: str, ok: bool, value: Any, expect: str, mode: str = "enforce") -> dict[str, Any]:
    return {
        "id": str(check_id),
        "ok": bool(ok),
        "value": value,
        "expect": str(expect),
        "mode": str(mode or "enforce"),
    }


def _load_json_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _collect_files(pattern: str) -> list[Path]:
    rows: list[Path] = []
    seen: set[str] = set()
    for raw in sorted(glob.glob(str(pattern), recursive=True)):
        path = Path(raw)
        if not path.exists() or (not path.is_file()):
            continue
        key = path.resolve().as_posix().lower()
        if key in seen:
            continue
        seen.add(key)
        rows.append(path)
    return rows


def _compile_patterns(policy: dict[str, Any]) -> tuple[list[tuple[str, re.Pattern[str]]], list[str]]:
    compiled: list[tuple[str, re.Pattern[str]]] = []
    errors: list[str] = []
    rows = policy.get("sensitive_patterns") if isinstance(policy.get("sensitive_patterns"), list) else []
    for index, item in enumerate(rows, start=1):
        if not isinstance(item, dict):
            continue
        rule_id = str(item.get("id") or f"pattern_{index}").strip() or f"pattern_{index}"
        raw = str(item.get("regex") or "").strip()
        if not raw:
            errors.append(f"{rule_id}:empty_regex")
            continue
        try:
            compiled.append((rule_id, re.compile(raw)))
        except re.error as exc:
            errors.append(f"{rule_id}:{exc}")
    return (compiled, errors)


def _scan_file(
    *,
    path: Path,
    patterns: list[tuple[str, re.Pattern[str]]],
    classification: str,
    rule_id: str,
    max_capture: int,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if max_capture <= 0:
        return findings
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return findings
    for line_no, raw_line in enumerate(str(text or "").splitlines(), start=1):
        line = str(raw_line or "")
        for pattern_id, pattern in patterns:
            for match in pattern.finditer(line):
                secret = str(match.group(0) or "")
                findings.append(
                    {
                        "path": path.as_posix(),
                        "line": line_no,
                        "rule_id": str(rule_id),
                        "classification": str(classification),
                        "pattern_id": str(pattern_id),
                        "masked_match": _mask(secret),
                    }
                )
                if len(findings) >= max_capture:
                    return findings
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Data classification and retention guard for operational artifacts.")
    parser.add_argument("--policy", default="security/data_classification_policy.json")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--require-rules", action="store_true", help="Require required=true rules to match files.")
    parser.add_argument("--max-unmasked-findings", type=int, default=-1, help="Override total finding threshold.")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    started = time.time()
    policy_path = Path(str(args.policy))
    policy = _load_json_dict(policy_path)

    checks: list[dict[str, Any]] = []
    checks.append(
        _check_row(
            check_id="policy_loaded",
            ok=bool(policy),
            value=policy_path.as_posix(),
            expect="classification policy should be valid json object",
            mode="enforce",
        )
    )

    patterns, pattern_errors = _compile_patterns(policy)
    checks.append(
        _check_row(
            check_id="sensitive_patterns_compiled",
            ok=len(pattern_errors) == 0 and len(patterns) > 0,
            value={"pattern_count": len(patterns), "errors": pattern_errors},
            expect="sensitive regex patterns should compile",
            mode="enforce",
        )
    )

    rules = policy.get("artifact_rules") if isinstance(policy.get("artifact_rules"), list) else []
    rule_summaries: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    retention_violations: list[dict[str, Any]] = []
    findings_by_class: dict[str, int] = {}
    all_files_count = 0
    max_capture = max(100, max(0, int(args.max_unmasked_findings)) + 200)
    now = time.time()

    for index, item in enumerate(rules, start=1):
        if not isinstance(item, dict):
            continue
        rule_id = str(item.get("id") or f"rule_{index}").strip() or f"rule_{index}"
        pattern = str(item.get("glob") or "").strip()
        classification = str(item.get("classification") or "internal").strip().lower() or "internal"
        required = bool(item.get("required"))
        max_age_days = max(0.0, _safe_float(item.get("max_age_days"), 0.0))
        files = _collect_files(pattern) if pattern else []
        all_files_count += len(files)
        rule_summaries.append(
            {
                "id": rule_id,
                "glob": pattern,
                "classification": classification,
                "required": required,
                "max_age_days": max_age_days,
                "files_count": len(files),
            }
        )
        checks.append(
            _check_row(
                check_id=f"rule_{rule_id}_matched_files",
                ok=(len(files) > 0) or (not required) or (not bool(args.require_rules)),
                value={"files_count": len(files), "glob": pattern, "required": required},
                expect="required rule should match at least one file",
                mode="enforce" if bool(args.strict or args.require_rules) else "warn",
            )
        )

        for path in files:
            if max_age_days > 0:
                age_days = max(0.0, (now - float(path.stat().st_mtime)) / 86400.0)
                if age_days > max_age_days:
                    retention_violations.append(
                        {
                            "path": path.as_posix(),
                            "rule_id": rule_id,
                            "classification": classification,
                            "age_days": round(age_days, 3),
                            "max_age_days": max_age_days,
                        }
                    )
            if len(findings) < max_capture:
                captured = _scan_file(
                    path=path,
                    patterns=patterns,
                    classification=classification,
                    rule_id=rule_id,
                    max_capture=max_capture - len(findings),
                )
                findings.extend(captured)
                findings_by_class[classification] = int(findings_by_class.get(classification, 0)) + len(captured)

    checks.append(
        _check_row(
            check_id="artifact_files_scanned",
            ok=all_files_count > 0,
            value=all_files_count,
            expect="at least one artifact file should be scanned",
            mode="enforce" if bool(args.strict) else "warn",
        )
    )
    checks.append(
        _check_row(
            check_id="retention_window_enforced",
            ok=len(retention_violations) == 0,
            value={"violations": len(retention_violations)},
            expect="artifact retention should respect max_age_days policy",
            mode="enforce",
        )
    )

    default_limit = max(0, _safe_int(policy.get("default_max_unmasked_findings"), 0))
    class_limits = policy.get("class_limits") if isinstance(policy.get("class_limits"), dict) else {}
    known_classes = sorted(set([*findings_by_class.keys(), *[str(x) for x in class_limits.keys()]]))
    for classification in known_classes:
        node = class_limits.get(classification) if isinstance(class_limits.get(classification), dict) else {}
        allowed = max(0, _safe_int(node.get("max_unmasked_findings"), default_limit))
        observed = max(0, _safe_int(findings_by_class.get(classification), 0))
        checks.append(
            _check_row(
                check_id=f"class_{classification}_unmasked_threshold",
                ok=observed <= allowed,
                value={"observed": observed, "allowed": allowed},
                expect="unmasked sensitive findings should stay within threshold",
                mode="enforce",
            )
        )

    if int(args.max_unmasked_findings) >= 0:
        checks.append(
            _check_row(
                check_id="override_total_unmasked_threshold",
                ok=len(findings) <= int(args.max_unmasked_findings),
                value={"observed": len(findings), "allowed": int(args.max_unmasked_findings)},
                expect="total findings should stay within override threshold",
                mode="enforce",
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
        "policy_file": policy_path.as_posix(),
        "strict": bool(args.strict),
        "require_rules": bool(args.require_rules),
        "rules": rule_summaries,
        "findings_by_class": findings_by_class,
        "findings": findings[:300],
        "retention_violations": retention_violations[:300],
        "checks": checks,
    }

    out_default = Path(".data/out") / f"data_classification_guard_{int(ended)}.json"
    out_path = Path(str(args.out or out_default))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report.get("ok")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
