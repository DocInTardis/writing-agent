"""Route Graph Metrics Domain module.

Provides lightweight observability for route-graph execution and fallback behavior.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any


_METRICS_LOCK = threading.Lock()
_BOOL_FALSE = {"0", "false", "no", "off"}


def route_graph_metrics_enabled() -> bool:
    raw = str(os.environ.get("WRITING_AGENT_ROUTE_GRAPH_METRICS_ENABLE", "1")).strip().lower()
    return raw not in _BOOL_FALSE


def route_graph_metrics_path() -> Path:
    raw = str(os.environ.get("WRITING_AGENT_ROUTE_GRAPH_METRICS_PATH", "")).strip()
    if raw:
        return Path(raw)
    return Path(".data/metrics/route_graph_events.jsonl")


def route_graph_metrics_max_bytes() -> int:
    raw = str(os.environ.get("WRITING_AGENT_ROUTE_GRAPH_METRICS_MAX_BYTES", "2097152")).strip()
    try:
        parsed = int(float(raw))
    except Exception:
        parsed = 2097152
    return max(262144, parsed)


def _trim_metrics_file_locked(path: Path, max_bytes: int) -> None:
    try:
        if not path.exists():
            return
        size = path.stat().st_size
    except Exception:
        return
    if size <= max_bytes:
        return
    try:
        raw = path.read_bytes()
    except Exception:
        return
    if len(raw) <= max_bytes:
        return
    tail = raw[-max_bytes:]
    first_nl = tail.find(b"\n")
    if first_nl >= 0 and first_nl + 1 < len(tail):
        tail = tail[first_nl + 1 :]
    try:
        path.write_bytes(tail)
    except Exception:
        return


def extract_error_code(value: object, *, default: str = "E_RUNTIME") -> str:
    if isinstance(value, BaseException):
        raw = str(value)
    else:
        raw = str(value or "")
    text = raw.strip()
    if text:
        m = re.search(r"(E_[A-Z0-9_]+)", text.upper())
        if m:
            return str(m.group(1))
    if isinstance(value, BaseException):
        name = str(type(value).__name__ or "").strip().upper()
        if name:
            return f"E_{name}"
    return str(default or "E_RUNTIME").strip().upper()


def should_inject_route_graph_failure(*, phase: str = "") -> bool:
    flag = str(os.environ.get("WRITING_AGENT_FAIL_INJECT_ROUTE_GRAPH", "0")).strip().lower()
    if flag in _BOOL_FALSE:
        return False
    phase_raw = str(os.environ.get("WRITING_AGENT_FAIL_INJECT_ROUTE_GRAPH_PHASES", "")).strip()
    if not phase_raw:
        return True
    allowed = {token.strip().lower() for token in re.split(r"[,\s;]+", phase_raw) if token.strip()}
    if not allowed:
        return True
    return str(phase or "").strip().lower() in allowed


def record_route_graph_metric(
    event: str,
    *,
    phase: str,
    path: str,
    route_id: str = "",
    route_entry: str = "",
    engine: str = "",
    fallback_triggered: bool | None = None,
    fallback_recovered: bool | None = None,
    error_code: str = "",
    elapsed_ms: float | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    if not route_graph_metrics_enabled():
        return
    row: dict[str, Any] = {
        "ts": round(time.time(), 3),
        "event": str(event or "").strip() or "unknown",
        "phase": str(phase or "").strip() or "unknown",
        "path": str(path or "").strip() or "unknown",
        "route_id": str(route_id or "").strip(),
        "route_entry": str(route_entry or "").strip(),
        "engine": str(engine or "").strip(),
    }
    if fallback_triggered is not None:
        row["fallback_triggered"] = bool(fallback_triggered)
    if fallback_recovered is not None:
        row["fallback_recovered"] = bool(fallback_recovered)
    if error_code:
        row["error_code"] = str(error_code).strip().upper()
    if elapsed_ms is not None:
        try:
            row["elapsed_ms"] = round(max(0.0, float(elapsed_ms)), 3)
        except Exception:
            row["elapsed_ms"] = 0.0
    if isinstance(extra, dict) and extra:
        row["extra"] = dict(extra)

    path_obj = route_graph_metrics_path()
    line = json.dumps(row, ensure_ascii=False) + "\n"
    with _METRICS_LOCK:
        try:
            path_obj.parent.mkdir(parents=True, exist_ok=True)
            _trim_metrics_file_locked(path_obj, route_graph_metrics_max_bytes())
            with path_obj.open("a", encoding="utf-8") as f:
                f.write(line)
            _trim_metrics_file_locked(path_obj, route_graph_metrics_max_bytes())
        except Exception:
            return

