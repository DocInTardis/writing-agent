"""Graph runner evidence, references, and fact-pack assembly."""

from __future__ import annotations

from writing_agent.v2.graph_runner_core_domain import *
from writing_agent.v2.graph_runner_analysis_domain import *
from writing_agent.v2.graph_runner_post_domain import _mcp_rag_retrieve, _section_title

from writing_agent.v2 import graph_runner_evidence_support_domain as evidence_support_domain

def _build_evidence_queries(*, section_title: str, plan: PlanSection | None, analysis: dict | None) -> list[str]:
    items: list[str] = []
    if section_title:
        items.append(section_title)
    if plan:
        items.extend([str(x).strip() for x in (plan.evidence_queries or []) if str(x).strip()])
        items.extend([str(x).strip() for x in (plan.key_points or []) if str(x).strip()])
    if isinstance(analysis, dict):
        items.extend([str(x).strip() for x in (analysis.get("keywords") or []) if str(x).strip()])
        topic = str(analysis.get("topic") or "").strip()
        if topic:
            items.append(topic)
    out: list[str] = []
    seen: set[str] = set()
    for it in items:
        if not it or it in seen:
            continue
        seen.add(it)
        out.append(it)
    return out


def _extract_sources_from_context(context: str) -> list[dict]:
    return evidence_support_domain._extract_sources_from_context(context)


def _filter_context_by_sources(context: str, sources: list[dict]) -> str:
    return evidence_support_domain._filter_context_by_sources(context, sources)


def _filter_facts_by_sources(facts: list[dict], sources: list[dict]) -> list[dict]:
    return evidence_support_domain._filter_facts_by_sources(facts, sources)


def _extract_year(text: str) -> str:
    return evidence_support_domain._extract_year(text)


def _format_authors(authors: list[str]) -> str:
    return evidence_support_domain._format_authors(authors)


def _enrich_sources_with_rag(sources: list[dict]) -> list[dict]:
    return evidence_support_domain._enrich_sources_with_rag(sources)


def _collect_reference_sources(evidence_map: dict[str, dict], *, query: str = "") -> list[dict]:
    return evidence_support_domain._collect_reference_sources(evidence_map, query=query)


def _sort_reference_sources(sources: list[dict], *, query: str) -> list[dict]:
    return evidence_support_domain._sort_reference_sources(
        sources,
        query=query,
        extract_year_fn=_extract_year,
    )


def _format_reference_items(sources: list[dict]) -> list[str]:
    return evidence_support_domain._format_reference_items(
        sources,
        extract_year_fn=_extract_year,
        format_authors_fn=_format_authors,
    )


def _validate_reference_items(lines: list[str]) -> list[str]:
    return evidence_support_domain._validate_reference_items(
        lines,
        extract_year_fn=_extract_year,
        format_authors_fn=_format_authors,
    )


def _fallback_reference_sources(*, instruction: str) -> list[dict]:
    return evidence_support_domain._fallback_reference_sources(
        instruction=instruction,
        mcp_rag_retrieve=lambda query, top_k, per_paper, max_chars: _mcp_rag_retrieve(
            query=query,
            top_k=top_k,
            per_paper=per_paper,
            max_chars=max_chars,
        ),
        extract_sources_from_context=_extract_sources_from_context,
        enrich_sources_with_rag_fn=_enrich_sources_with_rag,
        extract_year_fn=_extract_year,
    )


def _summarize_evidence(
    *,
    base_url: str,
    model: str,
    section: str,
    analysis_summary: str,
    context: str,
    sources: list[dict],
) -> dict:
    return evidence_support_domain._summarize_evidence(
        base_url=base_url,
        model=model,
        section=section,
        analysis_summary=analysis_summary,
        context=context,
        sources=sources,
        require_json_response=_require_json_response,
        provider_factory=get_default_provider,
    )


def _format_evidence_summary(facts: list[dict], sources: list[dict]) -> tuple[str, list[str]]:
    return evidence_support_domain._format_evidence_summary(facts, sources)


def _topic_tokens(text: str) -> list[str]:
    return evidence_support_domain._topic_tokens(text)


def _evidence_alignment_score(*, query: str, context: str, sources: list[dict]) -> float:
    return evidence_support_domain._evidence_alignment_score(query=query, context=context, sources=sources)


def _evaluate_data_starvation(*, query: str, section: str, context: str, sources: list[dict]) -> dict[str, object]:
    return evidence_support_domain._evaluate_data_starvation(
        query=query,
        section=section,
        context=context,
        sources=sources,
    )


def _build_evidence_pack(
    *,
    instruction: str,
    section: str,
    analysis: dict | None,
    plan: PlanSection | None,
    base_url: str,
    model: str,
) -> dict:
    enabled_raw = os.environ.get("WRITING_AGENT_EVIDENCE_ENABLED", "1").strip().lower()
    if enabled_raw not in {"1", "true", "yes", "on"}:
        return {"summary": "", "sources": [], "allowed_urls": [], "data_starvation": {"is_starved": False}}
    try:
        from writing_agent.v2.rag.retrieve import retrieve_context
    except Exception:
        return {"summary": "", "sources": [], "allowed_urls": [], "data_starvation": {"is_starved": False}}
    repo_root = Path(__file__).resolve().parents[2]
    data_dir = Path(os.environ.get("WRITING_AGENT_DATA_DIR", str(repo_root / ".data"))).resolve()
    rag_dir = data_dir / "rag"
    queries = _build_evidence_queries(section_title=_section_title(section) or section, plan=plan, analysis=analysis)
    q = " ".join([instruction] + queries).strip()
    top_k = int(os.environ.get("WRITING_AGENT_RAG_TOP_K", "6"))
    max_chars = int(os.environ.get("WRITING_AGENT_RAG_MAX_CHARS", "2800"))
    per_paper = int(os.environ.get("WRITING_AGENT_RAG_PER_PAPER", "2"))
    res = retrieve_context(rag_dir=rag_dir, query=q, top_k=top_k, per_paper=per_paper, max_chars=max_chars)
    context = res.context or ""
    sources = _extract_sources_from_context(context)
    section_gate_dropped: list[dict] = []
    if sources:
        try:
            section_gate_enabled = str(os.environ.get("WRITING_AGENT_RAG_SECTION_GATE_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}
        except Exception:
            section_gate_enabled = True
        if section_gate_enabled:
            try:
                section_min_score = max(0.0, min(1.0, float(os.environ.get("WRITING_AGENT_RAG_SECTION_THEME_MIN_SCORE", "0.35"))))
            except Exception:
                section_min_score = 0.35
            doc_title = str((analysis or {}).get("topic") or instruction).strip()
            section_title = _section_title(section) or section
            gate_result = rag_gate.filter_sources_for_section(
                document_title=doc_title,
                section_title=section_title,
                sources=sources,
                min_theme_score=max(0.18, min(1.0, float(os.environ.get("WRITING_AGENT_RAG_THEME_MIN_SCORE", "0.25")))),
                min_section_score=section_min_score,
                mode="strict",
            )
            section_gate_dropped = [row for row in (gate_result.get("dropped") or []) if isinstance(row, dict)]
            sources = [row for row in (gate_result.get("kept") or []) if isinstance(row, dict)]
            context = _filter_context_by_sources(context, sources)
    starvation = _evaluate_data_starvation(
        query=q,
        section=_section_title(section) or section,
        context=context,
        sources=sources,
    )
    fail_on_starvation = str(os.environ.get("WRITING_AGENT_RAG_DATA_STARVATION_FAIL", "0")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if bool(starvation.get("is_starved")):
        starvation["status"] = "failed" if fail_on_starvation else "warning"
        starvation["warning"] = "Data_Deficit_Warning"
        starvation["stub_mode"] = True
        return {
            "summary": "",
            "sources": sources,
            "allowed_urls": [],
            "data_starvation": starvation,
            "context": context,
            "facts": [],
            "fact_gain_count": 0,
            "fact_density_score": 0.0,
            "online_hits": int(getattr(res, "online_hits", 0) or 0),
            "section_gate_dropped": section_gate_dropped,
        }
    summary_data = _summarize_evidence(
        base_url=base_url,
        model=model,
        section=section,
        analysis_summary=_format_analysis_summary(analysis or {}, fallback=instruction),
        context=context,
        sources=sources,
    )
    facts = [x for x in (summary_data.get("facts") or []) if isinstance(x, dict)]
    facts = _filter_facts_by_sources(facts, sources)
    summary_text, allowed_urls = _format_evidence_summary(facts, sources)
    fact_gain_count = len(facts)
    fact_density_score = round(float(fact_gain_count) / float(max(1, len(sources))), 4)
    starvation["status"] = "ok"
    starvation["stub_mode"] = False
    return {
        "summary": summary_text,
        "sources": sources,
        "allowed_urls": allowed_urls,
        "data_starvation": starvation,
        "facts": facts,
        "fact_gain_count": fact_gain_count,
        "fact_density_score": fact_density_score,
        "online_hits": int(getattr(res, "online_hits", 0) or 0),
        "section_gate_dropped": section_gate_dropped,
    }


def _format_plan_hint(plan: PlanSection | None) -> str:
    if not plan:
        return ""
    payload: dict[str, object] = {}
    # Avoid leaking writing-guide style descriptors into drafter input.
    payload["section_title"] = str(plan.title or "").strip()
    payload["target_chars"] = int(plan.target_chars or 0)
    if plan.key_points:
        clean_points: list[str] = []
        for raw in plan.key_points:
            token = str(raw or "").strip()
            if not token:
                continue
            if _meta_firewall_scan(token):
                continue
            clean_points.append(token)
            if len(clean_points) >= 6:
                break
        if clean_points:
            payload["key_points"] = clean_points
    if plan.evidence_queries:
        payload["evidence_queries"] = [str(x).strip() for x in plan.evidence_queries if str(x).strip()][:6]
    visual_priority = graph_reference_domain.visual_value_score_for_section(
        str(plan.title or "").strip(),
        is_reference=_is_reference_section(str(plan.title or "").strip()),
        section_type=_classify_section_type(str(plan.title or "").strip()),
    )
    payload["visual_priority"] = visual_priority
    if plan.figures:
        fig_items: list[dict[str, str]] = []
        for f in plan.figures:
            f_type = str(f.get("type") or "").strip()
            cap = str(f.get("caption") or "").strip()
            if f_type or cap:
                fig_items.append({"type": f_type or "figure", "caption": cap})
        if fig_items:
            payload["figures"] = fig_items
    if plan.tables:
        tab_items = [str(t.get("caption") or "").strip() for t in plan.tables if str(t.get("caption") or "").strip()]
        if tab_items:
            payload["tables"] = tab_items
    return json.dumps(payload, ensure_ascii=False)


def _sync_plan_media(plan_map: dict[str, PlanSection], targets: dict[str, SectionTargets]) -> dict[str, PlanSection]:
    out: dict[str, PlanSection] = {}
    for sec, plan in plan_map.items():
        t = targets.get(sec)
        if not t:
            out[sec] = plan
            continue
        min_tables = max(plan.min_tables, int(t.min_tables))
        min_figures = max(plan.min_figures, int(t.min_figures))
        if min_tables == plan.min_tables and min_figures == plan.min_figures:
            out[sec] = plan
            continue
        out[sec] = PlanSection(
            title=plan.title,
            target_chars=plan.target_chars,
            min_chars=plan.min_chars,
            max_chars=plan.max_chars,
            min_tables=min_tables,
            min_figures=min_figures,
            key_points=plan.key_points,
            figures=plan.figures,
            tables=plan.tables,
            evidence_queries=plan.evidence_queries,
        )
    return out


def _section_body_len(text: str) -> int:
    if not text:
        return 0
    body = re.sub(r"\[\[(?:FIGURE|TABLE)\s*:\s*\{[\s\S]*?\}\s*\]\]", "", text, flags=re.IGNORECASE)
    return len(body.strip())


def _doc_body_len(text: str) -> int:
    if not text:
        return 0
    body = re.sub(r"(?m)^#{1,6}\s+.+$", "", text or "")
    return _section_body_len(body)


def _count_text_chars(text: str) -> int:
    if not text:
        return 0
    return len(str(text).strip())


def _truncate_to_chars(text: str, max_chars: int) -> str:
    if not text or max_chars <= 0:
        return ""
    s = str(text).strip()
    if len(s) <= max_chars:
        return s
    clipped = s[:max_chars]
    # Prefer cutting at a sentence boundary if possible.
    for sep in ["。", "！", "？", ".", "!", "?", ";"]:
        idx = clipped.rfind(sep)
        if idx >= max(0, int(max_chars * 0.5)):
            return clipped[: idx + 1].strip()
    return clipped.strip()


def _blocks_to_doc_text(blocks: list[DocBlock]) -> str:
    if not blocks:
        return ""
    out: list[str] = []
    for b in blocks:
        if b.type == "heading":
            level = b.level or 1
            out.append(f"{'#' * level} {(b.text or '').strip()}")
        elif b.type == "paragraph":
            out.append((b.text or "").strip())
        elif b.type == "table":
            out.append("[[TABLE:{}]]".format(json.dumps(b.table or {}, ensure_ascii=False)))
        elif b.type == "figure":
            out.append("[[FIGURE:{}]]".format(json.dumps(b.figure or {}, ensure_ascii=False)))
    return "\n\n".join([s for s in out if s])


def _validate_plan_results(
    *,
    base_url: str,
    model: str,
    title: str,
    instruction: str,
    sections: list[str],
    plan_map: dict[str, PlanSection],
    section_text: dict[str, str],
) -> list[dict]:
    _ = (base_url, model, title, instruction)
    if not sections:
        return []

    issues: list[dict] = []
    for sec in sections:
        plan = plan_map.get(sec)
        if not plan:
            continue
        chars = _section_body_len(section_text.get(sec) or "")
        if chars < int(plan.min_chars):
            issues.append({"title": plan.title or sec, "issue": "short", "action": "expand"})
        elif int(plan.max_chars) > 0 and chars > int(plan.max_chars):
            issues.append({"title": plan.title or sec, "issue": "long", "action": "trim"})
    return issues


def _load_support_section_keywords() -> list[str]:
    raw = os.environ.get("WRITING_AGENT_SUPPORT_SECTIONS", "").strip()
    if raw:
        return _split_csv_env(raw)
    return ["引言", "背景", "相关", "综述", "文献", "参考", "绪论", "概述"]


def _is_support_section(section: str, keywords: list[str]) -> bool:
    s = (_section_title(section) or "").strip()
    if not s:
        return False
    for k in keywords:
        if k and k in s:
            return True
    return False

__all__ = [name for name in globals() if not name.startswith("__")]
