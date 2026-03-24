"""Runtime support helpers for model readiness, pull, and timeout resilience."""

from __future__ import annotations

import json
import queue
import threading
import time
from collections.abc import Iterable


def recommended_stream_timeouts(*, load_stream_metrics_fn, percentile_fn, load_probe_fn) -> tuple[float, float]:
    data = load_stream_metrics_fn()
    runs = data.get("runs") if isinstance(data.get("runs"), list) else []
    totals = [float(row.get("total_s", 0)) for row in runs if row.get("total_s")]
    gaps = [float(row.get("max_gap_s", 0)) for row in runs if row.get("max_gap_s")]
    p95_total = percentile_fn(totals, 0.95)
    p95_gap = percentile_fn(gaps, 0.95)
    default_total = 600.0
    default_gap = 180.0
    probe = load_probe_fn() or {}
    if isinstance(probe, dict):
        try:
            max_total_ms = float(probe.get("max_total_ms") or 0)
            max_gap_ms = float(probe.get("max_gap_ms") or 0)
            if max_total_ms > 0:
                default_total = max(default_total, (max_total_ms / 1000.0) * 1.2)
            if max_gap_ms > 0:
                default_gap = max(default_gap, (max_gap_ms / 1000.0) * 3.0)
        except Exception:
            pass
    overall_s = max(default_total, p95_total * 1.3 if p95_total > 0 else 0.0)
    stall_s = max(default_gap, p95_gap * 3 if p95_gap > 0 else 0.0)
    return overall_s, stall_s


def run_with_heartbeat(fn, timeout_s: float, fallback, *, label: str, heartbeat_s: float = 3.0):
    if timeout_s <= 0:
        return fn()
    result_queue: queue.Queue = queue.Queue()

    def _worker() -> None:
        try:
            result_queue.put(("ok", fn()))
        except Exception as exc:
            result_queue.put(("err", exc))

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    start_ts = time.time()
    last_emit = time.time()
    while True:
        try:
            kind, payload = result_queue.get(timeout=1.0)
            if kind == "ok":
                return payload
            return fallback
        except queue.Empty:
            if time.time() - start_ts > timeout_s:
                return fallback
            if time.time() - last_emit > heartbeat_s:
                yield f"{label}..."
                last_emit = time.time()


def pull_model_stream_iter(
    *,
    base_url: str,
    name: str,
    timeout_s: float,
    url_request_cls,
    urlopen_fn,
) -> Iterable[str] | tuple[bool, str]:
    url = f"{base_url}/api/pull"
    payload = json.dumps({"name": name, "stream": True}).encode("utf-8")
    request = url_request_cls(url=url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    started = time.time()
    last_status = ""
    try:
        with urlopen_fn(request, timeout=min(10.0, max(2.0, timeout_s))) as resp:
            for raw in resp:
                if time.time() - started > timeout_s:
                    return False, f"pull timeout: {name}"
                line = raw.decode("utf-8", errors="ignore").strip() if isinstance(raw, (bytes, bytearray)) else str(raw).strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except Exception:
                    continue
                status = str(data.get("status") or "")
                completed = data.get("completed")
                total = data.get("total")
                if status and status != last_status:
                    last_status = status
                if status and isinstance(completed, (int, float)) and isinstance(total, (int, float)) and total > 0:
                    pct = int((completed / total) * 100)
                    last_status = f"{status} {pct}%"
                if last_status:
                    yield f"{name}: {last_status}"
                if status.lower() == "success":
                    return True, ""
    except Exception as exc:
        return False, f"pull failed: {exc}"
    return True, ""


def pull_model_stream(*, base_url: str, name: str, timeout_s: float, pull_model_stream_iter_fn) -> tuple[bool, str]:
    iterator = pull_model_stream_iter_fn(base_url=base_url, name=name, timeout_s=timeout_s)
    if isinstance(iterator, tuple):
        return iterator
    ok = True
    msg = ""
    try:
        for _ in iterator:
            pass
    except StopIteration as exc:
        ok, msg = exc.value or (True, "")
    return ok, msg


def ensure_ollama_ready_iter(
    *,
    get_ollama_settings_fn,
    ollama_client_cls,
    start_ollama_serve_fn,
    wait_until_fn,
) -> Iterable[str] | tuple[bool, str]:
    settings = get_ollama_settings_fn()
    if not settings.enabled:
        return False, "model service disabled"
    base_url = settings.base_url
    probe = ollama_client_cls(base_url=base_url, model=settings.model, timeout_s=min(5.0, settings.timeout_s))
    if not probe.is_running():
        yield f"checking model service: {base_url}"
        try:
            start_ollama_serve_fn()
        except FileNotFoundError:
            return False, "ollama executable not found in PATH"
        if not wait_until_fn(probe.is_running, timeout_s=12):
            return False, f"ollama not ready: {base_url}"
    return True, ""


def ensure_ollama_ready(*, get_ollama_settings_fn, ollama_client_cls, start_ollama_serve_fn, wait_until_fn) -> tuple[bool, str]:
    settings = get_ollama_settings_fn()
    if not settings.enabled:
        return False, "model service disabled"
    base_url = settings.base_url
    probe = ollama_client_cls(base_url=base_url, model=settings.model, timeout_s=min(5.0, settings.timeout_s))
    if probe.is_running():
        return True, ""
    try:
        start_ollama_serve_fn()
    except FileNotFoundError:
        return False, "ollama executable not found in PATH"
    if not wait_until_fn(probe.is_running, timeout_s=12):
        return False, f"ollama not ready: {base_url}"
    return True, ""


__all__ = [name for name in globals() if not name.startswith("__")]
