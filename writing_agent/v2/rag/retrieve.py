"""Retrieve module.

This module belongs to `writing_agent.v2.rag` in the writing-agent codebase.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from writing_agent.v2.rag.index import RagChunkHit, RagIndex
from writing_agent.v2.rag.query_expand import expand_queries
from writing_agent.v2.rag.re_rank import RerankItem, rerank_texts
from writing_agent.v2.rag.search import RagSearchHit, build_rag_context, search_papers
from writing_agent.v2.rag.source_quality import score_source
from writing_agent.v2.rag.store import RagStore


@dataclass(frozen=True)
class RetrieveResult:
    context: str
    chunk_hits: list[RagChunkHit]
    paper_hits: list[RagSearchHit]


def retrieve_context(
    *,
    rag_dir: Path,
    query: str,
    top_k: int = 6,
    per_paper: int = 2,
    max_chars: int = 2500,
) -> RetrieveResult:
    rag_dir = Path(rag_dir)
    q = (query or "").strip()
    if not q:
        return RetrieveResult(context="", chunk_hits=[], paper_hits=[])

    try:
        from writing_agent.v2.rag.auto_enhance import auto_fetch_on_empty

        auto_fetch_on_empty(rag_dir=rag_dir, query=q, min_papers=5)
    except Exception:
        pass

    index = RagIndex(rag_dir)
    alpha = float(os.environ.get("WRITING_AGENT_RAG_ALPHA", "0.75"))
    use_emb_raw = os.environ.get("WRITING_AGENT_RAG_USE_EMBEDDINGS", "1").strip().lower()
    use_embeddings = use_emb_raw in {"1", "true", "yes", "on"}

    queries = expand_queries(q, max_queries=int(os.environ.get("WRITING_AGENT_RAG_MULTI_QUERY", "4") or 4))
    if not queries:
        queries = [q]

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

    if chunk_hits:
        context = _format_chunk_context(chunk_hits=chunk_hits, max_chars=max_chars)
        return RetrieveResult(context=context, chunk_hits=chunk_hits, paper_hits=[])

    rag = RagStore(rag_dir)
    papers = rag.list_papers()

    if len(papers) < 10:
        try:
            from writing_agent.v2.rag.auto_enhance import expand_with_related

            expand_with_related(rag_dir=rag_dir, paper_ids=[p.paper_id for p in papers], max_expand=3)
            papers = rag.list_papers()
        except Exception:
            pass

    paper_hits = _search_papers_multi_query(papers=papers, queries=queries, top_k=max(1, min(20, top_k)))
    context = build_rag_context(hits=paper_hits[: max(1, min(8, top_k))], max_chars=max_chars)
    if not context.strip():
        context = "[NO_EVIDENCE] Retrieval evidence is insufficient. Please provide additional trustworthy sources."
    return RetrieveResult(context=context, chunk_hits=[], paper_hits=paper_hits)


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
