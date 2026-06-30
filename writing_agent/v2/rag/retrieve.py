"""Retrieve module.

This module belongs to `writing_agent.v2.rag` in the writing-agent codebase.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

from writing_agent.v2.rag.hierarchical_retriever import (
    EvidenceHit,
    HierarchicalRetriever,
    HierarchicalRetrieveResult,
    SectionHit,
    format_hierarchical_context,
)
from writing_agent.v2.rag.index import RagChunkHit, RagIndex
from writing_agent.v2.rag.openalex import OpenAlexWork, search_openalex
from writing_agent.v2.rag.query_expand import expand_queries
from writing_agent.v2.rag.re_rank import RerankItem, rerank_texts
from writing_agent.v2.rag.search import RagSearchHit, build_rag_context, search_papers
from writing_agent.v2.rag.source_quality import score_source
from writing_agent.v2.rag.store import RagStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetrieveResult:
    context: str
    chunk_hits: list[RagChunkHit]
    paper_hits: list[RagSearchHit]
    online_hits: int = 0
    kg_hits: list = None  # type: ignore[assignment]  # list[KnowledgeUnit] when KG active
    section_hits: list[SectionHit] = None  # type: ignore[assignment]
    evidence_hits: list[EvidenceHit] = None  # type: ignore[assignment]
    trail_id: str = ""

    def __post_init__(self) -> None:
        # dataclass frozen with mutable default workaround
        object.__setattr__(self, "kg_hits", self.kg_hits or [])
        object.__setattr__(self, "section_hits", self.section_hits or [])
        object.__setattr__(self, "evidence_hits", self.evidence_hits or [])


_ONLINE_TOPUP_DISABLED_UNTIL = 0.0


def retrieve_context(
    *,
    rag_dir: Path,
    query: str,
    top_k: int = 6,
    per_paper: int = 2,
    max_chars: int = 2500,
    use_kg: bool = True,
) -> RetrieveResult:
    rag_dir = Path(rag_dir)
    q = (query or "").strip()
    if not q:
        return RetrieveResult(context="", chunk_hits=[], paper_hits=[])

    _schedule_auto_fetch(rag_dir=rag_dir, query=q)
    _schedule_failed_preprocessing(rag_dir=rag_dir)

    index = RagIndex(rag_dir)
    alpha = float(os.environ.get("WRITING_AGENT_RAG_ALPHA", "0.75"))
    use_emb_raw = os.environ.get("WRITING_AGENT_RAG_USE_EMBEDDINGS", "1").strip().lower()
    use_embeddings = use_emb_raw in {"1", "true", "yes", "on"}

    queries = expand_queries(q, max_queries=int(os.environ.get("WRITING_AGENT_RAG_MULTI_QUERY", "4") or 4))
    if not queries:
        queries = [q]

    hierarchical = HierarchicalRetrieveResult(section_hits=[], evidence_hits=[])
    if _env_on("WRITING_AGENT_RAG_HIERARCHICAL_ENABLED", default=True):
        try:
            hierarchical = _search_hierarchical_multi_query(
                rag_dir=rag_dir,
                queries=queries,
                top_k=top_k,
                per_paper=per_paper,
                use_embeddings=use_embeddings,
            )
        except Exception as exc:
            logger.debug("Hierarchical retrieval skipped: %s", exc)

    chunk_hits: list[RagChunkHit] = []
    if index.index_path.exists():
        try:
            chunk_hits = _search_chunks_multi_query(
                index=index,
                queries=queries,
                top_k=top_k,
                per_paper=per_paper,
                use_embeddings=use_embeddings,
                alpha=alpha,
            )
        except Exception:
            chunk_hits = []

    kg_hits: list = []
    if use_kg:
        try:
            kg_hits = _kg_retrieve(
                rag_dir=rag_dir,
                query=q,
                top_k=top_k,
            )
        except Exception as exc:
            logger.debug("KG retrieval skipped: %s", exc)

    hierarchical_context = format_hierarchical_context(hierarchical, max_chars=max_chars)
    if hierarchical_context:
        trail_id = _record_retrieval_trail(
            rag_dir=rag_dir,
            query=q,
            queries=queries,
            context=hierarchical_context,
            section_hits=hierarchical.section_hits,
            evidence_hits=hierarchical.evidence_hits,
            kg_hits=kg_hits,
        )
        return RetrieveResult(
            context=hierarchical_context,
            chunk_hits=[],
            paper_hits=[],
            online_hits=0,
            kg_hits=kg_hits,
            section_hits=hierarchical.section_hits,
            evidence_hits=hierarchical.evidence_hits,
            trail_id=trail_id,
        )

    if chunk_hits:
        online_hits = _online_topup_hits(
            query=q,
            existing_hits=chunk_hits,
            top_k=top_k,
            per_paper=per_paper,
        )
        if online_hits:
            chunk_hits = _merge_chunk_hits(
                base=chunk_hits,
                extra=online_hits,
                top_k=top_k,
                per_paper=per_paper,
                query=queries[0],
            )
        context = _format_chunk_context(chunk_hits=chunk_hits, max_chars=max_chars)
        trail_id = _record_retrieval_trail(
            rag_dir=rag_dir,
            query=q,
            queries=queries,
            context=context,
            chunk_hits=chunk_hits,
            kg_hits=kg_hits,
            online_hits=len(online_hits),
        )
        return RetrieveResult(
            context=context,
            chunk_hits=chunk_hits,
            paper_hits=[],
            online_hits=len(online_hits),
            kg_hits=kg_hits,
            trail_id=trail_id,
        )

    online_hits = _online_topup_hits(
        query=q,
        existing_hits=[],
        top_k=top_k,
        per_paper=per_paper,
    )
    if online_hits:
        online_merged = _merge_chunk_hits(
            base=[],
            extra=online_hits,
            top_k=top_k,
            per_paper=per_paper,
            query=queries[0],
        )
        context = _format_chunk_context(chunk_hits=online_merged, max_chars=max_chars)
        if context.strip():
            trail_id = _record_retrieval_trail(
                rag_dir=rag_dir,
                query=q,
                queries=queries,
                context=context,
                chunk_hits=online_merged,
                kg_hits=kg_hits,
                online_hits=len(online_hits),
            )
            return RetrieveResult(
                context=context,
                chunk_hits=online_merged,
                paper_hits=[],
                online_hits=len(online_hits),
                kg_hits=kg_hits,
                trail_id=trail_id,
            )

    rag = RagStore(rag_dir)
    papers = rag.list_papers()

    if len(papers) < 10:
        _schedule_related_expand(rag_dir=rag_dir, paper_ids=[p.paper_id for p in papers])

    paper_hits = _search_papers_multi_query(papers=papers, queries=queries, top_k=max(1, min(20, top_k)))
    context = build_rag_context(hits=paper_hits[: max(1, min(8, top_k))], max_chars=max_chars)
    if not context.strip():
        context = "[NO_EVIDENCE] Retrieval evidence is insufficient. Please provide additional trustworthy sources."
    trail_id = _record_retrieval_trail(
        rag_dir=rag_dir,
        query=q,
        queries=queries,
        context=context,
        kg_hits=kg_hits,
        paper_hits=paper_hits,
    )
    return RetrieveResult(
        context=context,
        chunk_hits=[],
        paper_hits=paper_hits,
        online_hits=0,
        kg_hits=kg_hits,
        trail_id=trail_id,
    )


def _search_chunks_multi_query(
    *,
    index: RagIndex,
    queries: list[str],
    top_k: int,
    per_paper: int,
    use_embeddings: bool,
    alpha: float,
) -> list[RagChunkHit]:
    merged: dict[str, RagChunkHit] = {}
    for q in queries:
        rows = index.search(query=q, top_k=top_k, per_paper=per_paper, use_embeddings=use_embeddings, alpha=alpha)
        for hit in rows:
            prev = merged.get(hit.chunk_id)
            if prev is None or float(hit.score) > float(prev.score):
                merged[hit.chunk_id] = hit

    rerank_input = [RerankItem(text=h.text, score=float(h.score)) for h in merged.values()]
    reranked = rerank_texts(query=queries[0], items=rerank_input, top_k=top_k)

    score_map = {r.text: r.score for r in reranked}
    ranked_hits = list(merged.values())
    ranked_hits.sort(key=lambda h: score_map.get(h.text, float(h.score)), reverse=True)

    out: list[RagChunkHit] = []
    per: dict[str, int] = {}
    for hit in ranked_hits:
        if len(out) >= top_k:
            break
        n = per.get(hit.paper_id, 0)
        if n >= per_paper:
            continue
        per[hit.paper_id] = n + 1
        out.append(hit)
    return out


def _search_papers_multi_query(*, papers, queries: list[str], top_k: int) -> list[RagSearchHit]:
    scored: dict[str, RagSearchHit] = {}
    for q in queries:
        hits = search_papers(papers=papers, query=q, top_k=top_k)
        for row in hits:
            key = str(row.paper_id or row.title or "")
            prev = scored.get(key)
            if prev is None or float(row.score) > float(prev.score):
                scored[key] = row
    rows = list(scored.values())
    rows.sort(key=lambda x: float(x.score), reverse=True)
    return rows[:top_k]


def _format_chunk_context(*, chunk_hits: list[RagChunkHit], max_chars: int) -> str:
    max_chars = int(max(400, min(20000, max_chars)))
    out: list[str] = []
    used = 0
    seen_titles: set[str] = set()
    for h in chunk_hits:
        quality = score_source(url=h.abs_url)
        conflict = ""
        title_key = str(h.title or "").strip().lower()
        if title_key in seen_titles:
            conflict = " [near-duplicate]"
        seen_titles.add(title_key)
        head = f"[{h.paper_id}] {h.title} ({h.kind}) [quality:{quality.level}] {h.abs_url}{conflict}".strip()
        body = (h.text or "").strip()
        block = (head + "\n" + body).strip()
        if not block:
            continue
        if used + len(block) + 2 > max_chars:
            break
        out.append(block)
        used += len(block) + 2
    if not out:
        return "[NO_EVIDENCE] Retrieval evidence is insufficient. Please provide additional trustworthy sources."
    return "\n\n".join(out).strip()


def _online_topup_hits(
    *,
    query: str,
    existing_hits: list[RagChunkHit],
    top_k: int,
    per_paper: int,
) -> list[RagChunkHit]:
    global _ONLINE_TOPUP_DISABLED_UNTIL
    if not _env_on("WRITING_AGENT_RAG_ONLINE_FILL_ENABLED", default=False):
        return []
    now = time.time()
    if now < float(_ONLINE_TOPUP_DISABLED_UNTIL or 0.0):
        return []
    min_local_hits = _env_int("WRITING_AGENT_RAG_ONLINE_FILL_MIN_LOCAL_HITS", 3, minimum=0, maximum=30)
    if len(existing_hits or []) >= min_local_hits:
        return []
    max_online = _env_int("WRITING_AGENT_RAG_ONLINE_FILL_MAX_RESULTS", max(4, top_k), minimum=1, maximum=30)
    timeout_s = _env_float("WRITING_AGENT_RAG_ONLINE_TIMEOUT_S", 20.0, minimum=3.0, maximum=90.0)
    seed = _openalex_query_seed(query)
    if not seed:
        return []
    try:
        result = search_openalex(query=seed, max_results=max_online, timeout_s=timeout_s)
    except Exception as exc:
        msg = str(exc or "")
        if "429" in msg or "Too Many Requests" in msg:
            cooldown_s = _env_float("WRITING_AGENT_RAG_ONLINE_429_COOLDOWN_S", 300.0, minimum=10.0, maximum=3600.0)
            _ONLINE_TOPUP_DISABLED_UNTIL = now + cooldown_s
        return []
    if not result.works:
        return []
    return _openalex_works_to_chunk_hits(result.works, top_k=max_online, per_paper=per_paper)


def _openalex_works_to_chunk_hits(works: list[OpenAlexWork], *, top_k: int, per_paper: int) -> list[RagChunkHit]:
    if not works:
        return []
    per_counter: dict[str, int] = {}
    hits: list[RagChunkHit] = []
    for idx, work in enumerate(works, start=1):
        if len(hits) >= max(1, int(top_k)):
            break
        if not isinstance(work, OpenAlexWork):
            continue
        paper_id = str(work.paper_id or "").strip()
        if not paper_id:
            continue
        c = per_counter.get(paper_id, 0)
        if c >= max(1, int(per_paper)):
            continue
        text = _normalize_online_text(work)
        if len(text) < 32:
            continue
        per_counter[paper_id] = c + 1
        score = 0.35 + max(0.0, (float(max(1, int(top_k))) - float(idx - 1)) / float(max(1, int(top_k)))) * 0.1
        score += _authority_bonus(work)
        hits.append(
            RagChunkHit(
                chunk_id=f"{paper_id}:online:{idx:03d}",
                paper_id=paper_id,
                title=str(work.title or "").strip(),
                abs_url=str(work.abs_url or work.pdf_url or "").strip(),
                kind="openalex_online",
                score=float(score),
                text=text,
            )
        )
    return hits


def _normalize_online_text(work: OpenAlexWork) -> str:
    title = str(work.title or "").strip()
    summary = str(work.summary or "").strip()
    if summary:
        return f"{title}\n{summary}".strip()
    return title


def _authority_bonus(work: OpenAlexWork) -> float:
    cited = max(0, int(getattr(work, "cited_by_count", 0) or 0))
    year = max(0, int(getattr(work, "publication_year", 0) or 0))
    cited_bonus = min(0.2, float(cited) / 1000.0)
    recency_bonus = 0.0
    if year >= 2024:
        recency_bonus = 0.08
    elif year >= 2021:
        recency_bonus = 0.05
    elif year >= 2018:
        recency_bonus = 0.02
    return cited_bonus + recency_bonus


def _merge_chunk_hits(
    *,
    base: list[RagChunkHit],
    extra: list[RagChunkHit],
    top_k: int,
    per_paper: int,
    query: str,
) -> list[RagChunkHit]:
    merged: dict[str, RagChunkHit] = {}
    for hit in (base or []) + (extra or []):
        key = str(hit.chunk_id or "").strip()
        if not key:
            continue
        prev = merged.get(key)
        if prev is None or float(hit.score) > float(prev.score):
            merged[key] = hit
    if not merged:
        return []

    rerank_input = [RerankItem(text=h.text, score=float(h.score)) for h in merged.values()]
    reranked = rerank_texts(query=query, items=rerank_input, top_k=max(1, int(top_k)))
    score_map = {r.text: r.score for r in reranked}
    ranked = list(merged.values())
    ranked.sort(key=lambda h: score_map.get(h.text, float(h.score)), reverse=True)

    out: list[RagChunkHit] = []
    per: dict[str, int] = {}
    for hit in ranked:
        if len(out) >= max(1, int(top_k)):
            break
        cnt = per.get(hit.paper_id, 0)
        if cnt >= max(1, int(per_paper)):
            continue
        per[hit.paper_id] = cnt + 1
        out.append(hit)
    return out


def _openalex_query_seed(query: str) -> str:
    src = str(query or "").strip()
    if not src:
        return ""
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z][a-zA-Z0-9\-]{2,}", src.lower())
    if not tokens:
        return src
    english = [tok for tok in tokens if re.search(r"[a-z]", tok)]
    if english:
        return " ".join(english[:8])
    return " ".join(tokens[:8])


def _kg_retrieve(
    *,
    rag_dir: Path,
    query: str,
    top_k: int,
) -> list:
    """Optional KG-RAG layer: retrieve KnowledgeUnits via graph traversal."""
    try:
        from writing_agent.v2.rag.kg_retriever import KGRetriever
        from writing_agent.v2.rag.knowledge_unit import KUStore
    except Exception as exc:
        logger.debug("KG modules not available: %s", exc)
        return []

    kg_dir = rag_dir.parent / "kg"
    store = KUStore(kg_dir)
    graph_path = kg_dir / "knowledge_graph.json"
    retriever = KGRetriever(store=store, graph_path=graph_path)
    if not retriever.graph.entities:
        return []
    return retriever.retrieve(query=query, top_k=top_k)


def _search_hierarchical_multi_query(
    *,
    rag_dir: Path,
    queries: list[str],
    top_k: int,
    per_paper: int,
    use_embeddings: bool,
) -> HierarchicalRetrieveResult:
    retriever = HierarchicalRetriever(rag_dir)
    sections: dict[str, SectionHit] = {}
    evidence: dict[str, EvidenceHit] = {}
    for query in queries:
        result = retriever.retrieve(
            query=query,
            section_top_k=max(top_k, 4),
            evidence_top_k=max(top_k * 2, 6),
            per_paper=per_paper,
            use_embeddings=use_embeddings,
        )
        for hit in result.section_hits:
            current = sections.get(hit.section.section_id)
            if current is None or hit.score > current.score:
                sections[hit.section.section_id] = hit
        for hit in result.evidence_hits:
            current = evidence.get(hit.evidence.evidence_id)
            if current is None or hit.score > current.score:
                evidence[hit.evidence.evidence_id] = hit
    section_rows = sorted(sections.values(), key=lambda row: row.score, reverse=True)[: max(1, top_k)]
    selected_sections = {row.section.section_id for row in section_rows}
    evidence_rows = [
        row
        for row in sorted(evidence.values(), key=lambda item: item.score, reverse=True)
        if row.section.section_id in selected_sections
    ][: max(1, top_k * 2)]
    return HierarchicalRetrieveResult(section_hits=section_rows, evidence_hits=evidence_rows)


def _schedule_auto_fetch(*, rag_dir: Path, query: str) -> None:
    if not _env_on("WRITING_AGENT_RAG_AUTO_FETCH_ENABLED", default=True):
        return
    try:
        from writing_agent.v2.rag.auto_enhance import auto_fetch_on_empty
        from writing_agent.v2.rag.background_jobs import schedule_once

        key = f"auto-fetch:{Path(rag_dir).resolve()}:{_openalex_query_seed(query)}"
        schedule_once(key, lambda: auto_fetch_on_empty(rag_dir=rag_dir, query=query, min_papers=5))
    except Exception as exc:
        logger.debug("Auto-fetch scheduling skipped: %s", exc)


def _schedule_related_expand(*, rag_dir: Path, paper_ids: list[str]) -> None:
    if not paper_ids or not _env_on("WRITING_AGENT_RAG_EXPAND_ENABLED", default=True):
        return
    try:
        from writing_agent.v2.rag.auto_enhance import expand_with_related
        from writing_agent.v2.rag.background_jobs import schedule_once

        key = f"related-expand:{Path(rag_dir).resolve()}:{','.join(sorted(paper_ids)[:5])}"
        schedule_once(key, lambda: expand_with_related(rag_dir=rag_dir, paper_ids=paper_ids, max_expand=3))
    except Exception as exc:
        logger.debug("Related expansion scheduling skipped: %s", exc)


def _schedule_failed_preprocessing(*, rag_dir: Path) -> None:
    if not _env_on("WRITING_AGENT_RAG_RETRY_FAILED_ENABLED", default=True):
        return
    try:
        from writing_agent.v2.rag.background_jobs import schedule_once
        from writing_agent.v2.rag.preprocess import DocumentPreprocessor

        key = f"retry-preprocessing:{Path(rag_dir).resolve()}"
        schedule_once(
            key,
            lambda: DocumentPreprocessor(rag_dir).retry_due(embed=True, limit=5),
            group=f"paper-index-store:{Path(rag_dir).resolve()}",
        )
    except Exception as exc:
        logger.debug("Preprocessing retry scheduling skipped: %s", exc)


def _record_retrieval_trail(
    *,
    rag_dir: Path,
    query: str,
    queries: list[str],
    context: str,
    chunk_hits: list[RagChunkHit] | None = None,
    section_hits: list[SectionHit] | None = None,
    evidence_hits: list[EvidenceHit] | None = None,
    kg_hits: list | None = None,
    paper_hits: list[RagSearchHit] | None = None,
    online_hits: int = 0,
) -> str:
    if not _env_on("WRITING_AGENT_RAG_AUDIT_ENABLED", default=True):
        return ""
    try:
        from writing_agent.v2.rag.audit_trail import AuditTrailStore, RetrievalTrail

        trail = RetrievalTrail(
            query=query,
            expanded_queries=list(queries),
            chunk_hits=[
                {
                    "chunk_id": row.chunk_id,
                    "paper_id": row.paper_id,
                    "score": row.score,
                    "kind": row.kind,
                }
                for row in chunk_hits or []
            ],
            section_hits=[
                {
                    "section_id": row.section.section_id,
                    "paper_id": row.source.paper_id,
                    "score": row.score,
                }
                for row in section_hits or []
            ],
            evidence_hits=[
                {
                    "evidence_id": row.evidence.evidence_id,
                    "section_id": row.section.section_id,
                    "paper_id": row.source.paper_id,
                    "score": row.score,
                }
                for row in evidence_hits or []
            ],
            kg_hits=[
                {
                    "ku_id": str(getattr(row, "ku_id", "")),
                    "source_doc": str(getattr(row, "source_doc", "")),
                    "confidence": float(getattr(row, "confidence", 0.0) or 0.0),
                }
                for row in kg_hits or []
            ],
            context_preview=str(context or "")[:1000],
            local_chunks=len(chunk_hits or []),
            online_chunks=max(0, int(online_hits)),
            kg_units=len(kg_hits or []),
            papers=len({row.paper_id for row in paper_hits or []}),
        )
        AuditTrailStore(Path(rag_dir) / "audit").record(trail)
        return trail.trail_id
    except Exception as exc:
        logger.debug("Retrieval audit skipped: %s", exc)
        return ""


def _env_on(name: str, *, default: bool) -> bool:
    raw = str(os.environ.get(name, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = str(os.environ.get(name, str(default))).strip()
    try:
        value = int(raw)
    except Exception:
        value = int(default)
    return max(minimum, min(maximum, value))


def _env_float(name: str, default: float, *, minimum: float, maximum: float) -> float:
    raw = str(os.environ.get(name, str(default))).strip()
    try:
        value = float(raw)
    except Exception:
        value = float(default)
    return max(minimum, min(maximum, value))
