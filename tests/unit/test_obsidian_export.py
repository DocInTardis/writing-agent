"""Tests for Obsidian vault export/import."""

from __future__ import annotations

from pathlib import Path

import pytest

from writing_agent.v2.rag.knowledge_unit import KnowledgeUnit
from writing_agent.v2.rag.obsidian_export import (
    export_to_obsidian_vault,
    import_from_obsidian,
    _safe_filename,
)


class TestObsidianExport:
    @pytest.fixture
    def sample_units(self) -> list[KnowledgeUnit]:
        return [
            KnowledgeUnit(
                ku_id="KU-001",
                claim="BERT improves NLP significantly.",
                evidence="Devlin et al. demonstrated state-of-the-art results.",
                source_doc="https://arxiv.org/abs/1810.04805",
                source_page=3,
                confidence=0.9,
                entities=["BERT", "NLP"],
            ),
        ]

    def test_export_roundtrip(self, tmp_path: Path, sample_units: list[KnowledgeUnit]) -> None:
        written = export_to_obsidian_vault(sample_units, tmp_path)
        assert len(written) == 1
        assert written[0].exists()

        imported = import_from_obsidian(tmp_path)
        assert len(imported) == 1
        assert imported[0].ku_id == "KU-001"
        assert "BERT" in imported[0].claim
        assert "Devlin" in imported[0].evidence

    def test_safe_filename(self) -> None:
        assert _safe_filename('foo/bar"baz') == "foo_bar_baz"
        assert _safe_filename("  hello world  ") == "hello_world"

    def test_import_empty_vault(self, tmp_path: Path) -> None:
        assert import_from_obsidian(tmp_path) == []

    def test_export_creates_subdir(self, tmp_path: Path, sample_units: list[KnowledgeUnit]) -> None:
        export_to_obsidian_vault(sample_units, tmp_path, subdir="custom_kg")
        assert (tmp_path / "custom_kg").is_dir()
