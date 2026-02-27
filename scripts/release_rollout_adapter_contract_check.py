#!/usr/bin/env python3
"""Release Rollout Adapter Contract Check command utility.

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
    from scripts import release_rollout_executor
except Exception:
    _EXECUTOR_PATH = Path(__file__).with_name("release_rollout_executor.py")
    _SPEC = importlib.util.spec_from_file_location("release_rollout_executor", _EXECUTOR_PATH)
    if _SPEC is None or _SPEC.loader is None:
        raise
    release_rollout_executor = importlib.util.module_from_spec(_SPEC)
    _SPEC.loader.exec_module(release_rollout_executor)


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None


def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if not text:
        return bool(default)
    return text in {"1", "true", "yes", "on"}


def _check_row(*, check_id: str, ok: bool, value: Any, expect: str, mode: str = "enforce") -> dict[str, Any]:
    return {
        "id": str(check_id),
        "ok": bool(ok),
        "value": value,
        "expect": str(expect),
        "mode": str(mode or "enforce"),
    }


def _validate_adapter_row(
    *,
    item: dict[str, Any],
    index: int,
    required_placeholders: set[str],
    allowed_placeholders: set[str],
) -> dict[str, Any]:
    adapter_id = str(item.get("id") or f"adapter_{index}").strip()
    command_template = str(item.get("command_template") or "").strip()
    checks: list[dict[str, Any]] = []
    checks.append(
        _check_row(
            check_id="adapter_id_present",
            ok=bool(adapter_id),
            value=adapter_id,
            expect="adapter id must be non-empty",
        )
    )
    checks.append(
        _check_row(
            check_id="adapter_command_template_present",
            ok=bool(command_template),
            value=bool(command_template),
            expect="adapter command_template must be non-empty",
        )
    )
    validate_out = release_rollout_executor._validate_traffic_template(command_template)  # noqa: SLF001
    checks.append(
        _check_row(
            check_id="adapter_command_template_valid",
            ok=bool(validate_out.get("ok")),
            value=validate_out,
            expect="template braces and placeholders are valid",
        )
    )
    found_placeholders = {
        str(node).strip()
        for node in (
            validate_out.get("placeholders")
            if isinstance(validate_out.get("placeholders"), list)
            else []
        )
        if str(node).strip()
    }
    adapter_required = {
        str(node).strip()
        for node in (
            item.get("required_placeholders")
            if isinstance(item.get("required_placeholders"), list)
            else []
        )
        if str(node).strip()
    }
    combined_required = required_placeholders | adapter_required
    missing_required = sorted([name for name in combined_required if name not in found_placeholders])
    unknown_required = sorted([name for name in combined_required if name not in allowed_placeholders])
    checks.append(
        _check_row(
            check_id="adapter_required_placeholders_known",
            ok=len(unknown_required) == 0,
            value={"unknown_required_placeholders": unknown_required},
            expect="required placeholders must be subset of allowed placeholders",
        )
    )
    checks.append(
        _check_row(
            check_id="adapter_required_placeholders_present",
            ok=len(missing_required) == 0,
            value={"missing_required_placeholders": missing_required, "found_placeholders": sorted(found_placeholders)},
            expect="command template includes required placeholders",
        )
    )
    row_ok = all(bool(row.get("ok")) for row in checks)
    return {
        "id": adapter_id,
        "kind": str(item.get("kind") or "").strip(),
        "description": str(item.get("description") or "").strip(),
        "command_template": command_template,
        "ok": bool(row_ok),
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate release traffic adapter contract and command template examples.")
    parser.add_argument("--contract", default="security/release_traffic_adapter_contract.json")
    parser.add_argument("--command-template", default="")
    parser.add_argument("--require-runtime-command", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    started = time.time()
    checks: list[dict[str, Any]] = []

    contract_path = Path(str(args.contract))
    contract = _load_json(contract_path)
    checks.append(
        _check_row(
            check_id="contract_loaded",
            ok=isinstance(contract, dict),
            value=contract_path.as_posix(),
            expect="adapter contract json exists and valid",
            mode="enforce",
        )
    )

    node = contract if isinstance(contract, dict) else {}
    placeholders_node = node.get("placeholders") if isinstance(node.get("placeholders"), dict) else {}
    rules = node.get("rules") if isinstance(node.get("rules"), dict) else {}
    adapters = node.get("adapters") if isinstance(node.get("adapters"), list) else []

    supported_placeholders = set(release_rollout_executor.traffic_template_placeholders())
    allowed_placeholders = {
        str(name).strip()
        for name in (
            placeholders_node.get("allowed")
            if isinstance(placeholders_node.get("allowed"), list)
            else sorted(supported_placeholders)
        )
        if str(name).strip()
    }
    required_placeholders = {
        str(name).strip()
        for name in (
            placeholders_node.get("required")
            if isinstance(placeholders_node.get("required"), list)
            else ["action", "target_version"]
        )
        if str(name).strip()
    }
    recommended_placeholders = {
        str(name).strip()
        for name in (
            placeholders_node.get("recommended")
            if isinstance(placeholders_node.get("recommended"), list)
            else []
        )
        if str(name).strip()
    }

    unknown_allowed = sorted([name for name in allowed_placeholders if name not in supported_placeholders])
    missing_supported = sorted([name for name in supported_placeholders if name not in allowed_placeholders])
    unknown_required = sorted([name for name in required_placeholders if name not in allowed_placeholders])
    unknown_recommended = sorted([name for name in recommended_placeholders if name not in allowed_placeholders])

    checks.append(
        _check_row(
            check_id="contract_allowed_placeholders_supported",
            ok=len(unknown_allowed) == 0,
            value={"unknown_allowed_placeholders": unknown_allowed},
            expect="contract allowed placeholders should be subset of rollout executor supported placeholders",
        )
    )
    checks.append(
        _check_row(
            check_id="contract_required_placeholders_known",
            ok=len(unknown_required) == 0,
            value={"unknown_required_placeholders": unknown_required},
            expect="contract required placeholders should be subset of allowed placeholders",
        )
    )
    checks.append(
        _check_row(
            check_id="contract_recommended_placeholders_known",
            ok=len(unknown_recommended) == 0,
            value={"unknown_recommended_placeholders": unknown_recommended},
            expect="contract recommended placeholders should be subset of allowed placeholders",
            mode="warn",
        )
    )
    checks.append(
        _check_row(
            check_id="contract_has_all_supported_placeholders",
            ok=len(missing_supported) == 0,
            value={"missing_supported_placeholders": missing_supported},
            expect="contract allowed placeholders should include all currently supported rollout executor placeholders",
            mode="warn",
        )
    )

    require_examples = _safe_bool(rules.get("require_examples"), True)
    checks.append(
        _check_row(
            check_id="contract_has_examples",
            ok=(not require_examples) or (len(adapters) > 0),
            value={"adapters": len(adapters), "require_examples": require_examples},
            expect="adapter contract includes at least one example command template",
            mode="enforce",
        )
    )

    adapter_reports: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    duplicate_ids: list[str] = []
    for index, row in enumerate(adapters):
        if not isinstance(row, dict):
            adapter_reports.append(
                {
                    "id": f"adapter_{index}",
                    "ok": False,
                    "checks": [
                        _check_row(
                            check_id="adapter_row_type",
                            ok=False,
                            value=type(row).__name__,
                            expect="adapter row must be object",
                        )
                    ],
                }
            )
            continue
        rep = _validate_adapter_row(
            item=row,
            index=index,
            required_placeholders=required_placeholders,
            allowed_placeholders=allowed_placeholders,
        )
        adapter_id = str(rep.get("id") or "")
        if adapter_id in seen_ids:
            duplicate_ids.append(adapter_id)
        seen_ids.add(adapter_id)
        adapter_reports.append(rep)

    checks.append(
        _check_row(
            check_id="adapter_ids_unique",
            ok=len(duplicate_ids) == 0,
            value={"duplicate_ids": sorted(set(duplicate_ids))},
            expect="adapter ids must be unique",
            mode="enforce",
        )
    )
    checks.append(
        _check_row(
            check_id="all_adapter_examples_valid",
            ok=all(bool(item.get("ok")) for item in adapter_reports),
            value={
                "total_adapters": len(adapter_reports),
                "valid_adapters": sum(1 for item in adapter_reports if bool(item.get("ok"))),
            },
            expect="all adapter example rows should be valid",
            mode="enforce",
        )
    )

    runtime_template = str(args.command_template or "").strip()
    checks.append(
        _check_row(
            check_id="runtime_command_present_when_required",
            ok=(not bool(args.require_runtime_command)) or bool(runtime_template),
            value={
                "require_runtime_command": bool(args.require_runtime_command),
                "runtime_command_present": bool(runtime_template),
            },
            expect="runtime command template should be provided when required",
            mode="enforce" if bool(args.require_runtime_command or args.strict) else "warn",
        )
    )
    runtime_validation = release_rollout_executor._validate_traffic_template(runtime_template)  # noqa: SLF001
    runtime_placeholders = {
        str(name).strip()
        for name in (
            runtime_validation.get("placeholders")
            if isinstance(runtime_validation.get("placeholders"), list)
            else []
        )
        if str(name).strip()
    }
    runtime_missing_required = sorted([name for name in required_placeholders if name not in runtime_placeholders])
    runtime_missing_recommended = sorted([name for name in recommended_placeholders if name not in runtime_placeholders])
    checks.append(
        _check_row(
            check_id="runtime_command_template_valid",
            ok=(not runtime_template) or bool(runtime_validation.get("ok")),
            value=runtime_validation,
            expect="runtime command template syntax and placeholders are valid",
            mode="enforce" if bool(args.strict) else "warn",
        )
    )
    checks.append(
        _check_row(
            check_id="runtime_command_contains_required_placeholders",
            ok=(not runtime_template) or (len(runtime_missing_required) == 0),
            value={"missing_required_placeholders": runtime_missing_required},
            expect="runtime command template includes required placeholders",
            mode="enforce" if bool(args.strict) else "warn",
        )
    )
    checks.append(
        _check_row(
            check_id="runtime_command_contains_recommended_placeholders",
            ok=(not runtime_template) or (len(runtime_missing_recommended) == 0),
            value={"missing_recommended_placeholders": runtime_missing_recommended},
            expect="runtime command template includes recommended placeholders",
            mode="warn",
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
        "contract_path": contract_path.as_posix(),
        "supported_placeholders": sorted(supported_placeholders),
        "contract_placeholders": {
            "allowed": sorted(allowed_placeholders),
            "required": sorted(required_placeholders),
            "recommended": sorted(recommended_placeholders),
        },
        "runtime_command_template": runtime_template,
        "checks": checks,
        "adapters": adapter_reports,
    }
    out_default = Path(".data/out") / f"release_rollout_adapter_contract_{int(ended)}.json"
    out_path = Path(str(args.out or out_default))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report.get("ok")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
