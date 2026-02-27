#!/usr/bin/env python3
"""Citation Verify Soak command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _percentile(values: list[float], p: float) -> float:
    rows = sorted(float(x) for x in values if float(x) >= 0.0)
    if not rows:
        return 0.0
    if len(rows) == 1:
        return rows[0]
    rank = (len(rows) - 1) * max(0.0, min(1.0, float(p)))
    low = int(rank)
    high = min(len(rows) - 1, low + 1)
    ratio = rank - low
    return rows[low] * (1.0 - ratio) + rows[high] * ratio


def _build_url(base_url: str, path: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    route = str(path or "").strip()
    if not route.startswith("/"):
        route = "/" + route
    return f"{base}{route}"


def _request_once(url: str, timeout_s: float, headers: dict[str, str]) -> dict[str, Any]:
    started = time.perf_counter()
    status = 0
    degraded = False
    severity = "unknown"
    error = ""
    try:
        req = Request(url, method="GET", headers=headers)
        with urlopen(req, timeout=max(0.2, float(timeout_s))) as resp:
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
    elapsed_ms = round((time.perf_counter() - started) * 1000.0, 3)
    return {
        "ok": bool(200 <= status < 300 and not error),
        "status": status,
        "elapsed_ms": elapsed_ms,
        "degraded": degraded,
        "severity": severity,
        "error": error,
    }


def _window_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    if total <= 0:
        return {
            "requests": 0,
            "success": 0,
            "failed": 0,
            "success_rate": 0.0,
            "degraded_count": 0,
            "degraded_rate": 0.0,
            "latency_ms": {"min": 0.0, "avg": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0},
        }
    success = sum(1 for row in rows if bool(row.get("ok")))
    failed = total - success
    degraded = sum(1 for row in rows if bool(row.get("degraded")))
    latencies = [float(row.get("elapsed_ms") or 0.0) for row in rows]
    return {
        "requests": total,
        "success": success,
        "failed": failed,
        "success_rate": round(success / float(total), 6),
        "degraded_count": degraded,
        "degraded_rate": round(degraded / float(total), 6),
        "latency_ms": {
            "min": round(min(latencies), 3),
            "avg": round(sum(latencies) / float(total), 3),
            "p50": round(_percentile(latencies, 0.50), 3),
            "p95": round(_percentile(latencies, 0.95), 3),
            "p99": round(_percentile(latencies, 0.99), 3),
            "max": round(max(latencies), 3),
        },
    }


def _run_window(
    *,
    url: str,
    timeout_s: float,
    headers: dict[str, str],
    requests: int,
    concurrency: int,
) -> dict[str, Any]:
    target = max(1, int(requests))
    workers = max(1, min(256, int(concurrency)))
    started = time.time()
    rows: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_request_once, url, timeout_s, headers) for _ in range(target)]
        for future in as_completed(futures):
            rows.append(dict(future.result()))
    ended = time.time()
    summary = _window_summary(rows)
    return {
        "started_at": round(started, 3),
        "ended_at": round(ended, 3),
        "duration_s": round(ended - started, 3),
        "summary": summary,
        "sample_failures": [row for row in rows if not bool(row.get("ok"))][:10],
    }


def _aggregate_windows(windows: list[dict[str, Any]]) -> dict[str, Any]:
    if not windows:
        return {
            "requests": 0,
            "success": 0,
            "failed": 0,
            "success_rate": 0.0,
            "degraded_count": 0,
            "degraded_rate": 0.0,
            "latency_p95_ms": 0.0,
            "window_count": 0,
            "max_window_p95_ms": 0.0,
        }
    requests = sum(int((row.get("summary") if isinstance(row.get("summary"), dict) else {}).get("requests") or 0) for row in windows)
    success = sum(int((row.get("summary") if isinstance(row.get("summary"), dict) else {}).get("success") or 0) for row in windows)
    failed = sum(int((row.get("summary") if isinstance(row.get("summary"), dict) else {}).get("failed") or 0) for row in windows)
    degraded_count = sum(
        int((row.get("summary") if isinstance(row.get("summary"), dict) else {}).get("degraded_count") or 0)
        for row in windows
    )
    p95_values = [
        float(((row.get("summary") if isinstance(row.get("summary"), dict) else {}).get("latency_ms") or {}).get("p95") or 0.0)
        for row in windows
    ]
    return {
        "requests": requests,
        "success": success,
        "failed": failed,
        "success_rate": round((success / float(requests)) if requests > 0 else 0.0, 6),
        "degraded_count": degraded_count,
        "degraded_rate": round((degraded_count / float(requests)) if requests > 0 else 0.0, 6),
        "latency_p95_ms": round(_percentile(p95_values, 0.95), 3) if p95_values else 0.0,
        "window_count": len(windows),
        "max_window_p95_ms": round(max(p95_values), 3) if p95_values else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Long-running soak probe for citation_verify metric endpoint.")
    parser.add_argument("--base-url", default=os.environ.get("WA_METRICS_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--path", default=os.environ.get("WA_METRICS_PATH", "/api/metrics/citation_verify"))
    parser.add_argument("--duration-s", type=float, default=_safe_float(os.environ.get("WA_SOAK_DURATION_S"), 1800.0))
    parser.add_argument("--interval-s", type=float, default=_safe_float(os.environ.get("WA_SOAK_INTERVAL_S"), 30.0))
    parser.add_argument("--requests-per-window", type=int, default=_safe_int(os.environ.get("WA_SOAK_REQUESTS_PER_WINDOW"), 32))
    parser.add_argument("--concurrency", type=int, default=_safe_int(os.environ.get("WA_SOAK_CONCURRENCY"), 8))
    parser.add_argument("--timeout-s", type=float, default=_safe_float(os.environ.get("WA_SOAK_TIMEOUT_S"), 6.0))
    parser.add_argument("--min-overall-success-rate", type=float, default=_safe_float(os.environ.get("WA_SOAK_MIN_SUCCESS_RATE"), 0.995))
    parser.add_argument("--max-overall-p95-ms", type=float, default=_safe_float(os.environ.get("WA_SOAK_MAX_P95_MS"), 2000.0))
    parser.add_argument("--max-overall-degraded-rate", type=float, default=_safe_float(os.environ.get("WA_SOAK_MAX_DEGRADED_RATE"), 0.05))
    parser.add_argument("--admin-key", default=os.environ.get("WA_ADMIN_KEY", ""))
    parser.add_argument("--label", default=os.environ.get("WA_SOAK_LABEL", ""))
    parser.add_argument("--out", default=os.environ.get("WA_SOAK_OUT", ""))
    args = parser.parse_args()

    duration_s = max(5.0, float(args.duration_s))
    interval_s = max(2.0, float(args.interval_s))
    timeout_s = max(0.2, float(args.timeout_s))
    req_per_window = max(1, int(args.requests_per_window))
    concurrency = max(1, min(256, int(args.concurrency)))
    url = _build_url(str(args.base_url), str(args.path))

    headers: dict[str, str] = {}
    if str(args.admin_key or "").strip():
        headers["X-Admin-Key"] = str(args.admin_key).strip()

    started = time.time()
    deadline = started + duration_s
    windows: list[dict[str, Any]] = []
    while True:
        now = time.time()
        if now >= deadline:
            break
        row = _run_window(
            url=url,
            timeout_s=timeout_s,
            headers=headers,
            requests=req_per_window,
            concurrency=concurrency,
        )
        windows.append(row)
        remain = deadline - time.time()
        if remain <= 0:
            break
        sleep_s = min(interval_s, remain)
        if sleep_s > 0:
            time.sleep(sleep_s)

    ended = time.time()
    aggregate = _aggregate_windows(windows)
    checks = [
        {
            "id": "overall_success_rate",
            "ok": float(aggregate.get("success_rate") or 0.0) >= float(args.min_overall_success_rate),
            "value": float(aggregate.get("success_rate") or 0.0),
            "expect": f">={float(args.min_overall_success_rate):.4f}",
        },
        {
            "id": "overall_latency_p95_ms",
            "ok": float(aggregate.get("latency_p95_ms") or 0.0) <= float(args.max_overall_p95_ms),
            "value": float(aggregate.get("latency_p95_ms") or 0.0),
            "expect": f"<={float(args.max_overall_p95_ms):.2f}",
        },
        {
            "id": "overall_degraded_rate",
            "ok": float(aggregate.get("degraded_rate") or 0.0) <= float(args.max_overall_degraded_rate),
            "value": float(aggregate.get("degraded_rate") or 0.0),
            "expect": f"<={float(args.max_overall_degraded_rate):.4f}",
        },
    ]

    report = {
        "ok": all(bool(row.get("ok")) for row in checks),
        "started_at": round(started, 3),
        "ended_at": round(ended, 3),
        "duration_s": round(ended - started, 3),
        "label": str(args.label or ""),
        "target": {
            "url": url,
            "duration_s": round(duration_s, 3),
            "interval_s": round(interval_s, 3),
            "requests_per_window": req_per_window,
            "concurrency": concurrency,
            "timeout_s": round(timeout_s, 3),
        },
        "aggregate": aggregate,
        "checks": checks,
        "windows": windows,
    }

    default_out = Path(".data/out") / f"citation_verify_soak_{int(ended)}.json"
    out_path = Path(str(args.out or default_out))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report.get("ok")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
