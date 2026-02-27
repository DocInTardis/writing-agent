#!/usr/bin/env python3
"""Audit Chain command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

DEFAULT_LOG_PATH = ".data/audit/operations_audit_chain.ndjson"
DEFAULT_STATE_PATH = ".data/audit/operations_audit_chain_state.json"
REQUIRED_ENTRY_FIELDS = (
    "schema_version",
    "seq",
    "ts",
    "action",
    "actor",
    "source",
    "status",
    "context",
    "prev_hash",
    "entry_hash",
)


def resolve_log_path(value: str | Path | None = None) -> Path:
    text = str(value or "").strip()
    if text:
        return Path(text)
    env_text = str(os.environ.get("WA_AUDIT_CHAIN_LOG", "")).strip()
    return Path(env_text or DEFAULT_LOG_PATH)


def resolve_state_path(value: str | Path | None = None) -> Path:
    text = str(value or "").strip()
    if text:
        return Path(text)
    env_text = str(os.environ.get("WA_AUDIT_CHAIN_STATE_FILE", "")).strip()
    return Path(env_text or DEFAULT_STATE_PATH)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def _canonical_json(value: Any) -> str:
    return json.dumps(_json_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _payload_for_hash(entry: dict[str, Any]) -> dict[str, Any]:
    out = {str(k): _json_safe(v) for k, v in entry.items() if str(k) != "entry_hash"}
    return out


def compute_entry_hash(entry: dict[str, Any]) -> str:
    payload = _payload_for_hash(entry)
    text = _canonical_json(payload)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _check_row(
    checks: list[dict[str, Any]],
    *,
    check_id: str,
    ok: bool,
    value: Any,
    expect: str,
    mode: str = "enforce",
) -> None:
    checks.append(
        {
            "id": str(check_id),
            "ok": bool(ok),
            "value": value,
            "expect": str(expect),
            "mode": str(mode or "enforce"),
        }
    )


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def write_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(_json_safe(state), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _build_state(*, log_path: Path, verification: dict[str, Any]) -> dict[str, Any]:
    summary = verification if isinstance(verification, dict) else {}
    return {
        "schema_version": 1,
        "updated_at": round(time.time(), 3),
        "log_path": log_path.as_posix(),
        "entry_count": int(summary.get("entry_count") or 0),
        "last_hash": str(summary.get("last_hash") or ""),
        "last_ts": round(_safe_float(summary.get("last_ts"), 0.0), 3),
        "file_size": int(log_path.stat().st_size) if log_path.exists() else 0,
    }


def build_state_snapshot(*, log_path: Path, verification: dict[str, Any]) -> dict[str, Any]:
    return _build_state(log_path=log_path, verification=verification)


def verify_chain(
    *,
    log_path: Path,
    state: dict[str, Any] | None = None,
    require_log: bool = False,
    require_state: bool = False,
    strict: bool = False,
    max_age_s: float = 0.0,
    now_ts: float | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    parse_errors: list[dict[str, Any]] = []
    entries: list[dict[str, Any]] = []
    hash_chain: list[str] = []
    now_value = float(now_ts if now_ts is not None else time.time())

    log_exists = bool(log_path.exists())
    _check_row(
        checks,
        check_id="audit_log_exists",
        ok=bool(log_exists or (not require_log)),
        value=log_path.as_posix(),
        expect="audit chain log exists when required",
        mode="enforce",
    )

    if log_exists:
        with log_path.open("r", encoding="utf-8") as f:
            for index, raw_line in enumerate(f, start=1):
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception as exc:
                    parse_errors.append({"line": index, "error": f"{exc.__class__.__name__}: {exc}"})
                    continue
                if isinstance(row, dict):
                    entries.append(row)
                else:
                    parse_errors.append({"line": index, "error": "entry is not a json object"})

    _check_row(
        checks,
        check_id="audit_log_parse_ok",
        ok=len(parse_errors) == 0,
        value={"errors": parse_errors[:20], "count": len(parse_errors)},
        expect="all audit entries should be valid json objects",
        mode="enforce",
    )

    if require_log:
        _check_row(
            checks,
            check_id="audit_log_non_empty",
            ok=len(entries) > 0,
            value=len(entries),
            expect="audit chain should contain at least one entry",
            mode="enforce",
        )

    prior_hash = ""
    prior_ts = 0.0
    for index, entry in enumerate(entries, start=1):
        missing = [name for name in REQUIRED_ENTRY_FIELDS if name not in entry]
        _check_row(
            checks,
            check_id=f"entry_{index}_required_fields",
            ok=len(missing) == 0,
            value={"missing": missing},
            expect="entry contains required schema fields",
            mode="enforce",
        )

        seq = _safe_int(entry.get("seq"), 0)
        _check_row(
            checks,
            check_id=f"entry_{index}_seq_continuous",
            ok=seq == index,
            value=seq,
            expect=f"sequence should equal {index}",
            mode="enforce",
        )

        action = str(entry.get("action") or "").strip()
        actor = str(entry.get("actor") or "").strip()
        source = str(entry.get("source") or "").strip()
        status = str(entry.get("status") or "").strip()
        _check_row(
            checks,
            check_id=f"entry_{index}_action_present",
            ok=bool(action),
            value=action,
            expect="action should be non-empty",
            mode="enforce" if strict else "warn",
        )
        _check_row(
            checks,
            check_id=f"entry_{index}_actor_present",
            ok=bool(actor),
            value=actor,
            expect="actor should be non-empty",
            mode="enforce" if strict else "warn",
        )
        _check_row(
            checks,
            check_id=f"entry_{index}_source_present",
            ok=bool(source),
            value=source,
            expect="source should be non-empty",
            mode="enforce" if strict else "warn",
        )
        _check_row(
            checks,
            check_id=f"entry_{index}_status_present",
            ok=bool(status),
            value=status,
            expect="status should be non-empty",
            mode="enforce" if strict else "warn",
        )

        context = entry.get("context")
        _check_row(
            checks,
            check_id=f"entry_{index}_context_is_object",
            ok=isinstance(context, dict),
            value=type(context).__name__,
            expect="context should be a json object",
            mode="enforce",
        )

        ts = _safe_float(entry.get("ts"), 0.0)
        _check_row(
            checks,
            check_id=f"entry_{index}_timestamp_positive",
            ok=ts > 0,
            value=ts,
            expect="timestamp should be > 0",
            mode="enforce",
        )
        _check_row(
            checks,
            check_id=f"entry_{index}_timestamp_monotonic",
            ok=(prior_ts <= 0.0) or (ts >= prior_ts),
            value={"prev_ts": prior_ts, "ts": ts},
            expect="timestamps should be non-decreasing",
            mode="enforce",
        )
        if ts > 0:
            prior_ts = ts

        prev_hash = str(entry.get("prev_hash") or "")
        _check_row(
            checks,
            check_id=f"entry_{index}_prev_hash_match",
            ok=prev_hash == prior_hash,
            value={"prev_hash": prev_hash, "expected_prev_hash": prior_hash},
            expect="prev_hash should match prior entry hash",
            mode="enforce",
        )

        stored_hash = str(entry.get("entry_hash") or "")
        computed_hash = compute_entry_hash(entry)
        _check_row(
            checks,
            check_id=f"entry_{index}_hash_match",
            ok=bool(stored_hash) and stored_hash == computed_hash,
            value={"entry_hash": stored_hash, "computed_hash": computed_hash},
            expect="entry hash should match canonical payload hash",
            mode="enforce",
        )
        prior_hash = stored_hash
        hash_chain.append(stored_hash)

    last_ts = prior_ts if prior_ts > 0 else 0.0
    if max_age_s > 0 and len(entries) > 0:
        age_s = max(0.0, now_value - last_ts)
        _check_row(
            checks,
            check_id="audit_last_entry_fresh",
            ok=age_s <= float(max_age_s),
            value={"age_s": round(age_s, 3), "max_age_s": float(max_age_s)},
            expect="latest audit entry should be fresh enough",
            mode="enforce",
        )

    state_obj = state if isinstance(state, dict) else {}
    state_present = bool(state_obj)
    _check_row(
        checks,
        check_id="audit_state_present",
        ok=state_present or (not require_state),
        value={"state_file_present": state_present},
        expect="audit continuity state exists when required",
        mode="enforce",
    )

    if state_present:
        state_log_path = str(state_obj.get("log_path") or "").strip()
        if state_log_path:
            _check_row(
                checks,
                check_id="audit_state_log_path_match",
                ok=Path(state_log_path).as_posix() == log_path.as_posix(),
                value={"state_log_path": state_log_path, "log_path": log_path.as_posix()},
                expect="state snapshot should point to the same log file",
                mode="warn",
            )

        state_count = max(0, _safe_int(state_obj.get("entry_count"), 0))
        state_last_hash = str(state_obj.get("last_hash") or "")
        if state_count > 0:
            if len(entries) < state_count:
                continuity_ok = False
                continuity_value: dict[str, Any] = {
                    "state_count": state_count,
                    "current_count": len(entries),
                    "state_last_hash": state_last_hash,
                    "reason": "truncated",
                }
            elif len(entries) == state_count:
                continuity_ok = str(prior_hash or "") == state_last_hash
                continuity_value = {
                    "state_count": state_count,
                    "current_count": len(entries),
                    "state_last_hash": state_last_hash,
                    "current_last_hash": str(prior_hash or ""),
                }
            else:
                bridge_hash = hash_chain[state_count - 1] if state_count - 1 < len(hash_chain) else ""
                continuity_ok = bridge_hash == state_last_hash
                continuity_value = {
                    "state_count": state_count,
                    "current_count": len(entries),
                    "state_last_hash": state_last_hash,
                    "bridge_hash": bridge_hash,
                }
            _check_row(
                checks,
                check_id="audit_append_only_state_continuity",
                ok=continuity_ok,
                value=continuity_value,
                expect="current chain should continue from persisted state snapshot",
                mode="enforce",
            )

    enforce_rows = [row for row in checks if str(row.get("mode") or "enforce") == "enforce"]
    ok = all(bool(row.get("ok")) for row in enforce_rows)
    return {
        "ok": bool(ok),
        "log_path": log_path.as_posix(),
        "entry_count": len(entries),
        "last_hash": str(prior_hash or ""),
        "last_ts": round(last_ts, 3),
        "checks": checks,
        "parse_errors": parse_errors,
    }


def append_entry(
    *,
    action: str,
    actor: str,
    source: str,
    status: str,
    context: dict[str, Any] | None = None,
    log_path: Path | None = None,
    state_path: Path | None = None,
    strict: bool = True,
    update_state: bool = True,
) -> dict[str, Any]:
    resolved_log_path = resolve_log_path(log_path)
    resolved_state_path = resolve_state_path(state_path)
    current_state = load_state(resolved_state_path)
    before = verify_chain(
        log_path=resolved_log_path,
        state=current_state,
        require_log=False,
        require_state=False,
        strict=True,
    )
    if strict and (not bool(before.get("ok"))):
        failing = [str(row.get("id")) for row in before.get("checks", []) if not bool(row.get("ok"))]
        raise RuntimeError(f"audit_chain_invalid:{','.join(failing)}")

    context_value = context if isinstance(context, dict) else {}
    record = {
        "schema_version": 1,
        "seq": int(before.get("entry_count") or 0) + 1,
        "ts": round(time.time(), 3),
        "action": str(action or "").strip(),
        "actor": str(actor or "system").strip() or "system",
        "source": str(source or "").strip() or "unknown",
        "status": str(status or "").strip() or "ok",
        "context": _json_safe(context_value if isinstance(context_value, dict) else {}),
        "prev_hash": str(before.get("last_hash") or ""),
    }
    record["entry_hash"] = compute_entry_hash(record)

    resolved_log_path.parent.mkdir(parents=True, exist_ok=True)
    with resolved_log_path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
        f.write("\n")

    if update_state:
        after = verify_chain(
            log_path=resolved_log_path,
            state=current_state,
            require_log=True,
            require_state=False,
            strict=True,
        )
        if strict and (not bool(after.get("ok"))):
            failing = [str(row.get("id")) for row in after.get("checks", []) if not bool(row.get("ok"))]
            raise RuntimeError(f"audit_chain_post_write_invalid:{','.join(failing)}")
        write_state(resolved_state_path, _build_state(log_path=resolved_log_path, verification=after))

    return record


def record_operation(
    *,
    action: str,
    actor: str,
    source: str,
    status: str,
    context: dict[str, Any] | None = None,
    log_path: str | Path | None = None,
    state_path: str | Path | None = None,
    strict: bool = False,
) -> dict[str, Any]:
    resolved_log_path = resolve_log_path(log_path)
    resolved_state_path = resolve_state_path(state_path)
    try:
        entry = append_entry(
            action=action,
            actor=actor,
            source=source,
            status=status,
            context=context,
            log_path=resolved_log_path,
            state_path=resolved_state_path,
            strict=True,
            update_state=True,
        )
    except Exception as exc:
        if strict:
            raise
        return {
            "ok": False,
            "error": f"{exc.__class__.__name__}: {exc}",
            "log_path": resolved_log_path.as_posix(),
            "state_path": resolved_state_path.as_posix(),
        }
    return {
        "ok": True,
        "log_path": resolved_log_path.as_posix(),
        "state_path": resolved_state_path.as_posix(),
        "entry": entry,
    }
