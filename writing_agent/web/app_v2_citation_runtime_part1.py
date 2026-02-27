"""App V2 Citation Runtime Part1 module.

This module belongs to `writing_agent.web` in the writing-agent codebase.
"""

from __future__ import annotations

from functools import wraps
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from urllib.request import Request as UrlRequest, urlopen

from fastapi import HTTPException, Request

_BIND_SKIP_NAMES = {
    "__builtins__",
    "__cached__",
    "__doc__",
    "__file__",
    "__loader__",
    "__name__",
    "__package__",
    "__spec__",
    "_BIND_SKIP_NAMES",
    "_STATE_PREFIXES",
    "bind",
    "install",
    "_proxy_factory",
    "_sync_state_from_namespace",
    "_sync_state_to_namespace",
    "_is_state_key",
}
_STATE_PREFIXES = ("_CITATION_VERIFY_", "_DEBUG_")
_ORIGINAL_FUNCS: dict[str, object] = {}

def _is_state_key(name: object) -> bool:
    key = str(name or "")
    return any(key.startswith(prefix) for prefix in _STATE_PREFIXES)

def _sync_state_from_namespace(namespace: dict) -> None:
    for key, value in namespace.items():
        if _is_state_key(key):
            globals()[key] = value
    for key, value in list(globals().items()):
        if _is_state_key(key):
            namespace.setdefault(key, value)

def _sync_state_to_namespace(namespace: dict) -> None:
    for key, value in list(globals().items()):
        if _is_state_key(key):
            namespace[key] = value

def bind(namespace: dict) -> None:
    for key, value in namespace.items():
        if key in _BIND_SKIP_NAMES:
            continue
        if callable(value) and bool(getattr(value, "_wa_runtime_proxy", False)):
            if str(getattr(value, "_wa_runtime_proxy_target_module", "")) == __name__:
                # Restore original implementation when namespace holds this module's proxy.
                original = _ORIGINAL_FUNCS.get(key)
                if callable(original):
                    globals()[key] = original
                continue
        local = globals().get(key)
        if key in globals() and local is value:
            continue
        globals()[key] = value
    _sync_state_from_namespace(namespace)

def _proxy_factory(fn_name: str, namespace: dict):
    fn = globals()[fn_name]

    @wraps(fn)
    def _proxy(*args, **kwargs):
        bind(namespace)
        try:
            return fn(*args, **kwargs)
        finally:
            _sync_state_to_namespace(namespace)

    _proxy._wa_runtime_proxy = True
    _proxy._wa_runtime_proxy_target_module = __name__
    _proxy._wa_runtime_proxy_target_name = fn_name
    return _proxy

def _normalize_citation_items(items: object) -> dict[str, Citation]:
    citations: dict[str, Citation] = {}
    if not isinstance(items, list):
        return citations
    for raw in items:
        if not isinstance(raw, dict):
            continue
        key = str(raw.get("id") or raw.get("key") or "").strip()
        title = str(raw.get("title") or "").strip()
        if not key or not title:
            continue
        authors = str(raw.get("author") or raw.get("authors") or "").strip() or None
        year = str(raw.get("year") or "").strip() or None
        source = str(raw.get("source") or raw.get("venue") or "").strip() or None
        url = str(raw.get("url") or "").strip() or None
        if source and not url and re.match(r"^https?://", source):
            url = source
            source = None
        citations[key] = Citation(
            key=key,
            title=title,
            url=url,
            authors=authors,
            year=year,
            venue=source,
        )
    return citations

_CITATION_YEAR_RE = re.compile(r"(?:19|20)\d{2}")
_CITATION_TOKEN_RE = re.compile(r"[a-z0-9\u4e00-\u9fff]{2,}")
_CITATION_VERIFY_CACHE: dict[str, tuple[float, dict, Citation]] = {}
_CITATION_VERIFY_CACHE_LOCK = threading.Lock()
_CITATION_VERIFY_CACHE_METRICS: dict[str, int] = {"hit": 0, "miss": 0, "set": 0, "expired": 0, "evicted": 0}
_CITATION_VERIFY_CACHE_TTL_S_DEFAULT = 6 * 3600.0
_CITATION_VERIFY_OBSERVE_LOCK = threading.Lock()
_CITATION_VERIFY_OBSERVE_RUNS: list[dict] = []
_DEBUG_EMAIL_RE = re.compile(r"\b([A-Za-z0-9._%+-]{1,64})@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
_DEBUG_URL_RE = re.compile(r"https?://[^\s]+")
_DEBUG_LONG_TOKEN_RE = re.compile(r"\b[A-Za-z0-9_-]{16,}\b")
_DEBUG_SECRET_TOKEN_RE = re.compile(r"\b(?:sk|pk|rk|api|key|token)[-_]?[A-Za-z0-9_-]{8,}\b", flags=re.IGNORECASE)
_DEBUG_FULL_RATE_LOCK = threading.Lock()
_DEBUG_FULL_RATE_BUCKETS: dict[str, list[float]] = {}

def _normalize_citation_text(value: object) -> str:
    return " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split()).strip()

def _normalize_citation_title(value: object) -> str:
    text = _normalize_citation_text(value).lower()
    text = re.sub(
        r"[`~!@#$%^&*()_+\-=\[\]{}|\\:;\"'<>,.?/，。！？；：“”‘’（）【】《》、]+",
        " ",
        text,
    )
    return " ".join(text.split()).strip()

def _extract_citation_year(value: object) -> str:
    found = _CITATION_YEAR_RE.search(str(value or ""))
    return found.group(0) if found else ""

def _citation_author_tokens(value: object) -> set[str]:
    text = _normalize_citation_text(value).lower()
    if not text:
        return set()
    tokens = set(_CITATION_TOKEN_RE.findall(text))
    return {tok for tok in tokens if tok not in {"and", "the", "et", "al"}}

def _citation_verify_cache_ttl_s() -> float:
    raw = str(os.environ.get("WRITING_AGENT_CITATION_VERIFY_CACHE_TTL_S", "")).strip()
    if not raw:
        return _CITATION_VERIFY_CACHE_TTL_S_DEFAULT
    try:
        return max(30.0, float(raw))
    except Exception:
        return _CITATION_VERIFY_CACHE_TTL_S_DEFAULT

def _citation_verify_cache_max_entries() -> int:
    raw = str(os.environ.get("WRITING_AGENT_CITATION_VERIFY_CACHE_MAX_ENTRIES", "2048")).strip()
    try:
        return max(1, min(50000, int(raw)))
    except Exception:
        return 2048

def _citation_verify_observe_max_runs() -> int:
    raw = str(os.environ.get("WRITING_AGENT_CITATION_VERIFY_OBSERVE_MAX_RUNS", "240")).strip()
    try:
        return max(20, min(5000, int(raw)))
    except Exception:
        return 240

def _citation_verify_observe_window_s() -> float:
    raw = str(os.environ.get("WRITING_AGENT_CITATION_VERIFY_OBSERVE_WINDOW_S", "1800")).strip()
    try:
        return max(60.0, min(86400.0, float(raw)))
    except Exception:
        return 1800.0

def _citation_verify_cache_metrics_snapshot() -> dict[str, int]:
    with _CITATION_VERIFY_CACHE_LOCK:
        return {
            "hit": int(_CITATION_VERIFY_CACHE_METRICS.get("hit", 0)),
            "miss": int(_CITATION_VERIFY_CACHE_METRICS.get("miss", 0)),
            "set": int(_CITATION_VERIFY_CACHE_METRICS.get("set", 0)),
            "expired": int(_CITATION_VERIFY_CACHE_METRICS.get("expired", 0)),
            "evicted": int(_CITATION_VERIFY_CACHE_METRICS.get("evicted", 0)),
        }

def _citation_verify_cache_prune_locked(*, now: float) -> None:
    ttl = _citation_verify_cache_ttl_s()
    floor = float(now) - float(ttl)
    expired_keys = [key for key, row in _CITATION_VERIFY_CACHE.items() if float((row or (0.0, {}, None))[0]) < floor]
    if expired_keys:
        for key in expired_keys:
            _CITATION_VERIFY_CACHE.pop(key, None)
        _CITATION_VERIFY_CACHE_METRICS["expired"] = int(_CITATION_VERIFY_CACHE_METRICS.get("expired", 0)) + len(expired_keys)

    max_entries = _citation_verify_cache_max_entries()
    evicted = 0
    while len(_CITATION_VERIFY_CACHE) > max_entries:
        oldest_key = next(iter(_CITATION_VERIFY_CACHE))
        _CITATION_VERIFY_CACHE.pop(oldest_key, None)
        evicted += 1
    if evicted:
        _CITATION_VERIFY_CACHE_METRICS["evicted"] = int(_CITATION_VERIFY_CACHE_METRICS.get("evicted", 0)) + evicted

def _citation_verify_cache_snapshot() -> dict:
    with _CITATION_VERIFY_CACHE_LOCK:
        _citation_verify_cache_prune_locked(now=time.time())
        return {
            "size": len(_CITATION_VERIFY_CACHE),
            "ttl_s": _citation_verify_cache_ttl_s(),
            "max_entries": _citation_verify_cache_max_entries(),
            "hit": int(_CITATION_VERIFY_CACHE_METRICS.get("hit", 0)),
            "miss": int(_CITATION_VERIFY_CACHE_METRICS.get("miss", 0)),
            "set": int(_CITATION_VERIFY_CACHE_METRICS.get("set", 0)),
            "expired": int(_CITATION_VERIFY_CACHE_METRICS.get("expired", 0)),
            "evicted": int(_CITATION_VERIFY_CACHE_METRICS.get("evicted", 0)),
        }

def _citation_verify_cache_key(cite: Citation) -> str:
    title = _normalize_citation_title(cite.title)
    year = _extract_citation_year(cite.year)
    author_tokens = sorted(_citation_author_tokens(cite.authors or ""))
    author_key = ",".join(author_tokens[:6])
    return f"{title}|{year}|{author_key}"

def _citation_verify_cache_get(cite: Citation) -> tuple[dict, Citation] | None:
    key = _citation_verify_cache_key(cite)
    if not key or key == "||":
        return None
    with _CITATION_VERIFY_CACHE_LOCK:
        _citation_verify_cache_prune_locked(now=time.time())
        row = _CITATION_VERIFY_CACHE.get(key)
        if not row:
            _CITATION_VERIFY_CACHE_METRICS["miss"] = int(_CITATION_VERIFY_CACHE_METRICS.get("miss", 0)) + 1
            return None
        ts, item, next_cite = row
        # Keep entry order as LRU-ish for size-based evictions.
        _CITATION_VERIFY_CACHE.pop(key, None)
        _CITATION_VERIFY_CACHE[key] = (float(ts), dict(item or {}), next_cite)
        _CITATION_VERIFY_CACHE_METRICS["hit"] = int(_CITATION_VERIFY_CACHE_METRICS.get("hit", 0)) + 1
    return dict(item or {}), next_cite

def _citation_verify_cache_set(cite: Citation, item: dict, next_cite: Citation) -> None:
    key = _citation_verify_cache_key(cite)
    if not key or key == "||":
        return
    with _CITATION_VERIFY_CACHE_LOCK:
        now = time.time()
        _citation_verify_cache_prune_locked(now=now)
        if key in _CITATION_VERIFY_CACHE:
            _CITATION_VERIFY_CACHE.pop(key, None)
        _CITATION_VERIFY_CACHE[key] = (float(now), dict(item or {}), next_cite)
        _CITATION_VERIFY_CACHE_METRICS["set"] = int(_CITATION_VERIFY_CACHE_METRICS.get("set", 0)) + 1
        _citation_verify_cache_prune_locked(now=now)

def _citation_verify_observe_prune_locked(*, now: float) -> None:
    floor = float(now) - _citation_verify_observe_window_s()
    rows: list[dict] = []
    for raw in _CITATION_VERIFY_OBSERVE_RUNS:
        row = raw if isinstance(raw, dict) else {}
        try:
            ts = float(row.get("ts") or 0.0)
        except Exception:
            ts = 0.0
        if ts >= floor:
            rows.append(row)
    max_runs = _citation_verify_observe_max_runs()
    if len(rows) > max_runs:
        rows = rows[-max_runs:]
    _CITATION_VERIFY_OBSERVE_RUNS[:] = rows

def _citation_verify_observe_record(
    *,
    elapsed_ms: float,
    item_count: int,
    worker_count: int,
    error_count: int,
    cache_before: dict[str, int] | None,
    cache_after: dict[str, int] | None,
) -> dict:
    before = cache_before if isinstance(cache_before, dict) else {}
    after = cache_after if isinstance(cache_after, dict) else {}
    delta = {}
    for key in ("hit", "miss", "set", "expired", "evicted"):
        b = int(before.get(key, 0))
        a = int(after.get(key, 0))
        delta[key] = max(0, a - b)
    row = {
        "ts": time.time(),
        "elapsed_ms": max(0.0, float(elapsed_ms)),
        "item_count": max(0, int(item_count)),
        "worker_count": max(0, int(worker_count)),
        "error_count": max(0, int(error_count)),
        "cache_delta": delta,
    }
    with _CITATION_VERIFY_OBSERVE_LOCK:
        _citation_verify_observe_prune_locked(now=time.time())
        _CITATION_VERIFY_OBSERVE_RUNS.append(row)
        _citation_verify_observe_prune_locked(now=time.time())
    return row

def _citation_verify_observe_snapshot(*, include_recent: bool = True) -> dict:
    with _CITATION_VERIFY_OBSERVE_LOCK:
        _citation_verify_observe_prune_locked(now=time.time())
        rows = list(_CITATION_VERIFY_OBSERVE_RUNS)

    def _as_non_negative_float(value: object) -> float:
        try:
            return max(0.0, float(value or 0.0))
        except Exception:
            return 0.0

    def _as_non_negative_int(value: object) -> int:
        try:
            return max(0, int(value or 0))
        except Exception:
            try:
                return max(0, int(float(value or 0.0)))
            except Exception:
                return 0

    elapsed_values = [_as_non_negative_float((row if isinstance(row, dict) else {}).get("elapsed_ms")) for row in rows]
    item_values = [_as_non_negative_float((row if isinstance(row, dict) else {}).get("item_count")) for row in rows]
    worker_values = [_as_non_negative_float((row if isinstance(row, dict) else {}).get("worker_count")) for row in rows]
    error_values = [_as_non_negative_float((row if isinstance(row, dict) else {}).get("error_count")) for row in rows]

    delta_sum = {"hit": 0, "miss": 0, "set": 0, "expired": 0, "evicted": 0}
    for row in rows:
        delta = row.get("cache_delta") if isinstance(row, dict) else {}
        if not isinstance(delta, dict):
            continue
        for key in delta_sum:
            delta_sum[key] += _as_non_negative_int(delta.get(key, 0))

    def _avg(values: list[float]) -> float:
        if not values:
            return 0.0
        return float(sum(values) / max(1, len(values)))

    elapsed_avg = _avg(elapsed_values)
    items_avg = _avg(item_values)
    workers_avg = _avg(worker_values)
    errors_total = int(sum(error_values))
    error_rate = (errors_total / max(1, len(rows))) if rows else 0.0
    cache_delta_lookups = max(0, int(delta_sum["hit"] + delta_sum["miss"]))
    cache_delta_hit_rate = (int(delta_sum["hit"]) / cache_delta_lookups) if cache_delta_lookups > 0 else 0.0

    recent: list[dict] = []
    if include_recent:
        for row in rows[-20:]:
            payload = row if isinstance(row, dict) else {}
            delta = payload.get("cache_delta") if isinstance(payload.get("cache_delta"), dict) else {}
            hit = _as_non_negative_int(delta.get("hit"))
            miss = _as_non_negative_int(delta.get("miss"))
            recent.append(
                {
                    "ts": _as_non_negative_float(payload.get("ts")),
                    "elapsed_ms": round(_as_non_negative_float(payload.get("elapsed_ms")), 2),
                    "item_count": _as_non_negative_int(payload.get("item_count")),
                    "worker_count": _as_non_negative_int(payload.get("worker_count")),
                    "error_count": _as_non_negative_int(payload.get("error_count")),
                    "cache_delta": {
                        "hit": hit,
                        "miss": miss,
                        "set": _as_non_negative_int(delta.get("set")),
                        "expired": _as_non_negative_int(delta.get("expired")),
                        "evicted": _as_non_negative_int(delta.get("evicted")),
                        "hit_rate": round(
                            (hit / max(1, hit + miss)),
                            4,
                        )
                        if (hit + miss) > 0
                        else 0.0,
                    },
                }
            )

    return {
        "window_s": _citation_verify_observe_window_s(),
        "max_runs": _citation_verify_observe_max_runs(),
        "runs": len(rows),
        "elapsed_ms": {
            "avg": round(elapsed_avg, 2),
            "p50": round(_percentile(elapsed_values, 0.50), 2),
            "p95": round(_percentile(elapsed_values, 0.95), 2),
            "max": round(max(elapsed_values) if elapsed_values else 0.0, 2),
        },
        "items": {
            "total": int(sum(item_values)),
            "avg": round(items_avg, 2),
            "p50": round(_percentile(item_values, 0.50), 2),
            "p95": round(_percentile(item_values, 0.95), 2),
            "max": int(max(item_values) if item_values else 0.0),
        },
        "workers": {
            "avg": round(workers_avg, 2),
            "max": int(max(worker_values) if worker_values else 0.0),
        },
        "errors": {
            "total": errors_total,
            "rate_per_run": round(error_rate, 4),
        },
        "cache_delta": {
            "hit": int(delta_sum["hit"]),
            "miss": int(delta_sum["miss"]),
            "set": int(delta_sum["set"]),
            "expired": int(delta_sum["expired"]),
            "evicted": int(delta_sum["evicted"]),
            "hit_rate": round(cache_delta_hit_rate, 4),
        },
        "recent": recent,
    }

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

def _parse_bounded_int(value: object, *, default: int, min_value: int, max_value: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        try:
            parsed = int(float(value))
        except Exception:
            parsed = int(default)
    return max(int(min_value), min(int(max_value), int(parsed)))

def _parse_bounded_float(value: object, *, default: float, min_value: float, max_value: float) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = float(default)
    return max(float(min_value), min(float(max_value), float(parsed)))

def _citation_verify_alerts_env_defaults() -> dict:
    return {
        "enabled": _coerce_bool(os.environ.get("WRITING_AGENT_CITATION_VERIFY_ALERTS", "1"), default=True),
        "min_runs": _parse_bounded_int(
            os.environ.get("WRITING_AGENT_CITATION_VERIFY_ALERT_MIN_RUNS", "8"),
            default=8,
            min_value=1,
            max_value=500,
        ),
        "p95_ms": _parse_bounded_float(
            os.environ.get("WRITING_AGENT_CITATION_VERIFY_ALERT_P95_MS", "4500"),
            default=4500.0,
            min_value=100.0,
            max_value=60000.0,
        ),
        "error_rate_per_run": _parse_bounded_float(
            os.environ.get("WRITING_AGENT_CITATION_VERIFY_ALERT_ERROR_RATE", "0.30"),
            default=0.30,
            min_value=0.0,
            max_value=1.0,
        ),
        "cache_delta_hit_rate": _parse_bounded_float(
            os.environ.get("WRITING_AGENT_CITATION_VERIFY_ALERT_HIT_RATE", "0.35"),
            default=0.35,
            min_value=0.0,
            max_value=1.0,
        ),
    }

def _normalize_citation_verify_alerts_config(raw: object, *, defaults: dict | None = None) -> dict:
    base = dict(defaults or _citation_verify_alerts_env_defaults())
    row = raw if isinstance(raw, dict) else {}
    if "enabled" in row:
        base["enabled"] = _coerce_bool(row.get("enabled"), default=bool(base.get("enabled", True)))
    if "min_runs" in row:
        base["min_runs"] = _parse_bounded_int(row.get("min_runs"), default=int(base.get("min_runs", 8)), min_value=1, max_value=500)
    if "p95_ms" in row:
        base["p95_ms"] = _parse_bounded_float(
            row.get("p95_ms"),
            default=float(base.get("p95_ms", 4500.0)),
            min_value=100.0,
            max_value=60000.0,
        )
    if "error_rate_per_run" in row:
        base["error_rate_per_run"] = _parse_bounded_float(
            row.get("error_rate_per_run"),
            default=float(base.get("error_rate_per_run", 0.30)),
            min_value=0.0,
            max_value=1.0,
        )
    if "cache_delta_hit_rate" in row:
        base["cache_delta_hit_rate"] = _parse_bounded_float(
            row.get("cache_delta_hit_rate"),
            default=float(base.get("cache_delta_hit_rate", 0.35)),
            min_value=0.0,
            max_value=1.0,
        )
    return base

def _citation_verify_alerts_config_reset_cache() -> None:
    global _CITATION_VERIFY_ALERTS_CONFIG_CACHE, _CITATION_VERIFY_ALERTS_CONFIG_LOADED
    with _CITATION_VERIFY_ALERTS_CONFIG_LOCK:
        _CITATION_VERIFY_ALERTS_CONFIG_CACHE = None
        _CITATION_VERIFY_ALERTS_CONFIG_LOADED = False

def _citation_verify_alerts_config_load_from_disk_locked(*, defaults: dict) -> dict | None:
    path = _CITATION_VERIFY_ALERTS_CONFIG_PATH
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("failed to parse citation verify alerts config: %s", str(path), exc_info=True)
        return None
    if not isinstance(raw, dict):
        return None
    return _normalize_citation_verify_alerts_config(raw, defaults=defaults)

def _citation_verify_alerts_config_effective() -> dict:
    global _CITATION_VERIFY_ALERTS_CONFIG_CACHE, _CITATION_VERIFY_ALERTS_CONFIG_LOADED
    defaults = _citation_verify_alerts_env_defaults()
    with _CITATION_VERIFY_ALERTS_CONFIG_LOCK:
        if not _CITATION_VERIFY_ALERTS_CONFIG_LOADED:
            _CITATION_VERIFY_ALERTS_CONFIG_CACHE = _citation_verify_alerts_config_load_from_disk_locked(defaults=defaults)
            _CITATION_VERIFY_ALERTS_CONFIG_LOADED = True
        cache = _CITATION_VERIFY_ALERTS_CONFIG_CACHE
    if isinstance(cache, dict):
        return _normalize_citation_verify_alerts_config(cache, defaults=defaults)
    return defaults

def _citation_verify_alerts_config_source() -> str:
    with _CITATION_VERIFY_ALERTS_CONFIG_LOCK:
        cache = _CITATION_VERIFY_ALERTS_CONFIG_CACHE
    return "file" if isinstance(cache, dict) else "env"

def _citation_verify_alerts_config_save(raw: object) -> dict:
    global _CITATION_VERIFY_ALERTS_CONFIG_CACHE, _CITATION_VERIFY_ALERTS_CONFIG_LOADED
    defaults = _citation_verify_alerts_env_defaults()
    config = _normalize_citation_verify_alerts_config(raw, defaults=defaults)
    path = _CITATION_VERIFY_ALERTS_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with _CITATION_VERIFY_ALERTS_CONFIG_LOCK:
        path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        _CITATION_VERIFY_ALERTS_CONFIG_CACHE = dict(config)
        _CITATION_VERIFY_ALERTS_CONFIG_LOADED = True
    return config

def _citation_verify_alerts_config_reset() -> dict:
    global _CITATION_VERIFY_ALERTS_CONFIG_CACHE, _CITATION_VERIFY_ALERTS_CONFIG_LOADED
    defaults = _citation_verify_alerts_env_defaults()
    path = _CITATION_VERIFY_ALERTS_CONFIG_PATH
    with _CITATION_VERIFY_ALERTS_CONFIG_LOCK:
        try:
            if path.exists():
                path.unlink()
        except Exception:
            logger.warning("failed to delete citation verify alerts config: %s", str(path), exc_info=True)
        _CITATION_VERIFY_ALERTS_CONFIG_CACHE = None
        _CITATION_VERIFY_ALERTS_CONFIG_LOADED = True
    return defaults

def _citation_verify_alerts_enabled() -> bool:
    return bool(_citation_verify_alerts_config_effective().get("enabled", True))

def _citation_verify_alert_min_runs() -> int:
    return int(_citation_verify_alerts_config_effective().get("min_runs", 8))

def _citation_verify_alert_p95_ms_threshold() -> float:
    return float(_citation_verify_alerts_config_effective().get("p95_ms", 4500.0))

def _citation_verify_alert_error_rate_threshold() -> float:
    return float(_citation_verify_alerts_config_effective().get("error_rate_per_run", 0.30))

def _citation_verify_alert_hit_rate_threshold() -> float:
    return float(_citation_verify_alerts_config_effective().get("cache_delta_hit_rate", 0.35))

def _citation_verify_alert_notify_enabled() -> bool:
    raw = os.environ.get("WRITING_AGENT_CITATION_VERIFY_ALERT_NOTIFY", "1")
    return _coerce_bool(raw, default=True)

def _citation_verify_alert_notify_cooldown_s() -> float:
    raw = os.environ.get("WRITING_AGENT_CITATION_VERIFY_ALERT_NOTIFY_COOLDOWN_S", "300")
    return _parse_bounded_float(raw, default=300.0, min_value=10.0, max_value=86400.0)

def _citation_verify_alert_notify_timeout_s() -> float:
    raw = os.environ.get("WRITING_AGENT_CITATION_VERIFY_ALERT_NOTIFY_TIMEOUT_S", "4")
    return _parse_bounded_float(raw, default=4.0, min_value=1.0, max_value=30.0)

def _citation_verify_alert_notify_webhook_url() -> str:
    return str(os.environ.get("WRITING_AGENT_CITATION_VERIFY_ALERT_WEBHOOK_URL", "")).strip()

def _admin_api_key() -> str:
    return str(os.environ.get("WRITING_AGENT_ADMIN_API_KEY", "")).strip()

def _ops_rbac_enabled() -> bool:
    raw = os.environ.get("WRITING_AGENT_OPS_RBAC_ENABLED", "1")
    return _coerce_bool(raw, default=True)

def _ops_rbac_policy_path() -> Path:
    raw = str(os.environ.get("WRITING_AGENT_OPS_RBAC_POLICY", "")).strip()
    if raw:
        return Path(raw)
    return Path("security/ops_rbac_policy.json")

def _ops_rbac_policy_load() -> dict:
    if not _ops_rbac_enabled():
        return {}
    path = _ops_rbac_policy_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("failed to parse ops rbac policy: %s", str(path), exc_info=True)
        return {}
    return raw if isinstance(raw, dict) else {}

def _request_admin_token(request: Request) -> str:
    key = str(request.headers.get("x-admin-key") or "").strip()
    if key:
        return key
    auth = str(request.headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""

def _ops_rbac_principals(policy: dict) -> list[dict]:
    principals_raw = policy.get("principals") if isinstance(policy.get("principals"), list) else []
    principals: list[dict] = []
    for item in principals_raw:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        if not role:
            continue
        token = str(item.get("token") or "").strip()
        token_env = str(item.get("token_env") or "").strip()
        if not token and token_env:
            token = str(os.environ.get(token_env, "")).strip()
        if not token:
            continue
        principals.append(
            {
                "id": str(item.get("id") or role).strip(),
                "role": role,
                "token": token,
            }
        )
    return principals

def _ops_rbac_role_permissions(policy: dict, role: str) -> set[str]:
    roles = policy.get("roles") if isinstance(policy.get("roles"), dict) else {}
    rows = roles.get(role) if isinstance(roles.get(role), list) else []
    return {str(item).strip() for item in rows if str(item).strip()}

def _ops_rbac_match_principal(token: str, principals: list[dict]) -> dict | None:
    needle = str(token or "").strip()
    if not needle:
        return None
    for principal in principals:
        if str(principal.get("token") or "").strip() == needle:
            return principal
    return None

def _require_ops_permission(request: Request, permission: str) -> None:
    expected_admin = _admin_api_key()
    token = _request_admin_token(request)

    if not _ops_rbac_enabled():
        if expected_admin and token != expected_admin:
            raise HTTPException(status_code=403, detail="forbidden")
        return

    policy = _ops_rbac_policy_load()
    principals = _ops_rbac_principals(policy)
    auth_configured = bool(expected_admin) or bool(principals)

    # Preserve backward compatibility: admin key always has full permission.
    if expected_admin and token and token == expected_admin:
        return

    matched = _ops_rbac_match_principal(token, principals)
    if matched is not None:
        role = str(matched.get("role") or "").strip()
        perms = _ops_rbac_role_permissions(policy, role)
        if "*" in perms or str(permission).strip() in perms:
            return
        raise HTTPException(status_code=403, detail="forbidden")

    if auth_configured:
        raise HTTPException(status_code=403, detail="forbidden")

def _require_admin_key(request: Request) -> None:
    expected = _admin_api_key()
    if not expected:
        return
    key = _request_admin_token(request)
    if key != expected:
        raise HTTPException(status_code=403, detail="forbidden")

def _citation_verify_metrics_trend_enabled() -> bool:
    return _coerce_bool(os.environ.get("WRITING_AGENT_CITATION_VERIFY_TREND_ENABLED", "1"), default=True)

def _citation_verify_metrics_trends_max_entries() -> int:
    raw = os.environ.get("WRITING_AGENT_CITATION_VERIFY_TREND_MAX_ENTRIES", "3000")
    return _parse_bounded_int(raw, default=3000, min_value=200, max_value=50000)

def _citation_verify_metrics_trends_load_locked() -> list[dict]:
    path = _CITATION_VERIFY_METRICS_TRENDS_PATH
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("failed to parse citation verify trend file: %s", str(path), exc_info=True)
        return []
    rows = raw.get("points") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, dict)]

def _citation_verify_metrics_trends_write_locked(rows: list[dict]) -> None:
    path = _CITATION_VERIFY_METRICS_TRENDS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    max_entries = _citation_verify_metrics_trends_max_entries()
    data = {"points": list(rows or [])[-max_entries:]}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _citation_verify_metrics_trends_append(point: dict) -> dict:
    row = dict(point or {})
    row["id"] = str(row.get("id") or uuid.uuid4().hex)
    row["ts"] = float(row.get("ts") or time.time())
    if not _citation_verify_metrics_trend_enabled():
        return row
    with _CITATION_VERIFY_METRICS_TRENDS_LOCK:
        rows = _citation_verify_metrics_trends_load_locked()
        rows.append(row)
        _citation_verify_metrics_trends_write_locked(rows)
    return row

def _citation_verify_metrics_trends_snapshot(*, limit: int = 60) -> dict:
    size = _parse_bounded_int(limit, default=60, min_value=1, max_value=500)
    with _CITATION_VERIFY_METRICS_TRENDS_LOCK:
        rows = _citation_verify_metrics_trends_load_locked()
    return {"enabled": _citation_verify_metrics_trend_enabled(), "total": len(rows), "limit": size, "points": list(rows[-size:])}

def _citation_verify_metrics_trend_context(*, ts: float, limit: int = 12) -> dict:
    size = _parse_bounded_int(limit, default=12, min_value=1, max_value=120)
    target = float(ts or 0.0)
    with _CITATION_VERIFY_METRICS_TRENDS_LOCK:
        rows = _citation_verify_metrics_trends_load_locked()
    if not rows:
        return {"total": 0, "limit": size, "before": 0, "after": 0, "points": []}
    if target <= 0:
        points = sorted(rows, key=lambda row: float((row or {}).get("ts") or 0.0))[-size:]
        return {"total": len(rows), "limit": size, "before": 0, "after": 0, "points": points}
    nearest = sorted(rows, key=lambda row: abs(float((row or {}).get("ts") or 0.0) - target))[:size]
    nearest = sorted(nearest, key=lambda row: float((row or {}).get("ts") or 0.0))
    before = 0
    after = 0
    for row in nearest:
        row_ts = float((row or {}).get("ts") or 0.0)
        if row_ts < target:
            before += 1
        elif row_ts > target:
            after += 1
    return {"total": len(rows), "limit": size, "before": before, "after": after, "points": nearest}

def _citation_verify_alert_events_max_entries() -> int:
    raw = os.environ.get("WRITING_AGENT_CITATION_VERIFY_ALERT_EVENTS_MAX", "800")
    return _parse_bounded_int(raw, default=800, min_value=50, max_value=20000)

def _citation_verify_alert_events_load_locked() -> list[dict]:
    path = _CITATION_VERIFY_ALERT_EVENTS_PATH
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("failed to parse citation verify alert events: %s", str(path), exc_info=True)
        return []
    rows = raw.get("events") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, dict)]

def _citation_verify_alert_events_write_locked(rows: list[dict]) -> None:
    path = _CITATION_VERIFY_ALERT_EVENTS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    max_entries = _citation_verify_alert_events_max_entries()
    data = {"events": list(rows or [])[-max_entries:]}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _citation_verify_alert_events_append(event: dict) -> dict:
    row = dict(event or {})
    row["id"] = str(row.get("id") or uuid.uuid4().hex)
    row["ts"] = float(row.get("ts") or time.time())
    with _CITATION_VERIFY_ALERT_EVENTS_LOCK:
        rows = _citation_verify_alert_events_load_locked()
        rows.append(row)
        _citation_verify_alert_events_write_locked(rows)
    return row

def _citation_verify_alert_events_snapshot(*, limit: int = 20) -> dict:
    size = _parse_bounded_int(limit, default=20, min_value=1, max_value=200)
    with _CITATION_VERIFY_ALERT_EVENTS_LOCK:
        rows = _citation_verify_alert_events_load_locked()
    return {"total": len(rows), "limit": size, "events": list(rows[-size:])}

def _citation_verify_alert_event_get(event_id: str) -> dict | None:
    key = str(event_id or "").strip()
    if not key:
        return None
    with _CITATION_VERIFY_ALERT_EVENTS_LOCK:
        rows = _citation_verify_alert_events_load_locked()
    for row in reversed(rows):
        if str((row or {}).get("id") or "") == key:
            return dict(row)
    return None

def _citation_verify_alert_signature(*, severity: str, triggered_ids: list[str], degraded: bool) -> str:
    return citation_alert_domain.citation_verify_alert_signature(
        severity=severity,
        triggered_ids=triggered_ids,
        degraded=degraded,
    )

def _citation_verify_release_context() -> dict:
    return citation_alert_domain.citation_verify_release_context(
        correlation_id=str(os.environ.get("WRITING_AGENT_CORRELATION_ID", "") or ""),
        release_candidate_id=str(os.environ.get("WRITING_AGENT_RELEASE_CANDIDATE_ID", "") or ""),
    )

def _citation_verify_alert_notify_state_reset() -> None:
    with _CITATION_VERIFY_ALERT_NOTIFY_LOCK:
        _CITATION_VERIFY_ALERT_NOTIFY_STATE.update(
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

def _alert_notify_webhook(url: str, payload: dict, *, timeout_s: float) -> tuple[bool, str]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = UrlRequest(str(url), data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=float(timeout_s)) as resp:
        code = int(getattr(resp, "status", 0) or resp.getcode() or 0)
    if 200 <= code < 300:
        return True, f"http_{code}"
    return False, f"http_{code}"

def _maybe_notify_citation_verify_alerts(*, alerts: dict, degraded: bool, errors: list[str]) -> dict:
    return citation_alert_domain.maybe_notify_citation_verify_alerts(
        alerts=alerts,
        degraded=degraded,
        errors=errors,
        config=citation_alert_domain.CitationAlertNotifyConfig(
            notify_enabled=_citation_verify_alert_notify_enabled(),
            webhook_url=_citation_verify_alert_notify_webhook_url(),
            cooldown_s=_citation_verify_alert_notify_cooldown_s(),
            timeout_s=_citation_verify_alert_notify_timeout_s(),
            release_ctx=_citation_verify_release_context(),
        ),
        hooks=citation_alert_domain.CitationAlertNotifyHooks(
            append_event=_citation_verify_alert_events_append,
            events_snapshot=_citation_verify_alert_events_snapshot,
            alert_notify_webhook=lambda url, payload, timeout_s: _alert_notify_webhook(url, payload, timeout_s=timeout_s),
            log_info=lambda msg: logger.info(msg),
            log_warn=lambda msg: logger.warning(msg),
            log_error=lambda msg: logger.error(msg),
        ),
        notify_state=_CITATION_VERIFY_ALERT_NOTIFY_STATE,
        notify_lock=_CITATION_VERIFY_ALERT_NOTIFY_LOCK,
    )

def _citation_verify_alerts_fallback() -> dict:
    return citation_alert_domain.citation_verify_alerts_fallback(
        min_runs=_citation_verify_alert_min_runs(),
        threshold_p95=_citation_verify_alert_p95_ms_threshold(),
        threshold_error_rate=_citation_verify_alert_error_rate_threshold(),
        threshold_hit_rate=_citation_verify_alert_hit_rate_threshold(),
    )

def _build_citation_verify_alerts_payload(*, degraded: bool, errors: list[str], observe: dict) -> dict:
    return citation_alert_domain.build_citation_verify_alerts_payload(
        degraded=degraded,
        errors=errors,
        observe=observe,
        alerts_enabled=_citation_verify_alerts_enabled(),
        min_runs=_citation_verify_alert_min_runs(),
        threshold_p95=_citation_verify_alert_p95_ms_threshold(),
        threshold_error_rate=_citation_verify_alert_error_rate_threshold(),
        threshold_hit_rate=_citation_verify_alert_hit_rate_threshold(),
        log_info=lambda msg: logger.info(msg),
    )

def _citation_verify_cache_snapshot_fallback() -> dict:
    return {
        "size": 0,
        "ttl_s": _citation_verify_cache_ttl_s(),
        "max_entries": _citation_verify_cache_max_entries(),
        "hit": 0,
        "miss": 0,
        "set": 0,
        "expired": 0,
        "evicted": 0,
    }

def _citation_verify_observe_snapshot_fallback() -> dict:
    return citation_alert_domain.citation_verify_observe_snapshot_fallback(
        window_s=_citation_verify_observe_window_s(),
        max_runs=_citation_verify_observe_max_runs(),
    )

def _safe_citation_verify_metrics_payload() -> dict:
    return citation_alert_domain.safe_citation_verify_metrics_payload(
        cache_snapshot=_citation_verify_cache_snapshot,
        cache_snapshot_fallback=_citation_verify_cache_snapshot_fallback,
        observe_snapshot=_citation_verify_observe_snapshot,
        observe_snapshot_fallback_fn=_citation_verify_observe_snapshot_fallback,
        build_alerts_payload=lambda degraded, errors, observe: _build_citation_verify_alerts_payload(
            degraded=degraded,
            errors=errors,
            observe=observe,
        ),
        alerts_fallback_fn=_citation_verify_alerts_fallback,
        maybe_notify_alerts=lambda alerts, degraded, errors: _maybe_notify_citation_verify_alerts(
            alerts=alerts,
            degraded=degraded,
            errors=errors,
        ),
        webhook_url=_citation_verify_alert_notify_webhook_url,
        cooldown_s=_citation_verify_alert_notify_cooldown_s,
        append_trend_point=_citation_verify_metrics_trends_append,
        trend_snapshot=_citation_verify_metrics_trends_snapshot,
        log_warn=lambda msg: logger.warning(msg, exc_info=True),
    )

def install(namespace: dict) -> None:
    bind(namespace)
    _sync_state_to_namespace(namespace)
    for fn_name, fn in list(globals().items()):
        if fn_name in {
            "bind",
            "install",
            "_proxy_factory",
            "_sync_state_from_namespace",
            "_sync_state_to_namespace",
            "_is_state_key",
        }:
            continue
        if fn_name.startswith("_") and callable(fn) and str(getattr(fn, "__module__", "")) == __name__:
            _ORIGINAL_FUNCS.setdefault(fn_name, fn)
            namespace[fn_name] = _proxy_factory(fn_name, namespace)
