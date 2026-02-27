#!/usr/bin/env python3
"""Citation Verify Load Probe command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def _percentile(values: list[float], p: float) -> float:
    rows = sorted(float(x) for x in values if float(x) >= 0)
    if not rows:
        return 0.0
    if len(rows) == 1:
        return rows[0]
    rank = (len(rows) - 1) * max(0.0, min(1.0, float(p)))
    low = int(rank)
    high = min(len(rows) - 1, low + 1)
    ratio = rank - low
    return rows[low] * (1.0 - ratio) + rows[high] * ratio


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _request_once(url: str, timeout_s: float, headers: dict[str, str]) -> dict[str, Any]:
    started = time.perf_counter()
    status = 0
    degraded = False
    severity = "unknown"
    error = ""
    try:
        req = Request(url, method="GET", headers=headers)
        with urlopen(req, timeout=timeout_s) as resp:
            status = int(getattr(resp, "status", 0) or resp.getcode() or 0)
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8"))
        if isinstance(payload, dict):
            degraded = bool(payload.get("degraded"))
            alerts = payload.get("alerts") if isinstance(payload.get("alerts"), dict) else {}
            sev = str(alerts.get("severity") or "").strip().lower()
            severity = sev if sev in {"ok", "warn", "critical"} else "unknown"
    except HTTPError as exc:
        status = int(exc.code or 0)
        error = f"http_{status}"
    except Exception as exc:
        error = exc.__class__.__name__
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 2)
    return {
        "status": status,
        "ok": bool(200 <= status < 300 and not error),
        "elapsed_ms": elapsed_ms,
        "degraded": degraded,
        "severity": severity,
        "error": error,
    }


def _fetch_recent_events(base_url: str, timeout_s: float, headers: dict[str, str]) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/api/metrics/citation_verify/alerts/events?limit=10"
    try:
        req = Request(url, method="GET", headers=headers)
        with urlopen(req, timeout=timeout_s) as resp:
            status = int(getattr(resp, "status", 0) or resp.getcode() or 0)
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8"))
        if isinstance(payload, dict) and int(payload.get("ok") or 0) == 1:
            events = payload.get("events")
            return {
                "ok": True,
                "status": status,
                "total": int(payload.get("total") or 0),
                "recent_count": len(events) if isinstance(events, list) else 0,
            }
        return {"ok": False, "status": status, "error": "invalid_payload"}
    except HTTPError as exc:
        return {"ok": False, "status": int(exc.code or 0), "error": f"http_{int(exc.code or 0)}"}
    except Exception as exc:
        return {"ok": False, "status": 0, "error": exc.__class__.__name__}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Concurrent load probe for /api/metrics/citation_verify with threshold checks."
    )
    parser.add_argument("--base-url", default=os.environ.get("WA_METRICS_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--path", default=os.environ.get("WA_METRICS_PATH", "/api/metrics/citation_verify"))
    parser.add_argument("--requests", type=int, default=_safe_int(os.environ.get("WA_LOAD_REQUESTS"), 240))
    parser.add_argument("--concurrency", type=int, default=_safe_int(os.environ.get("WA_LOAD_CONCURRENCY"), 16))
    parser.add_argument("--timeout-s", type=float, default=_safe_float(os.environ.get("WA_LOAD_TIMEOUT_S"), 6.0))
    parser.add_argument("--min-success-rate", type=float, default=_safe_float(os.environ.get("WA_LOAD_MIN_SUCCESS_RATE"), 0.99))
    parser.add_argument("--max-p95-ms", type=float, default=_safe_float(os.environ.get("WA_LOAD_MAX_P95_MS"), 1500.0))
    parser.add_argument(
        "--max-degraded-rate",
        type=float,
        default=_safe_float(os.environ.get("WA_LOAD_MAX_DEGRADED_RATE"), 0.05),
    )
    parser.add_argument("--admin-key", default=os.environ.get("WA_ADMIN_KEY", ""))
    parser.add_argument("--out", default=os.environ.get("WA_LOAD_OUT", ""))
    args = parser.parse_args()

    req_total = max(1, int(args.requests))
    workers = max(1, min(512, int(args.concurrency)))
    timeout_s = max(0.2, float(args.timeout_s))

    base_url = str(args.base_url or "").rstrip("/")
    path = str(args.path or "").strip()
    if not path.startswith("/"):
        path = "/" + path
    url = f"{base_url}{path}"
    headers: dict[str, str] = {}
    if str(args.admin_key or "").strip():
        headers["X-Admin-Key"] = str(args.admin_key).strip()

    started_at = time.time()
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_request_once, url, timeout_s, headers) for _ in range(req_total)]
        for fut in as_completed(futures):
            rows.append(dict(fut.result()))
    ended_at = time.time()

    ok_rows = [row for row in rows if bool(row.get("ok"))]
    fail_rows = [row for row in rows if not bool(row.get("ok"))]
    latencies = [float(row.get("elapsed_ms") or 0.0) for row in rows]
    success_rate = (len(ok_rows) / float(len(rows))) if rows else 0.0
    degraded_count = sum(1 for row in rows if bool(row.get("degraded")))
    degraded_rate = (degraded_count / float(len(rows))) if rows else 0.0
    severity_counter = Counter(str(row.get("severity") or "unknown") for row in ok_rows)
    error_counter = Counter(str(row.get("error") or "none") for row in fail_rows)

    summary = {
        "url": url,
        "requests": req_total,
        "concurrency": workers,
        "timeout_s": round(timeout_s, 3),
        "duration_s": round(ended_at - started_at, 3),
        "success": len(ok_rows),
        "failed": len(fail_rows),
        "success_rate": round(success_rate, 6),
        "degraded_count": degraded_count,
        "degraded_rate": round(degraded_rate, 6),
        "latency_ms": {
            "min": round(min(latencies) if latencies else 0.0, 3),
            "avg": round((sum(latencies) / len(latencies)) if latencies else 0.0, 3),
            "p50": round(_percentile(latencies, 0.50), 3),
            "p95": round(_percentile(latencies, 0.95), 3),
            "p99": round(_percentile(latencies, 0.99), 3),
            "max": round(max(latencies) if latencies else 0.0, 3),
        },
        "severity": dict(severity_counter),
        "top_errors": error_counter.most_common(6),
    }

    checks = []
    checks.append(
        {
            "id": "success_rate",
            "ok": success_rate >= float(args.min_success_rate),
            "value": round(success_rate, 6),
            "expect": f">={float(args.min_success_rate):.4f}",
        }
    )
    checks.append(
        {
            "id": "latency_p95_ms",
            "ok": summary["latency_ms"]["p95"] <= float(args.max_p95_ms),
            "value": summary["latency_ms"]["p95"],
            "expect": f"<={float(args.max_p95_ms):.2f}",
        }
    )
    checks.append(
        {
            "id": "degraded_rate",
            "ok": degraded_rate <= float(args.max_degraded_rate),
            "value": round(degraded_rate, 6),
            "expect": f"<={float(args.max_degraded_rate):.4f}",
        }
    )

    events_probe = _fetch_recent_events(base_url, timeout_s, headers)
    all_ok = all(bool(row.get("ok")) for row in checks)
    report = {
        "ok": all_ok,
        "ts": round(ended_at, 3),
        "summary": summary,
        "checks": checks,
        "events_probe": events_probe,
        "sample_failures": fail_rows[:12],
    }

    default_out = Path(".data/out") / f"citation_verify_load_probe_{int(ended_at)}.json"
    out_path = Path(str(args.out or default_out))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    if all_ok:
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

