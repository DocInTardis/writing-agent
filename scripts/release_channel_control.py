#!/usr/bin/env python3
"""Release Channel Control command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import time
from pathlib import Path
from typing import Any


SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
VERSION_RE = re.compile(r'__version__\s*=\s*"([^"]+)"')

try:
    from scripts import audit_chain
except Exception:
    _AUDIT_CHAIN_PATH = Path(__file__).with_name("audit_chain.py")
    _AUDIT_SPEC = importlib.util.spec_from_file_location("audit_chain", _AUDIT_CHAIN_PATH)
    if _AUDIT_SPEC is None or _AUDIT_SPEC.loader is None:
        raise
    audit_chain = importlib.util.module_from_spec(_AUDIT_SPEC)
    _AUDIT_SPEC.loader.exec_module(audit_chain)


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


def _is_semver(text: str) -> bool:
    return bool(SEMVER_RE.match(str(text or "").strip()))


def _load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _extract_app_version(path: Path) -> str:
    m = VERSION_RE.search(_load_text(path))
    return str(m.group(1)).strip() if m else ""


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
                "version": str(((channels_raw.get("canary") if isinstance(channels_raw.get("canary"), dict) else {}) or {}).get("version") or ""),
                "rollout_percent": int(((channels_raw.get("canary") if isinstance(channels_raw.get("canary"), dict) else {}) or {}).get("rollout_percent") or 0),
                "updated_at": float(((channels_raw.get("canary") if isinstance(channels_raw.get("canary"), dict) else {}) or {}).get("updated_at") or 0.0),
            },
            "stable": {
                "version": str(((channels_raw.get("stable") if isinstance(channels_raw.get("stable"), dict) else {}) or {}).get("version") or ""),
                "rollout_percent": int(((channels_raw.get("stable") if isinstance(channels_raw.get("stable"), dict) else {}) or {}).get("rollout_percent") or 0),
                "updated_at": float(((channels_raw.get("stable") if isinstance(channels_raw.get("stable"), dict) else {}) or {}).get("updated_at") or 0.0),
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
        }
    )
    store["history"] = rows[-300:]
    store["updated_at"] = now


def _validate_store(
    store: dict[str, Any],
    *,
    expected_version: str,
    strict: bool,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    channels = store.get("channels") if isinstance(store.get("channels"), dict) else {}
    canary = channels.get("canary") if isinstance(channels.get("canary"), dict) else {}
    stable = channels.get("stable") if isinstance(channels.get("stable"), dict) else {}

    def row(check_id: str, ok: bool, value: Any, expect: str, mode: str = "enforce") -> None:
        checks.append({"id": check_id, "ok": bool(ok), "value": value, "expect": expect, "mode": mode})

    row("channels_present_canary", isinstance(canary, dict), bool(isinstance(canary, dict)), "canary channel exists")
    row("channels_present_stable", isinstance(stable, dict), bool(isinstance(stable, dict)), "stable channel exists")

    canary_version = str(canary.get("version") or "")
    stable_version = str(stable.get("version") or "")
    row("canary_version_semver", _is_semver(canary_version), canary_version, "semantic version x.y.z")
    row("stable_version_semver", _is_semver(stable_version), stable_version, "semantic version x.y.z")

    canary_rollout = int(canary.get("rollout_percent") or 0)
    stable_rollout = int(stable.get("rollout_percent") or 0)
    row("canary_rollout_range", 0 <= canary_rollout <= 100, canary_rollout, "0..100")
    row("stable_rollout_range", 0 <= stable_rollout <= 100, stable_rollout, "0..100")
    row(
        "stable_rollout_100",
        stable_rollout == 100,
        stable_rollout,
        "stable rollout is 100%",
        mode="enforce" if strict else "warn",
    )

    if expected_version:
        match = expected_version in {canary_version, stable_version}
        row(
            "expected_version_present_in_channels",
            match,
            {"expected": expected_version, "canary": canary_version, "stable": stable_version},
            "expected version exists in canary or stable",
            mode="enforce" if strict else "warn",
        )

    enforce_rows = [x for x in checks if str(x.get("mode") or "enforce") == "enforce"]
    return {"ok": all(bool(x.get("ok")) for x in enforce_rows), "checks": checks}


def _cmd_validate(args: argparse.Namespace) -> int:
    path = Path(str(args.file))
    store = _load_store(path)
    expected = str(args.expected_version or "").strip() or _extract_app_version(Path(str(args.init_file)))
    out = _validate_store(store, expected_version=expected, strict=bool(args.strict))
    report = {
        "ok": bool(out.get("ok")),
        "ts": round(time.time(), 3),
        "file": path.as_posix(),
        "expected_version": expected,
        "store": store,
        "checks": out.get("checks") if isinstance(out.get("checks"), list) else [],
    }
    audit_result = _record_audit(
        args,
        action="release_channel_validate",
        actor=_resolve_actor(args, fallback="release-auditor"),
        status="ok" if bool(report.get("ok")) else "failed",
        context={
            "file": path.as_posix(),
            "expected_version": expected,
            "strict": bool(args.strict),
            "check_count": len(report["checks"]) if isinstance(report.get("checks"), list) else 0,
        },
    )
    report["audit"] = audit_result
    if bool(args.audit_strict) and (not bool(audit_result.get("ok"))):
        report["ok"] = False
    out_path = Path(str(args.out or Path(".data/out") / f"release_channels_validate_{int(time.time())}.json"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report.get("ok")) else 2


def _cmd_status(args: argparse.Namespace) -> int:
    path = Path(str(args.file))
    store = _load_store(path)
    print(json.dumps(store, ensure_ascii=False, indent=2))
    return 0


def _ensure_channel(name: str) -> str:
    v = str(name or "").strip().lower()
    if v not in {"canary", "stable"}:
        raise ValueError("channel must be canary|stable")
    return v


def _cmd_set(args: argparse.Namespace) -> int:
    channel = _ensure_channel(str(args.channel))
    version = str(args.version or "").strip()
    if not _is_semver(version):
        raise SystemExit("invalid --version, expected semantic version x.y.z")
    path = Path(str(args.file))
    store = _load_store(path)
    row = (store.get("channels") if isinstance(store.get("channels"), dict) else {}).get(channel)
    if not isinstance(row, dict):
        row = {}
    old = str(row.get("version") or "")
    now = round(time.time(), 3)
    row["version"] = version
    if channel == "stable":
        row["rollout_percent"] = 100
    elif "rollout_percent" not in row:
        row["rollout_percent"] = 5
    row["updated_at"] = now
    store["channels"][channel] = row  # type: ignore[index]
    _append_history(
        store,
        action="set",
        channel=channel,
        from_version=old,
        to_version=version,
        reason=str(args.reason or ""),
        actor=str(args.actor or "system"),
    )
    _save_store(path, store)
    report = {"ok": True, "action": "set", "channel": channel, "from_version": old, "to_version": version, "file": path.as_posix()}
    audit_result = _record_audit(
        args,
        action="release_channel_set",
        actor=_resolve_actor(args, fallback="release-bot"),
        status="ok",
        context=report,
    )
    report["audit"] = audit_result
    if bool(args.audit_strict) and (not bool(audit_result.get("ok"))):
        report["ok"] = False
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report.get("ok")) else 2


def _cmd_promote(args: argparse.Namespace) -> int:
    source = _ensure_channel(str(args.source))
    target = _ensure_channel(str(args.target))
    if source == target:
        raise SystemExit("--source and --target must differ")
    path = Path(str(args.file))
    store = _load_store(path)
    channels = store.get("channels") if isinstance(store.get("channels"), dict) else {}
    src = channels.get(source) if isinstance(channels.get(source), dict) else {}
    dst = channels.get(target) if isinstance(channels.get(target), dict) else {}
    source_version = str(src.get("version") or "")
    version = str(args.version or "").strip() or source_version
    if not _is_semver(version):
        raise SystemExit("invalid promote version")
    old = str(dst.get("version") or "")
    now = round(time.time(), 3)
    dst["version"] = version
    dst["updated_at"] = now
    if target == "stable":
        dst["rollout_percent"] = 100
    channels[target] = dst
    store["channels"] = channels
    _append_history(
        store,
        action="promote",
        channel=f"{source}->{target}",
        from_version=old,
        to_version=version,
        reason=str(args.reason or ""),
        actor=str(args.actor or "system"),
    )
    _save_store(path, store)
    report = {
        "ok": True,
        "action": "promote",
        "source": source,
        "target": target,
        "from_version": old,
        "to_version": version,
        "file": path.as_posix(),
    }
    audit_result = _record_audit(
        args,
        action="release_channel_promote",
        actor=_resolve_actor(args, fallback="release-bot"),
        status="ok",
        context=report,
    )
    report["audit"] = audit_result
    if bool(args.audit_strict) and (not bool(audit_result.get("ok"))):
        report["ok"] = False
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report.get("ok")) else 2


def _cmd_rollback(args: argparse.Namespace) -> int:
    channel = _ensure_channel(str(args.channel))
    version = str(args.to_version or "").strip()
    if not _is_semver(version):
        raise SystemExit("invalid --to-version, expected semantic version x.y.z")
    path = Path(str(args.file))
    store = _load_store(path)
    channels = store.get("channels") if isinstance(store.get("channels"), dict) else {}
    row = channels.get(channel) if isinstance(channels.get(channel), dict) else {}
    old = str(row.get("version") or "")
    now = round(time.time(), 3)
    row["version"] = version
    row["updated_at"] = now
    if channel == "stable":
        row["rollout_percent"] = 100
    channels[channel] = row
    store["channels"] = channels
    _append_history(
        store,
        action="rollback",
        channel=channel,
        from_version=old,
        to_version=version,
        reason=str(args.reason or ""),
        actor=str(args.actor or "system"),
    )
    _save_store(path, store)
    report = {"ok": True, "action": "rollback", "channel": channel, "from_version": old, "to_version": version, "file": path.as_posix()}
    audit_result = _record_audit(
        args,
        action="release_channel_rollback",
        actor=_resolve_actor(args, fallback="release-bot"),
        status="ok",
        context=report,
    )
    report["audit"] = audit_result
    if bool(args.audit_strict) and (not bool(audit_result.get("ok"))):
        report["ok"] = False
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report.get("ok")) else 2


def _resolve_actor(args: argparse.Namespace, *, fallback: str) -> str:
    actor = str(getattr(args, "audit_actor", "") or "").strip()
    if actor:
        return actor
    action_actor = str(getattr(args, "actor", "") or "").strip()
    if action_actor:
        return action_actor
    return str(fallback or "system")


def _record_audit(
    args: argparse.Namespace,
    *,
    action: str,
    actor: str,
    status: str,
    context: dict[str, Any],
) -> dict[str, Any]:
    if bool(getattr(args, "skip_audit_log", False)):
        return {"ok": True, "skipped": True}
    return audit_chain.record_operation(
        action=action,
        actor=actor,
        source="release_channel_control",
        status=status,
        context=context,
        log_path=str(getattr(args, "audit_log", "") or ""),
        state_path=str(getattr(args, "audit_state_file", "") or ""),
        strict=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Release channel control (canary/stable) and validation.")
    parser.add_argument("--audit-log", default="")
    parser.add_argument("--audit-state-file", default="")
    parser.add_argument("--audit-actor", default="")
    parser.add_argument("--skip-audit-log", action="store_true")
    parser.add_argument("--audit-strict", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_validate = sub.add_parser("validate")
    p_validate.add_argument("--file", default="security/release_channels.json")
    p_validate.add_argument("--init-file", default="writing_agent/__init__.py")
    p_validate.add_argument("--expected-version", default="")
    p_validate.add_argument("--strict", action="store_true")
    p_validate.add_argument("--out", default="")
    p_validate.set_defaults(func=_cmd_validate)

    p_status = sub.add_parser("status")
    p_status.add_argument("--file", default="security/release_channels.json")
    p_status.set_defaults(func=_cmd_status)

    p_set = sub.add_parser("set")
    p_set.add_argument("--file", default="security/release_channels.json")
    p_set.add_argument("--channel", required=True)
    p_set.add_argument("--version", required=True)
    p_set.add_argument("--reason", default="")
    p_set.add_argument("--actor", default="system")
    p_set.set_defaults(func=_cmd_set)

    p_promote = sub.add_parser("promote")
    p_promote.add_argument("--file", default="security/release_channels.json")
    p_promote.add_argument("--source", default="canary")
    p_promote.add_argument("--target", default="stable")
    p_promote.add_argument("--version", default="")
    p_promote.add_argument("--reason", default="")
    p_promote.add_argument("--actor", default="system")
    p_promote.set_defaults(func=_cmd_promote)

    p_rollback = sub.add_parser("rollback")
    p_rollback.add_argument("--file", default="security/release_channels.json")
    p_rollback.add_argument("--channel", default="stable")
    p_rollback.add_argument("--to-version", required=True)
    p_rollback.add_argument("--reason", default="")
    p_rollback.add_argument("--actor", default="system")
    p_rollback.set_defaults(func=_cmd_rollback)

    args = parser.parse_args()
    func = getattr(args, "func", None)
    if func is None:
        raise SystemExit(2)
    return int(func(args))


if __name__ == "__main__":
    raise SystemExit(main())
