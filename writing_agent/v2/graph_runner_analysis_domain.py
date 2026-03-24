"""Graph runner analysis normalization and guards."""

from __future__ import annotations

from writing_agent.v2.graph_runner_core_domain import *
from writing_agent.v2.graph_reference_domain import _topic_tokens

def _analyze_instruction(
    *,
    base_url: str,
    model: str,
    instruction: str,
    current_text: str,
    trace_hook=None,
) -> dict:
    fast_raw = os.environ.get("WRITING_AGENT_ANALYSIS_FAST", "").strip().lower()
    force_fast = fast_raw in {"force", "always"}
    if force_fast or fast_raw in {"1", "true", "yes", "on"}:
        if force_fast or (len((instruction or "").strip()) <= 120 and not (current_text or "").strip()):
            return _normalize_analysis_for_generation({"topic": (instruction or "").strip(), "doc_type": _resolve_doc_type_for_prompt(instruction)}, instruction)
    client = get_default_provider(model=model, timeout_s=_analysis_timeout_s(), route_key="v2.analysis")
    route, prompt_meta = _route_prompt_for_role(
        role="analysis",
        instruction=instruction,
        intent="analyze",
    )
    config = get_prompt_config("analysis", route=route)
    if callable(trace_hook):
        try:
            trace_hook(
                {
                    "event": "prompt_route",
                    "stage": "analysis",
                    "metadata": prompt_meta,
                }
            )
        except Exception:
            pass
    excerpt = _truncate_text(current_text or "", max_chars=800)
    system, user = PromptBuilder.build_analysis_prompt(
        instruction=instruction,
        excerpt=excerpt,
        route=route,
    )
    out = _require_json_response(
        client=client,
        system=system,
        user=user,
        stage="analysis",
        temperature=config.temperature,
        max_retries=max(2, int(os.environ.get("WRITING_AGENT_JSON_RETRIES", "2"))),
    )
    normalized = _normalize_analysis_for_generation(out, instruction)
    if _analysis_strict_schema_enabled() and not bool(normalized.get("_schema_valid")):
        raise ValueError(
            "analysis_schema_invalid:"
            + ",".join([str(x) for x in (normalized.get("_schema_missing") or []) if str(x).strip()])
        )
    if float(normalized.get("_confidence_score") or 0.0) < _analysis_conf_threshold():
        questions = [str(x).strip() for x in (normalized.get("_clarification_questions") or []) if str(x).strip()]
        normalized["_needs_clarification"] = True
        normalized["_clarification_questions"] = questions
    else:
        normalized["_needs_clarification"] = False
    return normalized


def _analysis_strict_schema_enabled() -> bool:
    raw = str(os.environ.get("WRITING_AGENT_ANALYSIS_STRICT_SCHEMA", "1")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _analysis_conf_threshold() -> float:
    raw = str(os.environ.get("WRITING_AGENT_ANALYSIS_CONF_THRESHOLD", "0.62")).strip()
    try:
        return max(0.0, min(1.0, float(raw)))
    except Exception:
        return 0.62


from writing_agent.v2.graph_runner_analysis_requirements_domain import (
    _canonicalize_section_name,
    _dedupe_keep_order,
    _merge_required_sections_from_analysis,
    _normalize_analysis_for_generation,
    _normalize_must_include_sections,
)


def _analysis_correctness_guard(
    *,
    analysis: dict | None,
    instruction: str,
    sections: list[str],
    section_title: Callable[[str], str],
    is_reference_section: Callable[[str], bool],
) -> tuple[bool, list[str], dict]:
    obj = analysis if isinstance(analysis, dict) else {}
    reasons: list[str] = []
    titles = [str(section_title(s) or s).strip() for s in (sections or []) if str(section_title(s) or s).strip()]
    canonical_titles = [_canonicalize_section_name(t) for t in titles]
    canonical_title_set = {str(x).strip() for x in canonical_titles if str(x).strip()}
    body_titles = [t for t in titles if not is_reference_section(t)]
    paradigm = str(obj.get("_paradigm") or "").strip().lower()

    lang = instruction_language(instruction)
    expected_zh = str(lang).lower().startswith("zh")
    if expected_zh and titles:
        zh_count = 0
        for title in titles:
            if any("\u4e00" <= ch <= "\u9fff" for ch in title):
                zh_count += 1
        zh_ratio = zh_count / float(max(1, len(titles)))
        if zh_ratio < 0.6:
            reasons.append("section_language_mismatch")

    doc_type = str(obj.get("doc_type") or "").strip().lower()
    if doc_type in {"academic", "thesis", "paper"} and len(body_titles) < 4:
        reasons.append("section_hierarchy_insufficient")

    must_include_raw = obj.get("must_include")
    must_include_items = [str(x).strip() for x in must_include_raw] if isinstance(must_include_raw, list) else []
    must_include_items = [x for x in must_include_items if x]
    constraints_raw = obj.get("constraints")
    constraints_items = [str(x).strip() for x in constraints_raw] if isinstance(constraints_raw, list) else []
    constraints_items = [x for x in constraints_items if x]
    force_required_outline_only = bool(obj.get("_force_required_outline_only"))
    if force_required_outline_only:
        must_include = _dedupe_keep_order([x for x in must_include_items if x])
    else:
        must_include = _normalize_must_include_sections(
            must_include_raw=must_include_items,
            constraints_raw=constraints_items,
            instruction=instruction,
            doc_type=doc_type,
        )
    if (paradigm == "bibliometric" or _is_bibliometric_instruction(instruction)) and not _user_explicitly_requests_engineering_sections(
        instruction
    ):
        # Bibliometric mode is physically isolated to a fixed section spine; ignore
        # model-side must_include drift (e.g. "相关研究"/"研究方法") to avoid false hard-fail.
        biblio_allowed = {_canonicalize_section_name(x) for x in _bibliometric_section_spine()}
        must_include = [x for x in must_include if _canonicalize_section_name(x) in biblio_allowed]
    missing_required: list[str] = []
    for item in must_include:
        c_item = _canonicalize_section_name(item)
        if not c_item:
            continue
        if c_item in canonical_title_set:
            continue
        if any(c_item in title for title in titles):
            continue
        missing_required.append(c_item)
    if missing_required:
        reasons.append("must_include_missing")

    if (paradigm == "bibliometric" or _is_bibliometric_instruction(instruction)) and not _user_explicitly_requests_engineering_sections(instruction):
        expected_biblio = [
            "数据来源与检索策略",
            "发文量时空分布",
            "作者与机构合作网络",
            "关键词共现与聚类分析",
            "研究热点演化与突现分析",
        ]
        canonical_expected = {_canonicalize_section_name(x) for x in expected_biblio}
        if not any(x in canonical_title_set for x in canonical_expected):
            reasons.append("bibliometric_structure_mismatch")
        if any(
            re.search(r"(绯荤粺|鏋舵瀯|瀹炵幇|宸ョ▼|deployment|api|module|architecture|implementation)", t, flags=re.IGNORECASE)
            for t in titles
        ):
            reasons.append("paradigm_conflict")

    keywords_raw = obj.get("keywords")
    keywords = [str(x).strip() for x in keywords_raw] if isinstance(keywords_raw, list) else []
    keywords = [x for x in keywords if x]
    strict_keyword_title_match = str(os.environ.get("WRITING_AGENT_KEYWORD_SECTION_MATCH_STRICT", "0")).strip().lower() in {"1", "true", "yes", "on"}
    keyword_title_match_count = 0
    if keywords and body_titles:
        matched = 0
        for key in keywords:
            if any(key in title for title in body_titles):
                matched += 1
        keyword_title_match_count = matched
        if strict_keyword_title_match and matched == 0:
            reasons.append("keyword_domain_mismatch")

    meta = {
        "lang": lang,
        "paradigm": paradigm,
        "doc_type": doc_type,
        "section_count": len(titles),
        "body_section_count": len(body_titles),
        "section_titles": titles[:20],
        "section_titles_canonical": canonical_titles[:20],
        "must_include_missing": missing_required[:8],
        "keywords": keywords[:8],
        "keyword_title_match_count": keyword_title_match_count,
        "keyword_title_match_strict": strict_keyword_title_match,
    }
    return (len(reasons) == 0), reasons, meta


def _format_analysis_summary(analysis: dict, *, fallback: str) -> str:
    if not isinstance(analysis, dict) or not analysis:
        return (fallback or "").strip()

    lines: list[str] = []

    def _add(label: str, value: object) -> None:
        val = str(value or "").strip()
        if val:
            lines.append(f"{label}: {val}")

    def _add_list(label: str, values: list[str], limit: int = 10) -> None:
        items = [str(x).strip() for x in values if str(x).strip()]
        if items:
            lines.append(f"{label}: " + "、".join(items[:limit]))

    _add("topic", analysis.get("topic"))
    _add("doc_type", analysis.get("doc_type"))
    _add("audience", analysis.get("audience"))
    _add("style", analysis.get("style"))
    _add_list("keywords", list(analysis.get("keywords") or []))
    _add_list("must_include", list(analysis.get("must_include") or []))
    _add_list("avoid_sections", list(analysis.get("avoid_sections") or []))
    _add_list("constraints", list(analysis.get("constraints") or []))
    _add_list("questions", list(analysis.get("questions") or []), limit=6)

    return "\n".join(lines).strip() or (fallback or "").strip()


def _format_writer_requirement(analysis: dict, *, fallback: str) -> str:
    """Compact writer-facing brief without process labels like topic:/key points:."""

    if not isinstance(analysis, dict) or not analysis:
        return (fallback or "").strip()
    topic = str(analysis.get("topic") or "").strip()
    doc_type = str(analysis.get("doc_type") or "").strip()
    style = str(analysis.get("style") or "").strip()
    keywords = [str(x).strip() for x in (analysis.get("keywords") or []) if str(x).strip()]
    parts: list[str] = []
    if topic:
        parts.append(f"主题“{topic}”")
    if doc_type:
        parts.append(f"文体{doc_type}")
    if style:
        parts.append(f"语体要求{style}")
    if keywords:
        parts.append("关键词" + "、".join(keywords[:6]))
    parts.append("只输出可直接阅读的正文，不输出过程说明或写作指导")
    brief = "；".join(parts).strip("；")

__all__ = [name for name in globals() if not name.startswith("__")]
