"""Two-stage section and evidence retrieval."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from writing_agent.v2.rag.index import _cosine_sim, _decode_vec, _embed_model_name, _embed_query, _keyword_score
from writing_agent.v2.rag.structured_records import EvidenceRecord, SectionRecord, SourceRecord
from writing_agent.v2.rag.structured_store import StructuredRagStore


@dataclass(frozen=True)
class SectionHit:
    section: SectionRecord
    source: SourceRecord
    score: float


@dataclass(frozen=True)
class EvidenceHit:
    evidence: EvidenceRecord
    section: SectionRecord
    source: SourceRecord
    score: float


@dataclass(frozen=True)
class HierarchicalRetrieveResult:
    section_hits: list[SectionHit]
    evidence_hits: list[EvidenceHit]


class HierarchicalRetriever:
    def __init__(self, rag_dir: Path) -> None:
        self.store = StructuredRagStore(rag_dir)

    def retrieve(
        self,
        *,
        query: str,
        section_top_k: int = 6,
        evidence_top_k: int = 8,
        per_paper: int = 2,
        use_embeddings: bool = True,
    ) -> HierarchicalRetrieveResult:
        q = str(query or "").strip()
        if not q:
            return HierarchicalRetrieveResult(section_hits=[], evidence_hits=[])
        ready_sources = {row.paper_id: row for row in self.store.list_canonical_sources(status="ready")}
        sections = [row for row in self.store.list_sections() if row.paper_id in ready_sources]
        if not sections:
            return HierarchicalRetrieveResult(section_hits=[], evidence_hits=[])

        query_vector = _query_vector(q) if use_embeddings else []
        scored_sections: list[SectionHit] = []
        for section in sections:
            source = ready_sources[section.paper_id]
            keyword = _normalized_keyword(q, section.retrieval_text(), section.title)
            vector = _record_similarity(
                query_vector,
                section.embedding_b64,
                section.embedding_dim,
                section.embedding_codec,
                section.embedding_scale,
            )
            semantic = vector if query_vector and section.embedding_b64 else keyword
            score = (
                0.60 * semantic
                + 0.25 * keyword
                + 0.10 * _metadata_quality(source)
                + 0.05 * _authority_score(source)
            )
            if score > 0:
                scored_sections.append(SectionHit(section=section, source=source, score=score))
        scored_sections.sort(key=lambda row: row.score, reverse=True)
        section_hits = _limit_sections(scored_sections, top_k=section_top_k, per_paper=per_paper)

        section_map = {row.section.section_id: row for row in section_hits}
        evidence_rows = self.store.list_evidence(section_ids=set(section_map))
        scored_evidence: list[EvidenceHit] = []
        for evidence in evidence_rows:
            section_hit = section_map.get(evidence.section_id)
            if section_hit is None:
                continue
            keyword = _normalized_keyword(q, evidence.retrieval_text(), section_hit.section.title)
            vector = _record_similarity(
                query_vector,
                evidence.embedding_b64,
                evidence.embedding_dim,
                evidence.embedding_codec,
                evidence.embedding_scale,
            )
            semantic = vector if query_vector and evidence.embedding_b64 else keyword
            score = 0.55 * semantic + 0.25 * keyword + 0.15 * section_hit.score + 0.05 * evidence.confidence
            if score > 0:
                scored_evidence.append(
                    EvidenceHit(
                        evidence=evidence,
                        section=section_hit.section,
                        source=section_hit.source,
                        score=score,
                    )
                )
        scored_evidence.sort(key=lambda row: row.score, reverse=True)
        return HierarchicalRetrieveResult(
            section_hits=section_hits,
            evidence_hits=_dedupe_evidence(scored_evidence, top_k=evidence_top_k, per_paper=per_paper),
        )


def format_hierarchical_context(result: HierarchicalRetrieveResult, *, max_chars: int = 2500) -> str:
    limit = max(400, int(max_chars))
    blocks: list[str] = []
    used = 0
    evidence_by_section: dict[str, list[EvidenceHit]] = {}
    for hit in result.evidence_hits:
        evidence_by_section.setdefault(hit.section.section_id, []).append(hit)
    for section_hit in result.section_hits:
        section = section_hit.section
        source = section_hit.source
        lines = [
            (
                f"[paper_id={source.paper_id} section_id={section.section_id}] "
                f"{source.title} > {section.title} [level={source.data_level}]"
            ),
        ]
        if source.abs_url:
            lines.append(source.abs_url)
        lines.append(section.summary)
        for evidence_hit in evidence_by_section.get(section.section_id, []):
            evidence = evidence_hit.evidence
            location = f" p.{evidence.page}" if evidence.page else ""
            lines.append(
                f"[evidence_id={evidence.evidence_id}{location} type={evidence.evidence_type}] "
                f"{evidence.evidence_text}"
            )
        block = "\n".join(line for line in lines if line).strip()
        if not block:
            continue
        if used + len(block) + 2 > limit:
            break
        blocks.append(block)
        used += len(block) + 2
    return "\n\n".join(blocks).strip()


def _query_vector(query: str) -> list[float]:
    try:
        return _embed_query(query, embed_model=_embed_model_name())
    except Exception:
        return []


def _record_similarity(
    query_vector: list[float],
    embedding_b64: str,
    dim: int,
    codec: str,
    scale: float,
) -> float:
    if not query_vector or not embedding_b64 or not dim:
        return 0.0
    value = _cosine_sim(
        query_vector,
        _decode_vec(embedding_b64, dim, codec=codec, scale=scale),
    )
    return max(0.0, min(1.0, (value + 1.0) / 2.0))


def _normalized_keyword(query: str, text: str, title: str) -> float:
    raw = max(0.0, _keyword_score(query, text, title))
    return 1.0 - math.exp(-raw / 8.0)


def _metadata_quality(source: SourceRecord) -> float:
    return {"L2": 1.0, "L1": 0.65, "L0": 0.3}.get(source.data_level, 0.2)


def _authority_score(source: SourceRecord) -> float:
    url = f"{source.abs_url} {source.pdf_url}".lower()
    authority = 0.8 if any(host in url for host in ("doi.org", "arxiv.org", "openalex.org")) else 0.45
    if source.year:
        current_year = datetime.now(timezone.utc).year
        age = max(0, current_year - source.year)
        authority = min(1.0, authority + max(0.0, 0.2 - age * 0.01))
    return authority


def _limit_sections(rows: list[SectionHit], *, top_k: int, per_paper: int) -> list[SectionHit]:
    out: list[SectionHit] = []
    counts: dict[str, int] = {}
    for row in rows:
        if len(out) >= max(1, int(top_k)):
            break
        count = counts.get(row.source.paper_id, 0)
        if count >= max(1, int(per_paper)):
            continue
        counts[row.source.paper_id] = count + 1
        out.append(row)
    return out


def _dedupe_evidence(rows: list[EvidenceHit], *, top_k: int, per_paper: int) -> list[EvidenceHit]:
    out: list[EvidenceHit] = []
    counts: dict[str, int] = {}
    seen: set[str] = set()
    for row in rows:
        normalized = re.sub(r"\s+", " ", row.evidence.evidence_text).strip().lower()
        key = normalized[:240]
        if not key or key in seen:
            continue
        count = counts.get(row.source.paper_id, 0)
        if count >= max(1, int(per_paper)):
            continue
        seen.add(key)
        counts[row.source.paper_id] = count + 1
        out.append(row)
        if len(out) >= max(1, int(top_k)):
            break
    return out
