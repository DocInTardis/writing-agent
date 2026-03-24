"""Reference fallback retrieval helpers."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from collections.abc import Callable
from pathlib import Path



def _reference_domain_module():
    from writing_agent.v2 import graph_reference_domain as _reference_domain

    return _reference_domain



def _normalize_reference_query(query: str) -> str:
    return str(_reference_domain_module().normalize_reference_query(query))



def _expanded_query_tokens(query: str) -> set[str]:
    return set(_reference_domain_module()._expanded_query_tokens(query))



def _filter_sources_by_topic(rows: list[dict], *, query: str, min_score: int) -> list[dict]:
    return list(_reference_domain_module().filter_sources_by_topic(rows, query=query, min_score=min_score))


def _reference_cache_dir() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    data_dir = Path(os.environ.get("WRITING_AGENT_DATA_DIR", str(repo_root / ".data"))).resolve()
    cache_dir = data_dir / "cache" / "reference_fallback"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _reference_cache_path(query: str) -> Path:
    digest = hashlib.sha1(str(query or "").strip().lower().encode("utf-8", errors="ignore")).hexdigest()
    return _reference_cache_dir() / f"{digest}.json"


def _load_cached_reference_sources(query: str) -> list[dict]:
    if not query:
        return []
    ttl_s = max(300, int(os.environ.get("WRITING_AGENT_REFERENCE_CACHE_TTL_S", str(86400 * 3))))
    path = _reference_cache_path(query)
    if not path.exists():
        return []
    try:
        if (time.time() - path.stat().st_mtime) > ttl_s:
            return []
    except Exception:
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _save_cached_reference_sources(query: str, rows: list[dict]) -> None:
    clean_rows = [dict(row) for row in (rows or []) if isinstance(row, dict)]
    if not query or not clean_rows:
        return
    cap = max(8, min(80, int(os.environ.get("WRITING_AGENT_REFERENCE_CACHE_ROWS", "48"))))
    payload = {
        "query": str(query or "").strip(),
        "saved_at": time.time(),
        "rows": clean_rows[:cap],
    }
    try:
        _reference_cache_path(query).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        return


def _fallback_query_seeds(query: str) -> list[str]:
    normalized = _normalize_reference_query(query)
    if not normalized:
        return []
    expanded = list(_expanded_query_tokens(normalized))
    english = [tok.strip().lower() for tok in expanded if re.search(r"[a-z]", str(tok or ""))]
    english_joined = " ".join(english)

    def _has(fragment: str) -> bool:
        return fragment in english_joined

    seeds: list[str] = []

    def _push(seed: str) -> None:
        clean = " ".join(str(seed or "").split()).strip()
        if not clean or clean in seeds:
            return
        seeds.append(clean)

    _push(normalized)
    preferred = [
        "blockchain rural service citespace",
        "blockchain agricultural service citespace",
        "blockchain rural service",
        "distributed ledger rural governance",
        "rural socialized service blockchain",
        "scientometric analysis blockchain rural service",
    ]
    if _has("blockchain") and (_has("rural") or _has("agricultural") or _has("village")):
        for seed in preferred:
            _push(seed)
    if _has("citespace") or _has("cite") or _has("scientometric"):
        _push("blockchain citespace")
        _push("rural service citespace")
    if _has("public service") or _has("social service"):
        _push("blockchain public service")
    if _has("smart contract"):
        _push("smart contract agricultural service")
    topic_tokens: list[str] = []
    for key in ("blockchain", "distributed ledger", "rural", "agricultural", "service", "public service", "social service", "governance", "citespace"):
        if key in english and key not in topic_tokens:
            topic_tokens.append(key)
    if topic_tokens:
        _push(" ".join(topic_tokens[:6]))
    try:
        seed_cap = max(1, min(8, int(os.environ.get("WRITING_AGENT_REFERENCE_QUERY_SEED_CAP", "6"))))
    except Exception:
        seed_cap = 6
    return seeds[:seed_cap]


def _search_crossref_rows(query_seed: str, *, max_results: int) -> list[dict]:
    try:
        from writing_agent.v2.rag.crossref import search_crossref
    except Exception:
        return []
    try:
        result = search_crossref(query=query_seed, max_results=max_results, timeout_s=18.0)
    except Exception:
        return []
    rows: list[dict] = []
    for work in result.works:
        rows.append(
            {
                "id": work.paper_id,
                "title": work.title,
                "url": work.abs_url or work.pdf_url,
                "authors": list(work.authors or []),
                "published": work.published,
                "updated": work.updated,
                "source": "crossref",
                "kind": "fallback_crossref",
            }
        )
    return rows


def _search_openalex_rows(query_seed: str, *, max_results: int) -> list[dict]:
    try:
        from writing_agent.v2.rag.openalex import search_openalex
    except Exception:
        return []
    try:
        result = search_openalex(query=query_seed, max_results=max_results, timeout_s=18.0)
    except Exception:
        return []
    rows: list[dict] = []
    for work in result.works:
        rows.append(
            {
                "id": work.paper_id,
                "title": work.title,
                "url": work.abs_url or work.pdf_url,
                "authors": list(work.authors or []),
                "published": work.published,
                "updated": work.updated,
                "source": "openalex",
                "kind": "fallback_openalex",
            }
        )
    return rows


def fallback_reference_sources(
    *,
    instruction: str,
    mcp_rag_retrieve: Callable[..., tuple[str, list[dict]]],
    extract_sources_from_context: Callable[[str], list[dict]],
    enrich_sources_with_rag_fn: Callable[[list[dict]], list[dict]],
    extract_year_fn: Callable[[str], str],
) -> list[dict]:
    query = _normalize_reference_query(instruction)
    if not query:
        return []
    top_k = int(os.environ.get("WRITING_AGENT_RAG_TOP_K", "10"))
    max_chars = int(os.environ.get("WRITING_AGENT_RAG_MAX_CHARS", "3600"))
    per_paper = int(os.environ.get("WRITING_AGENT_RAG_PER_PAPER", "4"))
    min_refs_target = int(os.environ.get("WRITING_AGENT_MIN_REFERENCE_ITEMS", "18"))

    def _dedupe_sources(rows: list[dict]) -> list[dict]:
        out_rows: list[dict] = []
        seen_keys: set[str] = set()
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            key = str(row.get("url") or row.get("id") or row.get("title") or "").strip().lower()
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            out_rows.append(row)
        return out_rows

    def _normalize_candidates(rows: list[dict]) -> list[dict]:
        deduped = _dedupe_sources(rows)
        return _filter_sources_by_topic(deduped, query=query, min_score=1)

    context, srcs = mcp_rag_retrieve(query=query, top_k=top_k, per_paper=per_paper, max_chars=max_chars)
    if srcs:
        enriched = enrich_sources_with_rag_fn(srcs)
        enriched = _normalize_candidates(enriched)
        if len(enriched) >= min_refs_target:
            return enriched
    if context.strip():
        sources = extract_sources_from_context(context)
        enriched = enrich_sources_with_rag_fn(sources)
        enriched = _normalize_candidates(enriched)
        if enriched:
            if len(enriched) >= min_refs_target:
                return enriched

    try:
        from writing_agent.v2.rag.retrieve import retrieve_context
        from writing_agent.v2.rag.store import RagStore
    except Exception:
        return []

    repo_root = Path(__file__).resolve().parents[2]
    data_dir = Path(os.environ.get("WRITING_AGENT_DATA_DIR", str(repo_root / ".data"))).resolve()
    rag_dir = data_dir / "rag"
    res = retrieve_context(rag_dir=rag_dir, query=query, top_k=top_k, per_paper=per_paper, max_chars=max_chars)
    sources = extract_sources_from_context(res.context or "")
    enriched = enrich_sources_with_rag_fn(sources)
    enriched = _normalize_candidates(enriched)
    if enriched:
        if len(enriched) >= min_refs_target:
            return enriched

    try:
        store = RagStore(rag_dir)
        papers = store.list_papers()
    except Exception:
        return []

    def _year_key(paper) -> int:
        year = extract_year_fn(getattr(paper, "published", "") or "") or extract_year_fn(getattr(paper, "updated", "") or "")
        return int(year) if year.isdigit() else 0

    papers.sort(key=_year_key, reverse=True)
    rows: list[dict] = []
    try:
        max_store_rows = max(12, min(80, int(os.environ.get("WRITING_AGENT_REFERENCE_STORE_ROWS", "40"))))
    except Exception:
        max_store_rows = 40
    for paper in papers[:max_store_rows]:
        rows.append(
            {
                "id": paper.paper_id,
                "title": paper.title,
                "url": paper.abs_url or paper.pdf_url,
                "authors": paper.authors,
                "published": paper.published,
                "updated": paper.updated,
                "source": paper.source,
                "kind": "fallback",
            }
        )
    enriched_rows = enrich_sources_with_rag_fn(rows)
    enriched_rows = _normalize_candidates(enriched_rows)
    if len(enriched_rows) >= min_refs_target:
        _reference_domain_module()._save_cached_reference_sources(query, enriched_rows)
        return enriched_rows

    cached_rows = _normalize_candidates(_reference_domain_module()._load_cached_reference_sources(query))
    if len(cached_rows) >= min_refs_target:
        return cached_rows
    if len(cached_rows) > len(enriched_rows):
        enriched_rows = _dedupe_sources(enriched_rows + cached_rows)
        enriched_rows = _normalize_candidates(enriched_rows)

    seeds = _reference_domain_module()._fallback_query_seeds(query)
    if not seeds:
        if enriched_rows:
            _reference_domain_module()._save_cached_reference_sources(query, enriched_rows)
        return enriched_rows

    provider_order_raw = str(os.environ.get("WRITING_AGENT_REFERENCE_ONLINE_PROVIDERS", "crossref,openalex")).strip()
    provider_order = [tok.strip().lower() for tok in provider_order_raw.split(",") if tok.strip()] or ["crossref", "openalex"]
    try:
        per_seed_max = max(6, min(24, int(os.environ.get("WRITING_AGENT_REFERENCE_ONLINE_PER_SEED", "10"))))
    except Exception:
        per_seed_max = 10

    online_rows: list[dict] = []
    for provider in provider_order:
        for query_seed in seeds:
            if provider == "crossref":
                online_rows.extend(_reference_domain_module()._search_crossref_rows(query_seed, max_results=per_seed_max))
            elif provider == "openalex":
                online_rows.extend(_reference_domain_module()._search_openalex_rows(query_seed, max_results=per_seed_max))
        if online_rows:
            merged = _dedupe_sources(enriched_rows + online_rows)
            merged = enrich_sources_with_rag_fn(merged)
            merged = _normalize_candidates(merged)
            if merged:
                enriched_rows = merged
                _reference_domain_module()._save_cached_reference_sources(query, enriched_rows)
            if len(enriched_rows) >= min_refs_target:
                return enriched_rows

    if enriched_rows:
        _reference_domain_module()._save_cached_reference_sources(query, enriched_rows)
    return enriched_rows


