"""Tests for KnowledgeGraph, KGEntity, KGRelation."""

from __future__ import annotations

import pytest
from writing_agent.v2.rag.knowledge_graph import KGEntity, KGRelation, KnowledgeGraph
from writing_agent.v2.rag.knowledge_unit import KnowledgeUnit


class TestKGEntity:
    def test_create(self) -> None:
        e = KGEntity(id="ENT-1", name="BERT", entity_type="method")
        assert e.name == "BERT"
        assert e.entity_type == "method"

    def test_name_stripped(self) -> None:
        e = KGEntity(id="ENT-1", name="  BERT  ", entity_type="method")
        assert e.name == "BERT"

    def test_invalid_type_rejected(self) -> None:
        with pytest.raises(ValueError):
            KGEntity(id="ENT-1", name="X", entity_type="invalid")


class TestKGRelation:
    def test_create(self) -> None:
        r = KGRelation(from_id="A", to_id="B", relation="supports")
        assert r.weight == 1.0

    def test_invalid_relation_rejected(self) -> None:
        with pytest.raises(ValueError):
            KGRelation(from_id="A", to_id="B", relation="loves")


class TestKnowledgeGraph:
    @pytest.fixture
    def graph(self) -> KnowledgeGraph:
        return KnowledgeGraph()

    def test_add_entity(self, graph: KnowledgeGraph) -> None:
        e = KGEntity(id="ENT-A", name="Alpha")
        graph.add_entity(e)
        assert "ENT-A" in graph.entities

    def test_add_entity_merge_ku_ids(self, graph: KnowledgeGraph) -> None:
        e1 = KGEntity(id="ENT-A", name="Alpha", ku_ids=["KU-1"])
        e2 = KGEntity(id="ENT-A", name="Alpha", ku_ids=["KU-2"])
        graph.add_entity(e1)
        graph.add_entity(e2)
        assert graph.entities["ENT-A"].ku_ids == ["KU-1", "KU-2"]

    def test_add_relation_missing_endpoint_ignored(self, graph: KnowledgeGraph) -> None:
        graph.add_relation(KGRelation(from_id="MISSING", to_id="ALSO_MISSING"))
        assert len(graph.relations) == 0

    def test_add_relation(self, graph: KnowledgeGraph) -> None:
        graph.add_entity(KGEntity(id="A", name="Alpha"))
        graph.add_entity(KGEntity(id="B", name="Beta"))
        graph.add_relation(KGRelation(from_id="A", to_id="B", relation="supports"))
        assert len(graph.relations) == 1
        assert len(graph._adj["A"]) == 1
        assert len(graph._adj["B"]) == 1

    def test_build_from_kus(self, graph: KnowledgeGraph) -> None:
        units = [
            KnowledgeUnit(
                ku_id="KU-001",
                claim="BERT improves NLP significantly.",
                evidence="Evidence one is strong here.",
                source_doc="doc-1",
                entities=["BERT", "NLP"],
                relation_hints=["extends"],
                confidence=0.9,
            ),
            KnowledgeUnit(
                ku_id="KU-002",
                claim="GPT models scale with data.",
                evidence="Evidence two supports scaling laws.",
                source_doc="doc-1",
                entities=["GPT", "scaling law"],
                confidence=0.85,
            ),
        ]
        graph.build_from_kus(units)
        stats = graph.stats()
        assert stats["entities"] == 6  # 2 claims + 4 unique entities
        assert stats["relations"] >= 4  # claim->entity links + relation hint

    def test_traverse(self, graph: KnowledgeGraph) -> None:
        graph.add_entity(KGEntity(id="A", name="Alpha"))
        graph.add_entity(KGEntity(id="B", name="Beta"))
        graph.add_entity(KGEntity(id="C", name="Gamma"))
        graph.add_relation(KGRelation(from_id="A", to_id="B", relation="supports"))
        graph.add_relation(KGRelation(from_id="B", to_id="C", relation="extends"))
        result = graph.traverse("A", max_depth=2)
        assert len(result["distances"]) == 3
        assert result["distances"]["C"] == 2

    def test_traverse_filter_relation(self, graph: KnowledgeGraph) -> None:
        graph.add_entity(KGEntity(id="A", name="Alpha"))
        graph.add_entity(KGEntity(id="B", name="Beta"))
        graph.add_entity(KGEntity(id="C", name="Gamma"))
        graph.add_relation(KGRelation(from_id="A", to_id="B", relation="supports"))
        graph.add_relation(KGRelation(from_id="A", to_id="C", relation="contradicts"))
        result = graph.traverse("A", max_depth=2, relation_filter={"supports"})
        assert "B" in result["distances"]
        assert "C" not in result["distances"]

    def test_get_neighbors(self, graph: KnowledgeGraph) -> None:
        graph.add_entity(KGEntity(id="A", name="Alpha"))
        graph.add_entity(KGEntity(id="B", name="Beta"))
        graph.add_relation(KGRelation(from_id="A", to_id="B", relation="uses"))
        neighbors = graph.get_neighbors("A")
        assert len(neighbors) == 1
        assert neighbors[0][0].id == "B"

    def test_save_and_load(self, tmp_path: pytest.fixture) -> None:
        graph = KnowledgeGraph()
        graph.add_entity(KGEntity(id="A", name="Alpha", ku_ids=["KU-1"]))
        graph.add_entity(KGEntity(id="B", name="Beta"))
        graph.add_relation(KGRelation(from_id="A", to_id="B", relation="supports"))
        path = tmp_path / "kg.json"
        graph.save(path)

        g2 = KnowledgeGraph()
        g2.load(path)
        assert g2.stats() == graph.stats()
        assert g2.entities["A"].ku_ids == ["KU-1"]
