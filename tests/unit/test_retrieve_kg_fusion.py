"""Tests for KG-RAG integration into retrieve_context and _maybe_rag_context."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from writing_agent.v2.graph_runner_rag_context_domain import _format_kg_context
from writing_agent.v2.rag.knowledge_unit import KnowledgeUnit, KUStore


class TestFormatKgContext:
    def test_empty(self) -> None:
        assert _format_kg_context([], max_chars=1000) == ""

    def test_single_unit(self) -> None:
        ku = KnowledgeUnit(
            claim="BERT improves NLP.",
            evidence="Devlin et al. showed BERT achieves SOTA.",
            source_doc="doc-1",
            source_page=3,
            confidence=0.9,
        )
        ctx = _format_kg_context([ku], max_chars=2000)
        assert "[KG-RAG]" in ctx
        assert "BERT improves NLP" in ctx
        assert "Devlin et al." in ctx
        assert "doc-1" in ctx
        assert "p.3" in ctx

    def test_respects_max_chars(self) -> None:
        ku = KnowledgeUnit(
            claim="A" * 500,
            evidence="B" * 500,
            source_doc="doc",
            confidence=0.8,
        )
        ctx = _format_kg_context([ku], max_chars=200)
        assert len(ctx) <= 250
        assert "[KG-RAG]" in ctx


class TestRetrieveContextKgFlag:
    """Test that retrieve_context accepts use_kg parameter and back-compat."""

    @pytest.fixture
    def mock_rag_dir(self, tmp_path: Path) -> Path:
        rag_dir = tmp_path / "rag"
        rag_dir.mkdir(parents=True, exist_ok=True)
        return rag_dir

    def test_retrieve_context_signature_accepts_use_kg(self, mock_rag_dir: Path) -> None:
        from writing_agent.v2.rag.retrieve import retrieve_context

        # Should not raise TypeError for unknown keyword
        with patch("writing_agent.v2.rag.retrieve._kg_retrieve", return_value=[]) as mock_kg:
            res = retrieve_context(
                rag_dir=mock_rag_dir,
                query="test query",
                top_k=2,
                use_kg=True,
            )
            mock_kg.assert_called_once()
            assert hasattr(res, "kg_hits")

    def test_retrieve_context_use_kg_false_skips_kg(self, mock_rag_dir: Path) -> None:
        from writing_agent.v2.rag.retrieve import retrieve_context

        with patch("writing_agent.v2.rag.retrieve._kg_retrieve", return_value=[]) as mock_kg:
            res = retrieve_context(
                rag_dir=mock_rag_dir,
                query="test query",
                top_k=2,
                use_kg=False,
            )
            mock_kg.assert_not_called()
            assert res.kg_hits == []

    def test_retrieve_context_backcompat_defaults(self, mock_rag_dir: Path) -> None:
        from writing_agent.v2.rag.retrieve import retrieve_context

        # Call without use_kg — should default to True but not crash
        with patch("writing_agent.v2.rag.retrieve._kg_retrieve", return_value=[]) as mock_kg:
            res = retrieve_context(
                rag_dir=mock_rag_dir,
                query="test query",
                top_k=2,
            )
            mock_kg.assert_called_once()
            assert res.kg_hits == []
