from __future__ import annotations

import json
import time
from datetime import datetime, timezone

from writing_agent.bounded_jsonl import append_bounded_jsonl, read_recent_jsonl


def test_read_filters_expired_numeric_and_iso_timestamps(tmp_path):
    path = tmp_path / "events.jsonl"
    now = time.time()
    rows = [
        {"id": "old-number", "published_at": now - 1000},
        {"id": "old-iso", "timestamp": datetime.fromtimestamp(now - 1000, timezone.utc).isoformat()},
        {"id": "current", "recorded_at": now},
        {"id": "legacy-without-time"},
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    retained = read_recent_jsonl(path, max_bytes=4096, max_age_s=60)

    assert [row["id"] for row in retained] == ["current", "legacy-without-time"]


def test_append_compacts_expired_rows_and_stays_bounded(tmp_path):
    path = tmp_path / "events.jsonl"
    now = time.time()
    path.write_text(
        json.dumps({"id": "expired", "ts": now - 1000}) + "\n"
        + json.dumps({"id": "kept", "ts": now}) + "\n",
        encoding="utf-8",
    )

    assert append_bounded_jsonl(
        path,
        {"id": "new", "ts": now},
        max_bytes=180,
        max_age_s=60,
    )

    rows = read_recent_jsonl(path, max_bytes=180)
    assert [row["id"] for row in rows] == ["kept", "new"]
    assert path.stat().st_size <= 180


def test_future_appends_do_not_rewrite_until_sweep_interval(tmp_path, monkeypatch):
    path = tmp_path / "events.jsonl"
    now = time.time()
    path.write_text(json.dumps({"id": "first", "ts": now}) + "\n", encoding="utf-8")
    replacements = 0

    from writing_agent import bounded_jsonl

    original_replace = bounded_jsonl.os.replace

    def counting_replace(source, target):
        nonlocal replacements
        replacements += 1
        return original_replace(source, target)

    monkeypatch.setattr(bounded_jsonl.os, "replace", counting_replace)
    assert append_bounded_jsonl(path, {"id": "second", "ts": now}, max_bytes=4096, max_age_s=60)
    assert append_bounded_jsonl(path, {"id": "third", "ts": now}, max_bytes=4096, max_age_s=60)

    assert replacements == 1

