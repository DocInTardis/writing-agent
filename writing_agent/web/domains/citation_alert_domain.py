"""Citation Alert Domain module.

This module belongs to `writing_agent.web.domains` in the writing-agent codebase.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable


def citation_verify_alert_signature(*, severity: str, triggered_ids: list[str], degraded: bool) -> str:
    sig_rules = ",".join(sorted([str(x or "").strip() for x in (triggered_ids or []) if str(x or "").strip()]))
    return f"{str(severity or 'ok').lower()}|{int(bool(degraded))}|{sig_rules}"


def citation_verify_release_context(*, correlation_id: str, release_candidate_id: str) -> dict:
    corr = str(correlation_id or "").strip()
    release = str(release_candidate_id or "").strip()
    if not release and corr:
        release = corr
    if not corr and release:
        corr = release
    return {
        "correlation_id": corr,
        "release_candidate_id": release,
    }


@dataclass(frozen=True)
class CitationAlertNotifyConfig:
    notify_enabled: bool
    webhook_url: str
    cooldown_s: float
    timeout_s: float
    release_ctx: dict


@dataclass(frozen=True)
class CitationAlertNotifyHooks:
    append_event: Callable[[dict], dict]
    events_snapshot: Callable[..., dict]
    alert_notify_webhook: Callable[[str, dict, float], tuple[bool, str]]
    log_info: Callable[[str], None]
    log_warn: Callable[[str], None]
    log_error: Callable[[str], None]


@dataclass(frozen=True)
class CitationAlertEventData:
    now: float
    severity: str
    event_type: str
    signature: str
    triggered_ids: list[str]
    degraded: bool
    errors: list[str]
    sent_channels: list[str]
    notify_status: str
    webhook_configured: bool


def _normalize_alert_summary(*, alerts: dict, degraded: bool) -> tuple[str, list[str], str]:
    alerts_row = alerts if isinstance(alerts, dict) else {}
    severity = str(alerts_row.get("severity") or "ok").strip().lower()
    if severity not in {"ok", "warn", "critical"}:
        severity = "ok"
    triggered_rules = alerts_row.get("triggered_rules") if isinstance(alerts_row.get("triggered_rules"), list) else []
    triggered_ids = [str(x or "").strip() for x in triggered_rules if str(x or "").strip()]
    signature = citation_verify_alert_signature(severity=severity, triggered_ids=triggered_ids, degraded=bool(degraded))
    return severity, triggered_ids, signature


def _load_notify_state(*, notify_state: dict, notify_lock: Any) -> dict:
    with notify_lock:
        return {
            "prev_severity": str(notify_state.get("severity") or "ok").strip().lower(),
            "prev_signature": str(notify_state.get("signature") or ""),
            "last_sent_at": float(notify_state.get("last_sent_at") or 0.0),
            "suppressed": int(notify_state.get("suppressed") or 0),
            "last_error": str(notify_state.get("last_error") or ""),
        }


def _decide_notify(
    *,
    notify_enabled: bool,
    now: float,
    severity: str,
    signature: str,
    prev_severity: str,
    prev_signature: str,
    last_sent_at: float,
    cooldown_s: float,
) -> tuple[bool, str, bool]:
    should_send = False
    event_type = "none"
    dedupe_hit = False
    if not notify_enabled:
        return should_send, event_type, dedupe_hit

    if severity in {"warn", "critical"}:
        if prev_signature != signature:
            should_send = True
            event_type = "raise" if prev_severity == "ok" else "change"
        elif (now - last_sent_at) >= cooldown_s:
            should_send = True
            event_type = "repeat"
        else:
            dedupe_hit = True
    elif severity == "ok" and prev_severity in {"warn", "critical"}:
        should_send = True
        event_type = "recover"
    return should_send, event_type, dedupe_hit


def _emit_notify_event(
    *,
    should_send: bool,
    event_type: str,
    severity: str,
    signature: str,
    triggered_ids: list[str],
    degraded: bool,
    errors: list[str],
    now: float,
    config: CitationAlertNotifyConfig,
    hooks: CitationAlertNotifyHooks,
) -> tuple[list[str], str, str]:
    sent_channels: list[str] = []
    notify_status = "idle"
    notify_error = ""
    if not should_send:
        return sent_channels, notify_status, notify_error

    payload = {
        "source": "citation_verify",
        "ts": now,
        "signature": signature,
        "severity": severity,
        "event_type": event_type,
        "triggered_rules": triggered_ids,
        "degraded": bool(degraded),
        "errors": [str(x or "") for x in list(errors or [])[:8]],
        "cooldown_s": config.cooldown_s,
        "correlation_id": str(config.release_ctx.get("correlation_id") or ""),
        "release_candidate_id": str(config.release_ctx.get("release_candidate_id") or ""),
    }
    if severity == "critical":
        hooks.log_error(f"citation_verify alert event={event_type} severity={severity} rules={','.join(triggered_ids)}")
    elif severity == "warn":
        hooks.log_warn(f"citation_verify alert event={event_type} severity={severity} rules={','.join(triggered_ids)}")
    else:
        hooks.log_info(f"citation_verify alert event={event_type} severity={severity}")
    sent_channels.append("log")

    if not config.webhook_url:
        return sent_channels, "log_only", notify_error

    try:
        ok, status = hooks.alert_notify_webhook(config.webhook_url, payload, config.timeout_s)
        if ok:
            sent_channels.append("webhook")
        else:
            notify_error = status
        notify_status = status
    except Exception as exc:
        notify_error = f"webhook:{exc.__class__.__name__}"
        notify_status = "webhook_failed"
        hooks.log_warn("citation_verify alert webhook notify failed")
    return sent_channels, notify_status, notify_error


def _persist_notify_event(
    *,
    should_send: bool,
    dedupe_hit: bool,
    suppressed: int,
    event: CitationAlertEventData,
    release_ctx: dict,
    append_event: Callable[[dict], dict],
) -> str:
    persist_event = bool(should_send or event.event_type == "recover" or (dedupe_hit and suppressed == 0))
    if not persist_event:
        return ""

    event_row = append_event(
        {
            "ts": event.now,
            "severity": event.severity,
            "event_type": event.event_type,
            "signature": event.signature,
            "triggered_rules": event.triggered_ids,
            "degraded": bool(event.degraded),
            "degraded_errors": [str(x or "") for x in list(event.errors or [])[:8]],
            "sent": bool(should_send),
            "channels": event.sent_channels,
            "status": event.notify_status,
            "dedupe_hit": bool(dedupe_hit),
            "webhook_configured": bool(event.webhook_configured),
            "correlation_id": str(release_ctx.get("correlation_id") or ""),
            "release_candidate_id": str(release_ctx.get("release_candidate_id") or ""),
        }
    )
    return str(event_row.get("id") or "")


def _store_notify_state(
    *,
    notify_state: dict,
    notify_lock: Any,
    notify_enabled: bool,
    severity: str,
    signature: str,
    event_type: str,
    event_id: str,
    should_send: bool,
    now: float,
    notify_error: str,
) -> tuple[float, int, str, str]:
    with notify_lock:
        notify_state["severity"] = severity
        notify_state["signature"] = signature
        notify_state["last_event_type"] = event_type
        if event_id:
            notify_state["last_event_id"] = event_id
        if should_send:
            notify_state["last_sent_at"] = now
            notify_state["suppressed"] = 0
        elif notify_enabled and severity in {"warn", "critical"}:
            suppressed = int(notify_state.get("suppressed") or 0) + 1
            notify_state["suppressed"] = suppressed
        else:
            notify_state["suppressed"] = 0
        notify_state["last_error"] = notify_error if notify_error else ""
        state_last_error = str(notify_state.get("last_error") or "")
        state_last_sent_at = float(notify_state.get("last_sent_at") or 0.0)
        state_suppressed = int(notify_state.get("suppressed") or 0)
        state_last_event_id = str(notify_state.get("last_event_id") or "")
    return state_last_sent_at, state_suppressed, state_last_error, state_last_event_id


def maybe_notify_citation_verify_alerts(
    *,
    alerts: dict,
    degraded: bool,
    errors: list[str],
    config: CitationAlertNotifyConfig,
    hooks: CitationAlertNotifyHooks,
    notify_state: dict,
    notify_lock: Any,
) -> dict:
    webhook_configured = bool(config.webhook_url)
    now = float(time.time())
    severity, triggered_ids, signature = _normalize_alert_summary(alerts=alerts, degraded=degraded)
    state = _load_notify_state(notify_state=notify_state, notify_lock=notify_lock)
    should_send, event_type, dedupe_hit = _decide_notify(
        notify_enabled=bool(config.notify_enabled),
        now=now,
        severity=severity,
        signature=signature,
        prev_severity=str(state.get("prev_severity") or "ok"),
        prev_signature=str(state.get("prev_signature") or ""),
        last_sent_at=float(state.get("last_sent_at") or 0.0),
        cooldown_s=float(config.cooldown_s),
    )
    sent_channels, notify_status, notify_error = _emit_notify_event(
        should_send=bool(should_send),
        event_type=event_type,
        severity=severity,
        signature=signature,
        triggered_ids=triggered_ids,
        degraded=bool(degraded),
        errors=errors,
        now=now,
        config=config,
        hooks=hooks,
    )
    event = CitationAlertEventData(
        now=now,
        severity=severity,
        event_type=event_type,
        signature=signature,
        triggered_ids=triggered_ids,
        degraded=bool(degraded),
        errors=errors,
        sent_channels=sent_channels,
        notify_status=notify_status,
        webhook_configured=bool(webhook_configured),
    )
    event_id = _persist_notify_event(
        should_send=bool(should_send),
        dedupe_hit=bool(dedupe_hit),
        suppressed=int(state.get("suppressed") or 0),
        event=event,
        release_ctx=config.release_ctx,
        append_event=hooks.append_event,
    )
    state_last_sent_at, state_suppressed, state_last_error, state_last_event_id = _store_notify_state(
        notify_state=notify_state,
        notify_lock=notify_lock,
        notify_enabled=bool(config.notify_enabled),
        severity=severity,
        signature=signature,
        event_type=event_type,
        event_id=event_id,
        should_send=bool(should_send),
        now=now,
        notify_error=notify_error,
    )
    if (not should_send) and bool(config.notify_enabled) and severity in {"warn", "critical"}:
        notify_status = "suppressed"

    last_error = str(state.get("last_error") or "")
    snap = hooks.events_snapshot(limit=12)

    return {
        "enabled": bool(config.notify_enabled),
        "webhook_configured": webhook_configured,
        "sent": bool(should_send),
        "channels": sent_channels,
        "signature": signature,
        "dedupe_hit": bool(dedupe_hit),
        "event_type": event_type,
        "status": notify_status,
        "cooldown_s": round(float(config.cooldown_s), 2),
        "last_sent_at": state_last_sent_at,
        "suppressed": state_suppressed,
        "last_error": state_last_error if state_last_error else last_error,
        "event_id": state_last_event_id or event_id,
        "events_total": int(snap.get("total") or 0),
        "events_recent": snap.get("events") if isinstance(snap.get("events"), list) else [],
    }


def citation_verify_alerts_fallback(*, min_runs: int, threshold_p95: float, threshold_error_rate: float, threshold_hit_rate: float) -> dict:
    return {
        "enabled": False,
        "severity": "ok",
        "triggered": 0,
        "runs": 0,
        "min_runs": min_runs,
        "warmup": False,
        "thresholds": {
            "p95_ms": threshold_p95,
            "error_rate_per_run": threshold_error_rate,
            "cache_delta_hit_rate": threshold_hit_rate,
        },
        "rules": [],
        "triggered_rules": [],
        "notification": {
            "enabled": False,
            "webhook_configured": False,
            "sent": False,
            "channels": [],
            "signature": "",
            "dedupe_hit": False,
            "event_type": "none",
            "status": "disabled",
            "cooldown_s": 0.0,
            "last_sent_at": 0.0,
            "suppressed": 0,
            "last_error": "",
            "event_id": "",
            "events_total": 0,
            "events_recent": [],
        },
    }


def _safe_float(value: object) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _safe_int(value: object) -> int:
    try:
        return int(value or 0)
    except Exception:
        try:
            return int(float(value or 0.0))
        except Exception:
            return 0


def build_citation_verify_alerts_payload(
    *,
    degraded: bool,
    errors: list[str],
    observe: dict,
    alerts_enabled: bool,
    min_runs: int,
    threshold_p95: float,
    threshold_error_rate: float,
    threshold_hit_rate: float,
    log_info: Callable[[str], None],
) -> dict:
    observe_row = observe if isinstance(observe, dict) else {}
    runs = max(0, int(observe_row.get("runs") or 0))
    warmup = runs < min_runs
    elapsed = observe_row.get("elapsed_ms") if isinstance(observe_row.get("elapsed_ms"), dict) else {}
    errors_row = observe_row.get("errors") if isinstance(observe_row.get("errors"), dict) else {}
    cache_delta = observe_row.get("cache_delta") if isinstance(observe_row.get("cache_delta"), dict) else {}

    p95 = max(0.0, _safe_float(elapsed.get("p95")))
    error_rate = max(0.0, min(1.0, _safe_float(errors_row.get("rate_per_run"))))
    hit_rate = max(0.0, min(1.0, _safe_float(cache_delta.get("hit_rate"))))
    delta_lookups = max(0, _safe_int(cache_delta.get("hit")) + _safe_int(cache_delta.get("miss")))

    rules: list[dict] = []

    def _append_rule(
        *,
        rule_id: str,
        level: str,
        triggered: bool,
        value: float,
        threshold: float,
        op: str,
        message: str,
    ) -> None:
        rules.append(
            {
                "id": rule_id,
                "level": level,
                "triggered": bool(triggered),
                "value": round(float(value), 4),
                "threshold": round(float(threshold), 4),
                "op": str(op),
                "message": str(message),
            }
        )

    _append_rule(
        rule_id="metrics_degraded",
        level="critical",
        triggered=bool(degraded),
        value=1.0 if degraded else 0.0,
        threshold=1.0,
        op=">=",
        message="metrics payload degraded",
    )
    _append_rule(
        rule_id="latency_p95_ms",
        level="warn",
        triggered=(not warmup) and (p95 >= threshold_p95),
        value=p95,
        threshold=threshold_p95,
        op=">=",
        message="p95 latency above threshold",
    )
    _append_rule(
        rule_id="error_rate_per_run",
        level="critical",
        triggered=(not warmup) and (error_rate >= threshold_error_rate),
        value=error_rate,
        threshold=threshold_error_rate,
        op=">=",
        message="error rate above threshold",
    )
    _append_rule(
        rule_id="cache_delta_hit_rate",
        level="warn",
        triggered=(not warmup) and (delta_lookups > 0) and (hit_rate <= threshold_hit_rate),
        value=hit_rate,
        threshold=threshold_hit_rate,
        op="<=",
        message="cache hit rate below threshold",
    )

    if not alerts_enabled:
        rules = []

    triggered_rules = [str(row.get("id") or "") for row in rules if bool(row.get("triggered"))]
    has_critical = any(bool(row.get("triggered")) and str(row.get("level")) == "critical" for row in rules)
    has_warn = any(bool(row.get("triggered")) and str(row.get("level")) == "warn" for row in rules)
    severity = "critical" if has_critical else ("warn" if has_warn else "ok")
    if not alerts_enabled:
        severity = "ok"

    if warmup and alerts_enabled:
        log_info(
            "citation_verify alerts warmup: "
            f"runs={runs} min_runs={min_runs} p95={p95:.2f} error_rate={error_rate:.4f} "
            f"hit_rate={hit_rate:.4f} errors={len(errors or [])}"
        )

    return {
        "enabled": bool(alerts_enabled),
        "severity": severity,
        "triggered": len(triggered_rules),
        "runs": runs,
        "min_runs": min_runs,
        "warmup": bool(warmup),
        "thresholds": {
            "p95_ms": threshold_p95,
            "error_rate_per_run": threshold_error_rate,
            "cache_delta_hit_rate": threshold_hit_rate,
        },
        "rules": rules,
        "triggered_rules": triggered_rules,
    }


def citation_verify_observe_snapshot_fallback(*, window_s: float, max_runs: int) -> dict:
    return {
        "window_s": window_s,
        "max_runs": max_runs,
        "runs": 0,
        "elapsed_ms": {"avg": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0},
        "items": {"total": 0, "avg": 0.0, "p50": 0.0, "p95": 0.0, "max": 0},
        "workers": {"avg": 0.0, "max": 0},
        "errors": {"total": 0, "rate_per_run": 0.0},
        "cache_delta": {"hit": 0, "miss": 0, "set": 0, "expired": 0, "evicted": 0, "hit_rate": 0.0},
        "recent": [],
    }


def safe_citation_verify_metrics_payload(
    *,
    cache_snapshot: Callable[[], dict],
    cache_snapshot_fallback: Callable[[], dict],
    observe_snapshot: Callable[[], dict],
    observe_snapshot_fallback_fn: Callable[[], dict],
    build_alerts_payload: Callable[[bool, list[str], dict], dict],
    alerts_fallback_fn: Callable[[], dict],
    maybe_notify_alerts: Callable[[dict, bool, list[str]], dict],
    webhook_url: Callable[[], str],
    cooldown_s: Callable[[], float],
    append_trend_point: Callable[[dict], None],
    trend_snapshot: Callable[..., dict],
    log_warn: Callable[[str], None],
) -> dict:
    errors: list[str] = []
    try:
        cache = cache_snapshot()
    except Exception as exc:
        cache = cache_snapshot_fallback()
        errors.append(f"cache_snapshot:{exc.__class__.__name__}")
        log_warn("citation_verify metrics cache snapshot failed")
    try:
        observe = observe_snapshot()
    except Exception as exc:
        observe = observe_snapshot_fallback_fn()
        errors.append(f"observe_snapshot:{exc.__class__.__name__}")
        log_warn("citation_verify metrics observe snapshot failed")
    degraded = bool(errors)
    try:
        alerts = build_alerts_payload(degraded, errors, observe)
    except Exception as exc:
        alerts = alerts_fallback_fn()
        errors.append(f"alerts_eval:{exc.__class__.__name__}")
        log_warn("citation_verify metrics alerts eval failed")
    try:
        notification = maybe_notify_alerts(alerts, degraded, errors)
    except Exception as exc:
        notification = {
            "enabled": False,
            "webhook_configured": bool(webhook_url()),
            "sent": False,
            "channels": [],
            "signature": "",
            "dedupe_hit": False,
            "event_type": "none",
            "status": "notify_failed",
            "cooldown_s": round(cooldown_s(), 2),
            "last_sent_at": 0.0,
            "suppressed": 0,
            "last_error": f"notify:{exc.__class__.__name__}",
            "event_id": "",
            "events_total": 0,
            "events_recent": [],
        }
        log_warn("citation_verify metrics notify failed")
    if isinstance(alerts, dict):
        alerts["notification"] = notification
    trend = {"enabled": False, "total": 0, "limit": 30, "points": []}
    try:
        observe_row = observe if isinstance(observe, dict) else {}
        elapsed = observe_row.get("elapsed_ms") if isinstance(observe_row.get("elapsed_ms"), dict) else {}
        errors_row = observe_row.get("errors") if isinstance(observe_row.get("errors"), dict) else {}
        cache_delta = observe_row.get("cache_delta") if isinstance(observe_row.get("cache_delta"), dict) else {}
        point = {
            "ts": time.time(),
            "severity": str((alerts or {}).get("severity") or "ok"),
            "degraded": bool(degraded),
            "runs": int(observe_row.get("runs") or 0),
            "p95_ms": float(elapsed.get("p95") or 0.0),
            "error_rate_per_run": float(errors_row.get("rate_per_run") or 0.0),
            "cache_delta_hit_rate": float(cache_delta.get("hit_rate") or 0.0),
            "triggered_alerts": int((alerts or {}).get("triggered") or 0),
            "notification_status": str((notification or {}).get("status") or ""),
        }
        append_trend_point(point)
        trend = trend_snapshot(limit=30)
    except Exception as exc:
        errors.append(f"trend_record:{exc.__class__.__name__}")
        log_warn("citation_verify metrics trend record failed")
    degraded = bool(errors)
    return {
        "ok": 1,
        "cache": cache,
        "observe": observe,
        "alerts": alerts,
        "trend": trend,
        "degraded": degraded,
        "errors": errors,
    }
