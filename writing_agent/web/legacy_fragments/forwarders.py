"""Forwarders: inject functions into caller globals."""
from urllib.request import urlopen, Request as UrlRequest

from writing_agent.v2.graph_runner_post_domain import (
    _default_title,
    _fallback_title_from_instruction,
    _filter_ack_headings,
    _filter_ack_outline,
    _guess_title,
    _has_cjk,
    _is_engineering_instruction,
    _is_mostly_ascii_line,
    _looks_like_rag_meta_line,
    _maybe_rag_context,
    _mcp_rag_enabled,
    _mcp_rag_retrieve,
    _normalize_title_line,
    _sanitize_rag_context,
    _strip_rag_meta_lines,
    _wants_acknowledgement,
)
from writing_agent.v2.rag.arxiv import search_arxiv, download_arxiv_pdf
from writing_agent.v2.rag.retrieve import retrieve_context
from writing_agent.v2.rag.user_library import UserDocRecord


def _library_item_payload(rec: UserDocRecord | dict) -> dict:
    if isinstance(rec, dict):
        return {
            "doc_id": str(rec.get("doc_id") or ""),
            "title": str(rec.get("title") or ""),
            "status": str(rec.get("status") or ""),
            "source": str(rec.get("source") or ""),
            "source_name": str(rec.get("source_name") or ""),
            "char_count": int(rec.get("char_count") or 0),
            "created_at": str(rec.get("created_at") or ""),
            "updated_at": str(rec.get("updated_at") or ""),
        }
    return {
        "doc_id": rec.doc_id,
        "title": rec.title,
        "status": rec.status,
        "source": rec.source,
        "source_name": rec.source_name,
        "char_count": rec.char_count,
        "created_at": rec.created_at,
        "updated_at": rec.updated_at,
    }


def _mcp_rag_search(
    query: str,
    *,
    top_k: int = 5,
    sources: list[str] | None = None,
    max_results: int | None = None,
    mode: str = "local",
) -> dict | None:
    try:
        from writing_agent.mcp_client import fetch_mcp_json
        uri = f"rag/search?q={UrlRequest('').selector if False else query}"
        # Fallback: return None so caller falls back to local search
    except Exception:
        pass
    return None


def _mcp_rag_search_chunks(
    query: str,
    *,
    top_k: int = 6,
    per_paper: int = 2,
    alpha: float = 0.75,
    use_embeddings: bool = True,
) -> dict | None:
    try:
        from writing_agent.mcp_client import fetch_mcp_json
    except Exception:
        pass
    return None


_NAMES = [
    "UrlRequest",
    "_default_title",
    "_fallback_title_from_instruction",
    "_filter_ack_headings",
    "_filter_ack_outline",
    "_guess_title",
    "_has_cjk",
    "_is_engineering_instruction",
    "_is_mostly_ascii_line",
    "_library_item_payload",
    "_looks_like_rag_meta_line",
    "_maybe_rag_context",
    "_mcp_rag_enabled",
    "_mcp_rag_retrieve",
    "_mcp_rag_search",
    "_mcp_rag_search_chunks",
    "_normalize_title_line",
    "_sanitize_rag_context",
    "_strip_rag_meta_lines",
    "_wants_acknowledgement",
    "download_arxiv_pdf",
    "retrieve_context",
    "search_arxiv",
    "urlopen",
]


def install(g):
    for name in _NAMES:
        g[name] = globals()[name]
