from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from writing_agent.v2.rag.index import RagChunkHit, RagIndex
from writing_agent.v2.rag.search import RagSearchHit, build_rag_context, search_papers
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

    # Prefer chunk-level (hybrid) retrieval if index exists.
    index = RagIndex(rag_dir)
    alpha = float(os.environ.get("WRITING_AGENT_RAG_ALPHA", "0.75"))
    use_emb_raw = os.environ.get("WRITING_AGENT_RAG_USE_EMBEDDINGS", "1").strip().lower()
    use_embeddings = use_emb_raw in {"1", "true", "yes", "on"}

    chunk_hits: list[RagChunkHit] = []
    if index.index_path.exists():
        try:
            chunk_hits = index.search(query=q, top_k=top_k, per_paper=per_paper, use_embeddings=use_embeddings, alpha=alpha)
        except Exception:
            chunk_hits = []

    if chunk_hits:
        context = _format_chunk_context(chunk_hits=chunk_hits, max_chars=max_chars)
        return RetrieveResult(context=context, chunk_hits=chunk_hits, paper_hits=[])

    # Fallback: paper-level (title+summary) retrieval
    rag = RagStore(rag_dir)
    papers = rag.list_papers()
    paper_hits = search_papers(papers=papers, query=q, top_k=max(1, min(20, top_k)))
    context = build_rag_context(hits=paper_hits[: max(1, min(8, top_k))], max_chars=max_chars)
    return RetrieveResult(context=context, chunk_hits=[], paper_hits=paper_hits)


def _format_chunk_context(*, chunk_hits: list[RagChunkHit], max_chars: int) -> str:
    max_chars = int(max(400, min(20000, max_chars)))
    out: list[str] = []
    used = 0
    for h in chunk_hits:
        head = f"[{h.paper_id}] {h.title} ({h.kind})\n{h.abs_url}".strip()
        body = (h.text or "").strip()
        block = (head + "\n" + body).strip()
        if not block:
            continue
        if used + len(block) + 2 > max_chars:
            break
        out.append(block)
        used += len(block) + 2
    return "\n\n".join(out).strip()

