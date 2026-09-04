from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from writing_agent.v2 import cache as cache_module
from writing_agent.v2.cache import LocalCache


def test_byte_limit_counts_utf8_and_uses_lru(tmp_path, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(cache_module.time, "time", lambda: now[0])
    cache = LocalCache(tmp_path, max_bytes=12)
    cache.put("a", "中文")
    now[0] += 1
    cache.put("b", "中文")
    now[0] += 1
    assert cache.get("a") == "中文"
    now[0] += 1
    cache.put("c", "中文")
    assert cache.get("b") is None
    assert cache.get("a") == cache.get("c") == "中文"
    assert cache.stats()["total_bytes"] == 12


def test_update_at_capacity_does_not_evict_unrelated_entry(tmp_path):
    cache = LocalCache(tmp_path, max_size=2, max_bytes=6)
    cache.put("a", "123")
    cache.put("b", "123")
    cache.put("b", "456")
    assert cache.get("a") == "123"
    assert cache.get("b") == "456"
    assert cache.stats()["total_entries"] == 2


def test_oversized_update_removes_stale_value_without_evicting_others(tmp_path):
    cache = LocalCache(tmp_path, max_bytes=6)
    cache.put("a", "123")
    cache.put("b", "123")
    cache.put("b", "x" * 7)
    assert cache.get("a") == "123"
    assert cache.get("b") is None
    assert not (tmp_path / "b.txt").exists()


def test_expired_entries_are_cleaned_on_write(tmp_path, monkeypatch):
    now = [100.0]
    monkeypatch.setattr(cache_module.time, "time", lambda: now[0])
    cache = LocalCache(tmp_path, ttl_seconds=10)
    cache.put("expired", "old")
    now[0] += 11
    cache.put("new", "new")
    assert not (tmp_path / "expired.txt").exists()
    assert cache.get("new") == "new"


def test_startup_reconciles_legacy_index_and_applies_budget(tmp_path):
    (tmp_path / "index.json").write_text(
        json.dumps(
            {
                "old": {"created_at": 100, "last_hit": 100},
                "a": {"created_at": 1e12, "last_hit": 101},
                "b": {"created_at": 1e12, "last_hit": 102},
                "missing": {"created_at": 1e12},
            }
        ),
        encoding="utf-8",
    )
    for key in ("old", "a", "b"):
        (tmp_path / f"{key}.txt").write_text("1234", encoding="utf-8")
    cache = LocalCache(tmp_path, max_bytes=4)
    assert list(cache.index) == ["b"]
    assert cache.stats()["total_bytes"] == 4
    assert not (tmp_path / "old.txt").exists()
    assert not (tmp_path / "a.txt").exists()


def test_shared_instances_enforce_one_budget_in_process(tmp_path):
    first = LocalCache(tmp_path, max_size=3, max_bytes=6)
    second = LocalCache(tmp_path, max_size=3, max_bytes=6)
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(
            pool.map(
                lambda pair: pair[0].put(pair[1], "123"), [(first if i % 2 else second, str(i)) for i in range(20)]
            )
        )
    assert first.index is second.index
    assert first.stats()["total_bytes"] <= 6
    assert sum(p.stat().st_size for p in tmp_path.glob("*.txt")) <= 6


def test_invalid_index_entries_cannot_delete_outside_cache(tmp_path):
    outside = tmp_path / "document.txt"
    outside.write_text("keep", encoding="utf-8")
    root = tmp_path / "cache"
    root.mkdir()
    (root / "index.json").write_text(
        json.dumps(
            {
                "../document": {"created_at": 0},
                "bad": {"created_at": "oops"},
                "nan": {"created_at": float("nan")},
                "wrong": [],
            }
        ),
        encoding="utf-8",
    )
    cache = LocalCache(root)
    assert cache.stats()["total_entries"] == 0
    assert outside.read_text(encoding="utf-8") == "keep"
    with pytest.raises(ValueError, match="invalid cache key"):
        cache.put("../document", "overwrite")


def test_unindexed_files_are_not_treated_as_disposable_cache(tmp_path):
    (tmp_path / "notes.txt").write_text("keep", encoding="utf-8")
    cache = LocalCache(tmp_path, max_size=0)
    cache.put("a", "not cached")
    assert cache.get("a") is None
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "keep"


def test_locked_payload_blocks_new_writes_when_budget_cannot_be_met(tmp_path, monkeypatch):
    cache = LocalCache(tmp_path, max_bytes=3)
    cache.put("a", "123")
    monkeypatch.setattr(cache, "_remove", lambda _: False)
    cache.put("b", "456")
    assert cache.get("a") == "123"
    assert cache.get("b") is None


def test_corrupt_payload_is_a_cache_miss(tmp_path):
    cache = LocalCache(tmp_path)
    cache.put("a", "valid")
    (tmp_path / "a.txt").write_bytes(b"\xff")
    assert cache.get("a") is None
