from __future__ import annotations

import json
import os
import time

from writing_agent.storage_lifecycle import apply_cleanup, preview_cleanup


def _old(path, now):
    os.utime(path, (now - 40 * 86400, now - 40 * 86400))


def test_preview_keeps_cross_document_references_and_finds_orphans(tmp_path):
    now = time.time()
    text_root = tmp_path / "text_store"
    workspace_root = tmp_path / "workspaces"
    checkpoint_root = tmp_path / "graph_checkpoints"
    text_root.mkdir()
    workspace_root.mkdir()
    checkpoint_root.mkdir()
    referenced = "p_sha256_" + "a" * 64
    checkpoint_referenced = "p_sha256_" + "b" * 64
    orphan = "p_sha256_" + "c" * 64
    for block_id in (referenced, checkpoint_referenced, orphan):
        path = text_root / f"{block_id}.txt"
        path.write_text(block_id, encoding="utf-8")
        _old(path, now)
    (workspace_root / "doc.json").write_text(json.dumps({"block_id": referenced, "run_id": "active-run-123"}), encoding="utf-8")
    (checkpoint_root / "active-run-123.json").write_text(
        json.dumps({"run_id": "active-run-123", "saved_at": now - 40 * 86400, "state": {"block_id": checkpoint_referenced}}),
        encoding="utf-8",
    )
    (checkpoint_root / "orphan-run-456.json").write_text(
        json.dumps({"run_id": "orphan-run-456", "saved_at": now - 40 * 86400}), encoding="utf-8"
    )

    candidates = preview_cleanup(tmp_path, now=now)

    paths = {item.path for item in candidates}
    assert str((text_root / f"{orphan}.txt").resolve()) in paths
    assert str((text_root / f"{referenced}.txt").resolve()) not in paths
    assert str((text_root / f"{checkpoint_referenced}.txt").resolve()) not in paths
    assert str((checkpoint_root / "orphan-run-456.json").resolve()) in paths
    assert str((checkpoint_root / "active-run-123.json").resolve()) not in paths


def test_apply_removes_only_previewed_managed_files(tmp_path):
    now = time.time()
    text_root = tmp_path / "text_store"
    text_root.mkdir()
    old_block = text_root / ("p_sha256_" + "d" * 64 + ".txt")
    current_block = text_root / ("p_sha256_" + "e" * 64 + ".txt")
    old_block.write_text("old", encoding="utf-8")
    current_block.write_text("current", encoding="utf-8")
    _old(old_block, now)

    candidates = preview_cleanup(tmp_path, now=now)
    removed = apply_cleanup(candidates, tmp_path)

    assert removed == [str(old_block.resolve())]
    assert not old_block.exists()
    assert current_block.exists()
