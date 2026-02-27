"""Graph Reference Domain module.

This module belongs to `writing_agent.v2` in the writing-agent codebase.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Callable


def default_plan_map(
    *,
    sections: list[str],
    base_targets: dict,
    total_chars: int,
    compute_section_weights: Callable[[list[str]], dict[str, float]],
    section_title: Callable[[str], str],
    is_reference_section: Callable[[str], bool],
    classify_section_type: Callable[[str], str],
    plan_section_cls,
) -> dict:
    weights = compute_section_weights(sections)
    denom = sum(weights.values()) or 1.0
    plan: dict = {}
    for sec in sections:
        title = section_title(sec) or sec
        share = int(round(float(total_chars) * (weights.get(sec, 1.0) / denom)))
        target = max(200, share)
        if is_reference_section(title):
            target = max(220, min(1200, target))
        section_type = classify_section_type(title)
        if section_type == "intro":
            min_chars = max(400, int(round(target * 1.2)))
            max_chars = max(min_chars + 300, int(round(target * 1.6)))
        elif section_type == "method":
            min_chars = max(800, int(round(target * 2.0)))
            max_chars = max(min_chars + 600, int(round(target * 2.5)))
        elif section_type == "conclusion":
            min_chars = max(500, int(round(target * 1.5)))
            max_chars = max(min_chars + 400, int(round(target * 1.9)))
        else:
            min_chars = max(500, int(round(target * 1.4)))
            max_chars = max(min_chars + 400, int(round(target * 1.8)))
        target_row = base_targets.get(sec)
        min_tables = int(target_row.min_tables) if target_row else 0
        min_figures = int(target_row.min_figures) if target_row else 0
        plan[sec] = plan_section_cls(
            title=title,
            target_chars=target,
            min_chars=min_chars,
            max_chars=max_chars,
            min_tables=min_tables,
            min_figures=min_figures,
            key_points=[],
            figures=[],
            tables=[],
            evidence_queries=[],
        )
    return plan


def extract_year(text: str) -> str:
    value = (text or "").strip()
    if not value:
        return ""
    match = re.search(r"(19|20)\d{2}", value)
    return match.group(0) if match else ""


def format_authors(authors: list[str]) -> str:
    cleaned = [a.strip() for a in (authors or []) if str(a).strip()]
    if not cleaned:
        return ""
    if len(cleaned) <= 3:
        return ", ".join(cleaned)
    return f"{', '.join(cleaned[:3])} et al."


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
    rows: list[dict] = []
    for source in sources or []:
        title = str(source.get("title") or "").strip()
        if not title:
            title = str(source.get("id") or source.get("url") or "untitled source").strip()
        year = extract_year_fn(str(source.get("published") or "")) or extract_year_fn(str(source.get("updated") or ""))
        rows.append(
            {
                "title": title,
                "year": year,
                "authors": source.get("authors") or [],
                "url": str(source.get("url") or "").strip(),
                "source": str(source.get("source") or "").strip(),
            }
        )

    out: list[str] = []
    for idx, row in enumerate(rows, 1):
        authors = format_authors_fn(row.get("authors") or [])
        title = row.get("title") or "untitled source"
        year = row.get("year") or ""
        source = row.get("source") or ""
        url = row.get("url") or ""

        parts = []
        if authors:
            parts.append(f"{authors}.")
        parts.append(f"{title}.")
        if source:
            parts.append(f"{source}.")
        if year:
            parts.append(f"{year}.")
        if url:
            parts.append(f"URL: {url}")
        line = " ".join([p for p in parts if p]).strip()
        out.append(f"[{idx}] {line}")
        if len(out) >= 12:
            break
    return out


def fallback_reference_sources(
    *,
    instruction: str,
    mcp_rag_retrieve: Callable[..., tuple[str, list[dict]]],
    extract_sources_from_context: Callable[[str], list[dict]],
    enrich_sources_with_rag_fn: Callable[[list[dict]], list[dict]],
    extract_year_fn: Callable[[str], str],
) -> list[dict]:
    query = (instruction or "").strip()
    if not query:
        return []
    top_k = int(os.environ.get("WRITING_AGENT_RAG_TOP_K", "6"))
    max_chars = int(os.environ.get("WRITING_AGENT_RAG_MAX_CHARS", "2800"))
    per_paper = int(os.environ.get("WRITING_AGENT_RAG_PER_PAPER", "2"))

    context, srcs = mcp_rag_retrieve(query=query, top_k=top_k, per_paper=per_paper, max_chars=max_chars)
    if srcs:
        return enrich_sources_with_rag_fn(srcs)
    if context.strip():
        sources = extract_sources_from_context(context)
        enriched = enrich_sources_with_rag_fn(sources)
        if enriched:
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
    if enriched:
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
    for paper in papers[:12]:
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
    return enrich_sources_with_rag_fn(rows)


def summarize_evidence(
    *,
    base_url: str,
    model: str,
    section: str,
    analysis_summary: str,
    context: str,
    sources: list[dict],
    require_json_response: Callable[..., dict],
    ollama_client_cls,
) -> dict:
    if not context.strip():
        return {"facts": [], "missing": []}

    client = ollama_client_cls(base_url=base_url, model=model, timeout_s=120.0)
    system = (
        "You are an evidence extraction agent. Return JSON only.\n"
        "Schema: {facts:[{claim:string,source:string}],missing:[string]}.\n"
        "Use only the provided material and provided source ids/urls."
    )

    source_lines = []
    for source in sources:
        label = source.get("url") or source.get("id") or source.get("title") or ""
        title = source.get("title") or ""
        if label:
            source_lines.append(f"- {title} | {label}".strip())
    sources_block = "\n".join(source_lines) if source_lines else "(none)"

    user = (
        f"section: {section}\n"
        f"analysis summary:\n{analysis_summary}\n\n"
        f"available sources:\n{sources_block}\n\n"
        f"evidence material:\n{context}\n\n"
        "Return JSON only."
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

    lines = ["Evidence notes (use only listed facts):"]
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
        lines.append("Available sources:")
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
