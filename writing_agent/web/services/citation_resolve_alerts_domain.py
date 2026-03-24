"""Citation resolve alert and observe support."""

from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path
from urllib.request import Request as UrlRequest, urlopen

from .base import app_v2_module

_RESOLVE_OBSERVE_LOCK = threading.Lock()
_RESOLVE_OBSERVE_RUNS: list[dict] = []
_RESOLVE_ALERT_NOTIFY_LOCK = threading.Lock()
_RESOLVE_ALERT_EVENTS_LOCK = threading.Lock()
_RESOLVE_ALERT_EVENTS: list[dict] = []
_RESOLVE_ALERT_NOTIFY_STATE: dict[str, object] = {
    "severity": "ok",
    "signature": "",
    "last_sent_at": 0.0,
    "suppressed": 0,
    "last_error": "",
    "last_event_type": "",
    "last_event_id": "",
}
_RESOLVE_ALERTS_CONFIG_LOCK = threading.Lock()
_RESOLVE_ALERTS_CONFIG_CACHE: dict[str, object] | None = None
_RESOLVE_ALERTS_CONFIG_LOADED = False


def _as_bounded_int(value: object, *, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        try:
            parsed = int(float(value))
        except Exception:
            parsed = int(default)
    return max(int(min_value), min(int(max_value), int(parsed)))


def _as_bounded_float(value: object, *, default: float, min_value: float, max_value: float) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = float(default)
    return max(float(min_value), min(float(max_value), float(parsed)))


def _coerce_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, (int, float)):
        return float(value) != 0.0
    raw = str(value or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return bool(default)


def _resolve_alerts_config_path() -> Path:
    app_v2 = app_v2_module()
    raw = str(app_v2.os.environ.get("WRITING_AGENT_CITATION_RESOLVE_ALERT_CONFIG_PATH", "")).strip()
    if raw:
        return Path(raw)
    data_dir = Path(getattr(app_v2, "DATA_DIR", Path(".data")))
    return data_dir / "citation_resolve_alerts_config.json"


def _resolve_alerts_env_defaults() -> dict:
    env = app_v2_module().os.environ
    return {
        "enabled": _coerce_bool(env.get("WRITING_AGENT_CITATION_RESOLVE_ALERTS", "1"), default=True),
        "min_runs": _as_bounded_int(
            env.get("WRITING_AGENT_CITATION_RESOLVE_ALERT_MIN_RUNS", "8"),
            default=8,
            min_value=1,
            max_value=500,
        ),
        "failure_rate": _as_bounded_float(
            env.get("WRITING_AGENT_CITATION_RESOLVE_ALERT_FAILURE_RATE", "0.35"),
            default=0.35,
            min_value=0.0,
            max_value=1.0,
        ),
        "fallback_rate": _as_bounded_float(
            env.get("WRITING_AGENT_CITATION_RESOLVE_ALERT_FALLBACK_RATE", "0.55"),
            default=0.55,
            min_value=0.0,
            max_value=1.0,
        ),
        "p95_ms": _as_bounded_float(
            env.get("WRITING_AGENT_CITATION_RESOLVE_ALERT_P95_MS", "4500"),
            default=4500.0,
            min_value=100.0,
            max_value=60000.0,
        ),
        "low_confidence_rate": _as_bounded_float(
            env.get("WRITING_AGENT_CITATION_RESOLVE_ALERT_LOW_CONF_RATE", "0.40"),
            default=0.40,
            min_value=0.0,
            max_value=1.0,
        ),
        "notify_enabled": _coerce_bool(env.get("WRITING_AGENT_CITATION_RESOLVE_ALERT_NOTIFY", "1"), default=True),
        "notify_cooldown_s": _as_bounded_float(
            env.get("WRITING_AGENT_CITATION_RESOLVE_ALERT_NOTIFY_COOLDOWN_S", "300"),
            default=300.0,
            min_value=10.0,
            max_value=86400.0,
        ),
        "notify_timeout_s": _as_bounded_float(
            env.get("WRITING_AGENT_CITATION_RESOLVE_ALERT_NOTIFY_TIMEOUT_S", "4"),
            default=4.0,
            min_value=1.0,
            max_value=30.0,
        ),
    }


def _normalize_resolve_alerts_config(raw: object, *, defaults: dict | None = None) -> dict:
    base = dict(defaults or _resolve_alerts_env_defaults())
    row = raw if isinstance(raw, dict) else {}
    if "enabled" in row:
        base["enabled"] = _coerce_bool(row.get("enabled"), default=bool(base.get("enabled", True)))
    if "min_runs" in row:
        base["min_runs"] = _as_bounded_int(
            row.get("min_runs"),
            default=int(base.get("min_runs", 8)),
            min_value=1,
            max_value=500,
        )
    if "failure_rate" in row:
        base["failure_rate"] = _as_bounded_float(
            row.get("failure_rate"),
            default=float(base.get("failure_rate", 0.35)),
            min_value=0.0,
            max_value=1.0,
        )
    if "fallback_rate" in row:
        base["fallback_rate"] = _as_bounded_float(
            row.get("fallback_rate"),
            default=float(base.get("fallback_rate", 0.55)),
            min_value=0.0,
            max_value=1.0,
        )
    if "p95_ms" in row:
        base["p95_ms"] = _as_bounded_float(
            row.get("p95_ms"),
            default=float(base.get("p95_ms", 4500.0)),
            min_value=100.0,
            max_value=60000.0,
        )
    if "low_confidence_rate" in row:
        base["low_confidence_rate"] = _as_bounded_float(
            row.get("low_confidence_rate"),
            default=float(base.get("low_confidence_rate", 0.40)),
            min_value=0.0,
            max_value=1.0,
        )
    if "notify_enabled" in row:
        base["notify_enabled"] = _coerce_bool(row.get("notify_enabled"), default=bool(base.get("notify_enabled", True)))
    if "notify_cooldown_s" in row:
        base["notify_cooldown_s"] = _as_bounded_float(
            row.get("notify_cooldown_s"),
            default=float(base.get("notify_cooldown_s", 300.0)),
            min_value=10.0,
            max_value=86400.0,
        )
    if "notify_timeout_s" in row:
        base["notify_timeout_s"] = _as_bounded_float(
            row.get("notify_timeout_s"),
            default=float(base.get("notify_timeout_s", 4.0)),
            min_value=1.0,
            max_value=30.0,
        )
    return base


def _resolve_alerts_config_reset_cache() -> None:
    global _RESOLVE_ALERTS_CONFIG_CACHE, _RESOLVE_ALERTS_CONFIG_LOADED
    with _RESOLVE_ALERTS_CONFIG_LOCK:
        _RESOLVE_ALERTS_CONFIG_CACHE = None
        _RESOLVE_ALERTS_CONFIG_LOADED = False


def _resolve_alerts_config_load_from_disk_locked(*, defaults: dict) -> dict | None:
    path = _resolve_alerts_config_path()
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    return _normalize_resolve_alerts_config(raw, defaults=defaults)


def _resolve_alerts_config_effective() -> dict:
    global _RESOLVE_ALERTS_CONFIG_CACHE, _RESOLVE_ALERTS_CONFIG_LOADED
    defaults = _resolve_alerts_env_defaults()
    with _RESOLVE_ALERTS_CONFIG_LOCK:
        if not _RESOLVE_ALERTS_CONFIG_LOADED:
            _RESOLVE_ALERTS_CONFIG_CACHE = _resolve_alerts_config_load_from_disk_locked(defaults=defaults)
            _RESOLVE_ALERTS_CONFIG_LOADED = True
        cache = _RESOLVE_ALERTS_CONFIG_CACHE
    if isinstance(cache, dict):
        return _normalize_resolve_alerts_config(cache, defaults=defaults)
    return defaults


def _resolve_alerts_config_source() -> str:
    with _RESOLVE_ALERTS_CONFIG_LOCK:
        cache = _RESOLVE_ALERTS_CONFIG_CACHE
    return "file" if isinstance(cache, dict) else "env"


def _resolve_alerts_config_save(raw: object) -> dict:
    global _RESOLVE_ALERTS_CONFIG_CACHE, _RESOLVE_ALERTS_CONFIG_LOADED
    defaults = _resolve_alerts_env_defaults()
    config = _normalize_resolve_alerts_config(raw, defaults=defaults)
    path = _resolve_alerts_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _RESOLVE_ALERTS_CONFIG_LOCK:
        path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        _RESOLVE_ALERTS_CONFIG_CACHE = dict(config)
        _RESOLVE_ALERTS_CONFIG_LOADED = True
    return config


def _resolve_alerts_config_reset() -> dict:
    global _RESOLVE_ALERTS_CONFIG_CACHE, _RESOLVE_ALERTS_CONFIG_LOADED
    defaults = _resolve_alerts_env_defaults()
    path = _resolve_alerts_config_path()
    with _RESOLVE_ALERTS_CONFIG_LOCK:
        try:
            if path.exists():
                path.unlink()
        except Exception:
            pass
        _RESOLVE_ALERTS_CONFIG_CACHE = None
        _RESOLVE_ALERTS_CONFIG_LOADED = True
    return defaults


def _resolve_observe_max_runs() -> int:
    return _as_bounded_int(
        app_v2_module().os.environ.get("WRITING_AGENT_CITATION_RESOLVE_OBSERVE_MAX_RUNS", "240"),
        default=240,
        min_value=20,
        max_value=5000,
    )


def _resolve_observe_window_s() -> float:
    return _as_bounded_float(
        app_v2_module().os.environ.get("WRITING_AGENT_CITATION_RESOLVE_OBSERVE_WINDOW_S", "1800"),
        default=1800.0,
        min_value=60.0,
        max_value=86400.0,
    )


def _resolve_alerts_enabled() -> bool:
    return bool(_resolve_alerts_config_effective().get("enabled", True))


def _resolve_alert_min_runs() -> int:
    return int(_resolve_alerts_config_effective().get("min_runs", 8))


def _resolve_alert_failure_rate_threshold() -> float:
    return float(_resolve_alerts_config_effective().get("failure_rate", 0.35))


def _resolve_alert_fallback_rate_threshold() -> float:
    return float(_resolve_alerts_config_effective().get("fallback_rate", 0.55))


def _resolve_alert_p95_ms_threshold() -> float:
    return float(_resolve_alerts_config_effective().get("p95_ms", 4500.0))


def _resolve_alert_low_conf_rate_threshold() -> float:
    return float(_resolve_alerts_config_effective().get("low_confidence_rate", 0.40))


def _resolve_alert_notify_enabled() -> bool:
    return bool(_resolve_alerts_config_effective().get("notify_enabled", True))


def _resolve_alert_notify_webhook_url() -> str:
    return str(app_v2_module().os.environ.get("WRITING_AGENT_CITATION_RESOLVE_ALERT_WEBHOOK_URL", "")).strip()


def _resolve_alert_notify_cooldown_s() -> float:
    return float(_resolve_alerts_config_effective().get("notify_cooldown_s", 300.0))


def _resolve_alert_notify_timeout_s() -> float:
    return float(_resolve_alerts_config_effective().get("notify_timeout_s", 4.0))


def _resolve_alert_events_max_entries() -> int:
    return _as_bounded_int(
        app_v2_module().os.environ.get("WRITING_AGENT_CITATION_RESOLVE_ALERT_EVENTS_MAX", "800"),
        default=800,
        min_value=50,
        max_value=20000,
    )


def _resolve_alert_events_append(event: dict) -> dict:
    row = dict(event or {})
    row["id"] = str(row.get("id") or uuid.uuid4().hex)
    row["ts"] = float(row.get("ts") or time.time())
    with _RESOLVE_ALERT_EVENTS_LOCK:
        _RESOLVE_ALERT_EVENTS.append(row)
        max_entries = _resolve_alert_events_max_entries()
        if len(_RESOLVE_ALERT_EVENTS) > max_entries:
            _RESOLVE_ALERT_EVENTS[:] = _RESOLVE_ALERT_EVENTS[-max_entries:]
    return row


def _resolve_alert_events_snapshot(*, limit: int = 20) -> dict:
    size = _as_bounded_int(limit, default=20, min_value=1, max_value=200)
    with _RESOLVE_ALERT_EVENTS_LOCK:
        rows = list(_RESOLVE_ALERT_EVENTS)
    return {"total": len(rows), "limit": size, "events": list(rows[-size:])}


def _resolve_alert_signature(*, severity: str, triggered_rules: list[str]) -> str:
    level = str(severity or "").strip().lower() or "ok"
    rules = sorted({str(row or "").strip().lower() for row in (triggered_rules or []) if str(row or "").strip()})
    return f"{level}|{'/'.join(rules)}"


def _resolve_alert_notify_webhook(url: str, payload: dict, *, timeout_s: float) -> tuple[bool, str]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = UrlRequest(str(url), data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=float(timeout_s)) as resp:  # nosec B310
        code = int(getattr(resp, "status", 0) or resp.getcode() or 0)
    if 200 <= code < 300:
        return True, f"http_{code}"
    return False, f"http_{code}"


def _resolve_alert_notification_info(
    *,
    alerts: dict,
    snapshot: dict,
    notify_webhook_fn=None,
) -> dict:
    enabled = bool(alerts.get("enabled"))
    severity = str(alerts.get("severity") or "ok").strip().lower()
    triggered_rules = [str(x).strip() for x in (alerts.get("triggered_rules") or []) if str(x).strip()]
    notify_enabled = _resolve_alert_notify_enabled()
    webhook_url = _resolve_alert_notify_webhook_url()
    cooldown_s = _resolve_alert_notify_cooldown_s()
    timeout_s = _resolve_alert_notify_timeout_s()
    base = {
        "enabled": bool(notify_enabled),
        "webhook_configured": bool(webhook_url),
        "sent": False,
        "channels": ["webhook"] if webhook_url else [],
        "signature": "",
        "dedupe_hit": False,
        "event_type": "none",
        "status": "idle",
        "cooldown_s": float(cooldown_s),
        "timeout_s": float(timeout_s),
        "last_sent_at": 0.0,
        "suppressed": 0,
        "last_error": "",
        "event_id": "",
        "events_total": 0,
        "events_recent": [],
    }

    with _RESOLVE_ALERT_NOTIFY_LOCK:
        state = dict(_RESOLVE_ALERT_NOTIFY_STATE)

    base["last_sent_at"] = float(state.get("last_sent_at") or 0.0)
    base["suppressed"] = int(state.get("suppressed") or 0)
    base["last_error"] = str(state.get("last_error") or "")

    if not enabled:
        base["status"] = "alerts_disabled"
        snapshot_events = _resolve_alert_events_snapshot(limit=6)
        base["events_total"] = int(snapshot_events.get("total") or 0)
        base["events_recent"] = list(snapshot_events.get("events") or [])
        return base
    if severity == "ok":
        base["status"] = "ok"
        snapshot_events = _resolve_alert_events_snapshot(limit=6)
        base["events_total"] = int(snapshot_events.get("total") or 0)
        base["events_recent"] = list(snapshot_events.get("events") or [])
        return base
    if not notify_enabled:
        base["status"] = "notify_disabled"
        snapshot_events = _resolve_alert_events_snapshot(limit=6)
        base["events_total"] = int(snapshot_events.get("total") or 0)
        base["events_recent"] = list(snapshot_events.get("events") or [])
        return base
    if not webhook_url:
        base["status"] = "no_webhook"
        snapshot_events = _resolve_alert_events_snapshot(limit=6)
        base["events_total"] = int(snapshot_events.get("total") or 0)
        base["events_recent"] = list(snapshot_events.get("events") or [])
        return base

    signature = _resolve_alert_signature(severity=severity, triggered_rules=triggered_rules)
    base["signature"] = signature
    event_type = f"resolve_alert.{severity}"
    now = time.time()

    with _RESOLVE_ALERT_NOTIFY_LOCK:
        same_signature = str(_RESOLVE_ALERT_NOTIFY_STATE.get("signature") or "") == signature
        elapsed = now - float(_RESOLVE_ALERT_NOTIFY_STATE.get("last_sent_at") or 0.0)
        base["event_type"] = event_type
        if same_signature:
            _RESOLVE_ALERT_NOTIFY_STATE["suppressed"] = int(_RESOLVE_ALERT_NOTIFY_STATE.get("suppressed") or 0) + 1
            _RESOLVE_ALERT_NOTIFY_STATE["last_event_type"] = event_type
            base["dedupe_hit"] = True
            base["status"] = "dedupe_skip"
            base["suppressed"] = int(_RESOLVE_ALERT_NOTIFY_STATE.get("suppressed") or 0)
            base["last_sent_at"] = float(_RESOLVE_ALERT_NOTIFY_STATE.get("last_sent_at") or 0.0)
            base["last_error"] = str(_RESOLVE_ALERT_NOTIFY_STATE.get("last_error") or "")
        elif elapsed < cooldown_s:
            _RESOLVE_ALERT_NOTIFY_STATE["suppressed"] = int(_RESOLVE_ALERT_NOTIFY_STATE.get("suppressed") or 0) + 1
            _RESOLVE_ALERT_NOTIFY_STATE["last_event_type"] = event_type
            base["status"] = "cooldown_skip"
            base["suppressed"] = int(_RESOLVE_ALERT_NOTIFY_STATE.get("suppressed") or 0)
            base["last_sent_at"] = float(_RESOLVE_ALERT_NOTIFY_STATE.get("last_sent_at") or 0.0)
            base["last_error"] = str(_RESOLVE_ALERT_NOTIFY_STATE.get("last_error") or "")
        else:
            # mark as pending, actual network call happens outside lock
            base["status"] = "pending_send"

    if base["status"] != "pending_send":
        snapshot_events = _resolve_alert_events_snapshot(limit=6)
        base["events_total"] = int(snapshot_events.get("total") or 0)
        base["events_recent"] = list(snapshot_events.get("events") or [])
        return base

    payload = {
        "event_type": event_type,
        "severity": severity,
        "signature": signature,
        "triggered_rules": triggered_rules,
        "alerts": alerts,
        "snapshot": {
            "runs": int(snapshot.get("runs") or 0),
            "success_rate": float(snapshot.get("success_rate") or 0.0),
            "failure_rate": float(snapshot.get("failure_rate") or 0.0),
            "fallback_rate": float(snapshot.get("fallback_rate") or 0.0),
            "low_confidence_rate": float(snapshot.get("low_confidence_rate") or 0.0),
            "latency_ms": dict(snapshot.get("latency_ms") or {}),
        },
    }
    ok = False
    status = "send_error"
    last_error = ""
    try:
        webhook = notify_webhook_fn or _resolve_alert_notify_webhook
        ok, status = webhook(webhook_url, payload, timeout_s=timeout_s)
    except Exception as exc:
        ok = False
        status = f"exception:{exc.__class__.__name__}"
        last_error = status

    event = _resolve_alert_events_append(
        {
            "severity": severity,
            "event_type": event_type,
            "status": status,
            "sent": bool(ok),
            "dedupe_hit": False,
            "signature": signature,
            "triggered_rules": triggered_rules,
            "channels": ["webhook"],
        }
    )
    with _RESOLVE_ALERT_NOTIFY_LOCK:
        _RESOLVE_ALERT_NOTIFY_STATE["severity"] = severity
        _RESOLVE_ALERT_NOTIFY_STATE["signature"] = signature if ok else str(_RESOLVE_ALERT_NOTIFY_STATE.get("signature") or "")
        _RESOLVE_ALERT_NOTIFY_STATE["last_event_type"] = event_type
        _RESOLVE_ALERT_NOTIFY_STATE["last_event_id"] = str(event.get("id") or "")
        _RESOLVE_ALERT_NOTIFY_STATE["last_error"] = "" if ok else (last_error or status)
        if ok:
            _RESOLVE_ALERT_NOTIFY_STATE["last_sent_at"] = now
            _RESOLVE_ALERT_NOTIFY_STATE["suppressed"] = 0

        base["status"] = status
        base["sent"] = bool(ok)
        base["event_type"] = event_type
        base["event_id"] = str(event.get("id") or "")
        base["last_error"] = str(_RESOLVE_ALERT_NOTIFY_STATE.get("last_error") or "")
        base["last_sent_at"] = float(_RESOLVE_ALERT_NOTIFY_STATE.get("last_sent_at") or 0.0)
        base["suppressed"] = int(_RESOLVE_ALERT_NOTIFY_STATE.get("suppressed") or 0)

    snapshot_events = _resolve_alert_events_snapshot(limit=6)
    base["events_total"] = int(snapshot_events.get("total") or 0)
    base["events_recent"] = list(snapshot_events.get("events") or [])
    return base


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    vals = sorted([max(0.0, float(v)) for v in values])
    if len(vals) == 1:
        return float(vals[0])
    idx = max(0, min(len(vals) - 1, int(round((len(vals) - 1) * float(q)))))
    return float(vals[idx])


def _resolve_observe_prune_locked(*, now: float) -> None:
    floor = float(now) - _resolve_observe_window_s()
    rows: list[dict] = []
    for raw in _RESOLVE_OBSERVE_RUNS:
        row = raw if isinstance(raw, dict) else {}
        try:
            ts = float(row.get("ts") or 0.0)
        except Exception:
            ts = 0.0
        if ts >= floor:
            rows.append(row)
    max_runs = _resolve_observe_max_runs()
    if len(rows) > max_runs:
        rows = rows[-max_runs:]
    _RESOLVE_OBSERVE_RUNS[:] = rows


def _resolve_observe_record(
    *,
    ok: bool,
    elapsed_ms: float,
    resolver: str,
    provider: str,
    confidence: float,
    warnings: list[str],
    error: str = "",
) -> dict:
    warning_items = [str(w).strip() for w in (warnings or []) if str(w).strip()]
    row = {
        "ts": time.time(),
        "ok": bool(ok),
        "elapsed_ms": max(0.0, float(elapsed_ms)),
        "resolver": str(resolver or "").strip().lower(),
        "provider": str(provider or "").strip().lower(),
        "confidence": max(0.0, min(1.0, float(confidence or 0.0))),
        "warnings": warning_items[:8],
        "warning_count": len(warning_items),
        "metadata_only": "metadata_only" in warning_items or str(resolver or "").strip().lower() == "metadata_only",
        "low_confidence": ("low_confidence_match" in warning_items) or ("medium_confidence_match" in warning_items),
        "error": str(error or "").strip()[:160],
    }
    with _RESOLVE_OBSERVE_LOCK:
        _resolve_observe_prune_locked(now=time.time())
        _RESOLVE_OBSERVE_RUNS.append(row)
        _resolve_observe_prune_locked(now=time.time())
    return row


def _resolve_alerts_payload(snapshot: dict) -> dict:
    runs = int(snapshot.get("runs") or 0)
    min_runs = _resolve_alert_min_runs()
    enabled = _resolve_alerts_enabled()
    thresholds = {
        "failure_rate": float(_resolve_alert_failure_rate_threshold()),
        "fallback_rate": float(_resolve_alert_fallback_rate_threshold()),
        "p95_ms": float(_resolve_alert_p95_ms_threshold()),
        "low_confidence_rate": float(_resolve_alert_low_conf_rate_threshold()),
    }
    rules = [
        {
            "id": "failure_rate",
            "level": "critical",
            "value": float(snapshot.get("failure_rate") or 0.0),
            "threshold": thresholds["failure_rate"],
            "op": ">=",
            "message": "failure rate too high",
        },
        {
            "id": "fallback_rate",
            "level": "warn",
            "value": float(snapshot.get("fallback_rate") or 0.0),
            "threshold": thresholds["fallback_rate"],
            "op": ">=",
            "message": "metadata-only fallback rate high",
        },
        {
            "id": "p95_ms",
            "level": "warn",
            "value": float((((snapshot.get("latency_ms") or {}) if isinstance(snapshot.get("latency_ms"), dict) else {}).get("p95")) or 0.0),
            "threshold": thresholds["p95_ms"],
            "op": ">=",
            "message": "resolve latency p95 high",
        },
        {
            "id": "low_confidence_rate",
            "level": "warn",
            "value": float(snapshot.get("low_confidence_rate") or 0.0),
            "threshold": thresholds["low_confidence_rate"],
            "op": ">=",
            "message": "low-confidence resolve ratio high",
        },
    ]

    warmup = runs < min_runs
    triggered_rules: list[str] = []
    out_rules: list[dict] = []
    for rule in rules:
        triggered = False
        if enabled and not warmup:
            triggered = float(rule.get("value") or 0.0) >= float(rule.get("threshold") or 0.0)
        row = dict(rule)
        row["triggered"] = bool(triggered)
        row["value"] = float(row.get("value") or 0.0)
        row["threshold"] = float(row.get("threshold") or 0.0)
        out_rules.append(row)
        if triggered:
            triggered_rules.append(str(row.get("id") or ""))

    severity = "ok"
    if any((row.get("triggered") and str(row.get("level") or "") == "critical") for row in out_rules):
        severity = "critical"
    elif any(bool(row.get("triggered")) for row in out_rules):
        severity = "warn"

    return {
        "enabled": bool(enabled),
        "severity": severity,
        "triggered": len(triggered_rules),
        "runs": runs,
        "min_runs": min_runs,
        "warmup": bool(enabled and warmup),
        "thresholds": thresholds,
        "rules": out_rules,
        "triggered_rules": triggered_rules,
    }


def _resolve_observe_snapshot(*, limit: int = 60, alert_notification_info_fn=None) -> dict:
    size = _as_bounded_int(limit, default=60, min_value=1, max_value=300)
    with _RESOLVE_OBSERVE_LOCK:
        _resolve_observe_prune_locked(now=time.time())
        rows = list(_RESOLVE_OBSERVE_RUNS)

    requests = len(rows)
    success = sum(1 for row in rows if bool((row if isinstance(row, dict) else {}).get("ok")))
    failed = max(0, requests - success)
    metadata_only = sum(1 for row in rows if bool((row if isinstance(row, dict) else {}).get("metadata_only")))
    low_confidence = sum(1 for row in rows if bool((row if isinstance(row, dict) else {}).get("low_confidence")))

    elapsed_values = [
        max(0.0, float((row if isinstance(row, dict) else {}).get("elapsed_ms") or 0.0))
        for row in rows
    ]
    confidence_values = [
        max(0.0, min(1.0, float((row if isinstance(row, dict) else {}).get("confidence") or 0.0)))
        for row in rows
        if bool((row if isinstance(row, dict) else {}).get("ok"))
    ]

    providers: dict[str, int] = {}
    resolvers: dict[str, int] = {}
    for row in rows:
        payload = row if isinstance(row, dict) else {}
        provider = str(payload.get("provider") or "").strip().lower() or "_unknown"
        resolver = str(payload.get("resolver") or "").strip().lower() or "_unknown"
        providers[provider] = int(providers.get(provider, 0)) + 1
        resolvers[resolver] = int(resolvers.get(resolver, 0)) + 1

    recent: list[dict] = []
    for row in rows[-size:]:
        payload = row if isinstance(row, dict) else {}
        recent.append(
            {
                "ts": float(payload.get("ts") or 0.0),
                "ok": bool(payload.get("ok")),
                "elapsed_ms": round(max(0.0, float(payload.get("elapsed_ms") or 0.0)), 2),
                "resolver": str(payload.get("resolver") or ""),
                "provider": str(payload.get("provider") or ""),
                "confidence": round(max(0.0, min(1.0, float(payload.get("confidence") or 0.0))), 4),
                "warning_count": int(payload.get("warning_count") or 0),
                "metadata_only": bool(payload.get("metadata_only")),
                "low_confidence": bool(payload.get("low_confidence")),
                "error": str(payload.get("error") or ""),
            }
        )

    success_rate = (float(success) / float(requests)) if requests > 0 else 0.0
    failure_rate = (float(failed) / float(requests)) if requests > 0 else 0.0
    fallback_rate = (float(metadata_only) / float(success)) if success > 0 else 0.0
    low_confidence_rate = (float(low_confidence) / float(success)) if success > 0 else 0.0
    payload = {
        "window_s": _resolve_observe_window_s(),
        "max_runs": _resolve_observe_max_runs(),
        "runs": requests,
        "success_rate": round(success_rate, 4),
        "failure_rate": round(failure_rate, 4),
        "fallback_rate": round(fallback_rate, 4),
        "low_confidence_rate": round(low_confidence_rate, 4),
        "totals": {
            "requests": requests,
            "success": success,
            "failed": failed,
            "metadata_only": metadata_only,
            "low_confidence": low_confidence,
        },
        "latency_ms": {
            "avg": round((sum(elapsed_values) / max(1, len(elapsed_values))) if elapsed_values else 0.0, 2),
            "p50": round(_percentile(elapsed_values, 0.50), 2),
            "p95": round(_percentile(elapsed_values, 0.95), 2),
            "max": round(max(elapsed_values) if elapsed_values else 0.0, 2),
        },
        "confidence": {
            "avg": round((sum(confidence_values) / max(1, len(confidence_values))) if confidence_values else 0.0, 4),
            "p50": round(_percentile(confidence_values, 0.50), 4),
            "p95": round(_percentile(confidence_values, 0.95), 4),
        },
        "providers": providers,
        "resolvers": resolvers,
        "recent": recent,
    }
    alerts = _resolve_alerts_payload(payload)
    notification_info = alert_notification_info_fn or _resolve_alert_notification_info
    alerts["notification"] = notification_info(alerts=alerts, snapshot=payload)
    payload["alerts"] = alerts
    return payload


def _resolve_observe_reset() -> None:
    with _RESOLVE_OBSERVE_LOCK:
        _RESOLVE_OBSERVE_RUNS.clear()
    with _RESOLVE_ALERT_EVENTS_LOCK:
        _RESOLVE_ALERT_EVENTS.clear()
    with _RESOLVE_ALERT_NOTIFY_LOCK:
        _RESOLVE_ALERT_NOTIFY_STATE.update(
            {
                "severity": "ok",
                "signature": "",
                "last_sent_at": 0.0,
                "suppressed": 0,
                "last_error": "",
                "last_event_type": "",
                "last_event_id": "",
            }
        )
