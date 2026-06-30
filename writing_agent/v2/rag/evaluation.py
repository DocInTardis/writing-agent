"""Offline evaluation helpers for section and evidence retrieval."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path

from writing_agent.v2.rag.hierarchical_retriever import HierarchicalRetriever


@dataclass(frozen=True)
class RetrievalEvalCase:
    query: str
    expected_paper_ids: set[str] = field(default_factory=set)
    expected_section_ids: set[str] = field(default_factory=set)
    expected_evidence_ids: set[str] = field(default_factory=set)


def evaluate_cases(
    *,
    rag_dir: Path,
    cases: list[RetrievalEvalCase],
    top_k: int = 6,
    use_embeddings: bool = True,
) -> dict[str, float]:
    if not cases:
        return {
            "cases": 0.0,
            "section_recall_at_k": 0.0,
            "evidence_precision_at_k": 0.0,
            "mrr": 0.0,
            "ndcg_at_k": 0.0,
        }
    retriever = HierarchicalRetriever(rag_dir)
    recalls: list[float] = []
    precisions: list[float] = []
    reciprocal_ranks: list[float] = []
    ndcgs: list[float] = []
    for case in cases:
        result = retriever.retrieve(
            query=case.query,
            section_top_k=top_k,
            evidence_top_k=top_k,
            use_embeddings=use_embeddings,
        )
        section_ids = [row.section.section_id for row in result.section_hits]
        paper_ids = [row.source.paper_id for row in result.section_hits]
        evidence_ids = [row.evidence.evidence_id for row in result.evidence_hits]
        expected_sections = case.expected_section_ids
        expected_papers = case.expected_paper_ids
        if expected_sections:
            recalls.append(len(set(section_ids) & expected_sections) / len(expected_sections))
            relevant_section_positions = [
                index for index, value in enumerate(section_ids, start=1) if value in expected_sections
            ]
        elif expected_papers:
            recalls.append(len(set(paper_ids) & expected_papers) / len(expected_papers))
            relevant_section_positions = [
                index for index, value in enumerate(paper_ids, start=1) if value in expected_papers
            ]
        else:
            recalls.append(1.0)
            relevant_section_positions = []

        if case.expected_evidence_ids:
            precisions.append(
                len(set(evidence_ids) & case.expected_evidence_ids) / max(1, len(evidence_ids))
            )
            relevant_positions = [
                index for index, value in enumerate(evidence_ids, start=1) if value in case.expected_evidence_ids
            ]
        else:
            precisions.append(1.0)
            relevant_positions = relevant_section_positions
        reciprocal_ranks.append(1.0 / relevant_positions[0] if relevant_positions else 0.0)
        ndcgs.append(_ndcg(relevant_positions, top_k=top_k))
    return {
        "cases": float(len(cases)),
        "section_recall_at_k": _mean(recalls),
        "evidence_precision_at_k": _mean(precisions),
        "mrr": _mean(reciprocal_ranks),
        "ndcg_at_k": _mean(ndcgs),
    }


def _ndcg(relevant_positions: list[int], *, top_k: int) -> float:
    gains = sum(1.0 / math.log2(position + 1) for position in relevant_positions if position <= top_k)
    ideal_count = min(len(relevant_positions), top_k)
    ideal = sum(1.0 / math.log2(position + 1) for position in range(1, ideal_count + 1))
    return gains / ideal if ideal > 0 else 0.0


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
