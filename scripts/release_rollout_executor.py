#!/usr/bin/env python3
"""Release Rollout Executor command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations
import argparse
import glob
import importlib.util
import json
import os
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any
from scripts import release_rollout_template_utils as rollout_template_utils

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
VERSION_RE = re.compile(r'__version__\s*=\s*"([^"]+)"')
_TRUTHY = {"1", "true", "yes", "on"}
try:
    from scripts import audit_chain
except Exception:
    _AUDIT_CHAIN_PATH = Path(__file__).with_name("audit_chain.py")
    _AUDIT_SPEC = importlib.util.spec_from_file_location("audit_chain", _AUDIT_CHAIN_PATH)
    if _AUDIT_SPEC is None or _AUDIT_SPEC.loader is None:
        raise
    audit_chain = importlib.util.module_from_spec(_AUDIT_SPEC)
    _AUDIT_SPEC.loader.exec_module(audit_chain)
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

def _safe_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if not text:
        return bool(default)
    return text in _TRUTHY

def _is_semver(text: str) -> bool:
    return bool(SEMVER_RE.match(str(text or "").strip()))

def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None

def _load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""

def _extract_app_version(path: Path) -> str:
    m = VERSION_RE.search(_load_text(path))
    return str(m.group(1)).strip() if m else ""

def _check_row(*, check_id: str, ok: bool, value: Any, expect: str, mode: str) -> dict[str, Any]:
    return {
        "id": str(check_id),
        "ok": bool(ok),
        "value": value,
        "expect": str(expect),
        "mode": str(mode or "warn"),
    }

def _empty_store() -> dict[str, Any]:
    return {
        "version": 1,
        "updated_at": 0.0,
        "channels": {
            "canary": {"version": "", "rollout_percent": 5, "updated_at": 0.0},
            "stable": {"version": "", "rollout_percent": 100, "updated_at": 0.0},
        },
        "history": [],
    }

def _load_store(path: Path) -> dict[str, Any]:
    raw: Any = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            raw = {}
    base = _empty_store()
    if not isinstance(raw, dict):
        return base
    channels_raw = raw.get("channels") if isinstance(raw.get("channels"), dict) else {}
    history_raw = raw.get("history") if isinstance(raw.get("history"), list) else []
    out = {
        "version": int(raw.get("version") or 1),
        "updated_at": float(raw.get("updated_at") or 0.0),
        "channels": {
            "canary": {
                "version": str(
                    ((channels_raw.get("canary") if isinstance(channels_raw.get("canary"), dict) else {}) or {}).get(
                        "version"
                    )
                    or ""
                ),
                "rollout_percent": int(
                    ((channels_raw.get("canary") if isinstance(channels_raw.get("canary"), dict) else {}) or {}).get(
                        "rollout_percent"
                    )
                    or 0
                ),
                "updated_at": float(
                    ((channels_raw.get("canary") if isinstance(channels_raw.get("canary"), dict) else {}) or {}).get(
                        "updated_at"
                    )
                    or 0.0
                ),
            },
            "stable": {
                "version": str(
                    ((channels_raw.get("stable") if isinstance(channels_raw.get("stable"), dict) else {}) or {}).get(
                        "version"
                    )
                    or ""
                ),
                "rollout_percent": int(
                    ((channels_raw.get("stable") if isinstance(channels_raw.get("stable"), dict) else {}) or {}).get(
                        "rollout_percent"
                    )
                    or 0
                ),
                "updated_at": float(
                    ((channels_raw.get("stable") if isinstance(channels_raw.get("stable"), dict) else {}) or {}).get(
                        "updated_at"
                    )
                    or 0.0
                ),
            },
        },
        "history": [row for row in history_raw if isinstance(row, dict)],
    }
    return out

def _save_store(path: Path, store: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)

def _append_history(
    store: dict[str, Any],
    *,
    action: str,
    channel: str,
    from_version: str,
    to_version: str,
    reason: str,
    actor: str,
    correlation_id: str,
    release_candidate_id: str,
) -> None:
    rows = store.get("history") if isinstance(store.get("history"), list) else []
    now = round(time.time(), 3)
    rows.append(
        {
            "ts": now,
            "action": str(action),
            "channel": str(channel),
            "from_version": str(from_version),
            "to_version": str(to_version),
            "reason": str(reason),
            "actor": str(actor),
            "correlation_id": str(correlation_id or ""),
            "release_candidate_id": str(release_candidate_id or ""),
        }
    )
    store["history"] = rows[-300:]
    store["updated_at"] = now

def _latest_report(pattern: str) -> Path | None:
    rows = sorted((Path(p) for p in glob.glob(pattern)), key=lambda p: p.stat().st_mtime if p.exists() else 0.0)
    if not rows:
        return None
    return rows[-1]

def traffic_template_placeholders() -> list[str]:
    return rollout_template_utils.traffic_template_placeholders()

def _extract_template_placeholders(template: str) -> tuple[list[str], str]:
    return rollout_template_utils.extract_template_placeholders(template)

def _validate_traffic_template(command_template: str) -> dict[str, Any]:
    return rollout_template_utils.validate_traffic_template(command_template)

def _normalize_stage(values: list[Any], *, fallback: list[int]) -> list[int]:
    out = sorted({max(0, min(100, _safe_int(item, 0))) for item in values if _safe_int(item, -1) >= 0})
    if out:
        return out
    return sorted({max(0, min(100, _safe_int(item, 0))) for item in fallback})

def _latest_canary_change_ts(history_rows: list[dict[str, Any]], *, target_version: str, fallback_ts: float) -> float:
    for row in reversed(history_rows):
        if str(row.get("channel") or "") != "canary":
            continue
        if str(row.get("to_version") or "") != target_version:
            continue
        if str(row.get("action") or "") not in {"set", "rollout"}:
            continue
        return _safe_float(row.get("ts"), fallback_ts)
    return float(fallback_ts)

def _next_stage(current: int, stages: list[int]) -> int | None:
    for stage in stages:
        if int(stage) > int(current):
            return int(stage)
    return None

def _plan_action(
    *,
    target_version: str,
    canary_version: str,
    stable_version: str,
    canary_rollout: int,
    stable_rollout: int,
    canary_stages: list[int],
) -> dict[str, Any]:
    if stable_version == target_version and stable_rollout >= 100:
        return {"action": "noop", "reason": "target_already_stable"}
    if canary_version != target_version:
        start_rollout = int(canary_stages[0]) if canary_stages else 5
        return {
            "action": "set_canary",
            "target_version": target_version,
            "rollout_percent": start_rollout,
            "reason": "start_canary_stage",
        }
    if stable_version != target_version:
        next_rollout = _next_stage(canary_rollout, canary_stages)
        if next_rollout is not None:
            return {
                "action": "rollout_canary",
                "target_version": target_version,
                "from_rollout_percent": int(canary_rollout),
                "rollout_percent": int(next_rollout),
                "reason": "advance_canary_stage",
            }
        return {
            "action": "promote_stable",
            "target_version": target_version,
            "rollout_percent": 100,
            "reason": "canary_stages_completed",
        }
    if stable_rollout < 100:
        return {
            "action": "rollout_stable",
            "target_version": target_version,
            "from_rollout_percent": int(stable_rollout),
            "rollout_percent": 100,
            "reason": "normalize_stable_rollout",
        }
    return {"action": "noop", "reason": "no_change_needed"}

def _gates_check(
    *,
    now_ts: float,
    policy: dict[str, Any],
    strict: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    checks: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    gates = policy.get("gates") if isinstance(policy.get("gates"), dict) else {}
    rows = gates.get("required_reports") if isinstance(gates.get("required_reports"), list) else []
    for item in rows:
        if not isinstance(item, dict):
            continue
        gate_id = str(item.get("id") or "gate")
        pattern = str(item.get("pattern") or "").strip()
        max_age_s = max(1.0, _safe_float(item.get("max_age_s"), 7 * 24 * 3600.0))
        required = _safe_bool(item.get("required"), True)
        require_ok = _safe_bool(item.get("require_ok"), True)
        mode = "enforce" if (strict and required) else "warn"
        report_path = _latest_report(pattern) if pattern else None
        raw = _load_json(report_path) if isinstance(report_path, Path) else None
        report_ts = 0.0
        if isinstance(raw, dict):
            report_ts = _safe_float(raw.get("ended_at"), 0.0)
            if report_ts <= 0:
                report_ts = _safe_float(raw.get("generated_at"), 0.0)
            if report_ts <= 0:
                report_ts = _safe_float(raw.get("started_at"), 0.0)
        if report_ts <= 0 and isinstance(report_path, Path) and report_path.exists():
            report_ts = _safe_float(report_path.stat().st_mtime, 0.0)
        age_s = (now_ts - report_ts) if report_ts > 0 else float("inf")
        report_ok = bool((raw or {}).get("ok")) if isinstance(raw, dict) else False
        exists_ok = isinstance(raw, dict)
        fresh_ok = age_s <= max_age_s
        gate_ok = exists_ok and fresh_ok and ((not require_ok) or report_ok)
        checks.append(
            _check_row(
                check_id=f"gate::{gate_id}",
                ok=gate_ok,
                value={
                    "pattern": pattern,
                    "report_path": report_path.as_posix() if isinstance(report_path, Path) else "",
                    "exists": exists_ok,
                    "report_ok": report_ok,
                    "age_s": round(age_s, 3) if age_s != float("inf") else "inf",
                    "max_age_s": max_age_s,
                    "required": required,
                    "require_ok": require_ok,
                },
                expect="gate report exists, fresh, and healthy",
                mode=mode,
            )
        )
        evidence.append(
            {
                "id": gate_id,
                "pattern": pattern,
                "required": required,
                "require_ok": require_ok,
                "report_path": report_path.as_posix() if isinstance(report_path, Path) else "",
                "report_exists": exists_ok,
                "report_ok": report_ok,
                "age_s": round(age_s, 3) if age_s != float("inf") else "inf",
                "max_age_s": max_age_s,
                "passed": gate_ok,
            }
        )
    return checks, evidence

def _traffic_template_context(
    *,
    plan: dict[str, Any],
    apply_result: dict[str, Any],
    store_before: dict[str, Any],
    store_after: dict[str, Any],
    correlation_id: str,
    release_candidate_id: str,
) -> dict[str, str]:
    return rollout_template_utils.build_traffic_template_context(
        plan=plan,
        apply_result=apply_result,
        store_before=store_before,
        store_after=store_after,
        correlation_id=correlation_id,
        release_candidate_id=release_candidate_id,
        safe_int_fn=_safe_int,
    )

def _run_traffic_apply_command(
    *,
    command_template: str,
    template_context: dict[str, str],
    timeout_s: float,
) -> dict[str, Any]:
    raw_template = str(command_template or "").strip()
    if not raw_template:
        return {
            "executed": False,
            "ok": False,
            "reason": "empty_command",
            "command_template": "",
            "command_rendered": "",
            "command_argv": [],
            "return_code": -1,
            "stdout": "",
            "stderr": "",
        }
    try:
        rendered = raw_template.format(**template_context)
    except Exception as exc:
        return {
            "executed": False,
            "ok": False,
            "reason": f"template_render_error:{exc.__class__.__name__}:{exc}",
            "command_template": raw_template,
            "command_rendered": "",
            "command_argv": [],
            "return_code": -1,
            "stdout": "",
            "stderr": "",
        }
    try:
        argv = shlex.split(rendered, posix=(os.name != "nt"))
    except Exception as exc:
        return {
            "executed": False,
            "ok": False,
            "reason": f"argv_parse_error:{exc.__class__.__name__}:{exc}",
            "command_template": raw_template,
            "command_rendered": rendered,
            "command_argv": [],
            "return_code": -1,
            "stdout": "",
            "stderr": "",
        }
    if not argv:
        return {
            "executed": False,
            "ok": False,
            "reason": "empty_argv_after_render",
            "command_template": raw_template,
            "command_rendered": rendered,
            "command_argv": [],
            "return_code": -1,
            "stdout": "",
            "stderr": "",
        }
    try:
        proc = subprocess.run(
            argv,
            check=False,
            text=True,
            capture_output=True,
            timeout=max(0.1, float(timeout_s)),
        )
        return {
            "executed": True,
            "ok": int(proc.returncode) == 0,
            "reason": "ok" if int(proc.returncode) == 0 else f"non_zero_exit:{int(proc.returncode)}",
            "command_template": raw_template,
            "command_rendered": rendered,
            "command_argv": argv,
            "return_code": int(proc.returncode),
            "stdout": str(proc.stdout or "")[-4000:],
            "stderr": str(proc.stderr or "")[-4000:],
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "executed": True,
            "ok": False,
            "reason": "timeout",
            "command_template": raw_template,
            "command_rendered": rendered,
            "command_argv": argv,
            "return_code": -1,
            "stdout": str(getattr(exc, "stdout", "") or "")[-4000:],
            "stderr": str(getattr(exc, "stderr", "") or "")[-4000:],
        }
    except Exception as exc:
        return {
            "executed": True,
            "ok": False,
            "reason": f"exec_error:{exc.__class__.__name__}:{exc}",
            "command_template": raw_template,
            "command_rendered": rendered,
            "command_argv": argv,
            "return_code": -1,
            "stdout": "",
            "stderr": "",
        }

def _apply_action(
    *,
    store: dict[str, Any],
    plan: dict[str, Any],
    actor: str,
    reason: str,
    correlation_id: str,
    release_candidate_id: str,
) -> dict[str, Any]:
    channels = store.get("channels") if isinstance(store.get("channels"), dict) else {}
    canary = channels.get("canary") if isinstance(channels.get("canary"), dict) else {}
    stable = channels.get("stable") if isinstance(channels.get("stable"), dict) else {}
    action = str(plan.get("action") or "noop")
    now = round(time.time(), 3)
    details: dict[str, Any] = {"applied": False, "action": action}

    if action == "set_canary":
        target_version = str(plan.get("target_version") or "")
        target_rollout = max(0, min(100, _safe_int(plan.get("rollout_percent"), 5)))
        old_version = str(canary.get("version") or "")
        canary["version"] = target_version
        canary["rollout_percent"] = target_rollout
        canary["updated_at"] = now
        channels["canary"] = canary
        store["channels"] = channels
        _append_history(
            store,
            action="set",
            channel="canary",
            from_version=old_version,
            to_version=target_version,
            reason=reason or "start canary rollout",
            actor=actor,
            correlation_id=correlation_id,
            release_candidate_id=release_candidate_id,
        )
        details.update(
            {
                "applied": True,
                "target_version": target_version,
                "rollout_percent": target_rollout,
                "from_version": old_version,
            }
        )
        return details

    if action == "rollout_canary":
        target_version = str(plan.get("target_version") or "")
        from_rollout = _safe_int(canary.get("rollout_percent"), 0)
        target_rollout = max(0, min(100, _safe_int(plan.get("rollout_percent"), from_rollout)))
        canary["rollout_percent"] = target_rollout
        canary["updated_at"] = now
        channels["canary"] = canary
        store["channels"] = channels
        _append_history(
            store,
            action="rollout",
            channel="canary",
            from_version=target_version,
            to_version=target_version,
            reason=reason or f"canary rollout {from_rollout}->{target_rollout}",
            actor=actor,
            correlation_id=correlation_id,
            release_candidate_id=release_candidate_id,
        )
        details.update(
            {
                "applied": True,
                "target_version": target_version,
                "from_rollout_percent": from_rollout,
                "rollout_percent": target_rollout,
            }
        )
        return details

    if action == "promote_stable":
        target_version = str(plan.get("target_version") or "")
        old_version = str(stable.get("version") or "")
        stable["version"] = target_version
        stable["rollout_percent"] = 100
        stable["updated_at"] = now
        channels["stable"] = stable
        store["channels"] = channels
        _append_history(
            store,
            action="promote",
            channel="canary->stable",
            from_version=old_version,
            to_version=target_version,
            reason=reason or "promote canary to stable",
            actor=actor,
            correlation_id=correlation_id,
            release_candidate_id=release_candidate_id,
        )
        details.update(
            {
                "applied": True,
                "target_version": target_version,
                "from_version": old_version,
                "rollout_percent": 100,
            }
        )
        return details

    if action == "rollout_stable":
        target_version = str(plan.get("target_version") or "")
        from_rollout = _safe_int(stable.get("rollout_percent"), 0)
        stable["rollout_percent"] = 100
        stable["updated_at"] = now
        channels["stable"] = stable
        store["channels"] = channels
        _append_history(
            store,
            action="rollout",
            channel="stable",
            from_version=target_version,
            to_version=target_version,
            reason=reason or f"stable rollout {from_rollout}->100",
            actor=actor,
            correlation_id=correlation_id,
            release_candidate_id=release_candidate_id,
        )
        details.update(
            {
                "applied": True,
                "target_version": target_version,
                "from_rollout_percent": from_rollout,
                "rollout_percent": 100,
            }
        )
        return details

    details.update({"applied": False, "reason": str(plan.get("reason") or "no-op")})
    return details

def main() -> int:
    parser = argparse.ArgumentParser(description="Automated staged release rollout executor (canary -> stable).")
    parser.add_argument("--channels-file", default="security/release_channels.json")
    parser.add_argument("--policy", default="security/release_rollout_policy.json")
    parser.add_argument("--init-file", default="writing_agent/__init__.py")
    parser.add_argument("--target-version", default="")
    parser.add_argument("--actor", default="release-bot")
    parser.add_argument("--reason", default="")
    parser.add_argument("--correlation-id", default="")
    parser.add_argument("--release-candidate-id", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--apply", action="store_true", help="Apply rollout action to channels file.")
    parser.add_argument("--traffic-apply-command", default="")
    parser.add_argument("--traffic-apply-timeout-s", type=float, default=30.0)
    parser.add_argument("--traffic-apply-required", action="store_true")
    parser.add_argument("--audit-log", default="")
    parser.add_argument("--audit-state-file", default="")
    parser.add_argument("--skip-audit-log", action="store_true")
    parser.add_argument("--audit-strict", action="store_true")
    parser.add_argument("--allow-gate-failures", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    started = time.time()
    checks: list[dict[str, Any]] = []
    mode = "enforce" if bool(args.strict) else "warn"

    channels_path = Path(str(args.channels_file))
    policy_path = Path(str(args.policy))
    init_path = Path(str(args.init_file))

    store = _load_store(channels_path)
    policy = _load_json(policy_path) if isinstance(_load_json(policy_path), dict) else {}
    target_version = str(args.target_version or "").strip() or _extract_app_version(init_path)
    run_apply = bool(args.apply) and (not bool(args.dry_run))
    traffic_apply_command = str(args.traffic_apply_command or "").strip()
    traffic_apply_timeout_s = max(0.1, _safe_float(args.traffic_apply_timeout_s, 30.0))
    traffic_apply_required = bool(args.traffic_apply_required)
    correlation_id = str(args.correlation_id or os.environ.get("WA_RELEASE_CORRELATION_ID", "")).strip()
    release_candidate_id = str(args.release_candidate_id or os.environ.get("WA_RELEASE_CANDIDATE_ID", "")).strip()
    if not release_candidate_id and correlation_id:
        release_candidate_id = correlation_id
    if not correlation_id and release_candidate_id:
        correlation_id = release_candidate_id
    if not correlation_id:
        correlation_id = f"rollout-{int(started)}"
    if not release_candidate_id:
        release_candidate_id = f"rc-{str(target_version).replace('.', '-')}-{int(started)}"

    checks.append(
        _check_row(
            check_id="channels_store_loaded",
            ok=isinstance(store, dict),
            value=channels_path.as_posix(),
            expect="release channels store is available",
            mode="enforce",
        )
    )
    checks.append(
        _check_row(
            check_id="rollout_policy_loaded",
            ok=isinstance(policy, dict),
            value=policy_path.as_posix(),
            expect="rollout policy is available",
            mode="enforce",
        )
    )
    checks.append(
        _check_row(
            check_id="target_version_semver",
            ok=_is_semver(target_version),
            value=target_version,
            expect="semantic version x.y.z",
            mode="enforce",
        )
    )
    checks.append(
        _check_row(
            check_id="correlation_id_present",
            ok=bool(correlation_id),
            value=correlation_id,
            expect="correlation id should be present for rollout traceability",
            mode="enforce",
        )
    )
    checks.append(
        _check_row(
            check_id="release_candidate_id_present",
            ok=bool(release_candidate_id),
            value=release_candidate_id,
            expect="release candidate id should be present for rollout traceability",
            mode="enforce",
        )
    )

    channels = store.get("channels") if isinstance(store.get("channels"), dict) else {}
    canary = channels.get("canary") if isinstance(channels.get("canary"), dict) else {}
    stable = channels.get("stable") if isinstance(channels.get("stable"), dict) else {}
    history_rows = store.get("history") if isinstance(store.get("history"), list) else []

    canary_version = str(canary.get("version") or "")
    stable_version = str(stable.get("version") or "")
    canary_rollout = _safe_int(canary.get("rollout_percent"), 0)
    stable_rollout = _safe_int(stable.get("rollout_percent"), 0)
    canary_updated_at = _safe_float(canary.get("updated_at"), 0.0)

    stages = policy.get("stages") if isinstance(policy.get("stages"), dict) else {}
    canary_stages = _normalize_stage(
        stages.get("canary") if isinstance(stages.get("canary"), list) else [],
        fallback=[5, 20, 50],
    )
    stable_stages = _normalize_stage(
        stages.get("stable") if isinstance(stages.get("stable"), list) else [],
        fallback=[100],
    )
    min_stage_observe_s = max(0.0, _safe_float(stages.get("min_stage_observe_s"), 1800.0))
    if not stable_stages or stable_stages[-1] != 100:
        stable_stages = [100]

    gate_checks, gate_evidence = _gates_check(now_ts=started, policy=policy, strict=bool(args.strict))
    checks.extend(gate_checks)
    gate_failed_required = any(
        (not bool(row.get("passed")))
        and bool(row.get("required"))
        for row in gate_evidence
    )

    plan = _plan_action(
        target_version=target_version,
        canary_version=canary_version,
        stable_version=stable_version,
        canary_rollout=canary_rollout,
        stable_rollout=stable_rollout,
        canary_stages=canary_stages,
    )

    observe_ok = True
    observe_details: dict[str, Any] = {"required": False}
    action = str(plan.get("action") or "noop")
    if action in {"rollout_canary", "promote_stable"}:
        latest_canary_ts = _latest_canary_change_ts(
            history_rows if isinstance(history_rows, list) else [],
            target_version=target_version,
            fallback_ts=canary_updated_at,
        )
        observe_delta_s = (started - latest_canary_ts) if latest_canary_ts > 0 else float("inf")
        observe_ok = observe_delta_s >= min_stage_observe_s
        observe_details = {
            "required": True,
            "min_stage_observe_s": min_stage_observe_s,
            "latest_canary_change_ts": round(latest_canary_ts, 3) if latest_canary_ts > 0 else 0.0,
            "observe_delta_s": round(observe_delta_s, 3) if observe_delta_s != float("inf") else "inf",
        }
    checks.append(
        _check_row(
            check_id="canary_observation_window_met",
            ok=observe_ok,
            value=observe_details,
            expect="canary has been observed for minimum stage interval",
            mode=mode,
        )
    )

    gate_allow = bool(args.allow_gate_failures)
    apply_blocked = (gate_failed_required and (not gate_allow)) or (not observe_ok)
    should_execute_traffic = bool(run_apply) and action in {"set_canary", "rollout_canary", "promote_stable", "rollout_stable"}
    traffic_template_check = _validate_traffic_template(traffic_apply_command)
    traffic_template_invalid = bool(traffic_apply_command) and (not bool(traffic_template_check.get("ok")))
    if should_execute_traffic and traffic_template_invalid:
        apply_blocked = True
    checks.append(
        _check_row(
            check_id="traffic_apply_template_valid",
            ok=(not should_execute_traffic) or (not bool(traffic_apply_command)) or (not traffic_template_invalid),
            value=traffic_template_check,
            expect="traffic apply command template only uses supported placeholders and valid braces",
            mode="enforce" if bool(args.strict or traffic_apply_required) else "warn",
        )
    )
    checks.append(
        _check_row(
            check_id="traffic_apply_command_present_when_required",
            ok=(not should_execute_traffic) or (not traffic_apply_required) or bool(traffic_apply_command),
            value={
                "should_execute_traffic": should_execute_traffic,
                "traffic_apply_required": traffic_apply_required,
                "traffic_apply_command_present": bool(traffic_apply_command),
            },
            expect="traffic apply command should be provided when traffic apply is required",
            mode="enforce" if bool(traffic_apply_required) else "warn",
        )
    )
    checks.append(
        _check_row(
            check_id="rollout_apply_not_blocked",
            ok=(not run_apply) or (not apply_blocked),
            value={
                "run_apply": run_apply,
                "gate_failed_required": gate_failed_required,
                "allow_gate_failures": gate_allow,
                "observe_ok": observe_ok,
                "traffic_template_invalid": traffic_template_invalid,
            },
            expect="apply mode requires healthy gates and observation window unless override",
            mode="enforce",
        )
    )

    apply_result: dict[str, Any] = {
        "applied": False,
        "action": action,
        "blocked": bool(apply_blocked),
        "dry_run": bool(args.dry_run) or (not run_apply),
        "correlation_id": correlation_id,
        "release_candidate_id": release_candidate_id,
    }
    store_before_apply = json.loads(json.dumps(store, ensure_ascii=False))
    if run_apply and (not apply_blocked):
        reason = str(args.reason or "").strip() or str(plan.get("reason") or "rollout execution")
        apply_result = _apply_action(
            store=store,
            plan=plan,
            actor=str(args.actor or "release-bot"),
            reason=reason,
            correlation_id=correlation_id,
            release_candidate_id=release_candidate_id,
        )
        traffic_result: dict[str, Any] = {
            "executed": False,
            "ok": True,
            "reason": "not_required",
            "command_template": traffic_apply_command,
            "command_rendered": "",
            "command_argv": [],
            "return_code": 0,
            "stdout": "",
            "stderr": "",
        }
        if should_execute_traffic:
            if traffic_apply_command:
                traffic_context = _traffic_template_context(
                    plan=plan,
                    apply_result=apply_result,
                    store_before=store_before_apply,
                    store_after=store,
                    correlation_id=correlation_id,
                    release_candidate_id=release_candidate_id,
                )
                traffic_result = _run_traffic_apply_command(
                    command_template=traffic_apply_command,
                    template_context=traffic_context,
                    timeout_s=traffic_apply_timeout_s,
                )
            elif traffic_apply_required:
                traffic_result = {
                    "executed": False,
                    "ok": False,
                    "reason": "required_command_missing",
                    "command_template": "",
                    "command_rendered": "",
                    "command_argv": [],
                    "return_code": -1,
                    "stdout": "",
                    "stderr": "",
                }
            else:
                traffic_result = {
                    "executed": False,
                    "ok": True,
                    "reason": "optional_command_missing",
                    "command_template": "",
                    "command_rendered": "",
                    "command_argv": [],
                    "return_code": 0,
                    "stdout": "",
                    "stderr": "",
                }
        apply_result["traffic_apply"] = traffic_result
        apply_result["correlation_id"] = correlation_id
        apply_result["release_candidate_id"] = release_candidate_id
        if bool(traffic_result.get("ok")):
            _save_store(channels_path, store)
        else:
            _save_store(channels_path, store_before_apply)
            store = store_before_apply
            apply_result["applied"] = False
            apply_result["reverted"] = True
            apply_result["blocked"] = True
    elif (not run_apply) and (not bool(args.dry_run)):
        # Default mode is planning-only unless --apply is set.
        apply_result["dry_run"] = True
        apply_result["reason"] = "planning_only_run"
    if should_execute_traffic:
        traffic_row = apply_result.get("traffic_apply") if isinstance(apply_result.get("traffic_apply"), dict) else {}
        checks.append(
            _check_row(
                check_id="traffic_apply_command_ok",
                ok=bool((traffic_row or {}).get("ok")),
                value=traffic_row or {},
                expect="traffic apply command executes successfully",
                mode="enforce" if (bool(args.strict) or bool(traffic_apply_required)) else "warn",
            )
        )

    enforce_rows = [row for row in checks if str(row.get("mode") or "warn") == "enforce"]
    ok = all(bool(row.get("ok")) for row in enforce_rows)

    next_actions: list[str] = []
    if gate_failed_required and (not gate_allow):
        next_actions.append("Required rollout gates failed: rerun release guards/preflight until gate reports become healthy.")
    if action == "set_canary":
        next_actions.append("Start canary with target version; continue observing before next stage.")
    elif action == "rollout_canary":
        next_actions.append("Canary stage advanced; wait observation window and rerun executor for next stage.")
    elif action == "promote_stable":
        next_actions.append("Promote canary to stable and continue post-release observation.")
    elif action == "noop":
        next_actions.append("Rollout already converged for target version.")
    if run_apply and apply_blocked:
        next_actions.append("Apply mode was blocked by gate/observe checks. Use --allow-gate-failures only for emergency cases.")

    ended = time.time()
    report = {
        "ok": bool(ok),
        "started_at": round(started, 3),
        "ended_at": round(ended, 3),
        "duration_s": round(ended - started, 3),
        "strict": bool(args.strict),
        "dry_run": bool(args.dry_run) or (not run_apply),
        "run_apply": bool(run_apply),
        "target_version": target_version,
        "correlation": {
            "correlation_id": correlation_id,
            "release_candidate_id": release_candidate_id,
        },
        "channels_file": channels_path.as_posix(),
        "policy_file": policy_path.as_posix(),
        "state": {
            "canary_version": canary_version,
            "stable_version": stable_version,
            "canary_rollout_percent": canary_rollout,
            "stable_rollout_percent": stable_rollout,
            "history_entries": len(history_rows) if isinstance(history_rows, list) else 0,
        },
        "stages": {
            "canary": canary_stages,
            "stable": stable_stages,
            "min_stage_observe_s": min_stage_observe_s,
        },
        "plan": plan,
        "apply_result": apply_result,
        "gate_evidence": gate_evidence,
        "checks": checks,
        "next_actions": next_actions,
    }

    audit_result: dict[str, Any] = {"ok": True, "skipped": True}
    if not bool(args.skip_audit_log):
        audit_result = audit_chain.record_operation(
            action="release_rollout_execute",
            actor=str(args.actor or "release-bot"),
            source="release_rollout_executor",
            status="ok" if bool(report.get("ok")) else "failed",
            context={
                "target_version": target_version,
                "plan_action": str(plan.get("action") or ""),
                "run_apply": bool(run_apply),
                "dry_run": bool(args.dry_run) or (not run_apply),
                "strict": bool(args.strict),
                "report_ok": bool(report.get("ok")),
                "apply_applied": bool((apply_result or {}).get("applied")),
                "apply_blocked": bool((apply_result or {}).get("blocked")),
                "correlation_id": correlation_id,
                "release_candidate_id": release_candidate_id,
            },
            log_path=str(args.audit_log or ""),
            state_path=str(args.audit_state_file or ""),
            strict=False,
        )
    checks.append(
        _check_row(
            check_id="audit_chain_recorded",
            ok=bool(audit_result.get("ok")),
            value=audit_result,
            expect="rollout execution should be recorded in tamper-evident audit chain",
            mode="enforce" if bool(args.audit_strict) else "warn",
        )
    )
    report["audit"] = audit_result
    if bool(args.audit_strict) and (not bool(audit_result.get("ok"))):
        report["ok"] = False

    out_default = Path(".data/out") / f"release_rollout_executor_{int(ended)}.json"
    out_path = Path(str(args.out or out_default))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if bool(args.strict) or bool(args.audit_strict):
        return 0 if bool(report.get("ok")) else 2
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
