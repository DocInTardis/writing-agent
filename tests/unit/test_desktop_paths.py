from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from writing_agent.desktop_paths import configure_desktop_environment, desktop_cache_dir, desktop_data_dir, migrate_legacy_data


def test_desktop_paths_use_local_app_data(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("WRITING_AGENT_DATA_DIR", raising=False)
    monkeypatch.delenv("WRITING_AGENT_CACHE_DIR", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert desktop_data_dir() == (tmp_path / "WritingAgent/data").resolve()
    assert desktop_cache_dir() == (tmp_path / "WritingAgent/cache").resolve()


def test_migration_copies_without_deleting_or_overwriting(monkeypatch, tmp_path: Path) -> None:
    legacy = tmp_path / "legacy"
    target = tmp_path / "new"
    (legacy / "workspaces").mkdir(parents=True)
    (legacy / "workspaces/a.json").write_text("old", encoding="utf-8")
    (legacy / "keep.json").write_text("source", encoding="utf-8")
    target.mkdir()
    (target / "keep.json").write_text("target", encoding="utf-8")
    monkeypatch.setenv("WRITING_AGENT_LEGACY_DATA_DIR", str(legacy))
    result = migrate_legacy_data(target)
    assert result["status"] == "complete"
    assert result["copied_files"] == 1
    assert (target / "workspaces/a.json").read_text(encoding="utf-8") == "old"
    assert (target / "keep.json").read_text(encoding="utf-8") == "target"
    assert (legacy / "workspaces/a.json").exists()


def test_interrupted_migration_is_retryable(monkeypatch, tmp_path: Path) -> None:
    legacy = tmp_path / "legacy"
    target = tmp_path / "new"
    legacy.mkdir()
    (legacy / "a.json").write_text("a", encoding="utf-8")
    target.mkdir()
    (target / ".a.json.partial.migrating").write_text("partial", encoding="utf-8")
    monkeypatch.setenv("WRITING_AGENT_LEGACY_DATA_DIR", str(legacy))
    result = migrate_legacy_data(target)
    assert result["status"] == "complete"
    assert (target / "a.json").read_text(encoding="utf-8") == "a"


def test_parallel_migration_has_one_stable_result(monkeypatch, tmp_path: Path) -> None:
    legacy = tmp_path / "legacy"
    target = tmp_path / "new"
    legacy.mkdir()
    for index in range(20):
        (legacy / f"{index}.json").write_text(str(index), encoding="utf-8")
    monkeypatch.setenv("WRITING_AGENT_LEGACY_DATA_DIR", str(legacy))
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: migrate_legacy_data(target), range(4)))
    assert all(row["status"] == "complete" for row in results)
    marker = json.loads((target / "migration-v1.json").read_text(encoding="utf-8"))
    assert marker["copied_files"] == 20
    assert len(list(target.glob("*.json"))) == 21


def test_configure_sets_both_roots_before_app_import(monkeypatch, tmp_path: Path) -> None:
    data = tmp_path / "data"
    cache = tmp_path / "cache"
    monkeypatch.setenv("WRITING_AGENT_DATA_DIR", str(data))
    monkeypatch.setenv("WRITING_AGENT_CACHE_DIR", str(cache))
    resolved_data, resolved_cache = configure_desktop_environment()
    assert resolved_data == data.resolve()
    assert resolved_cache == cache.resolve()
    assert os.environ["WRITING_AGENT_DATA_DIR"] == str(data.resolve())
    assert os.environ["WRITING_AGENT_CACHE_DIR"] == str(cache.resolve())
