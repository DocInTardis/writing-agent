"""Mcp Ref Server module.

This module belongs to `writing_agent` in the writing-agent codebase.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse


def _default_refs() -> List[Dict[str, Any]]:
    # ASCII-only defaults to avoid encoding issues in some environments.
    return [
        {
            "key": "turing1950",
            "title": "Computing Machinery and Intelligence",
            "authors": "Turing, A. M.",
            "year": "1950",
            "venue": "Mind",
            "url": "https://doi.org/10.1093/mind/LIX.236.433",
        },
        {
            "key": "mccarthy1955",
            "title": "A Proposal for the Dartmouth Summer Research Project on Artificial Intelligence",
            "authors": "McCarthy, J.; Minsky, M.; Rochester, N.; Shannon, C.",
            "year": "1955",
            "venue": "Dartmouth College",
            "url": "https://www.dartmouth.edu/~ai50/homepage/homepage.html",
        },
        {
            "key": "russell2010",
            "title": "Artificial Intelligence: A Modern Approach",
            "authors": "Russell, S.; Norvig, P.",
            "year": "2010",
            "venue": "Prentice Hall",
            "url": "https://aima.cs.berkeley.edu/",
        },
    ]


def _load_refs() -> List[Dict[str, Any]]:
    path = Path(os.environ.get("MCP_REF_CACHE", ".data/mcp_refs.json"))
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
    except Exception:
        pass
    refs = _default_refs()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(refs, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    return refs


def _rag_dir() -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    data_dir = Path(os.environ.get("WRITING_AGENT_DATA_DIR", str(repo_root / ".data"))).resolve()
    return data_dir / "rag"


_RAG_CACHE: dict = {"ts": {}, "items": {}}


def _rag_cache_get(key: str, ttl_s: float) -> Optional[Dict[str, Any]]:
    if not key:
        return None
    ts = _RAG_CACHE.get("ts", {}).get(key)
    if ts is None:
        return None
    if (time.time() - float(ts)) > ttl_s:
        return None
    return _RAG_CACHE.get("items", {}).get(key)


def _rag_cache_set(key: str, value: Dict[str, Any]) -> None:
    if not key:
        return
    _RAG_CACHE.setdefault("ts", {})[key] = time.time()
    _RAG_CACHE.setdefault("items", {})[key] = value


def _parse_rag_uri(uri: str) -> tuple[str, dict[str, str]]:
    parsed = urlparse(uri)
    if parsed.scheme != "mcp" or parsed.netloc != "rag":
        return "", {}
    path = (parsed.path or "").strip("/")
    params_raw = parse_qs(parsed.query)
    params: dict[str, str] = {}
    for k, v in params_raw.items():
        if not v:
            continue
        params[str(k)] = str(v[0])
    return path, params


def _rag_search(uri: str) -> Optional[Dict[str, Any]]:
    path, params = _parse_rag_uri(uri)
    if path != "search":
        return None
    query = (params.get("query") or params.get("q") or "").strip()
    if not query:
        return {"results": [], "mode": "local"}
    try:
        top_k = int(params.get("top_k") or params.get("k") or 6)
    except Exception:
        top_k = 6
    try:
        ttl_s = float(params.get("cache_ttl") or os.environ.get("WRITING_AGENT_RAG_MCP_TTL", "120"))
    except Exception:
        ttl_s = 120.0
    cache_key = f"search|{query}|{top_k}|{params.get('sources') or ''}|{params.get('mode') or ''}|{params.get('max_results') or ''}"
    cached = _rag_cache_get(cache_key, ttl_s)
    if cached is not None:
        return cached
    sources_raw = (params.get("sources") or "").strip()
    mode = (params.get("mode") or "").strip().lower()
    if sources_raw or mode == "remote":
        payload = _rag_search_remote(query=query, sources=sources_raw, max_results=int(params.get("max_results") or 10))
    else:
        payload = _rag_search_local(query=query, top_k=top_k)
    if isinstance(payload, dict):
        _rag_cache_set(cache_key, payload)
    return payload


def _rag_search_chunks(uri: str) -> Optional[Dict[str, Any]]:
    path, params = _parse_rag_uri(uri)
    if path not in {"search/chunks", "search_chunks"}:
        return None
    query = (params.get("query") or params.get("q") or "").strip()
    if not query:
        return {"hits": []}
    try:
        top_k = int(params.get("top_k") or params.get("k") or 6)
    except Exception:
        top_k = 6
    try:
        per_paper = int(params.get("per_paper") or 2)
    except Exception:
        per_paper = 2
    try:
        alpha = float(params.get("alpha") or 0.75)
    except Exception:
        alpha = 0.75
    use_emb_raw = str(params.get("use_embeddings") or "1").strip().lower()
    use_embeddings = use_emb_raw in {"1", "true", "yes", "on"}
    try:
        ttl_s = float(params.get("cache_ttl") or os.environ.get("WRITING_AGENT_RAG_MCP_TTL", "120"))
    except Exception:
        ttl_s = 120.0
    cache_key = f"chunks|{query}|{top_k}|{per_paper}|{alpha}|{int(use_embeddings)}"
    cached = _rag_cache_get(cache_key, ttl_s)
    if cached is not None:
        return cached
    try:
        from writing_agent.v2.rag.index import RagIndex
    except Exception:
        return {"hits": []}
    index = RagIndex(_rag_dir())
    try:
        hits = index.search(query=query, top_k=top_k, per_paper=per_paper, use_embeddings=use_embeddings, alpha=alpha)
    except Exception:
        hits = []
    return {
        "hits": [
            {
                "chunk_id": h.chunk_id,
                "paper_id": h.paper_id,
                "title": h.title,
                "abs_url": h.abs_url,
                "kind": h.kind,
                "score": h.score,
                "text": h.text,
            }
            for h in hits
        ]
    }


def _rag_search_local(*, query: str, top_k: int) -> Dict[str, Any]:
    try:
        from writing_agent.v2.rag.search import search_papers
        from writing_agent.v2.rag.store import RagStore
    except Exception:
        return {"results": [], "mode": "local"}
    store = RagStore(_rag_dir())
    try:
        papers = store.list_papers()
    except Exception:
        papers = []
    hits = search_papers(papers=papers, query=query, top_k=top_k)
    results: list[dict[str, Any]] = []
    for h in hits:
        results.append(
            {
                "id": h.paper_id,
                "title": h.title,
                "summary": h.summary,
                "snippet": h.snippet,
                "score": h.score,
                "published": h.published,
                "url": h.abs_url,
                "source": "local",
            }
        )
    return {"results": results, "mode": "local"}


def _rag_search_remote(*, query: str, sources: str, max_results: int) -> Dict[str, Any]:
    try:
        from writing_agent.v2.rag.arxiv import search_arxiv
        from writing_agent.v2.rag.openalex import search_openalex
    except Exception:
        return {"results": [], "mode": "remote"}
    srcs = [s.strip().lower() for s in (sources or "").split(",") if s.strip()]
    if not srcs:
        srcs = ["openalex", "arxiv"]
    max_results = int(max(1, min(50, max_results)))
    results: list[dict[str, Any]] = []
    if "openalex" in srcs:
        try:
            res = search_openalex(query=query, max_results=max_results)
            for w in res.works:
                results.append(
                    {
                        "id": w.paper_id,
                        "title": w.title,
                        "summary": w.summary,
                        "authors": w.authors,
                        "published": w.published,
                        "updated": w.updated,
                        "url": w.abs_url,
                        "pdf_url": w.pdf_url,
                        "categories": w.categories,
                        "primary_category": w.primary_category,
                        "source": "openalex",
                    }
                )
        except Exception:
            pass
    if "arxiv" in srcs:
        try:
            res = search_arxiv(query=query, max_results=max_results)
            for p in res.papers:
                results.append(
                    {
                        "id": p.paper_id,
                        "title": p.title,
                        "summary": p.summary,
                        "authors": p.authors,
                        "published": p.published,
                        "updated": p.updated,
                        "url": p.abs_url,
                        "pdf_url": p.pdf_url,
                        "categories": p.categories,
                        "primary_category": p.primary_category,
                        "source": "arxiv",
                    }
                )
        except Exception:
            pass
    return {"results": results, "mode": "remote"}


def _rag_retrieve(uri: str) -> Optional[Dict[str, Any]]:
    path, params = _parse_rag_uri(uri)
    if path != "retrieve":
        return None
    query = (params.get("query") or params.get("q") or "").strip()
    if not query:
        return {"context": "", "sources": []}
    try:
        top_k = int(params.get("top_k") or params.get("k") or 6)
    except Exception:
        top_k = 6
    try:
        per_paper = int(params.get("per_paper") or 2)
    except Exception:
        per_paper = 2
    try:
        max_chars = int(params.get("max_chars") or 2500)
    except Exception:
        max_chars = 2500
    try:
        ttl_s = float(params.get("cache_ttl") or os.environ.get("WRITING_AGENT_RAG_MCP_TTL", "120"))
    except Exception:
        ttl_s = 120.0
    cache_key = f"retrieve|{query}|{top_k}|{per_paper}|{max_chars}"
    cached = _rag_cache_get(cache_key, ttl_s)
    if cached is not None:
        return cached
    try:
        from writing_agent.v2.rag.retrieve import retrieve_context
    except Exception:
        return {"context": "", "sources": []}
    res = retrieve_context(
        rag_dir=_rag_dir(),
        query=query,
        top_k=top_k,
        per_paper=per_paper,
        max_chars=max_chars,
    )
    sources: list[dict[str, Any]] = []
    for h in res.paper_hits:
        sources.append(
            {
                "id": h.paper_id,
                "title": h.title,
                "url": h.abs_url,
                "published": h.published,
            }
        )
    if not sources and res.chunk_hits:
        for h in res.chunk_hits[: max(1, min(12, top_k))]:
            sources.append(
                {
                    "id": h.paper_id,
                    "title": h.title,
                    "url": h.abs_url,
                    "kind": h.kind,
                }
            )
    payload = {"context": res.context, "sources": sources}
    _rag_cache_set(cache_key, payload)
    return payload


def _send(msg: Dict[str, Any]) -> None:
    raw = json.dumps(msg, ensure_ascii=False)
    payload = raw.encode("utf-8")
    header = f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
    sys.stdout.buffer.write(header + payload)
    sys.stdout.buffer.flush()


def _read_message() -> Optional[Dict[str, Any]]:
    headers: Dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        try:
            key, value = line.decode("ascii").split(":", 1)
            headers[key.strip().lower()] = value.strip()
        except Exception:
            continue
    length = int(headers.get("content-length", "0") or 0)
    if length <= 0:
        return None
    body = sys.stdin.buffer.read(length)
    if not body:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except Exception:
        return None


def _handle_request(req: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    req_id = req.get("id")
    method = req.get("method")
    params = req.get("params") or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "capabilities": {"resources": {}},
                "serverInfo": {"name": "mcp-ref-server", "version": "0.1.0"},
            },
        }

    if method == "resources/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "resources": [
                    {
                        "uri": "mcp://references/default",
                        "name": "Default References",
                        "description": "Cached reference list",
                        "mimeType": "application/json",
                    },
                    {
                        "uri": "mcp://rag/search",
                        "name": "RAG Search",
                        "description": "RAG search results (query params)",
                        "mimeType": "application/json",
                    },
                    {
                        "uri": "mcp://rag/retrieve",
                        "name": "RAG Retrieve",
                        "description": "RAG context retrieval (query params)",
                        "mimeType": "application/json",
                    },
                    {
                        "uri": "mcp://rag/search/chunks",
                        "name": "RAG Chunk Search",
                        "description": "RAG chunk search (query params)",
                        "mimeType": "application/json",
                    },
                ]
            },
        }

    if method == "resources/read":
        uri = str(params.get("uri") or "")
        if uri == "mcp://references/default":
            refs = _load_refs()
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "application/json",
                            "text": json.dumps(refs, ensure_ascii=False),
                        }
                    ]
                },
            }
        if uri.startswith("mcp://rag/"):
            payload = _rag_search(uri)
            if payload is None:
                payload = _rag_retrieve(uri)
            if payload is None:
                payload = _rag_search_chunks(uri)
            if payload is None:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32602, "message": "Unknown rag resource"},
                }
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "application/json",
                            "text": json.dumps(payload, ensure_ascii=False),
                        }
                    ]
                },
            }
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32602, "message": "Unknown resource"},
        }

    if method == "shutdown":
        return {"jsonrpc": "2.0", "id": req_id, "result": None}

    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {"code": -32601, "message": f"Unknown method: {method}"},
    }


def main() -> int:
    while True:
        req = _read_message()
        if req is None:
            break
        resp = _handle_request(req)
        if resp:
            _send(resp)
        if req.get("method") == "shutdown":
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
