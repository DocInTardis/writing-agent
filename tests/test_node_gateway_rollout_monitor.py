from __future__ import annotations

import json
from pathlib import Path

from scripts.node_gateway_rollout_monitor import summarize


def test_rollout_monitor_summary() -> None:
    rows = [
        {"ok": 1, "latency_ms": 100},
        {"ok": 1, "latency_ms": 200},
        {"ok": 0, "latency_ms": 300, "error": {"code": "SCHEMA_FAIL"}},
        {"ok": 0, "latency_ms": 400, "error": {"code": "TIMEOUT"}},
    ]
    fallback = [{"event": "node_backend_fallback"}, {"event": "node_backend_fallback"}]
    report = summarize(rows, fallback)
    assert report["total_requests"] == 4
    assert report["error_rate"] == 0.5
    assert report["schema_fail_rate"] == 0.25
    assert report["fallback_count"] == 2


def test_rollout_monitor_file_contract(tmp_path: Path) -> None:
    node_log = tmp_path / "node.jsonl"
    fallback_log = tmp_path / "fallback.jsonl"
    node_log.write_text(
        "\n".join(
            [
                json.dumps({"ok": 1, "latency_ms": 80}),
                json.dumps({"ok": 0, "latency_ms": 180, "error": {"code": "TIMEOUT"}}),
            ]
        ),
        encoding="utf-8",
    )
    fallback_log.write_text(json.dumps({"event": "node_backend_fallback"}), encoding="utf-8")
    from scripts.node_gateway_rollout_monitor import _read_jsonl

    report = summarize(_read_jsonl(node_log), _read_jsonl(fallback_log))
    assert report["total_requests"] == 2
    assert report["fallback_count"] == 1
