#!/usr/bin/env python3
"""Alert Escalation Guard command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any


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


def _latest_report(pattern: str) -> Path | None:
    rows = sorted(Path(".").glob(pattern), key=lambda p: p.stat().st_mtime if p.exists() else 0.0)
    if not rows:
        return None
    return rows[-1]


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


def _normalize_events(raw: dict[str, Any] | list[Any] | None) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [row for row in raw if isinstance(row, dict)]
    if isinstance(raw, dict):
        events = raw.get("events")
        if isinstance(events, list):
            return [row for row in events if isinstance(row, dict)]
    return []


def _recent_events(events: list[dict[str, Any]], *, now_ts: float, window_minutes: float) -> list[dict[str, Any]]:
    lookback_s = max(60.0, float(window_minutes) * 60.0)
    min_ts = float(now_ts) - lookback_s
    rows: list[dict[str, Any]] = []
    for event in events:
        ts = _safe_float(event.get("ts"), 0.0)
        if ts <= 0:
            continue
        if ts >= min_ts:
            rows.append(event)
    rows.sort(key=lambda row: _safe_float(row.get("ts"), 0.0))
    return rows


def _latest_text_field(events: list[dict[str, Any]], key: str) -> str:
    target = str(key or "").strip()
    if not target:
        return ""
    for row in reversed(events):
        value = str((row if isinstance(row, dict) else {}).get(target) or "").strip()
        if value:
            return value
    return ""


def _status_is_webhook_failure(status: str) -> bool:
    text = str(status or "").strip().lower()
    if not text:
        return False
    if text in {"webhook_failed", "notify_exception", "url_error"}:
        return True
    if text.startswith("http_"):
        code = _safe_int(text.split("_", 1)[1], 0)
        return code < 200 or code >= 300
    return False


def _evaluate(
    *,
    policy: dict[str, Any],
    events: list[dict[str, Any]],
    now_ts: float,
    quick: bool,
    slo_ok: bool | None,
) -> dict[str, Any]:
    node = policy.get("citation_verify") if isinstance(policy.get("citation_verify"), dict) else {}
    thresholds = node.get("thresholds") if isinstance(node.get("thresholds"), dict) else {}
    actions = node.get("actions") if isinstance(node.get("actions"), dict) else {}
    slo_cfg = node.get("slo_guard") if isinstance(node.get("slo_guard"), dict) else {}

    lookback_minutes = _safe_float(node.get("lookback_minutes"), 30.0)
    if bool(quick):
        lookback_minutes = min(lookback_minutes, 20.0)
    recent = _recent_events(events, now_ts=now_ts, window_minutes=lookback_minutes)

    active_event_types = {"raise", "change", "repeat"}
    critical_count = sum(
        1
        for row in recent
        if str(row.get("severity") or "").strip().lower() == "critical"
        and str(row.get("event_type") or "").strip().lower() in active_event_types
    )
    warn_count = sum(
        1
        for row in recent
        if str(row.get("severity") or "").strip().lower() == "warn"
        and str(row.get("event_type") or "").strip().lower() in active_event_types
    )
    repeat_count = sum(1 for row in recent if str(row.get("event_type") or "").strip().lower() == "repeat")
    suppressed_count = sum(
        1
        for row in recent
        if bool(row.get("dedupe_hit"))
        or str(row.get("status") or "").strip().lower() == "suppressed"
    )
    webhook_failures = sum(
        1
        for row in recent
        if _status_is_webhook_failure(str(row.get("status") or ""))
    )

    critical_events_min = max(1, _safe_int(thresholds.get("critical_events_min"), 1))
    warn_events_min = max(1, _safe_int(thresholds.get("warn_events_min"), 3))
    repeat_events_min = max(1, _safe_int(thresholds.get("repeat_events_min"), 6))
    suppressed_events_min = max(1, _safe_int(thresholds.get("suppressed_events_min"), 8))
    webhook_failures_min = max(1, _safe_int(thresholds.get("webhook_failures_min"), 2))

    slo_fail_as_critical = bool(slo_cfg.get("fail_as_critical", True))
    trigger_slo_fail = slo_fail_as_critical and (slo_ok is False)
    trigger_critical = critical_count >= critical_events_min
    trigger_webhook_failure = webhook_failures >= webhook_failures_min
    trigger_warn = warn_count >= warn_events_min
    trigger_repeat = repeat_count >= repeat_events_min
    trigger_suppressed = suppressed_count >= suppressed_events_min

    level = "none"
    severity = "ok"
    triggered_by: list[str] = []
    if trigger_slo_fail:
        triggered_by.append("slo_guard_failed")
    if trigger_critical:
        triggered_by.append("critical_events")
    if trigger_webhook_failure:
        triggered_by.append("webhook_failures")
    if trigger_warn:
        triggered_by.append("warn_events")
    if trigger_repeat:
        triggered_by.append("repeat_events")
    if trigger_suppressed:
        triggered_by.append("suppressed_events")

    if trigger_slo_fail or trigger_critical or trigger_webhook_failure:
        level = "p1"
        severity = "critical"
    elif trigger_warn or trigger_repeat or trigger_suppressed:
        level = "p2"
        severity = "warn"

    level_actions_raw = actions.get(level) if isinstance(actions.get(level), list) else []
    level_actions = [str(x).strip() for x in level_actions_raw if str(x).strip()]
    last_event = recent[-1] if recent else {}
    correlation_id = _latest_text_field(recent, "correlation_id") or _latest_text_field(events, "correlation_id")
    release_candidate_id = _latest_text_field(recent, "release_candidate_id") or _latest_text_field(
        events, "release_candidate_id"
    )
    if not release_candidate_id and correlation_id:
        release_candidate_id = correlation_id
    if not correlation_id and release_candidate_id:
        correlation_id = release_candidate_id

    return {
        "policy": {
            "lookback_minutes": lookback_minutes,
            "thresholds": {
                "critical_events_min": critical_events_min,
                "warn_events_min": warn_events_min,
                "repeat_events_min": repeat_events_min,
                "suppressed_events_min": suppressed_events_min,
                "webhook_failures_min": webhook_failures_min,
            },
            "slo_guard": {
                "require_report": bool(slo_cfg.get("require_report", False)),
                "fail_as_critical": slo_fail_as_critical,
            },
        },
        "window": {
            "events_total": len(events),
            "events_recent": len(recent),
            "from_ts": round(float(now_ts) - float(lookback_minutes) * 60.0, 3),
            "to_ts": round(float(now_ts), 3),
        },
        "observed": {
            "critical_events": critical_count,
            "warn_events": warn_count,
            "repeat_events": repeat_count,
            "suppressed_events": suppressed_count,
            "webhook_failures": webhook_failures,
            "last_event": {
                "id": str(last_event.get("id") or ""),
                "severity": str(last_event.get("severity") or ""),
                "event_type": str(last_event.get("event_type") or ""),
                "status": str(last_event.get("status") or ""),
                "ts": round(_safe_float(last_event.get("ts"), 0.0), 3),
                "correlation_id": str(last_event.get("correlation_id") or ""),
                "release_candidate_id": str(last_event.get("release_candidate_id") or ""),
            },
            "slo_ok": slo_ok,
        },
        "correlation": {
            "correlation_id": correlation_id,
            "release_candidate_id": release_candidate_id,
        },
        "escalation": {
            "level": level,
            "severity": severity,
            "triggered_by": triggered_by,
            "actions": level_actions,
        },
    }


def _check_row(*, check_id: str, ok: bool, value: Any, expect: str, mode: str = "enforce") -> dict[str, Any]:
    return {
        "id": str(check_id),
        "ok": bool(ok),
        "value": value,
        "expect": str(expect),
        "mode": str(mode or "enforce"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate alert escalation level from recent citation alert events.")
    parser.add_argument("--policy", default="security/alert_escalation_policy.json")
    parser.add_argument("--events-file", default=".data/citation_verify_alert_events.json")
    parser.add_argument("--slo-report", default="")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    started = time.time()
    checks: list[dict[str, Any]] = []

    policy_path = Path(str(args.policy))
    events_path = Path(str(args.events_file))
    slo_path = Path(str(args.slo_report)) if str(args.slo_report).strip() else _latest_report(".data/out/slo_guard_*.json")

    policy_raw = _load_json(policy_path)
    policy_loaded = isinstance(policy_raw, dict)
    checks.append(
        _check_row(
            check_id="policy_loaded",
            ok=policy_loaded,
            value=policy_path.as_posix(),
            expect="alert escalation policy json exists and valid",
        )
    )
    if not policy_loaded:
        ended = time.time()
        report = {
            "ok": False,
            "started_at": round(started, 3),
            "ended_at": round(ended, 3),
            "duration_s": round(ended - started, 3),
            "checks": checks,
            "escalation": {"level": "none", "severity": "ok", "triggered_by": [], "actions": []},
            "paths": {
                "policy": policy_path.as_posix(),
                "events_file": events_path.as_posix(),
                "slo_report": slo_path.as_posix() if isinstance(slo_path, Path) else "",
            },
        }
        out_path = Path(str(args.out or Path(".data/out") / f"alert_escalation_{int(ended)}.json"))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    events_raw = _load_json(events_path)
    events = _normalize_events(events_raw)
    checks.append(
        _check_row(
            check_id="events_file_loaded",
            ok=(events_raw is not None and isinstance(events, list)),
            value=events_path.as_posix(),
            expect="events file may be list or {events:list}",
            mode="warn",
        )
    )
    checks.append(
        _check_row(
            check_id="events_total_available",
            ok=len(events) > 0,
            value=len(events),
            expect=">0 events in source file",
            mode="warn",
        )
    )

    slo_raw = _load_json(slo_path) if isinstance(slo_path, Path) else None
    slo_ok: bool | None
    if isinstance(slo_raw, dict):
        slo_ok = bool(slo_raw.get("ok"))
        checks.append(
            _check_row(
                check_id="slo_report_loaded",
                ok=True,
                value=slo_path.as_posix() if isinstance(slo_path, Path) else "",
                expect="latest slo guard report loaded",
                mode="warn",
            )
        )
    else:
        slo_ok = None
        checks.append(
            _check_row(
                check_id="slo_report_loaded",
                ok=False,
                value=slo_path.as_posix() if isinstance(slo_path, Path) else "",
                expect="latest slo guard report loaded",
                mode="warn",
            )
        )

    ended = time.time()
    evaluated = _evaluate(
        policy=policy_raw if isinstance(policy_raw, dict) else {},
        events=events,
        now_ts=ended,
        quick=bool(args.quick),
        slo_ok=slo_ok,
    )
    level = str(((evaluated.get("escalation") if isinstance(evaluated.get("escalation"), dict) else {}) or {}).get("level") or "none")

    checks.append(
        _check_row(
            check_id="escalation_level_none",
            ok=level == "none",
            value=level,
            expect="none",
            mode="enforce" if bool(args.strict) else "warn",
        )
    )
    checks.append(
        _check_row(
            check_id="events_in_window_available",
            ok=int(((evaluated.get("window") if isinstance(evaluated.get("window"), dict) else {}).get("events_recent") or 0)) > 0,
            value=int(((evaluated.get("window") if isinstance(evaluated.get("window"), dict) else {}).get("events_recent") or 0)),
            expect=">0 events in lookback window",
            mode="warn",
        )
    )
    correlation_node = evaluated.get("correlation") if isinstance(evaluated.get("correlation"), dict) else {}
    correlation_id = str(correlation_node.get("correlation_id") or "").strip()
    release_candidate_id = str(correlation_node.get("release_candidate_id") or "").strip()
    checks.append(
        _check_row(
            check_id="correlation_context_available",
            ok=bool(correlation_id or release_candidate_id),
            value={
                "correlation_id": correlation_id,
                "release_candidate_id": release_candidate_id,
            },
            expect="at least one correlation identifier available from recent events",
            mode="warn",
        )
    )

    policy_slo = (
        (evaluated.get("policy") if isinstance(evaluated.get("policy"), dict) else {}).get("slo_guard")
        if isinstance(evaluated.get("policy"), dict)
        else {}
    )
    require_slo_report = bool((policy_slo if isinstance(policy_slo, dict) else {}).get("require_report", False))
    checks.append(
        _check_row(
            check_id="slo_report_required_when_policy_enabled",
            ok=(not require_slo_report) or isinstance(slo_raw, dict),
            value={"required": require_slo_report, "loaded": isinstance(slo_raw, dict)},
            expect="if require_report=true then slo report must exist",
            mode="enforce" if bool(args.strict) else "warn",
        )
    )

    enforce_rows = [row for row in checks if str(row.get("mode") or "enforce") == "enforce"]
    ok = all(bool(row.get("ok")) for row in enforce_rows)

    report = {
        "ok": bool(ok),
        "started_at": round(started, 3),
        "ended_at": round(ended, 3),
        "duration_s": round(ended - started, 3),
        "quick": bool(args.quick),
        "strict": bool(args.strict),
        "paths": {
            "policy": policy_path.as_posix(),
            "events_file": events_path.as_posix(),
            "slo_report": slo_path.as_posix() if isinstance(slo_path, Path) else "",
        },
        "checks": checks,
        "policy": evaluated.get("policy"),
        "window": evaluated.get("window"),
        "observed": evaluated.get("observed"),
        "correlation": evaluated.get("correlation"),
        "escalation": evaluated.get("escalation"),
    }
    out_path = Path(str(args.out or Path(".data/out") / f"alert_escalation_{int(ended)}.json"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report.get("ok")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
