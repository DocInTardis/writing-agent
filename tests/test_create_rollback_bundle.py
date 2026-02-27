from __future__ import annotations

from pathlib import Path

from scripts import create_rollback_bundle


def test_copy_entry_missing_file(tmp_path: Path) -> None:
    src = tmp_path / "missing.json"
    out_root = tmp_path / "bundle"
    row = create_rollback_bundle._copy_entry(src, out_root)
    assert row["exists"] is False
    assert row["copied"] is False


def test_copy_entry_existing_file(tmp_path: Path) -> None:
    src = tmp_path / "a.txt"
    src.write_text("hello", encoding="utf-8")
    out_root = tmp_path / "bundle"
    row = create_rollback_bundle._copy_entry(src, out_root)
    assert row["exists"] is True
    assert row["copied"] is True
    copied = out_root / str(row["path"])
    assert copied.exists()


def test_extract_correlation_prefers_correlation_node() -> None:
    raw = {
        "correlation": {"correlation_id": "corr-1", "release_candidate_id": "rc-1"},
        "incident": {"correlation_id": "corr-2", "release_candidate_id": "rc-2"},
    }
    out = create_rollback_bundle._extract_correlation(raw)
    assert out["correlation_id"] == "corr-1"
    assert out["release_candidate_id"] == "rc-1"
