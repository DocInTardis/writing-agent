#!/usr/bin/env python3
"""Release Rollout Guard command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any, Callable

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
_TRUTHY = {"1", "true", "yes", "on"}


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


def _check_row(*, check_id: str, ok: bool, value: Any, expect: str, mode: str) -> dict[str, Any]:
    return {
        "id": str(check_id),
        "ok": bool(ok),
        "value": value,
        "expect": str(expect),
        "mode": str(mode or "warn"),
    }


def _normalize_history(store: dict[str, Any]) -> list[dict[str, Any]]:
    raw = store.get("history") if isinstance(store.get("history"), list) else []
    rows: list[dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        rows.append(
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
    rows.sort(key=lambda item: _safe_float(item.get("ts"), 0.0))
    return rows


def _latest_matching(rows: list[dict[str, Any]], predicate: Callable[[dict[str, Any]], bool]) -> dict[str, Any] | None:
    for row in reversed(rows):
        if predicate(row):
            return row
    return None


def _stable_change_row(rows: list[dict[str, Any]], *, stable_version: str) -> dict[str, Any] | None:
    def _is_match(row: dict[str, Any]) -> bool:
        if str(row.get("to_version") or "") != stable_version:
            return False
        action = str(row.get("action") or "")
        channel = str(row.get("channel") or "")
        if action in {"set", "rollback"} and channel == "stable":
            return True
        if action == "promote" and channel.endswith("->stable"):
            return True
        return False

    return _latest_matching(rows, _is_match)


def _canary_evidence_row(rows: list[dict[str, Any]], *, version: str) -> dict[str, Any] | None:
    return _latest_matching(
        rows,
        lambda row: str(row.get("channel") or "") == "canary" and str(row.get("to_version") or "") == version,
    )


def _reason_has_keyword(reason: str, keywords: list[str]) -> bool:
    text = str(reason or "").strip().lower()
    if not text:
        return False
    return any(keyword in text for keyword in keywords)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate release rollout progression and channel promotion strategy.")
    parser.add_argument("--channels-file", default="security/release_channels.json")
    parser.add_argument("--policy", default="security/release_rollout_policy.json")
    parser.add_argument("--expected-version", default="")
    parser.add_argument("--max-history-age-s", type=float, default=0.0)
    parser.add_argument("--min-canary-observe-s", type=float, default=-1.0)
    parser.add_argument("--allow-direct-stable", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    started = time.time()
    checks: list[dict[str, Any]] = []
    mode = "enforce" if bool(args.strict) else "warn"

    channels_path = Path(str(args.channels_file))
    policy_path = Path(str(args.policy))
    channels_raw = _load_json(channels_path)
    policy_raw = _load_json(policy_path)

    checks.append(
        _check_row(
            check_id="release_channels_loaded",
            ok=isinstance(channels_raw, dict),
            value=channels_path.as_posix(),
            expect="release channel registry exists and valid",
            mode="enforce",
        )
    )
    checks.append(
        _check_row(
            check_id="release_rollout_policy_loaded",
            ok=isinstance(policy_raw, dict),
            value=policy_path.as_posix(),
            expect="release rollout policy exists and valid",
            mode="enforce",
        )
    )

    channels: dict[str, Any] = channels_raw if isinstance(channels_raw, dict) else {}
    policy: dict[str, Any] = policy_raw if isinstance(policy_raw, dict) else {}
    channel_map = channels.get("channels") if isinstance(channels.get("channels"), dict) else {}
    canary = channel_map.get("canary") if isinstance(channel_map.get("canary"), dict) else {}
    stable = channel_map.get("stable") if isinstance(channel_map.get("stable"), dict) else {}

    canary_version = str(canary.get("version") or "").strip()
    stable_version = str(stable.get("version") or "").strip()
    canary_rollout = _safe_int(canary.get("rollout_percent"), 0)
    stable_rollout = _safe_int(stable.get("rollout_percent"), 0)
    canary_updated_at = _safe_float(canary.get("updated_at"), 0.0)
    stable_updated_at = _safe_float(stable.get("updated_at"), 0.0)

    checks.append(
        _check_row(
            check_id="canary_version_semver",
            ok=_is_semver(canary_version),
            value=canary_version,
            expect="semantic version x.y.z",
            mode="enforce",
        )
    )
    checks.append(
        _check_row(
            check_id="stable_version_semver",
            ok=_is_semver(stable_version),
            value=stable_version,
            expect="semantic version x.y.z",
            mode="enforce",
        )
    )
    checks.append(
        _check_row(
            check_id="canary_rollout_range",
            ok=0 <= canary_rollout <= 100,
            value=canary_rollout,
            expect="0..100",
            mode="enforce",
        )
    )
    checks.append(
        _check_row(
            check_id="stable_rollout_range",
            ok=0 <= stable_rollout <= 100,
            value=stable_rollout,
            expect="0..100",
            mode="enforce",
        )
    )

    policy_channels = policy.get("channels") if isinstance(policy.get("channels"), dict) else {}
    policy_canary = policy_channels.get("canary") if isinstance(policy_channels.get("canary"), dict) else {}
    policy_stable = policy_channels.get("stable") if isinstance(policy_channels.get("stable"), dict) else {}
    canary_min = max(0, _safe_int(policy_canary.get("min_rollout_percent"), 1))
    canary_max = min(100, _safe_int(policy_canary.get("max_rollout_percent"), 25))
    stable_required = min(100, max(0, _safe_int(policy_stable.get("required_rollout_percent"), 100)))

    checks.append(
        _check_row(
            check_id="canary_rollout_policy_range",
            ok=canary_min <= canary_rollout <= canary_max,
            value={"canary_rollout": canary_rollout, "min": canary_min, "max": canary_max},
            expect="canary rollout within policy window",
            mode=mode,
        )
    )
    checks.append(
        _check_row(
            check_id="stable_rollout_required",
            ok=stable_rollout == stable_required,
            value={"stable_rollout": stable_rollout, "required": stable_required},
            expect="stable rollout equals policy required value",
            mode=mode,
        )
    )

    expected_version = str(args.expected_version or "").strip()
    if expected_version:
        checks.append(
            _check_row(
                check_id="expected_version_present",
                ok=expected_version in {canary_version, stable_version},
                value={"expected": expected_version, "canary": canary_version, "stable": stable_version},
                expect="expected release version exists in canary or stable",
                mode=mode,
            )
        )

    policy_history = policy.get("history") if isinstance(policy.get("history"), dict) else {}
    history_rows = _normalize_history(channels)
    min_entries = max(0, _safe_int(policy_history.get("min_entries"), 0))
    max_history_age_s = _safe_float(policy_history.get("max_age_s"), 30 * 24 * 3600.0)
    if _safe_float(args.max_history_age_s, 0.0) > 0:
        max_history_age_s = _safe_float(args.max_history_age_s, max_history_age_s)
    require_reason = _safe_bool(policy_history.get("require_reason"), True)
    require_actor = _safe_bool(policy_history.get("require_actor"), True)
    allow_initial_equal = _safe_bool(policy_history.get("allow_initial_equal_without_history"), True)

    checks.append(
        _check_row(
            check_id="history_min_entries",
            ok=len(history_rows) >= min_entries,
            value={"entries": len(history_rows), "min_entries": min_entries},
            expect="release history entries meet minimum",
            mode=mode,
        )
    )

    latest_history_ts = _safe_float(history_rows[-1].get("ts"), 0.0) if history_rows else 0.0
    latest_history_age_s = (started - latest_history_ts) if latest_history_ts > 0 else float("inf")
    if history_rows:
        checks.append(
            _check_row(
                check_id="history_fresh_enough",
                ok=latest_history_age_s <= max_history_age_s,
                value=round(latest_history_age_s, 3),
                expect=f"<= {round(max_history_age_s, 3)}s",
                mode=mode,
            )
        )

    if history_rows and require_reason:
        missing_reason = [
            idx
            for idx, row in enumerate(history_rows)
            if not str(row.get("reason") or "").strip()
        ]
        checks.append(
            _check_row(
                check_id="history_reason_present",
                ok=len(missing_reason) == 0,
                value={"missing_reason_rows": missing_reason[:10], "total_missing": len(missing_reason)},
                expect="history rows should include reason",
                mode=mode,
            )
        )

    if history_rows and require_actor:
        missing_actor = [
            idx
            for idx, row in enumerate(history_rows)
            if not str(row.get("actor") or "").strip()
        ]
        checks.append(
            _check_row(
                check_id="history_actor_present",
                ok=len(missing_actor) == 0,
                value={"missing_actor_rows": missing_actor[:10], "total_missing": len(missing_actor)},
                expect="history rows should include actor",
                mode=mode,
            )
        )

    promotion = policy.get("promotion") if isinstance(policy.get("promotion"), dict) else {}
    require_canary_for_stable = _safe_bool(promotion.get("require_canary_for_stable"), True)
    min_canary_observe_s = _safe_float(promotion.get("min_canary_observe_s"), 1800.0)
    if _safe_float(args.min_canary_observe_s, -1.0) >= 0.0:
        min_canary_observe_s = _safe_float(args.min_canary_observe_s, min_canary_observe_s)
    allow_direct_stable = bool(args.allow_direct_stable) or _safe_bool(
        promotion.get("allow_direct_stable_set"),
        False,
    )
    direct_reason_keywords = [
        str(item or "").strip().lower()
        for item in (
            promotion.get("direct_stable_reason_keywords")
            if isinstance(promotion.get("direct_stable_reason_keywords"), list)
            else ["hotfix", "emergency", "security", "rollback"]
        )
        if str(item or "").strip()
    ]

    stable_change = _stable_change_row(history_rows, stable_version=stable_version)
    canary_evidence = _canary_evidence_row(history_rows, version=stable_version)
    stable_change_ts = _safe_float(
        stable_change.get("ts") if isinstance(stable_change, dict) else stable_updated_at,
        stable_updated_at,
    )
    canary_evidence_ts = _safe_float(
        canary_evidence.get("ts") if isinstance(canary_evidence, dict) else 0.0,
        0.0,
    )
    if canary_evidence_ts <= 0 and canary_version == stable_version:
        canary_evidence_ts = canary_updated_at

    if require_canary_for_stable:
        has_lineage = False
        if stable_version == canary_version:
            has_lineage = True
        elif isinstance(stable_change, dict):
            has_lineage = True
        checks.append(
            _check_row(
                check_id="stable_version_lineage_present",
                ok=has_lineage or (allow_initial_equal and len(history_rows) == 0 and stable_version == canary_version),
                value={
                    "stable_version": stable_version,
                    "canary_version": canary_version,
                    "history_entries": len(history_rows),
                    "stable_change": stable_change or {},
                },
                expect="stable version should have canary lineage or explicit stable change record",
                mode=mode,
            )
        )

    direct_stable_set = bool(
        isinstance(stable_change, dict)
        and str(stable_change.get("action") or "") == "set"
        and str(stable_change.get("channel") or "") == "stable"
    )
    direct_reason_ok = _reason_has_keyword(
        str(stable_change.get("reason") if isinstance(stable_change, dict) else ""),
        direct_reason_keywords,
    )
    if require_canary_for_stable and direct_stable_set:
        checks.append(
            _check_row(
                check_id="direct_stable_set_allowed",
                ok=allow_direct_stable or direct_reason_ok,
                value={
                    "allow_direct_stable_set": allow_direct_stable,
                    "reason": str(stable_change.get("reason") if isinstance(stable_change, dict) else ""),
                    "keywords": direct_reason_keywords,
                },
                expect="direct stable set is disabled unless explicitly allowed or emergency-tagged",
                mode=mode,
            )
        )

    observe_delta_s = stable_change_ts - canary_evidence_ts if (stable_change_ts > 0 and canary_evidence_ts > 0) else -1.0
    observe_check_required = (
        require_canary_for_stable
        and stable_version == canary_version
        and len(history_rows) > 0
        and not (
            isinstance(stable_change, dict)
            and str(stable_change.get("action") or "") == "rollback"
        )
    )
    if observe_check_required:
        checks.append(
            _check_row(
                check_id="canary_observation_window_met",
                ok=observe_delta_s >= min_canary_observe_s,
                value={
                    "observe_delta_s": round(observe_delta_s, 3),
                    "required_s": round(min_canary_observe_s, 3),
                },
                expect="stable promotion should observe canary for minimum window",
                mode=mode,
            )
        )
    elif len(history_rows) == 0 and allow_initial_equal and stable_version == canary_version:
        checks.append(
            _check_row(
                check_id="initial_state_allowed_without_history",
                ok=True,
                value={"stable_version": stable_version, "canary_version": canary_version},
                expect="initial aligned state allowed before first rollout operations",
                mode="warn",
            )
        )

    next_actions: list[str] = []
    if stable_version != canary_version:
        next_actions.append("Canary and stable differ: continue canary observation and promote only after SLO/capacity gates remain healthy.")
    if len(history_rows) == 0:
        next_actions.append("No rollout history recorded yet: use release_channel_control with actor/reason for every set/promote/rollback operation.")
    if direct_stable_set and not (allow_direct_stable or direct_reason_ok):
        next_actions.append("Avoid direct stable set; use canary set + promote flow, or include emergency keyword for audited exception.")
    if observe_check_required and observe_delta_s < min_canary_observe_s:
        next_actions.append(
            f"Canary observation window is short ({round(observe_delta_s, 1)}s); wait at least {round(min_canary_observe_s, 1)}s before stable promotion."
        )
    if canary_rollout < canary_min or canary_rollout > canary_max:
        next_actions.append("Adjust canary rollout percent to the policy range before release.")

    ok = all(bool(row.get("ok")) for row in checks)
    ended = time.time()
    report = {
        "ok": bool(ok),
        "started_at": round(started, 3),
        "ended_at": round(ended, 3),
        "duration_s": round(ended - started, 3),
        "strict": bool(args.strict),
        "channels_file": channels_path.as_posix(),
        "policy_file": policy_path.as_posix(),
        "settings": {
            "expected_version": expected_version,
            "history": {
                "min_entries": min_entries,
                "max_age_s": max_history_age_s,
                "require_reason": require_reason,
                "require_actor": require_actor,
                "allow_initial_equal_without_history": allow_initial_equal,
            },
            "promotion": {
                "require_canary_for_stable": require_canary_for_stable,
                "min_canary_observe_s": min_canary_observe_s,
                "allow_direct_stable_set": allow_direct_stable,
                "direct_stable_reason_keywords": direct_reason_keywords,
            },
            "rollout": {
                "canary_min_rollout_percent": canary_min,
                "canary_max_rollout_percent": canary_max,
                "stable_required_rollout_percent": stable_required,
            },
        },
        "state": {
            "canary_version": canary_version,
            "stable_version": stable_version,
            "canary_rollout_percent": canary_rollout,
            "stable_rollout_percent": stable_rollout,
            "canary_updated_at": round(canary_updated_at, 3),
            "stable_updated_at": round(stable_updated_at, 3),
        },
        "history": {
            "entries": len(history_rows),
            "latest_ts": round(latest_history_ts, 3) if latest_history_ts > 0 else 0.0,
            "latest_age_s": round(latest_history_age_s, 3) if latest_history_age_s != float("inf") else "inf",
            "stable_change": stable_change or {},
            "canary_evidence": canary_evidence or {},
            "observe_delta_s": round(observe_delta_s, 3) if observe_delta_s >= 0 else -1.0,
        },
        "checks": checks,
        "next_actions": next_actions,
    }

    out_default = Path(".data/out") / f"release_rollout_guard_{int(ended)}.json"
    out_path = Path(str(args.out or out_default))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if bool(args.strict):
        return 0 if bool(ok) else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
