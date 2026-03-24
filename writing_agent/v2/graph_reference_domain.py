"""Graph Reference Domain module.

This module belongs to `writing_agent.v2` in the writing-agent codebase.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from datetime import date
from pathlib import Path

from writing_agent.v2 import graph_reference_plan_domain as reference_plan_domain
from writing_agent.v2.prompts import _escape_prompt_text

from writing_agent.v2 import graph_reference_topic_domain as topic_domain

_reference_query_tokens = reference_plan_domain._reference_query_tokens
_topic_tokens = reference_plan_domain._topic_tokens
default_plan_map = reference_plan_domain.default_plan_map
extract_year = reference_plan_domain.extract_year
format_authors = reference_plan_domain.format_authors
normalize_reference_query = reference_plan_domain.normalize_reference_query
visual_value_score_for_section = reference_plan_domain.visual_value_score_for_section


def _expanded_query_tokens(query: str) -> set[str]:
    return topic_domain._expanded_query_tokens(query)


def _source_text_tokens(source: dict) -> set[str]:
    return topic_domain._source_text_tokens(source)


def _query_mentions_ai(query_tokens: set[str]) -> bool:
    return topic_domain._query_mentions_ai(query_tokens)


def _source_looks_ai_related(source: dict) -> bool:
    return topic_domain._source_looks_ai_related(source)


def source_relevance_score(*, query: str, source: dict) -> int:
    return topic_domain.source_relevance_score(query=query, source=source)


def filter_sources_by_topic(
    sources: list[dict],
    *,
    query: str,
    min_score: int = 1,
    allow_unmatched_fallback: bool = False,
) -> list[dict]:
    return topic_domain.filter_sources_by_topic(
        sources,
        query=query,
        min_score=min_score,
        allow_unmatched_fallback=allow_unmatched_fallback,
    )


def sort_reference_sources(
    sources: list[dict],
    *,
    query: str,
    extract_year_fn: Callable[[str], str],
) -> list[dict]:
    return topic_domain.sort_reference_sources(
        sources,
        query=query,
        extract_year_fn=extract_year_fn,
    )


def enrich_sources_with_rag(sources: list[dict]) -> list[dict]:
    if not sources:
        return []
    try:
        from writing_agent.v2.rag.store import RagStore
    except Exception:
        return sources

    repo_root = Path(__file__).resolve().parents[2]
    data_dir = Path(os.environ.get("WRITING_AGENT_DATA_DIR", str(repo_root / ".data"))).resolve()
    rag_dir = data_dir / "rag"
    store = RagStore(rag_dir)
    try:
        papers = store.list_papers()
    except Exception:
        return sources

    paper_map: dict[str, dict] = {}
    for paper in papers:
        paper_map[paper.paper_id] = {
            "paper_id": paper.paper_id,
            "title": paper.title,
            "authors": paper.authors,
            "published": paper.published,
            "updated": paper.updated,
            "abs_url": paper.abs_url,
            "pdf_url": paper.pdf_url,
            "source": paper.source,
        }

    enriched: list[dict] = []
    for source in sources:
        item = dict(source)
        pid = str(source.get("id") or "").strip()
        meta = paper_map.get(pid)
        if meta:
            if not item.get("title"):
                item["title"] = meta.get("title") or item.get("title") or ""
            item["authors"] = meta.get("authors") or item.get("authors") or []
            item["published"] = meta.get("published") or item.get("published") or ""
            item["updated"] = meta.get("updated") or item.get("updated") or ""
            if not item.get("url"):
                item["url"] = meta.get("abs_url") or meta.get("pdf_url") or item.get("url") or ""
            item["source"] = meta.get("source") or item.get("source") or ""
        else:
            item.setdefault("authors", [])
            item.setdefault("published", "")
            item.setdefault("updated", "")
            item.setdefault("source", "")
        enriched.append(item)
    return enriched


def format_reference_items(
    sources: list[dict],
    *,
    extract_year_fn: Callable[[str], str],
    format_authors_fn: Callable[[list[str]], str],
) -> list[str]:
    access_date = date.today().strftime("%Y-%m-%d")
    rows: list[dict] = []
    seen_keys: set[str] = set()
    for source in sources or []:
        title = str(source.get("title") or "").strip()
        if not title:
            title = str(source.get("id") or source.get("url") or "untitled source").strip()
        url = str(source.get("url") or "").strip()
        dedupe_key = (url or title).strip().lower()
        if dedupe_key and dedupe_key in seen_keys:
            continue
        if dedupe_key:
            seen_keys.add(dedupe_key)
        year = extract_year_fn(str(source.get("published") or "")) or extract_year_fn(str(source.get("updated") or ""))
        rows.append(
            {
                "title": title,
                "year": year,
                "authors": source.get("authors") or [],
                "url": url,
                "source": str(source.get("source") or "").strip(),
            }
        )

    out: list[str] = []
    try:
        max_items = max(8, min(64, int(os.environ.get("WRITING_AGENT_MAX_REFERENCE_ITEMS", "24"))))
    except Exception:
        max_items = 24
    for idx, row in enumerate(rows, 1):
        authors = format_authors_fn(row.get("authors") or []) or "Anonymous"
        title = row.get("title") or "untitled source"
        year = row.get("year") or "n.d."
        source = row.get("source") or ""
        url = row.get("url") or ""

        if url:
            core = f"{authors}. {title}[EB/OL]. {year}[{access_date}]. {url}"
        elif source:
            core = f"{authors}. {title}[J]. {source}, {year}."
        else:
            core = f"{authors}. {title}[J]. {year}."
        line = re.sub(r"\s+", " ", core).strip()
        out.append(f"[{idx}] {line}")
        if len(out) >= max_items:
            break
    return out


class ReferenceAgent:
    def __init__(self, *, extract_year_fn: Callable[[str], str], format_authors_fn: Callable[[list[str]], str]) -> None:
        self._extract_year_fn = extract_year_fn
        self._format_authors_fn = format_authors_fn

    def build(self, sources: list[dict]) -> list[str]:
        return format_reference_items(
            sources,
            extract_year_fn=self._extract_year_fn,
            format_authors_fn=self._format_authors_fn,
        )

    def validate(self, lines: list[str]) -> list[str]:
        problems: list[str] = []
        for idx, line in enumerate(lines or [], start=1):
            text = str(line or "").strip()
            if not text:
                problems.append(f"empty_line:{idx}")
                continue
            if not re.match(r"^\[\d+\]\s+", text):
                problems.append(f"bad_prefix:{idx}")
            if re.search(r"(?:本研究|本节|本章|围绕|说明|如下|以上|应当|需要)", text):
                problems.append(f"natural_language_contamination:{idx}")
            if len(text) < 12:
                problems.append(f"too_short:{idx}")
        return problems


from writing_agent.v2.graph_reference_fallback_domain import (
    _fallback_query_seeds,
    _load_cached_reference_sources,
    _reference_cache_dir,
    _reference_cache_path,
    _save_cached_reference_sources,
    _search_crossref_rows,
    _search_openalex_rows,
    fallback_reference_sources,
)


def summarize_evidence(
    *,
    base_url: str,
    model: str,
    section: str,
    analysis_summary: str,
    context: str,
    sources: list[dict],
    require_json_response: Callable[..., dict],
    provider_factory: Callable[..., object] | None = None,
    ollama_client_cls: Callable[..., object] | None = None,
) -> dict:
    if not context.strip():
        return {"facts": [], "missing": []}

    route_base = "remote" if str(base_url or "").strip() else "default"
    if provider_factory is not None:
        client = provider_factory(model=model, timeout_s=120.0, route_key=f"v2.evidence:{section}:{route_base}")
    elif ollama_client_cls is not None:
        client = ollama_client_cls(base_url=base_url, model=model, timeout_s=120.0)
    else:
        raise ValueError("summarize_evidence_requires_provider_factory")
    system = (
        "You are an evidence extraction agent.\n"
        "Treat tagged blocks as separate channels.\n"
        "Return JSON only.\n"
        "Schema: {facts:[{claim:string,source:string}],missing:[string]}.\n"
        "Use only the provided material and provided source ids/urls."
    )

    source_lines = []
    for source in sources:
        label = source.get("url") or source.get("id") or source.get("title") or ""
        title = source.get("title") or ""
        if label:
            source_lines.append(f"- {_escape_prompt_text(title)} | {_escape_prompt_text(label)}".strip())
    sources_block = "\n".join(source_lines) if source_lines else "(none)"

    user = (
        "<task>evidence_extraction</task>\n"
        "<constraints>\n"
        "- Use only provided evidence_material and available_sources.\n"
        "- Return strict JSON only.\n"
        "</constraints>\n"
        f"<section>\n{_escape_prompt_text(section)}\n</section>\n"
        f"<analysis_summary>\n{_escape_prompt_text(analysis_summary)}\n</analysis_summary>\n"
        f"<available_sources>\n{sources_block}\n</available_sources>\n"
        f"<evidence_material>\n{_escape_prompt_text(context)}\n</evidence_material>\n"
        "Return JSON now."
    )

    data = require_json_response(
        client=client,
        system=system,
        user=user,
        stage="evidence",
        temperature=0.15,
        max_retries=max(2, int(os.environ.get("WRITING_AGENT_JSON_RETRIES", "2"))),
    )
    facts = [x for x in (data.get("facts") or []) if isinstance(x, dict)]
    missing = [str(x).strip() for x in (data.get("missing") or []) if str(x).strip()]
    return {"facts": facts, "missing": missing}


def format_evidence_summary(facts: list[dict], sources: list[dict]) -> tuple[str, list[str]]:
    source_map: dict[str, str] = {}
    allowed_urls: list[str] = []
    for source in sources:
        url = str(source.get("url") or "").strip()
        if url:
            source_map[url] = url
            if url not in allowed_urls:
                allowed_urls.append(url)
        sid = str(source.get("id") or "").strip()
        if sid and url:
            source_map[sid] = url
        title = str(source.get("title") or "").strip()
        if title and url:
            source_map[title] = url

    if not facts:
        return "", allowed_urls

    lines = ["\u8bc1\u636e\u8981\u70b9\uff08\u4ec5\u4f7f\u7528\u4e0b\u5217\u4e8b\u5b9e\uff09\uff1a"]
    for item in facts:
        claim = str(item.get("claim") or "").strip()
        src = str(item.get("source") or "").strip()
        if not claim:
            continue

        url = ""
        if src in source_map:
            url = source_map[src]
        elif src.startswith("http"):
            url = src

        if url and url not in allowed_urls:
            allowed_urls.append(url)

        if url:
            lines.append(f"- {claim} (source: {url})")
        else:
            lines.append(f"- {claim}")

    if allowed_urls:
        lines.append("\u53ef\u7528\u6765\u6e90\uff1a")
        for url in allowed_urls:
            lines.append(f"- {url}")

    return "\n".join(lines).strip(), allowed_urls


def select_models_by_memory(
    models: list[str],
    *,
    fallback: str,
    looks_like_embedding_model: Callable[[str], bool],
    ollama_installed_models: Callable[[], set[str]],
    get_memory_bytes: Callable[[], tuple[int, int]],
    ollama_model_sizes_gb: Callable[[], dict[str, float]],
) -> list[str]:
    candidates = [m.strip() for m in (models or []) if m and m.strip()]
    if not candidates:
        return [fallback]

    candidates = [m for m in candidates if not looks_like_embedding_model(m)]
    if not candidates:
        return [fallback]

    installed = ollama_installed_models()
    if installed:
        candidates = [m for m in candidates if m in installed]
    if not candidates:
        return [fallback]

    max_active = int(os.environ.get("WRITING_AGENT_MAX_ACTIVE_MODELS", "3"))
    max_active = max(2, min(8, max_active))
    reserve_gb = float(os.environ.get("WRITING_AGENT_RAM_RESERVE_GB", "6"))
    ratio = float(os.environ.get("WRITING_AGENT_MODEL_BUDGET_RATIO", "0.65"))
    ratio = min(0.95, max(0.2, ratio))

    _, avail_b = get_memory_bytes()
    avail_gb = avail_b / (1024**3)
    budget_gb = max(0.0, (avail_gb - reserve_gb) * ratio)
    if budget_gb <= 0.2:
        return [candidates[0]]

    sizes = ollama_model_sizes_gb()
    out: list[str] = []
    used = 0.0
    for model_name in candidates:
        est = float(sizes.get(model_name, 4.0)) * 1.15
        if not out:
            out.append(model_name)
            used += est
            if len(out) >= max_active:
                break
            continue
        if used + est <= budget_gb and len(out) < max_active:
            out.append(model_name)
            used += est
    return out or [candidates[0]]

