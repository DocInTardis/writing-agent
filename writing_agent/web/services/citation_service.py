"""Citation Service module.

This module belongs to `writing_agent.web.services` in the writing-agent codebase.
"""

from __future__ import annotations

import html
import ipaddress
import json
import re
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request as UrlRequest, urlopen

from fastapi import Request
from writing_agent.models import Citation

from .base import app_v2_module

_DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", flags=re.IGNORECASE)
_ARXIV_RE = re.compile(r"\b(\d{4}\.\d{4,5}(?:v\d+)?)\b", flags=re.IGNORECASE)
_OPENALEX_WORK_RE = re.compile(r"\bW\d+\b", flags=re.IGNORECASE)
_YEAR_RE = re.compile(r"(?:19|20)\d{2}")
_META_TAG_RE = re.compile(r"<meta\b[^>]*>", flags=re.IGNORECASE)
_META_ATTR_RE = re.compile(r"([A-Za-z_:][A-Za-z0-9_.:-]*)\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)")
_TITLE_RE = re.compile(r"<title\b[^>]*>(.*?)</title>", flags=re.IGNORECASE | re.DOTALL)
_JSONLD_RE = re.compile(
    r"<script\b[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    flags=re.IGNORECASE | re.DOTALL,
)
_RESOLVE_METADATA_MAX_BYTES = 256 * 1024
_RESOLVE_TIMEOUT_S = 8.0
_RESOLVE_USER_AGENT = "writing-agent-studio/2.0 (+citation resolve-url)"
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


def _resolve_alert_notification_info(*, alerts: dict, snapshot: dict) -> dict:
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
        ok, status = _resolve_alert_notify_webhook(webhook_url, payload, timeout_s=timeout_s)
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


def _resolve_observe_snapshot(*, limit: int = 60) -> dict:
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
    alerts["notification"] = _resolve_alert_notification_info(alerts=alerts, snapshot=payload)
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


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split()).strip()


def _extract_year(value: object) -> str:
    found = _YEAR_RE.search(str(value or ""))
    return found.group(0) if found else ""


def _normalize_doi(value: object) -> str:
    raw = _clean_text(value).lower()
    if not raw:
        return ""
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/", "doi:"):
        if raw.startswith(prefix):
            raw = raw[len(prefix) :]
            break
    raw = raw.lstrip("/")
    found = _DOI_RE.search(raw)
    if not found:
        return ""
    return str(found.group(0)).rstrip(").,;:")


def _normalize_public_url(raw_url: str) -> str:
    url = _clean_text(raw_url)
    if not url:
        raise ValueError("url required")
    parsed = urlsplit(url)
    scheme = str(parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        raise ValueError("url must be http or https")
    if not parsed.netloc:
        raise ValueError("url host required")
    if parsed.username or parsed.password:
        raise ValueError("url with credentials is not allowed")
    host = str(parsed.hostname or "").strip().lower()
    if not host:
        raise ValueError("url host required")
    if host == "localhost" or host.endswith(".local"):
        raise ValueError("url host is not allowed")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        raise ValueError("url host is not allowed")
    if parsed.port is not None and int(parsed.port) not in {80, 443}:
        raise ValueError("url port is not allowed")
    path = parsed.path or "/"
    return urlunsplit((scheme, parsed.netloc, path, parsed.query, ""))


def _extract_url_hints(url: str) -> dict[str, str]:
    parsed = urlsplit(url)
    host = str(parsed.hostname or "").strip().lower()
    path = str(parsed.path or "")
    hints = {"doi": "", "arxiv_id": "", "openalex_work": ""}

    if host in {"doi.org", "dx.doi.org"}:
        hints["doi"] = _normalize_doi(path.lstrip("/"))
    if not hints["doi"]:
        hints["doi"] = _normalize_doi(url)

    if "arxiv.org" in host:
        m = re.search(r"/(?:abs|pdf)/([^/?#]+)", path, flags=re.IGNORECASE)
        if m:
            arxiv_raw = str(m.group(1) or "").replace(".pdf", "")
            arxiv_match = _ARXIV_RE.search(arxiv_raw)
            if arxiv_match:
                hints["arxiv_id"] = str(arxiv_match.group(1))
    if not hints["arxiv_id"]:
        arxiv_match = _ARXIV_RE.search(url)
        if arxiv_match:
            hints["arxiv_id"] = str(arxiv_match.group(1))

    if "openalex.org" in host:
        work_match = _OPENALEX_WORK_RE.search(path.upper())
        if work_match:
            hints["openalex_work"] = str(work_match.group(0)).upper()

    return hints


def _decode_body(raw: bytes, content_type: str) -> str:
    charset = "utf-8"
    match = re.search(r"charset=([A-Za-z0-9._-]+)", str(content_type or ""), flags=re.IGNORECASE)
    if match:
        charset = str(match.group(1) or "utf-8").strip().lower()
    try:
        return raw.decode(charset, errors="replace")
    except Exception:
        return raw.decode("utf-8", errors="replace")


def _meta_value(meta_map: dict[str, list[str]], keys: list[str]) -> str:
    for key in keys:
        rows = meta_map.get(str(key).lower())
        if not rows:
            continue
        for row in rows:
            clean = _clean_text(row)
            if clean:
                return clean
    return ""


def _parse_meta_map(html_text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for tag in _META_TAG_RE.findall(html_text):
        attrs: dict[str, str] = {}
        for m in _META_ATTR_RE.finditer(tag):
            k = str(m.group(1) or "").strip().lower()
            v = str(m.group(2) or "").strip()
            if len(v) >= 2 and ((v[0] == '"' and v[-1] == '"') or (v[0] == "'" and v[-1] == "'")):
                v = v[1:-1]
            attrs[k] = _clean_text(html.unescape(v))
        key = attrs.get("name") or attrs.get("property") or attrs.get("itemprop") or ""
        value = attrs.get("content") or ""
        if not key or not value:
            continue
        out.setdefault(key.lower(), []).append(value)
    return out


def _jsonld_first_text(value: object) -> str:
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, dict):
        for key in ("name", "headline", "value"):
            text = _jsonld_first_text(value.get(key))
            if text:
                return text
        return ""
    if isinstance(value, list):
        for item in value:
            text = _jsonld_first_text(item)
            if text:
                return text
    return ""


def _jsonld_authors(value: object) -> list[str]:
    rows = value if isinstance(value, list) else [value]
    out: list[str] = []
    for row in rows:
        name = _jsonld_first_text(row)
        if not name:
            continue
        out.append(name)
    return out


def _jsonld_doi(value: object) -> str:
    if isinstance(value, str):
        return _normalize_doi(value)
    if isinstance(value, dict):
        property_id = _clean_text(value.get("propertyID") or value.get("propertyId")).lower()
        if "doi" in property_id:
            return _normalize_doi(value.get("value"))
        for key in ("value", "name", "url", "@id"):
            doi = _jsonld_doi(value.get(key))
            if doi:
                return doi
        return ""
    if isinstance(value, list):
        for row in value:
            doi = _jsonld_doi(row)
            if doi:
                return doi
    return ""


def _iter_jsonld_objects(html_text: str) -> list[dict]:
    objs: list[dict] = []
    for block in _JSONLD_RE.findall(html_text):
        raw = _clean_text(html.unescape(block))
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        queue: list[object] = [data]
        while queue:
            node = queue.pop(0)
            if isinstance(node, dict):
                objs.append(node)
                graph = node.get("@graph")
                if isinstance(graph, list):
                    queue.extend(graph)
            elif isinstance(node, list):
                queue.extend(node)
    return objs


def _fetch_page_metadata(
    url: str,
    *,
    timeout_s: float = _RESOLVE_TIMEOUT_S,
    max_bytes: int = _RESOLVE_METADATA_MAX_BYTES,
) -> dict:
    req = UrlRequest(
        url=str(url),
        headers={
            "User-Agent": _RESOLVE_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,text/plain;q=0.8,*/*;q=0.2",
        },
        method="GET",
    )
    with urlopen(req, timeout=timeout_s) as resp:  # nosec B310
        content_type = str(resp.headers.get("Content-Type") or "")
        raw = resp.read(max(1024, int(max_bytes) + 1))
    if len(raw) > int(max_bytes):
        raw = raw[: int(max_bytes)]
    text = _decode_body(raw, content_type)
    if not text:
        return {}

    meta_map = _parse_meta_map(text)
    title = ""
    m = _TITLE_RE.search(text)
    if m:
        title = _clean_text(html.unescape(str(m.group(1) or "")))
    title = _meta_value(meta_map, ["citation_title", "og:title", "dc.title"]) or title

    author_rows = meta_map.get("citation_author", []) + meta_map.get("author", []) + meta_map.get("dc.creator", [])
    authors = [_clean_text(row) for row in author_rows if _clean_text(row)]

    year = _extract_year(
        _meta_value(meta_map, ["citation_publication_date", "article:published_time", "dc.date", "citation_date"])
    )
    source = _meta_value(meta_map, ["citation_journal_title", "citation_conference_title", "og:site_name", "dc.source"])
    doi = _normalize_doi(_meta_value(meta_map, ["citation_doi", "dc.identifier"]))

    for obj in _iter_jsonld_objects(text):
        if not title:
            title = _jsonld_first_text(obj.get("headline") or obj.get("name"))
        if not authors:
            authors = _jsonld_authors(obj.get("author"))
        if not year:
            year = _extract_year(_jsonld_first_text(obj.get("datePublished") or obj.get("dateCreated")))
        if not source:
            source = _jsonld_first_text(obj.get("isPartOf") or obj.get("publisher"))
        if not doi:
            doi = _jsonld_doi(obj.get("identifier"))

    return {
        "title": _clean_text(title),
        "authors": [row for row in authors if row][:5],
        "year": _extract_year(year),
        "source": _clean_text(source),
        "doi": _normalize_doi(doi),
    }


def _work_title(work: object) -> str:
    return _clean_text(getattr(work, "title", ""))


def _work_authors(work: object) -> list[str]:
    rows = getattr(work, "authors", []) or []
    return [_clean_text(row) for row in rows if _clean_text(row)][:5]


def _work_year(work: object) -> str:
    return _extract_year(getattr(work, "published", ""))


def _work_source(work: object) -> str:
    source = _clean_text(getattr(work, "primary_category", ""))
    if source:
        return source
    categories = getattr(work, "categories", []) or []
    if isinstance(categories, list):
        for row in categories:
            clean = _clean_text(row)
            if clean:
                return clean
    return ""


def _work_url(work: object) -> str:
    return _clean_text(getattr(work, "abs_url", ""))


def _work_doi(work: object) -> str:
    return _normalize_doi(getattr(work, "doi", "")) or _normalize_doi(_work_url(work))


def _score_resolve_candidate(
    app_v2,
    *,
    hints: dict[str, str],
    cite_seed: Citation,
    query: str,
) -> tuple[str, object | None, float, str, list[str]]:
    warnings: list[str] = []
    candidates: list[tuple[str, object]] = []
    errors: list[str] = []

    query_value = _clean_text(query)
    if query_value:
        rows, row_errors = app_v2._collect_citation_candidates(query_value)
        candidates.extend(rows)
        errors.extend(row_errors)

    doi_hint = _normalize_doi(hints.get("doi"))
    if doi_hint and (not query_value or doi_hint not in query_value.lower()):
        rows, row_errors = app_v2._collect_citation_candidates(doi_hint)
        candidates.extend(rows)
        errors.extend(row_errors)

    if not candidates:
        if errors:
            warnings.append(f"search_error:{'|'.join(errors[:2])}")
        return "", None, 0.0, "metadata_only", warnings

    if doi_hint:
        for provider, work in candidates:
            work_doi = _work_doi(work)
            if work_doi and work_doi == doi_hint:
                return provider, work, 0.98, "doi_exact", warnings

    openalex_hint = str(hints.get("openalex_work") or "").upper()
    if openalex_hint:
        for provider, work in candidates:
            if openalex_hint in _work_url(work).upper():
                return provider, work, 0.96, "openalex_exact", warnings

    if _clean_text(cite_seed.title):
        provider, work, score, _, _ = app_v2._pick_best_citation_candidate(cite_seed, candidates)
        if work is not None:
            return provider, work, max(0.0, float(score)), "search_match", warnings

    provider, work = candidates[0]
    return provider, work, 0.58, "search_first", warnings


def _pick_first_surname(authors: str) -> str:
    raw = _clean_text(authors)
    if not raw:
        return ""
    first = re.split(r"[,;]| and ", raw, flags=re.IGNORECASE)[0].strip()
    tokens = [tok for tok in re.split(r"[^A-Za-z0-9]+", first) if tok]
    if not tokens:
        return ""
    return tokens[-1].lower()


def _pick_title_token(title: str) -> str:
    words = [tok.lower() for tok in re.split(r"[^A-Za-z0-9]+", _clean_text(title)) if len(tok) >= 3]
    if not words:
        words = [tok.lower() for tok in re.split(r"[^A-Za-z0-9]+", _clean_text(title)) if tok]
    return words[0] if words else ""


def _safe_citation_id(raw: str) -> str:
    value = re.sub(r"[^a-z0-9_]", "", str(raw or "").lower())
    value = re.sub(r"_+", "_", value).strip("_")
    if not value:
        return "cite"
    return value[:40]


def _suggest_citation_id(
    *,
    title: str,
    authors: str,
    year: str,
    doi: str,
    arxiv_id: str,
    existing_keys: set[str],
) -> str:
    surname = _pick_first_surname(authors)
    year_token = _extract_year(year)
    title_token = _pick_title_token(title)

    base = _safe_citation_id(f"{surname}{year_token}{title_token}")
    if base == "cite":
        if doi:
            base = _safe_citation_id(f"doi{re.sub(r'[^a-z0-9]+', '', doi.lower())[-12:]}")
        elif arxiv_id:
            base = _safe_citation_id(f"arxiv{re.sub(r'[^a-z0-9]+', '', arxiv_id.lower())}")

    candidate = base
    idx = 2
    while candidate.lower() in existing_keys:
        candidate = f"{base}_{idx}"
        idx += 1
    return candidate


class CitationService:
    def get_citations(self, doc_id: str) -> dict:
        app_v2 = app_v2_module()

        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        items: list[dict] = []
        for key, cite in (session.citations or {}).items():
            items.append(
                {
                    "id": key,
                    "author": cite.authors or "",
                    "title": cite.title or "",
                    "year": cite.year or "",
                    "source": cite.venue or cite.url or "",
                }
            )
        return {"items": items}

    async def save_citations(self, doc_id: str, request: Request) -> dict:
        app_v2 = app_v2_module()

        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        data = await request.json()
        items = data.get("items") if isinstance(data, dict) else None
        session.citations = app_v2._normalize_citation_items(items)
        app_v2.store.put(session)
        return {"ok": 1, "count": len(session.citations or {})}

    async def resolve_url(self, doc_id: str, request: Request) -> dict:
        app_v2 = app_v2_module()
        started = app_v2.time.perf_counter()
        resolver_label = ""
        provider_label = ""
        confidence_value = 0.0
        warnings_value: list[str] = []

        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        try:
            try:
                data = await request.json()
            except Exception:
                data = {}
            if not isinstance(data, dict):
                raise app_v2.HTTPException(status_code=400, detail="body must be object")
            raw_url = _clean_text(data.get("url"))
            if not raw_url:
                raise app_v2.HTTPException(status_code=400, detail="url required")
            try:
                url = _normalize_public_url(raw_url)
            except ValueError as exc:
                raise app_v2.HTTPException(status_code=400, detail=str(exc))

            warnings: list[str] = []
            hints = _extract_url_hints(url)
            metadata: dict = {}
            try:
                metadata = _fetch_page_metadata(url)
            except Exception as exc:
                warnings.append(f"metadata_fetch_failed:{exc.__class__.__name__}")

            if not metadata.get("doi") and hints.get("doi"):
                metadata["doi"] = hints.get("doi")

            metadata_title = _clean_text(metadata.get("title"))
            metadata_authors = metadata.get("authors") if isinstance(metadata.get("authors"), list) else []
            metadata_author_text = ", ".join([_clean_text(row) for row in metadata_authors if _clean_text(row)])
            metadata_year = _extract_year(metadata.get("year"))
            metadata_source = _clean_text(metadata.get("source"))

            query_parts: list[str] = []
            if metadata_title:
                query_parts.append(metadata_title)
            if metadata_author_text:
                query_parts.append(_pick_first_surname(metadata_author_text))
            if metadata_year:
                query_parts.append(metadata_year)
            query = _clean_text(" ".join([part for part in query_parts if part]))
            if not query:
                query = _clean_text(hints.get("doi") or hints.get("arxiv_id") or hints.get("openalex_work") or "")

            cite_seed = Citation(
                key="resolve_tmp",
                title=metadata_title or query,
                url=url,
                authors=metadata_author_text or None,
                year=metadata_year or None,
                venue=metadata_source or None,
            )
            provider, work, confidence, resolver, search_warnings = _score_resolve_candidate(
                app_v2,
                hints=hints,
                cite_seed=cite_seed,
                query=query,
            )
            warnings.extend(search_warnings)

            title = metadata_title
            author = metadata_author_text
            year = metadata_year
            source = metadata_source
            final_url = url
            doi = _normalize_doi(metadata.get("doi") or hints.get("doi"))

            if work is not None:
                title = _work_title(work) or title
                author = ", ".join(_work_authors(work)) or author
                year = _work_year(work) or year
                source = _work_source(work) or source
                final_url = _work_url(work) or final_url
                doi = _work_doi(work) or doi

            if not title:
                raise app_v2.HTTPException(status_code=422, detail="unable to resolve citation title")

            if resolver == "metadata_only":
                confidence = 0.45 if title else 0.0
                warnings.append("metadata_only")
            elif resolver in {"search_match", "search_first"} and confidence < 0.60:
                warnings.append("low_confidence_match")
            elif resolver == "search_match" and confidence < 0.82:
                warnings.append("medium_confidence_match")

            existing_keys = {str(k).strip().lower() for k in (session.citations or {}).keys() if str(k).strip()}
            citation_id = _suggest_citation_id(
                title=title,
                authors=author,
                year=year,
                doi=doi,
                arxiv_id=str(hints.get("arxiv_id") or ""),
                existing_keys=existing_keys,
            )

            resolver_label = str(resolver or "").strip().lower()
            provider_label = str(provider or "").strip().lower()
            confidence_value = max(0.0, min(1.0, float(confidence or 0.0)))
            warnings_value = [str(w).strip() for w in warnings if str(w).strip()]

            item = {
                "id": citation_id,
                "author": author,
                "title": title,
                "year": year,
                "source": source or final_url,
                "url": final_url,
            }
            response = {
                "ok": 1,
                "item": item,
                "confidence": round(confidence_value, 3),
                "warnings": sorted({str(w).strip() for w in warnings_value if str(w).strip()}),
                "debug": {
                    "resolver": resolver_label,
                    "provider": provider_label,
                    "score": round(confidence_value, 3),
                },
            }
            _resolve_observe_record(
                ok=True,
                elapsed_ms=round((app_v2.time.perf_counter() - started) * 1000.0, 2),
                resolver=resolver_label,
                provider=provider_label,
                confidence=confidence_value,
                warnings=warnings_value,
                error="",
            )
            return response
        except app_v2.HTTPException as exc:
            _resolve_observe_record(
                ok=False,
                elapsed_ms=round((app_v2.time.perf_counter() - started) * 1000.0, 2),
                resolver=resolver_label,
                provider=provider_label,
                confidence=confidence_value,
                warnings=warnings_value,
                error=f"http_{int(getattr(exc, 'status_code', 500) or 500)}",
            )
            raise
        except Exception as exc:
            _resolve_observe_record(
                ok=False,
                elapsed_ms=round((app_v2.time.perf_counter() - started) * 1000.0, 2),
                resolver=resolver_label,
                provider=provider_label,
                confidence=confidence_value,
                warnings=warnings_value,
                error=f"exception:{exc.__class__.__name__}",
            )
            raise

    async def verify_citations(self, doc_id: str, request: Request) -> dict:
        app_v2 = app_v2_module()

        session = app_v2.store.get(doc_id)
        if session is None:
            raise app_v2.HTTPException(status_code=404, detail="document not found")
        req_started = app_v2.time.perf_counter()
        cache_before = app_v2._citation_verify_cache_metrics_snapshot()
        try:
            data = await request.json()
        except Exception:
            data = {}

        items = data.get("items") if isinstance(data, dict) else None
        persist = bool(data.get("persist", True)) if isinstance(data, dict) else True
        debug_enabled = bool(data.get("debug", False)) if isinstance(data, dict) else False
        if not debug_enabled:
            debug_enabled = str(app_v2.os.environ.get("WRITING_AGENT_CITATION_VERIFY_DEBUG", "")).strip() == "1"
        requested_debug_level = app_v2._normalize_verify_debug_level(data.get("debug_level") if isinstance(data, dict) else "")
        debug_level = requested_debug_level
        rate_limited_full = False
        if debug_enabled and debug_level == "full":
            if not app_v2._allow_full_debug(doc_id):
                debug_level = "safe"
                rate_limited_full = True
        source_citations = app_v2._normalize_citation_items(items) if isinstance(items, list) else dict(session.citations or {})
        worker_count = 0
        if not source_citations:
            empty = {
                "ok": 1,
                "items": [],
                "updated_items": [],
                "summary": {"total": 0, "verified": 0, "possible": 0, "not_found": 0, "error": 0},
            }
            elapsed_ms = round((app_v2.time.perf_counter() - req_started) * 1000.0, 2)
            cache_after = app_v2._citation_verify_cache_metrics_snapshot()
            request_observe = app_v2._citation_verify_observe_record(
                elapsed_ms=elapsed_ms,
                item_count=0,
                worker_count=0,
                error_count=0,
                cache_before=cache_before,
                cache_after=cache_after,
            )
            observe_snapshot = app_v2._citation_verify_observe_snapshot()
            if debug_enabled:
                empty["debug"] = app_v2._build_citation_verify_debug_payload(
                    persist=persist,
                    input_count=0,
                    worker_count=0,
                    elapsed_ms=elapsed_ms,
                    requested_level=requested_debug_level,
                    debug_level=debug_level,
                    rate_limited_full=rate_limited_full,
                    debug_items=[],
                    request_observe=request_observe,
                    observe_snapshot=observe_snapshot,
                )
            return empty

        results, updated, debug_items, worker_count = app_v2._verify_citation_batch(source_citations, debug_enabled=debug_enabled)

        summary = {"total": len(results), "verified": 0, "possible": 0, "not_found": 0, "error": 0}
        for item in results:
            status = str(item.get("status") or "")
            if status == "verified":
                summary["verified"] += 1
            elif status == "possible":
                summary["possible"] += 1
            elif status == "error":
                summary["error"] += 1
            else:
                summary["not_found"] += 1

        if persist:
            session.citations = updated
            app_v2._set_internal_pref(
                session,
                app_v2._CITATION_VERIFY_KEY,
                {
                    "updated_at": app_v2.time.time(),
                    "items": {str(item.get("id") or ""): item for item in results if str(item.get("id") or "")},
                    "summary": summary,
                },
            )
            app_v2.store.put(session)

        elapsed_ms = round((app_v2.time.perf_counter() - req_started) * 1000.0, 2)
        cache_after = app_v2._citation_verify_cache_metrics_snapshot()
        request_observe = app_v2._citation_verify_observe_record(
            elapsed_ms=elapsed_ms,
            item_count=len(results),
            worker_count=worker_count,
            error_count=int(summary.get("error") or 0),
            cache_before=cache_before,
            cache_after=cache_after,
        )
        observe_snapshot = app_v2._citation_verify_observe_snapshot()

        updated_items = [app_v2._citation_payload(cite) for cite in updated.values()]
        response = {"ok": 1, "items": results, "updated_items": updated_items, "summary": summary}
        if debug_enabled:
            response["debug"] = app_v2._build_citation_verify_debug_payload(
                persist=persist,
                input_count=len(source_citations),
                worker_count=worker_count,
                elapsed_ms=elapsed_ms,
                requested_level=requested_debug_level,
                debug_level=debug_level,
                rate_limited_full=rate_limited_full,
                debug_items=debug_items,
                request_observe=request_observe,
                observe_snapshot=observe_snapshot,
            )
        return response

    def metrics_citation_verify(self) -> dict:
        app_v2 = app_v2_module()

        return app_v2._safe_citation_verify_metrics_payload()

    def metrics_citation_resolve_url(self, limit: int = 60) -> dict:
        return {"ok": 1, **_resolve_observe_snapshot(limit=limit)}

    def metrics_citation_resolve_alerts_config(self, request: Request) -> dict:
        app_v2 = app_v2_module()

        app_v2._require_ops_permission(request, "alerts.read")
        return {"ok": 1, "config": _resolve_alerts_config_effective(), "source": _resolve_alerts_config_source()}

    async def metrics_citation_resolve_alerts_config_save(self, request: Request) -> dict:
        app_v2 = app_v2_module()

        app_v2._require_ops_permission(request, "alerts.write")
        try:
            data = await request.json()
        except Exception:
            data = {}
        if not isinstance(data, dict):
            raise app_v2.HTTPException(status_code=400, detail="body must be object")
        if bool(data.get("reset")):
            config = _resolve_alerts_config_reset()
            return {"ok": 1, "config": config, "source": "env", "reset": True}
        payload = data.get("config") if isinstance(data.get("config"), dict) else data
        config = _resolve_alerts_config_save(payload)
        return {"ok": 1, "config": config, "source": "file", "reset": False}

    def metrics_citation_verify_alerts_config(self, request: Request) -> dict:
        app_v2 = app_v2_module()

        app_v2._require_ops_permission(request, "alerts.read")
        config = app_v2._citation_verify_alerts_config_effective()
        return {"ok": 1, "config": config, "source": app_v2._citation_verify_alerts_config_source()}

    async def metrics_citation_verify_alerts_config_save(self, request: Request) -> dict:
        app_v2 = app_v2_module()

        app_v2._require_ops_permission(request, "alerts.write")
        try:
            data = await request.json()
        except Exception:
            data = {}
        if not isinstance(data, dict):
            raise app_v2.HTTPException(status_code=400, detail="body must be object")
        if bool(data.get("reset")):
            config = app_v2._citation_verify_alerts_config_reset()
            return {"ok": 1, "config": config, "source": "env", "reset": True}
        payload = data.get("config") if isinstance(data.get("config"), dict) else data
        config = app_v2._citation_verify_alerts_config_save(payload)
        return {"ok": 1, "config": config, "source": "file", "reset": False}

    def metrics_citation_verify_alerts_events(self, request: Request, limit: int = 50) -> dict:
        app_v2 = app_v2_module()

        app_v2._require_ops_permission(request, "alerts.read")
        snapshot = app_v2._citation_verify_alert_events_snapshot(limit=limit)
        return {"ok": 1, **snapshot}

    def metrics_citation_verify_alerts_event_detail(self, request: Request, event_id: str, context: int = 12) -> dict:
        app_v2 = app_v2_module()

        app_v2._require_ops_permission(request, "alerts.read")
        event = app_v2._citation_verify_alert_event_get(event_id)
        if not isinstance(event, dict):
            raise app_v2.HTTPException(status_code=404, detail="event not found")
        trend_context = app_v2._citation_verify_metrics_trend_context(ts=float(event.get("ts") or 0.0), limit=context)
        return {"ok": 1, "event": event, "trend_context": trend_context}

    def metrics_citation_verify_trends(self, limit: int = 120) -> dict:
        app_v2 = app_v2_module()

        snapshot = app_v2._citation_verify_metrics_trends_snapshot(limit=limit)
        return {"ok": 1, **snapshot}
