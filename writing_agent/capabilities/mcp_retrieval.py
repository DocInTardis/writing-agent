"""MCP citation and retrieval capability helpers."""

from __future__ import annotations

from typing import Any


def mcp_rag_enabled(*, os_module) -> bool:
    raw = os_module.environ.get("WRITING_AGENT_RAG_MCP", "1").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def mcp_first_json(*, result: dict | None, json_module):
    if not isinstance(result, dict):
        return None
    contents = result.get("contents")
    if not isinstance(contents, list) or not contents:
        return None
    item = contents[0] if isinstance(contents[0], dict) else None
    if not isinstance(item, dict):
        return None
    text = str(item.get("text") or "")
    if not text:
        return None
    try:
        return json_module.loads(text)
    except Exception:
        return None


def load_mcp_citations_cached(
    *,
    cache: dict[str, Any],
    os_module,
    time_module,
    json_module,
    fetch_mcp_resource_fn,
    citation_cls,
) -> dict[str, Any]:
    now = time_module.time()
    if cache.get("items") and (now - float(cache.get("ts") or 0)) < 3600:
        return cache.get("items") or {}
    uri = os_module.environ.get("WRITING_AGENT_MCP_REF_URI", "mcp://references/default")
    result = fetch_mcp_resource_fn(uri)
    items: dict[str, Any] = {}
    try:
        contents = result.get("contents") if isinstance(result, dict) else None
        if isinstance(contents, list) and contents:
            payload = contents[0].get("text") if isinstance(contents[0], dict) else None
            data = json_module.loads(payload) if payload else None
            if isinstance(data, list):
                for row in data:
                    if not isinstance(row, dict):
                        continue
                    key = str(row.get("key") or "").strip()
                    title = str(row.get("title") or "").strip()
                    if not key or not title:
                        continue
                    items[key] = citation_cls(
                        key=key,
                        title=title,
                        url=str(row.get("url") or "") or None,
                        authors=str(row.get("authors") or "") or None,
                        year=str(row.get("year") or "") or None,
                        venue=str(row.get("venue") or "") or None,
                    )
    except Exception:
        items = {}
    cache["ts"] = now
    cache["items"] = items
    return items


def ensure_mcp_citations(
    *,
    session,
    load_mcp_citations_cached_fn,
    doc_ir_from_dict_fn,
    doc_ir_from_text_fn,
    citation_style_from_session_fn,
    apply_citations_to_doc_ir_fn,
    doc_ir_to_dict_fn,
    doc_ir_to_text_fn,
) -> None:
    if session.citations:
        return
    items = load_mcp_citations_cached_fn()
    if not items:
        return
    session.citations = items
    try:
        doc_ir = None
        if session.doc_ir:
            doc_ir = doc_ir_from_dict_fn(session.doc_ir)
        elif session.doc_text:
            doc_ir = doc_ir_from_text_fn(session.doc_text)
        if doc_ir is not None:
            style = citation_style_from_session_fn(session)
            doc_ir = apply_citations_to_doc_ir_fn(doc_ir, session.citations, style)
            session.doc_ir = doc_ir_to_dict_fn(doc_ir)
            session.doc_text = doc_ir_to_text_fn(doc_ir)
    except Exception:
        pass


def mcp_rag_retrieve(
    *,
    query: str,
    top_k: int,
    per_paper: int,
    max_chars: int,
    rag_enabled_fn,
    quote_fn,
    fetch_mcp_resource_fn,
    first_json_fn,
):
    if not rag_enabled_fn():
        return None
    normalized = (query or "").strip()
    if not normalized:
        return None
    uri = (
        "mcp://rag/retrieve?query="
        + quote_fn(normalized)
        + f"&top_k={int(top_k)}&per_paper={int(per_paper)}&max_chars={int(max_chars)}"
    )
    result = fetch_mcp_resource_fn(uri)
    return first_json_fn(result)


def mcp_rag_search(
    *,
    query: str,
    top_k: int,
    sources=None,
    max_results: int | None = None,
    mode: str = "",
    rag_enabled_fn,
    quote_fn,
    fetch_mcp_resource_fn,
    first_json_fn,
):
    if not rag_enabled_fn():
        return None
    normalized = (query or "").strip()
    if not normalized:
        return None
    uri = "mcp://rag/search?query=" + quote_fn(normalized) + f"&top_k={int(top_k)}"
    if isinstance(sources, list) and sources:
        src = ",".join([str(item).strip() for item in sources if str(item).strip()])
        if src:
            uri += "&sources=" + quote_fn(src)
    if max_results:
        uri += f"&max_results={int(max_results)}"
    if mode:
        uri += "&mode=" + quote_fn(mode)
    result = fetch_mcp_resource_fn(uri)
    return first_json_fn(result)


def mcp_rag_search_chunks(
    *,
    query: str,
    top_k: int,
    per_paper: int,
    alpha: float,
    use_embeddings: bool,
    rag_enabled_fn,
    quote_fn,
    fetch_mcp_resource_fn,
    first_json_fn,
):
    if not rag_enabled_fn():
        return None
    normalized = (query or "").strip()
    if not normalized:
        return None
    use_flag = "1" if use_embeddings else "0"
    uri = (
        "mcp://rag/search/chunks?query="
        + quote_fn(normalized)
        + f"&top_k={int(top_k)}&per_paper={int(per_paper)}&alpha={float(alpha)}&use_embeddings={use_flag}"
    )
    result = fetch_mcp_resource_fn(uri)
    return first_json_fn(result)


__all__ = [name for name in globals() if not name.startswith("__")]
