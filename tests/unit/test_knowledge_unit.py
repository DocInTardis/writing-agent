"""Tests for Knowledge Unit extraction and storage."""

from __future__ import annotations

from pathlib import Path

import pytest

from writing_agent.v2.rag.knowledge_unit import (
    KnowledgeUnit,
    KnowledgeUnitExtractor,
    KUStore,
)


class TestKnowledgeUnit:
    def test_model_validate(self) -> None:
        ku = KnowledgeUnit(
            claim="BERT improves NLP performance.",
            evidence="Devlin et al. (2019) introduced BERT, achieving SOTA on 11 tasks.",
            source_doc="arxiv:1810.04805",
            source_title="BERT: Pre-training of Deep Bidirectional Transformers",
            source_page=3,
            source_para=2,
            confidence=0.92,
            entities=["BERT", "Transformer"],
        )
        assert ku.ku_id.startswith("KU-")
        assert "BERT" in ku.claim
        assert ku.source_page == 3

    def test_provenance_key_stable(self) -> None:
        ku1 = KnowledgeUnit(
            claim="X improves Y performance.",
            evidence="Experiment E1 shows improvement.",
            source_doc="doi:10.1/1",
        )
        ku2 = KnowledgeUnit(
            claim="X improves Y performance.",
            evidence="Experiment E1 shows improvement.",
            source_doc="doi:10.1/1",
        )
        assert ku1.provenance_key() == ku2.provenance_key()

    def test_to_obsidian_page(self) -> None:
        ku = KnowledgeUnit(
            claim="Test claim.",
            evidence="Test evidence.",
            source_doc="arxiv:1234",
            entities=["EntityA", "EntityB"],
        )
        md = ku.to_obsidian_page()
        assert "## Claim" in md
        assert "## Evidence" in md
        assert "[[EntityA]]" in md
        assert "[[EntityB]]" in md

    def test_invalid_confidence_rejected(self) -> None:
        with pytest.raises(Exception):
            KnowledgeUnit(
                claim="X.",
                evidence="E.",
                source_doc="S",
                confidence=1.5,
            )


class TestKnowledgeUnitExtractor:
    def test_heuristic_extract_fallback(self) -> None:
        extractor = KnowledgeUnitExtractor()
        text = (
            "Deep learning has revolutionized computer vision significantly. "
            "Convolutional neural networks achieve state-of-the-art accuracy on ImageNet benchmark. "
            "Recurrent networks are effective for sequential data processing."
        )
        units = extractor._heuristic_extract(
            text,
            source_doc="test-doc",
            source_title="Test Title",
            source_authors=["A. Author"],
        )
        assert len(units) >= 2
        assert all(u.source_doc == "test-doc" for u in units)
        assert all(u.confidence == 0.5 for u in units)

    def test_parse_response_structured(self) -> None:
        extractor = KnowledgeUnitExtractor()
        raw = (
            '{"units":[{'
            '"claim":"BERT improves NLP.",'
            '"evidence":"Devlin et al. introduced BERT.",'
            '"source_doc":"arxiv:1810.04805",'
            '"confidence":0.9,'
            '"entities":["BERT"],'
            '"relation_hints":["extends"]'
            '}]}'
        )
        units = extractor._parse_response(
            raw,
            source_doc="arxiv:1810.04805",
            source_title="BERT",
            source_authors=["Devlin"],
        )
        assert len(units) == 1
        assert units[0].claim == "BERT improves NLP."
        assert "BERT" in units[0].entities

    def test_parse_response_with_code_fence(self) -> None:
        extractor = KnowledgeUnitExtractor()
        raw = '```json\n{"units":[]}\n```'
        units = extractor._parse_response(
            raw,
            source_doc="x",
            source_title="T",
            source_authors=[],
        )
        assert units == []

    def test_enrich_units_dedupes(self) -> None:
        extractor = KnowledgeUnitExtractor()
        units = [
            KnowledgeUnit(claim="Same claim statement here.", evidence="Same evidence supports here.", source_doc="S"),
            KnowledgeUnit(claim="Same claim statement here.", evidence="Same evidence supports here.", source_doc="S"),
            KnowledgeUnit(claim="Different claim statement here.", evidence="Different evidence supports here.", source_doc="S"),
        ]
        enriched = extractor._enrich_units(units, "S", "T", ["A"])
        assert len(enriched) == 2  # deduped


class TestKUStore:
    @pytest.fixture
    def tmp_store(self, tmp_path: Path) -> KUStore:
        return KUStore(tmp_path / "kg")

    def test_save_and_load(self, tmp_store: KUStore) -> None:
        units = [
            KnowledgeUnit(claim="Claim one statement.", evidence="Evidence one supports.", source_doc="doc-a"),
            KnowledgeUnit(claim="Claim two statement.", evidence="Evidence two supports.", source_doc="doc-b"),
        ]
        added = tmp_store.save(units)
        assert added == 2
        loaded = tmp_store.load()
        assert len(loaded) == 2
        assert {u.claim for u in loaded} == {"Claim one statement.", "Claim two statement."}

    def test_dedupe_on_save(self, tmp_store: KUStore) -> None:
        u = KnowledgeUnit(claim="Claim one statement.", evidence="Evidence one supports.", source_doc="doc-a")
        assert tmp_store.save([u]) == 1
        assert tmp_store.save([u]) == 0  # dedupe

    def test_load_by_doc(self, tmp_store: KUStore) -> None:
        tmp_store.save([
            KnowledgeUnit(claim="Alpha claim statement.", evidence="Alpha evidence supports.", source_doc="doc-1"),
            KnowledgeUnit(claim="Beta claim statement.", evidence="Beta evidence supports.", source_doc="doc-2"),
        ])
        assert len(tmp_store.load_by_doc("doc-1")) == 1
        assert tmp_store.load_by_doc("doc-1")[0].claim == "Alpha claim statement."

    def test_load_by_entity(self, tmp_store: KUStore) -> None:
        tmp_store.save([
            KnowledgeUnit(claim="Alpha claim statement.", evidence="Alpha evidence supports.", source_doc="d1", entities=["BERT"]),
            KnowledgeUnit(claim="Beta claim statement.", evidence="Beta evidence supports.", source_doc="d2", entities=["GPT"]),
        ])
        assert len(tmp_store.load_by_entity("BERT")) == 1
        assert len(tmp_store.load_by_entity("gpt")) == 1  # case-insensitive

    def test_delete_by_doc(self, tmp_store: KUStore) -> None:
        tmp_store.save([
            KnowledgeUnit(claim="Alpha claim statement.", evidence="Alpha evidence supports.", source_doc="doc-1"),
            KnowledgeUnit(claim="Beta claim statement.", evidence="Beta evidence supports.", source_doc="doc-2"),
        ])
        removed = tmp_store.delete_by_doc("doc-1")
        assert removed == 1
        assert len(tmp_store.load()) == 1

    def test_compact(self, tmp_store: KUStore) -> None:
        u = KnowledgeUnit(claim="Compact claim statement.", evidence="Compact evidence supports.", source_doc="d")
        tmp_store.save([u, u, u])
        count = tmp_store.compact()
        assert count == 1
        assert len(tmp_store.load()) == 1
