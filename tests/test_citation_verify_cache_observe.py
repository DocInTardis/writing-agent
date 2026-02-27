from __future__ import annotations

import writing_agent.web.app_v2 as app_v2
from writing_agent.models import Citation


def test_citation_verify_cache_evicts_lru_when_over_capacity(monkeypatch):
    monkeypatch.setattr(app_v2, "_CITATION_VERIFY_CACHE", {})
    monkeypatch.setattr(app_v2, "_CITATION_VERIFY_CACHE_METRICS", {"hit": 0, "miss": 0, "set": 0, "expired": 0, "evicted": 0})
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_CACHE_MAX_ENTRIES", "2")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_CACHE_TTL_S", "3600")

    c1 = Citation(key="k1", title="Title A", authors="A", year="2024", venue="", url="")
    c2 = Citation(key="k2", title="Title B", authors="B", year="2024", venue="", url="")
    c3 = Citation(key="k3", title="Title C", authors="C", year="2024", venue="", url="")

    app_v2._citation_verify_cache_set(c1, {"id": "k1"}, c1)
    app_v2._citation_verify_cache_set(c2, {"id": "k2"}, c2)
    assert app_v2._citation_verify_cache_get(c1) is not None  # Refresh c1 as recently used
    app_v2._citation_verify_cache_set(c3, {"id": "k3"}, c3)

    # c2 should be evicted first because c1 was touched.
    assert app_v2._citation_verify_cache_get(c2) is None
    assert app_v2._citation_verify_cache_get(c1) is not None
    assert app_v2._citation_verify_cache_get(c3) is not None

    snap = app_v2._citation_verify_cache_snapshot()
    assert int(snap.get("size") or 0) == 2
    assert int(snap.get("max_entries") or 0) == 2
    assert int(snap.get("set") or 0) >= 3
    assert int(snap.get("hit") or 0) >= 2
    assert int(snap.get("miss") or 0) >= 1
    assert int(snap.get("evicted") or 0) >= 1


def test_citation_verify_cache_expired_entries_are_counted(monkeypatch):
    monkeypatch.setattr(app_v2, "_CITATION_VERIFY_CACHE", {})
    monkeypatch.setattr(app_v2, "_CITATION_VERIFY_CACHE_METRICS", {"hit": 0, "miss": 0, "set": 0, "expired": 0, "evicted": 0})
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_CACHE_TTL_S", "30")
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_CACHE_MAX_ENTRIES", "8")
    clock = [1700000000.0]
    monkeypatch.setattr(app_v2.time, "time", lambda: clock[0])

    cite = Citation(key="k1", title="Title A", authors="A", year="2024", venue="", url="")
    app_v2._citation_verify_cache_set(cite, {"id": "k1"}, cite)
    clock[0] += 31.0

    assert app_v2._citation_verify_cache_get(cite) is None
    snap = app_v2._citation_verify_cache_snapshot()
    assert int(snap.get("size") or 0) == 0
    assert int(snap.get("expired") or 0) >= 1
    assert int(snap.get("miss") or 0) >= 1


def test_citation_verify_observe_prune_tolerates_invalid_rows(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_OBSERVE_WINDOW_S", "120")
    monkeypatch.setattr(
        app_v2,
        "_CITATION_VERIFY_OBSERVE_RUNS",
        [
            {"ts": 1000.0, "elapsed_ms": 10.0},
            "noise-row",
            {"ts": "bad-ts", "elapsed_ms": 20.0},
            {"ts": 1190.0, "elapsed_ms": 30.0},
            {"ts": None, "elapsed_ms": 40.0},
        ],
    )

    app_v2._citation_verify_observe_prune_locked(now=1200.0)

    rows = app_v2._CITATION_VERIFY_OBSERVE_RUNS
    assert isinstance(rows, list)
    assert len(rows) == 1
    assert isinstance(rows[0], dict)
    assert float(rows[0].get("ts") or 0.0) == 1190.0


def test_citation_verify_observe_snapshot_tolerates_malformed_metrics(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_CITATION_VERIFY_OBSERVE_WINDOW_S", "3600")
    monkeypatch.setattr(app_v2.time, "time", lambda: 1700000250.0)
    monkeypatch.setattr(
        app_v2,
        "_CITATION_VERIFY_OBSERVE_RUNS",
        [
            {
                "ts": 1700000100.0,
                "elapsed_ms": "bad",
                "item_count": "bad",
                "worker_count": -2,
                "error_count": "bad",
                "cache_delta": {"hit": "3", "miss": "bad", "set": "4.8", "expired": -1, "evicted": None},
            },
            {
                "ts": 1700000200.0,
                "elapsed_ms": "5.5",
                "item_count": "2",
                "worker_count": "3",
                "error_count": "1",
                "cache_delta": {"hit": "2", "miss": "1", "set": "1", "expired": "0", "evicted": "0"},
            },
            "broken-row",
        ],
    )

    snap = app_v2._citation_verify_observe_snapshot()
    assert int(snap.get("runs") or 0) == 2
    assert isinstance(snap.get("elapsed_ms"), dict)
    assert isinstance(snap.get("items"), dict)
    assert isinstance(snap.get("workers"), dict)
    assert isinstance(snap.get("errors"), dict)
    cache_delta = snap.get("cache_delta")
    assert isinstance(cache_delta, dict)
    assert int(cache_delta.get("hit") or 0) == 5
    assert int(cache_delta.get("miss") or 0) == 1
    assert int(cache_delta.get("set") or 0) == 5
    assert int(cache_delta.get("expired") or 0) == 0
    assert int(cache_delta.get("evicted") or 0) == 0
    assert isinstance(snap.get("recent"), list)
    assert len(snap.get("recent")) == 2

    light = app_v2._citation_verify_observe_snapshot(include_recent=False)
    assert int(light.get("runs") or 0) == 2
    assert isinstance(light.get("recent"), list)
    assert len(light.get("recent")) == 0
