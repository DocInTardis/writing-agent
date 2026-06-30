"""Tests for NotionExporter (mocked API calls)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from writing_agent.v2.rag.notion_export import NotionExportConfig, NotionExporter
from writing_agent.v2.rag.knowledge_unit import KnowledgeUnit


class TestNotionExporter:
    @pytest.fixture
    def sample_units(self) -> list[KnowledgeUnit]:
        return [
            KnowledgeUnit(
                ku_id="KU-001",
                claim="BERT improves natural language processing significantly.",
                evidence="Devlin et al. 2019 demonstrated BERT achieves state-of-the-art results.",
                source_doc="https://arxiv.org/abs/1810.04805",
                source_page=3,
                confidence=0.9,
                entities=["BERT", "NLP"],
            ),
            KnowledgeUnit(
                ku_id="KU-002",
                claim="GPT models scale with data according to power laws.",
                evidence="Kaplan et al. showed predictable scaling.",
                source_doc="doc-1",
                confidence=0.85,
                entities=["GPT"],
            ),
        ]

    def test_missing_token_raises(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            exporter = NotionExporter()
            with pytest.raises(ValueError, match="Notion token missing"):
                exporter.client

    def test_export_units_mock(self, sample_units: list[KnowledgeUnit]) -> None:
        mock_client = MagicMock()
        mock_client.pages.create.return_value = {"id": "page-1"}

        exporter = NotionExporter(config=NotionExportConfig(token="fake", database_id="db-1"))
        exporter._client = mock_client

        results = exporter.export_units(sample_units)
        assert len(results) == 2
        assert mock_client.pages.create.call_count == 2

    def test_export_units_skips_on_error(self, sample_units: list[KnowledgeUnit]) -> None:
        mock_client = MagicMock()
        mock_client.pages.create.side_effect = [Exception("boom"), {"id": "page-2"}]

        exporter = NotionExporter(config=NotionExportConfig(token="fake", database_id="db-1"))
        exporter._client = mock_client

        results = exporter.export_units(sample_units)
        assert len(results) == 1
        assert results[0]["id"] == "page-2"

    def test_find_related_ku_ids(self, sample_units: list[KnowledgeUnit]) -> None:
        exporter = NotionExporter()
        related = exporter._find_related_ku_ids(sample_units[0], sample_units)
        # KU-001 shares no entities with KU-002 (BERT/NLP vs GPT)
        assert related == []

    def test_find_related_ku_ids_overlap(self) -> None:
        units = [
            KnowledgeUnit(ku_id="KU-A", claim="Claim one statement.", evidence="Evidence one supports here.", source_doc="S", entities=["BERT", "NLP"]),
            KnowledgeUnit(ku_id="KU-B", claim="Claim two statement.", evidence="Evidence two supports here.", source_doc="S", entities=["BERT", "CV"]),
        ]
        exporter = NotionExporter()
        related = exporter._find_related_ku_ids(units[0], units)
        assert related == ["KU-B"]

    def test_import_feedback_mock(self) -> None:
        mock_client = MagicMock()
        mock_client.databases.query.return_value = {
            "results": [
                {
                    "id": "page-1",
                    "properties": {
                        "KU ID": {"rich_text": [{"text": {"content": "KU-001"}}]},
                        "Status": {"select": {"name": "已通过"}},
                        "Comment": {"rich_text": [{"text": {"content": "Good"}}]},
                    },
                }
            ]
        }
        exporter = NotionExporter(config=NotionExportConfig(token="fake", database_id="db-1"))
        exporter._client = mock_client

        feedback = exporter.import_feedback()
        assert len(feedback) == 1
        assert feedback[0]["ku_id"] == "KU-001"
        assert feedback[0]["status"] == "已通过"
