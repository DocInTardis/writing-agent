from __future__ import annotations

import json
from dataclasses import dataclass
from types import SimpleNamespace

from writing_agent.capabilities.mcp_retrieval import (
    ensure_mcp_citations,
    load_mcp_citations_cached,
    mcp_rag_retrieve,
    mcp_rag_search,
    mcp_rag_search_chunks,
)


@dataclass
class _Citation:
    key: str
    title: str
    url: str | None = None
    authors: str | None = None
    year: str | None = None
    venue: str | None = None


def test_load_mcp_citations_cached_parses_and_caches_items() -> None:
    cache: dict[str, object] = {}
    calls: list[str] = []

    def _fetch(uri: str):
        calls.append(uri)
        return {
            "contents": [
                {
                    "text": json.dumps(
                        [
                            {"key": "ref1", "title": "Paper A", "url": "https://a", "authors": "A", "year": "2024"}
                        ]
                    )
                }
            ]
        }

    items = load_mcp_citations_cached(
        cache=cache,
        os_module=SimpleNamespace(environ={}),
        time_module=SimpleNamespace(time=lambda: 1000.0),
        json_module=json,
        fetch_mcp_resource_fn=_fetch,
        citation_cls=_Citation,
    )

    assert list(items) == ["ref1"]
    assert isinstance(items["ref1"], _Citation)
    again = load_mcp_citations_cached(
        cache=cache,
        os_module=SimpleNamespace(environ={}),
        time_module=SimpleNamespace(time=lambda: 1200.0),
        json_module=json,
        fetch_mcp_resource_fn=_fetch,
        citation_cls=_Citation,
    )
    assert again is items
    assert len(calls) == 1


def test_ensure_mcp_citations_updates_session_doc_state() -> None:
    session = SimpleNamespace(citations={}, doc_ir=None, doc_text="raw text")

    ensure_mcp_citations(
        session=session,
        load_mcp_citations_cached_fn=lambda: {"ref1": _Citation(key="ref1", title="Paper A")},
        doc_ir_from_dict_fn=lambda value: value,
        doc_ir_from_text_fn=lambda text: {"text": text},
        citation_style_from_session_fn=lambda _session: "apa",
        apply_citations_to_doc_ir_fn=lambda doc_ir, citations, style: {"text": doc_ir["text"], "citations": list(citations), "style": style},
        doc_ir_to_dict_fn=lambda doc_ir: dict(doc_ir),
        doc_ir_to_text_fn=lambda doc_ir: f"{doc_ir['text']}::{doc_ir['style']}::{len(doc_ir['citations'])}",
    )

    assert "ref1" in session.citations
    assert session.doc_ir["style"] == "apa"
    assert session.doc_text == "raw text::apa::1"


def test_mcp_rag_helpers_build_expected_uris() -> None:
    seen: list[str] = []

    def _fetch(uri: str):
        seen.append(uri)
        return {"contents": [{"text": json.dumps({"uri": uri})}]}

    def rag_enabled_fn() -> bool:
        return True

    def first_json_fn(result):
        return json.loads(result["contents"][0]["text"])

    search = mcp_rag_search(
        query="topic words",
        top_k=5,
        sources=["arxiv", "openalex"],
        max_results=12,
        mode="hybrid",
        rag_enabled_fn=rag_enabled_fn,
        quote_fn=lambda value: value.replace(" ", "%20"),
        fetch_mcp_resource_fn=_fetch,
        first_json_fn=first_json_fn,
    )
    retrieve = mcp_rag_retrieve(
        query="topic words",
        top_k=4,
        per_paper=2,
        max_chars=1500,
        rag_enabled_fn=rag_enabled_fn,
        quote_fn=lambda value: value.replace(" ", "%20"),
        fetch_mcp_resource_fn=_fetch,
        first_json_fn=first_json_fn,
    )
    chunks = mcp_rag_search_chunks(
        query="topic words",
        top_k=3,
        per_paper=2,
        alpha=0.7,
        use_embeddings=True,
        rag_enabled_fn=rag_enabled_fn,
        quote_fn=lambda value: value.replace(" ", "%20"),
        fetch_mcp_resource_fn=_fetch,
        first_json_fn=first_json_fn,
    )

    assert "mcp://rag/search?query=topic%20words&top_k=5&sources=arxiv,openalex&max_results=12&mode=hybrid" == search["uri"]
    assert "mcp://rag/retrieve?query=topic%20words&top_k=4&per_paper=2&max_chars=1500" == retrieve["uri"]
    assert "mcp://rag/search/chunks?query=topic%20words&top_k=3&per_paper=2&alpha=0.7&use_embeddings=1" == chunks["uri"]
    assert len(seen) == 3
