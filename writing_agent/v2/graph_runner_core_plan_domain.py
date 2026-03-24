"""Planning helpers extracted from graph runner core."""

from __future__ import annotations

import json
import os
import re


def _base():
    from writing_agent.v2 import graph_runner_core_domain as base

    return base


def _plan_sections_with_model(
    *,
    base_url: str,
    model: str,
    title: str,
    instruction: str,
    sections: list[str],
    total_chars: int,
    trace_hook=None,
) -> dict:
    if not sections:
        return {}
    base = _base()
    client = base.get_default_provider(model=model, timeout_s=base._plan_timeout_s(), route_key="v2.plan.detail")
    route, prompt_meta = base._route_prompt_for_role(
        role="planner",
        instruction=instruction,
        intent="plan",
    )
    config = base.get_prompt_config("planner", route=route)
    if callable(trace_hook):
        try:
            trace_hook(
                {
                    "event": "prompt_route",
                    "stage": "planner_detail",
                    "metadata": prompt_meta,
                }
            )
        except Exception:
            pass
    system, user = base.PromptBuilder.build_planner_prompt(
        title=title,
        total_chars=total_chars,
        sections=sections,
        instruction=instruction,
        route=route,
    )
    return base._require_json_response(
        client=client,
        system=system,
        user=user,
        stage="plan",
        temperature=config.temperature,
        max_retries=max(2, int(os.environ.get("WRITING_AGENT_JSON_RETRIES", "2"))),
    )


def _plan_sections_list_with_model(
    *,
    base_url: str,
    model: str,
    title: str,
    instruction: str,
    trace_hook=None,
) -> list[str]:
    base = _base()
    client = base.get_default_provider(model=model, timeout_s=base._plan_timeout_s(), route_key="v2.plan.sections")
    catalog = base.section_catalog_text()
    route, route_meta = base._route_prompt_for_role(
        role="planner",
        instruction=instruction,
        intent="plan",
    )
    if callable(trace_hook):
        try:
            trace_hook(
                {
                    "event": "prompt_route",
                    "stage": "planner_sections",
                    "metadata": route_meta,
                }
            )
        except Exception:
            pass
    profile = str(os.environ.get("WRITING_AGENT_QUALITY_PROFILE", "").strip() or "academic_cnki_default")
    include_abstract_keywords = profile == "academic_cnki_default"
    extra_rule = (
        "For academic_cnki_default profile include \u6458\u8981 and \u5173\u952e\u8bcd as mandatory sections."
        if include_abstract_keywords
        else "Do not force \u6458\u8981/\u5173\u952e\u8bcd unless user asks explicitly."
    )
    system = (
        "You are a Chinese academic writing structure planner.\n"
        "Return strict JSON only; no markdown.\n"
        'Schema: {"sections":[string]}.\n'
        "Rules: at most 16 sections, no duplicates, no empty titles; "
        f"{extra_rule} Typical size is 4-12 sections.\n"
        'Example: {"sections":["Introduction","Related Work","Method","Experiments","Conclusion","References"]}'
    )
    custom_system = str(route.payload.get("planner_list_system") or "").strip() if route else ""
    if custom_system:
        system = custom_system
    user = (
        "<task>plan_sections_list</task>\n"
        "<constraints>\n"
        "- Treat tagged blocks as separate channels.\n"
        "- Return strict JSON only.\n"
        "- Use only the provided section catalog where possible.\n"
        "</constraints>\n"
        f"<prompt_route>\n{base._escape_prompt_text(json.dumps(route_meta, ensure_ascii=False))}\n</prompt_route>\n"
        f"<report_title>\n{base._escape_prompt_text(title)}\n</report_title>\n"
        f"<user_requirement>\n{base._escape_prompt_text(instruction)}\n</user_requirement>\n"
        f"<section_catalog>\n{base._escape_prompt_text(catalog)}\n</section_catalog>\n"
        "Return section list JSON now."
    )
    data = base._require_json_response(
        client=client,
        system=system,
        user=user,
        stage="plan_sections",
        temperature=0.2,
        max_retries=max(2, int(os.environ.get("WRITING_AGENT_JSON_RETRIES", "2"))),
    )
    sections = data.get("sections") if isinstance(data, dict) else None
    if not isinstance(sections, list):
        raise ValueError("plan_sections: sections must be list")
    cleaned = base._sanitize_planned_sections(sections)
    return cleaned or ["\u5f15\u8a00", "\u7ed3\u8bba", "\u53c2\u8003\u6587\u732e"]


def _normalize_plan_map(
    *,
    plan_raw: dict,
    sections: list[str],
    base_targets: dict,
    total_chars: int,
) -> dict:
    base = _base()
    return base.graph_plan_domain.normalize_plan_map(
        plan_raw=plan_raw,
        sections=sections,
        base_targets=base_targets,
        total_chars=total_chars,
        default_plan_map=lambda s, b, t: base._default_plan_map(sections=s, base_targets=b, total_chars=t),
        section_title=base._section_title,
        classify_section_type=base._classify_section_type,
        is_reference_section=base._is_reference_section,
        plan_section_cls=base.PlanSection,
    )


def _stabilize_plan_map_minimums(
    *,
    plan_map: dict,
    sections: list[str],
    base_targets: dict,
    total_chars: int,
) -> dict:
    base = _base()
    default_map = base._default_plan_map(sections=sections, base_targets=base_targets, total_chars=total_chars)
    out: dict[str, object] = {}
    method_like_en = re.compile(r"(method|experiment|implementation|result|evaluation)", flags=re.IGNORECASE)
    method_like_canonical = {
        "\u7814\u7a76\u65b9\u6cd5",
        "\u7cfb\u7edf\u8bbe\u8ba1\u4e0e\u5b9e\u73b0",
        "\u5b9e\u9a8c\u8bbe\u8ba1\u4e0e\u7ed3\u679c",
    }

    for sec in sections:
        title = base._section_title(sec) or sec
        cur = plan_map.get(sec)
        dft = default_map.get(sec)
        if cur is None and dft is not None:
            out[sec] = dft
            continue
        if cur is None:
            continue

        key_points = base._dedupe_keep_order([str(x).strip() for x in (cur.key_points or []) if str(x).strip()])
        fallback_kp = [str(x).strip() for x in ((dft.key_points if dft else []) or []) if str(x).strip()]
        if len(key_points) < 2:
            key_points = base._dedupe_keep_order(key_points + fallback_kp)
        if len(key_points) < 2:
            key_points = base._dedupe_keep_order(
                key_points + [f"{title}\u6838\u5fc3\u95ee\u9898", f"{title}\u5173\u952e\u7ed3\u8bba"]
            )

        evidence_queries = base._dedupe_keep_order(
            [str(x).strip() for x in (cur.evidence_queries or []) if str(x).strip()]
        )
        fallback_eq = [str(x).strip() for x in ((dft.evidence_queries if dft else []) or []) if str(x).strip()]
        if not evidence_queries and fallback_eq:
            evidence_queries = base._dedupe_keep_order(evidence_queries + fallback_eq)

        tables = list(cur.tables or [])
        figures = list(cur.figures or [])
        canonical_title = base._canonicalize_section_name(title)
        is_method_like = (canonical_title in method_like_canonical) or bool(method_like_en.search(str(title or "")))
        if is_method_like and not tables and not figures:
            if dft is not None:
                tables = list(dft.tables or [])
                figures = list(dft.figures or [])
            if not tables and not figures:
                figures = [{"type": "flow", "caption": f"{title}\u6d41\u7a0b\u56fe"}]

        target_chars = int(cur.target_chars or (dft.target_chars if dft else 0))
        min_chars = int(cur.min_chars or (dft.min_chars if dft else 0))
        max_chars = int(cur.max_chars or (dft.max_chars if dft else 0))
        if target_chars > 0:
            if base._is_reference_section(title):
                lower = max(220, int(target_chars * 0.6))
                upper = max(lower, int(target_chars * 1.4))
            else:
                lower = max(260, int(target_chars * 0.7))
                upper = max(lower, int(target_chars * 1.35))
            if min_chars <= 0:
                min_chars = lower
            else:
                min_chars = max(lower, min(min_chars, upper))
            if max_chars <= 0:
                max_chars = max(min_chars + 260, int(target_chars * 1.65))
            elif max_chars < min_chars:
                max_chars = min_chars + 260

        out[sec] = base.PlanSection(
            title=str(cur.title or (dft.title if dft else title)),
            target_chars=target_chars,
            min_chars=min_chars,
            max_chars=max_chars,
            min_tables=int(cur.min_tables or (dft.min_tables if dft else 0)),
            min_figures=int(cur.min_figures or (dft.min_figures if dft else 0)),
            key_points=key_points,
            figures=figures,
            tables=tables,
            evidence_queries=evidence_queries,
        )
    return out


__all__ = [name for name in globals() if not name.startswith("__")]
