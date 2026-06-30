"""Tests for KGRetriever."""

from __future__ import annotations

import pytest
from writing_agent.v2.rag.kg_retriever import KGRetriever
from writing_agent.v2.rag.knowledge_graph import KnowledgeGraph
from writing_agent.v2.rag.knowledge_unit import KnowledgeUnit, KUStore


class TestKGRetriever:
    @pytest.fixture
    def sample_units(self) -> list[KnowledgeUnit]:
        return [
            KnowledgeUnit(
                ku_id="KU-001",
                claim="BERT improves natural language processing performance significantly.",
                evidence="Devlin et al. 2019 demonstrated BERT achieves state-of-the-art results.",
                source_doc="doc-1",
                entities=["BERT", "NLP"],
                relation_hints=["extends"],
                confidence=0.9,
            ),
            KnowledgeUnit(
                ku_id="KU-002",
                claim="GPT models scale with data according to power laws.",
                evidence="Kaplan et al. showed that loss scales predictably with compute.",
                source_doc="doc-1",
                entities=["GPT", "scaling law"],
                confidence=0.85,
            ),
            KnowledgeUnit(
                ku_id="KU-003",
                claim="Transformer architecture enables parallel training.",
                evidence="Vaswani et al. introduced self-attention mechanism for parallelization.",
                source_doc="doc-2",
                entities=["Transformer", "self-attention"],
                confidence=0.88,
            ),
        ]

    @pytest.fixture
    def retriever(self, tmp_path: pytest.fixture, sample_units: list[KnowledgeUnit]) -> KGRetriever:
        store = KUStore(tmp_path / "kus")
        store.save(sample_units)
        kg = KGRetriever(store=store)
        kg.build_graph()
        return kg

    def test_retrieve_empty_graph(self) -> None:
        kg = KGRetriever()
        assert kg.retrieve("BERT") == []

    def test_retrieve_by_entity(self, retriever: KGRetriever) -> None:
        results = retriever.retrieve("BERT", top_k=2)
        assert len(results) >= 1
        assert any("BERT" in r.claim for r in results)

    def test_retrieve_top_k_respected(self, retriever: KGRetriever) -> None:
        results = retriever.retrieve("model", top_k=1)
        assert len(results) <= 1

    def test_retrieve_min_confidence(self, retriever: KGRetriever) -> None:
        results = retriever.retrieve("model", min_confidence=0.9)
        assert all(r.confidence >= 0.9 for r in results)

    def test_retrieve_with_trail(self, retriever: KGRetriever) -> None:
        result = retriever.retrieve_with_trail("BERT", top_k=2)
        assert "units" in result
        assert "trail" in result
        assert result["trail"]["query"] == "BERT"
        assert isinstance(result["trail"]["linked_entities"], list)

    def test_link_entities(self, retriever: KGRetriever) -> None:
        linked = retriever._link_entities("BERT and Transformer")
        assert len(linked) >= 2

    def test_build_and_persist(self, tmp_path: pytest.fixture, sample_units: list[KnowledgeUnit]) -> None:
        store = KUStore(tmp_path / "kus")
        store.save(sample_units)
        kg = KGRetriever(store=store)
        kg.build_graph()
        graph_path = tmp_path / "kg.json"
        kg.persist(graph_path)
        assert graph_path.exists()

        # Reload
        kg2 = KGRetriever(store=store, graph_path=graph_path)
        results = kg2.retrieve("BERT", top_k=2)
        assert len(results) >= 1
