"""Evidence/reference support helpers for graph runner."""

from __future__ import annotations

from writing_agent.v2.graph_runner_core_domain import *


def _extract_sources_from_context(context: str) -> list[dict]:
    blocks = [b for b in (context or "").split("\n\n") if b.strip()]
    out: list[dict] = []
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        head = lines[0]
        url = ""
        if len(lines) > 1 and lines[1].startswith("http"):
            url = lines[1]
        m = re.match(r"^\[(.+?)\]\s+(.+?)(?:\s+\((.+)\))?$", head)
        if m:
            paper_id = m.group(1).strip()
            title = m.group(2).strip()
            kind = (m.group(3) or "").strip()
            out.append({"id": paper_id, "title": title, "kind": kind, "url": url})
        else:
            out.append({"id": "", "title": head.strip(), "kind": "", "url": url})
    return out


def _filter_context_by_sources(context: str, sources: list[dict]) -> str:
    blocks = [b for b in (context or "").split("\n\n") if b.strip()]
    if not blocks or not sources:
        return str(context or "").strip()
    keep_tokens: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            continue
        for field in ("id", "title", "url"):
            token = str(source.get(field) or "").strip().lower()
            if token:
                keep_tokens.add(token)
    if not keep_tokens:
        return str(context or "").strip()
    kept: list[str] = []
    for block in blocks:
        block_norm = str(block or "").lower()
        if any(token in block_norm for token in keep_tokens):
            kept.append(block.strip())
    if kept:
        return "\n\n".join(kept).strip()
    return ""


def _filter_facts_by_sources(facts: list[dict], sources: list[dict]) -> list[dict]:
    if not facts or not sources:
        return [dict(item) for item in (facts or []) if isinstance(item, dict)]
    keep_tokens: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            continue
        for field in ("id", "title", "url"):
            token = str(source.get(field) or "").strip().lower()
            if token:
                keep_tokens.add(token)
    if not keep_tokens:
        return [dict(item) for item in (facts or []) if isinstance(item, dict)]
    out: list[dict] = []
    for item in facts:
        if not isinstance(item, dict):
            continue
        src = str(item.get("source") or "").strip().lower()
        if src and any(token in src or src in token for token in keep_tokens):
            out.append(dict(item))
            continue
        if not src:
            out.append(dict(item))
    return out


def _extract_year(text: str) -> str:
    return graph_reference_domain.extract_year(text)


def _format_authors(authors: list[str]) -> str:
    return graph_reference_domain.format_authors(authors)


def _enrich_sources_with_rag(sources: list[dict]) -> list[dict]:
    return graph_reference_domain.enrich_sources_with_rag(sources)


def _collect_reference_sources(evidence_map: dict[str, dict], *, query: str = "") -> list[dict]:
    sources: list[dict] = []
    seen: set[str] = set()
    for data in (evidence_map or {}).values():
        items = data.get("sources") if isinstance(data, dict) else None
        if not isinstance(items, list):
            continue
        for s in items:
            if not isinstance(s, dict):
                continue
            url = str(s.get("url") or "").strip()
            title = str(s.get("title") or "").strip()
            key = url or title or str(s.get("id") or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            sources.append(
                {
                    "url": url,
                    "title": title,
                    "id": str(s.get("id") or "").strip(),
                    "kind": str(s.get("kind") or "").strip(),
                    "authors": s.get("authors") or [],
                    "published": s.get("published") or "",
                    "updated": s.get("updated") or "",
                    "source": s.get("source") or "",
                }
            )
    enriched = _enrich_sources_with_rag(sources)
    query_text = str(query or "").strip()
    if query_text:
        enriched = graph_reference_domain.filter_sources_by_topic(enriched, query=query_text, min_score=1)
    return enriched


def _sort_reference_sources(sources: list[dict], *, query: str, extract_year_fn) -> list[dict]:
    return graph_reference_domain.sort_reference_sources(
        sources,
        query=query,
        extract_year_fn=extract_year_fn,
    )


def _format_reference_items(sources: list[dict], *, extract_year_fn, format_authors_fn) -> list[str]:
    agent = graph_reference_domain.ReferenceAgent(
        extract_year_fn=extract_year_fn,
        format_authors_fn=format_authors_fn,
    )
    return agent.build(sources)


def _validate_reference_items(lines: list[str], *, extract_year_fn, format_authors_fn) -> list[str]:
    agent = graph_reference_domain.ReferenceAgent(
        extract_year_fn=extract_year_fn,
        format_authors_fn=format_authors_fn,
    )
    return agent.validate(lines)


def _fallback_reference_sources(
    *,
    instruction: str,
    mcp_rag_retrieve,
    extract_sources_from_context,
    enrich_sources_with_rag_fn,
    extract_year_fn,
) -> list[dict]:
    return graph_reference_domain.fallback_reference_sources(
        instruction=instruction,
        mcp_rag_retrieve=mcp_rag_retrieve,
        extract_sources_from_context=extract_sources_from_context,
        enrich_sources_with_rag_fn=enrich_sources_with_rag_fn,
        extract_year_fn=extract_year_fn,
    )


def _summarize_evidence(
    *,
    base_url: str,
    model: str,
    section: str,
    analysis_summary: str,
    context: str,
    sources: list[dict],
    require_json_response,
    provider_factory,
) -> dict:
    return graph_reference_domain.summarize_evidence(
        base_url=base_url,
        model=model,
        section=section,
        analysis_summary=analysis_summary,
        context=context,
        sources=sources,
        require_json_response=require_json_response,
        provider_factory=provider_factory,
    )


def _format_evidence_summary(facts: list[dict], sources: list[dict]) -> tuple[str, list[str]]:
    return graph_reference_domain.format_evidence_summary(facts, sources)


def _topic_tokens(text: str) -> list[str]:
    src = str(text or "").strip().lower()
    if not src:
        return []
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[a-z][a-z0-9\-]{1,}", src)
    seen: set[str] = set()
    out: list[str] = []
    for tok in tokens:
        t = tok.strip().lower()
        if not t or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def _evidence_alignment_score(*, query: str, context: str, sources: list[dict]) -> float:
    q_tokens = set(_topic_tokens(query))
    if not q_tokens:
        return 1.0
    src_parts = [str(context or "")]
    for row in sources or []:
        if not isinstance(row, dict):
            continue
        src_parts.append(str(row.get("title") or ""))
        src_parts.append(str(row.get("url") or ""))
        src_parts.append(str(row.get("source") or ""))
    src_tokens = set(_topic_tokens(" ".join(src_parts)))
    if not src_tokens:
        return 0.0
    overlap = len([tok for tok in q_tokens if tok in src_tokens])
    return float(overlap) / float(max(1, len(q_tokens)))


def _evaluate_data_starvation(*, query: str, section: str, context: str, sources: list[dict]) -> dict[str, object]:
    compact_chars = len(re.sub(r"\s+", "", str(context or "")))
    source_count = len([row for row in (sources or []) if isinstance(row, dict)])
    alignment_score = _evidence_alignment_score(query=query, context=context, sources=sources)
    try:
        min_chars = max(0, int(os.environ.get("WRITING_AGENT_RAG_MIN_CONTEXT_CHARS", "260")))
    except Exception:
        min_chars = 260
    try:
        min_sources = max(0, int(os.environ.get("WRITING_AGENT_RAG_MIN_SOURCES", "2")))
    except Exception:
        min_sources = 2
    try:
        min_align = max(0.0, min(1.0, float(os.environ.get("WRITING_AGENT_RAG_DATA_STARVATION_MIN_SCORE", "0.12"))))
    except Exception:
        min_align = 0.12
    reasons: list[str] = []
    if compact_chars < min_chars:
        reasons.append("low_context_chars")
    if source_count < min_sources:
        reasons.append("low_source_count")
    if alignment_score < min_align:
        reasons.append("low_alignment_score")
    return {
        "section": str(section or ""),
        "is_starved": bool(reasons),
        "reasons": reasons,
        "compact_chars": compact_chars,
        "min_context_chars": min_chars,
        "source_count": source_count,
        "min_sources": min_sources,
        "alignment_score": round(float(alignment_score), 4),
        "min_alignment_score": float(min_align),
    }


__all__ = [name for name in globals() if not name.startswith("__")]
