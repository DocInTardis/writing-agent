#!/usr/bin/env python3
"""Node Gateway Rollout Monitor command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        raw = line.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
        except Exception:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    vals = sorted(values)
    idx = int((len(vals) - 1) * max(0.0, min(1.0, q)))
    return float(vals[idx])


def summarize(node_events: list[dict[str, Any]], fallback_events: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(node_events)
    failures = [x for x in node_events if int(x.get("ok", 0)) != 1]
    error_rate = (len(failures) / total) if total else 0.0
    latencies = [float(x.get("latency_ms") or 0.0) for x in node_events if x.get("latency_ms") is not None]
    schema_failures = [
        x
        for x in failures
        if str(((x.get("error") or {}) if isinstance(x.get("error"), dict) else {}).get("code") or "") == "SCHEMA_FAIL"
    ]
    fallback_rate = (len(fallback_events) / total) if total else 0.0
    return {
        "total_requests": total,
        "error_rate": round(error_rate, 6),
        "p95_latency_ms": round(_percentile(latencies, 0.95), 2),
        "p99_latency_ms": round(_percentile(latencies, 0.99), 2),
        "schema_fail_rate": round((len(schema_failures) / total) if total else 0.0, 6),
        "fallback_trigger_rate": round(fallback_rate, 6),
        "fallback_count": len(fallback_events),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize node gateway rollout metrics.")
    parser.add_argument(
        "--node-log",
        default=".data/metrics/node_gateway_events.jsonl",
        help="Path to node gateway JSONL logs.",
    )
    parser.add_argument(
        "--fallback-log",
        default=".data/metrics/node_backend_fallback.jsonl",
        help="Path to python fallback trigger JSONL logs.",
    )
    parser.add_argument("--out", default="", help="Optional output json path.")
    args = parser.parse_args(argv)

    node_rows = _read_jsonl(Path(args.node_log))
    fallback_rows = _read_jsonl(Path(args.fallback_log))
    report = summarize(node_rows, fallback_rows)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.out:
        out = Path(str(args.out))
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
