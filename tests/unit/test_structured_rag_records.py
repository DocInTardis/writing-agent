from __future__ import annotations

from dataclasses import replace

from writing_agent.v2.rag.audit_trail import AuditTrailStore, RetrievalTrail
from writing_agent.v2.rag.citation_registry import CitationRegistry
from writing_agent.v2.rag.evaluation import RetrievalEvalCase, evaluate_cases
from writing_agent.v2.rag.hierarchical_retriever import HierarchicalRetriever, format_hierarchical_context
from writing_agent.v2.rag.preprocess import DocumentPreprocessor
from writing_agent.v2.rag.retrieve import retrieve_context
from writing_agent.v2.rag.sectioning import build_structured_records, parse_document_sections
from writing_agent.v2.rag.structured_records import SourceRecord
from writing_agent.v2.rag.structured_store import StructuredRagStore
from writing_agent.v2.rag.user_library import UserLibrary


def test_section_parser_preserves_hierarchy_and_exact_evidence() -> None:
    text = (
        "# Introduction\n"
        "This paper studies retrieval quality.\n"
        "## Method\n"
        "We evaluated 120 samples with a hybrid retrieval model.\n"
        "## Results\n"
        "The model improved recall by 20 percent.\n"
    )
    parsed = parse_document_sections(text=text)
    sections, evidence = build_structured_records(paper_id="paper-1", sections=parsed)

    assert [row.title for row in sections] == ["Introduction", "Method", "Results"]
    assert sections[1].parent_section_id == sections[0].section_id
    assert evidence
    assert all(row.evidence_text in text for row in evidence)
    assert all(row.source_start is not None and row.source_end is not None for row in evidence)


def test_section_parser_keeps_table_figure_and_formula_evidence_types() -> None:
    text = (
        "# Results\n"
        "Table 1 reports accuracy for all models.\n"
        "Figure 2 shows the retrieval workflow.\n"
        "The score is defined as R = relevant / retrieved.\n"
    )
    parsed = parse_document_sections(text=text)
    _sections, evidence = build_structured_records(paper_id="paper-1", sections=parsed)

    assert {"table", "figure", "formula"}.issubset({row.evidence_type for row in evidence})


def test_structured_store_replaces_one_document_without_touching_others(tmp_path) -> None:
    store = StructuredRagStore(tmp_path)
    preprocessor = DocumentPreprocessor(tmp_path)
    preprocessor.process_text(
        paper_id="paper-1",
        title="First",
        text="# Results\nRecall improved by 20 percent.",
        embed=False,
    )
    preprocessor.process_text(
        paper_id="paper-2",
        title="Second",
        text="# Results\nLatency decreased by 10 ms.",
        embed=False,
    )

    first_before = store.list_sections(paper_id="paper-1")
    preprocessor.process_text(
        paper_id="paper-1",
        title="First",
        text="# Results\nRecall improved by 30 percent.",
        embed=False,
    )

    assert store.get_source("paper-1").processing_status == "ready"
    assert store.list_sections(paper_id="paper-2")
    assert store.list_sections(paper_id="paper-1") != first_before


def test_preprocessing_is_idempotent_for_same_content(tmp_path) -> None:
    preprocessor = DocumentPreprocessor(tmp_path)
    first = preprocessor.process_text(
        paper_id="paper-1",
        title="Study",
        text="# Method\nA deterministic method was evaluated.",
        embed=False,
    )
    sections_before = StructuredRagStore(tmp_path).list_sections(paper_id="paper-1")
    second = preprocessor.process_text(
        paper_id="paper-1",
        title="Study",
        text="# Method\nA deterministic method was evaluated.",
        embed=False,
    )

    assert first == second
    assert StructuredRagStore(tmp_path).list_sections(paper_id="paper-1") == sections_before


def test_hierarchical_retrieval_limits_evidence_to_selected_sections(tmp_path) -> None:
    preprocessor = DocumentPreprocessor(tmp_path)
    preprocessor.process_text(
        paper_id="paper-1",
        title="Retrieval Study",
        text=(
            "# Method\nThe experiment used a transformer encoder.\n"
            "# Results\nThe hybrid retriever improved recall by 20 percent.\n"
            "# Limitations\nThe evaluation used only one dataset.\n"
        ),
        embed=False,
    )

    result = HierarchicalRetriever(tmp_path).retrieve(
        query="hybrid retriever recall",
        section_top_k=1,
        evidence_top_k=4,
        use_embeddings=False,
    )

    assert len(result.section_hits) == 1
    selected = {row.section.section_id for row in result.section_hits}
    assert result.evidence_hits
    assert all(row.section.section_id in selected for row in result.evidence_hits)
    context = format_hierarchical_context(result)
    assert "paper_id=paper-1" in context
    assert "evidence_id=" in context


def test_citation_registry_only_accepts_evidence_from_same_paper(tmp_path) -> None:
    preprocessor = DocumentPreprocessor(tmp_path)
    preprocessor.process_text(
        paper_id="paper-1",
        title="Retrieval Study",
        text="# Results\nThe hybrid retriever improved recall by 20 percent.",
        embed=False,
    )
    store = StructuredRagStore(tmp_path)
    evidence = store.list_evidence(paper_id="paper-1")[0]
    registry = CitationRegistry(tmp_path)

    citation = registry.register(
        document_id="doc-1",
        generated_section_id="results",
        claim_text="The hybrid retriever improved recall by 20 percent.",
        paper_id="paper-1",
        evidence_ids=[evidence.evidence_id],
    )

    assert citation.verification_status == "supported"
    assert [row.paper_id for row in registry.references_for_document("doc-1")] == ["paper-1"]


def test_citation_registry_derives_references_from_supported_generated_text(tmp_path) -> None:
    preprocessor = DocumentPreprocessor(tmp_path)
    preprocessor.process_text(
        paper_id="paper-1",
        title="Retrieval Study",
        text="# Results\nThe hybrid retriever improved recall by 20 percent.",
        embed=False,
    )
    store = StructuredRagStore(tmp_path)
    evidence = store.list_evidence(paper_id="paper-1")[0]
    registry = CitationRegistry(tmp_path)

    citations = registry.register_supported_text(
        document_id="doc-1",
        generated_section_id="results",
        text="The hybrid retriever improved recall by 20 percent.",
        evidence_ids=[evidence.evidence_id],
    )

    assert len(citations) == 1
    assert registry.references_as_dicts("doc-1")[0]["id"] == "paper-1"


def test_citation_registry_rejects_numeric_drift_from_reference_list(tmp_path) -> None:
    preprocessor = DocumentPreprocessor(tmp_path)
    preprocessor.process_text(
        paper_id="paper-1",
        title="Retrieval Study",
        text="# Results\nThe hybrid retriever improved recall by 20 percent.",
        embed=False,
    )
    evidence = StructuredRagStore(tmp_path).list_evidence(paper_id="paper-1")[0]
    registry = CitationRegistry(tmp_path)

    citations = registry.register_supported_text(
        document_id="doc-1",
        generated_section_id="results",
        text="The hybrid retriever improved recall by 30 percent.",
        evidence_ids=[evidence.evidence_id],
    )

    assert len(citations) == 1
    assert citations[0].verification_status == "needs_review"
    assert registry.references_as_dicts("doc-1") == []


def test_store_filters_out_non_ready_sources_from_retrieval(tmp_path) -> None:
    preprocessor = DocumentPreprocessor(tmp_path)
    preprocessor.process_text(
        paper_id="paper-1",
        title="Ready",
        text="# Results\nRecall improved by 20 percent.",
        embed=False,
    )
    store = StructuredRagStore(tmp_path)
    source = store.get_source("paper-1")
    assert source is not None
    store.upsert_source(replace(source, processing_status="failed"))

    result = HierarchicalRetriever(tmp_path).retrieve(query="recall", use_embeddings=False)
    assert result.section_hits == []
    assert result.evidence_hits == []


def test_source_registry_deduplicates_same_title_and_year(tmp_path) -> None:
    store = StructuredRagStore(tmp_path)
    store.upsert_source(
        SourceRecord(
            paper_id="openalex:1",
            title="A Retrieval Study",
            year=2025,
            processing_status="ready",
            data_level="L1",
        )
    )
    store.upsert_source(
        SourceRecord(
            paper_id="crossref:2",
            title="A Retrieval Study",
            year=2025,
            processing_status="ready",
            data_level="L2",
        )
    )

    canonical = store.list_canonical_sources(status="ready")

    assert len(canonical) == 1
    assert canonical[0].paper_id == "crossref:2"


def test_audit_trail_jsonl_roundtrip(tmp_path) -> None:
    store = AuditTrailStore(tmp_path)
    trail = RetrievalTrail(
        query="hybrid retrieval",
        expanded_queries=["hybrid retrieval", "retrieval"],
        section_hits=[{"section_id": "sec-1"}],
        evidence_hits=[{"evidence_id": "ev-1"}],
    )
    store.record(trail)

    loaded = store.load()

    assert len(loaded) == 1
    assert loaded[0].trail_id == trail.trail_id
    assert loaded[0].evidence_hits == [{"evidence_id": "ev-1"}]


def test_retrieval_evaluation_reports_baseline_metrics(tmp_path) -> None:
    preprocessor = DocumentPreprocessor(tmp_path)
    preprocessor.process_text(
        paper_id="paper-1",
        title="Retrieval Study",
        text="# Results\nThe hybrid retriever improved recall by 20 percent.",
        embed=False,
    )
    evidence = StructuredRagStore(tmp_path).list_evidence(paper_id="paper-1")[0]
    metrics = evaluate_cases(
        rag_dir=tmp_path,
        cases=[
            RetrievalEvalCase(
                query="hybrid retriever recall",
                expected_paper_ids={"paper-1"},
                expected_evidence_ids={evidence.evidence_id},
            )
        ],
        top_k=3,
        use_embeddings=False,
    )

    assert metrics["section_recall_at_k"] == 1.0
    assert metrics["evidence_precision_at_k"] == 1.0
    assert metrics["mrr"] == 1.0


def test_retrieve_context_prefers_ready_structured_records_and_writes_audit(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("WRITING_AGENT_RAG_AUTO_FETCH_ENABLED", "0")
    monkeypatch.setenv("WRITING_AGENT_RAG_EXPAND_ENABLED", "0")
    monkeypatch.setenv("WRITING_AGENT_RAG_ONLINE_FILL_ENABLED", "0")
    monkeypatch.setenv("WRITING_AGENT_RAG_USE_EMBEDDINGS", "0")
    monkeypatch.setenv("WRITING_AGENT_RAG_AUDIT_ENABLED", "1")
    preprocessor = DocumentPreprocessor(tmp_path)
    preprocessor.process_text(
        paper_id="paper-1",
        title="Retrieval Study",
        text="# Results\nThe hybrid retriever improved recall by 20 percent.",
        embed=False,
    )

    result = retrieve_context(
        rag_dir=tmp_path,
        query="hybrid retriever recall",
        top_k=3,
        use_kg=False,
    )

    assert result.section_hits
    assert result.evidence_hits
    assert result.chunk_hits == []
    assert result.trail_id
    trails = AuditTrailStore(tmp_path / "audit").load()
    assert trails[-1].trail_id == result.trail_id


def test_user_library_trash_removes_structured_index(tmp_path) -> None:
    class _Index:
        def __init__(self, rag_dir):
            self.rag_dir = rag_dir
            self.deleted: list[str] = []

        def delete_by_paper_id(self, paper_id):
            self.deleted.append(paper_id)

    rag_dir = tmp_path / "rag"
    index = _Index(rag_dir)
    library = UserLibrary(tmp_path / "library", index)
    item = library.put_text(
        text="# Results\nRecall improved by 20 percent.",
        title="Draft",
        source="user",
        status="pending",
    )
    paper_id = f"user:{item.doc_id}"
    DocumentPreprocessor(rag_dir).process_text(
        paper_id=paper_id,
        title="Draft",
        text="# Results\nRecall improved by 20 percent.",
        embed=False,
    )
    assert StructuredRagStore(rag_dir).get_source(paper_id) is not None

    library.trash(item.doc_id)

    assert StructuredRagStore(rag_dir).get_source(paper_id) is None
    assert paper_id in index.deleted
