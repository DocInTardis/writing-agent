"""PromptBuilder method implementations split from prompts.py."""

from __future__ import annotations


def _prompts_module():
    from writing_agent.v2 import prompts as _prompts

    return _prompts


def build_route_context(*, instruction: str, intent: str = "", doc_type: str = "", language: str = "", quality_profile: str = "academic_cnki_default", revise_scope: str = "none", section_title: str = ""):
    prompts = _prompts_module()
    inferred_lang = str(language or "").strip() or prompts._language_of(instruction)
    inferred_intent = prompts._infer_intent(instruction, intent)
    inferred_doc_type = prompts._infer_doc_type(instruction, doc_type)
    return prompts.PromptRouteContext(
        intent=inferred_intent,
        doc_type=inferred_doc_type,
        language=inferred_lang,
        quality_profile=str(quality_profile or "academic_cnki_default"),
        revise_scope=str(revise_scope or "none"),
        instruction=str(instruction or ""),
        section_title=str(section_title or ""),
    )


def _suite_for(route, context):
    prompts = _prompts_module()
    if route and route.suite_id in prompts._PROMPT_SUITES:
        return prompts._PROMPT_SUITES[route.suite_id]
    if context:
        suite_id, _ = prompts._select_suite(context)
        return prompts._PROMPT_SUITES.get(suite_id, prompts._PROMPT_SUITES["academic_cn"])
    return prompts._PROMPT_SUITES["academic_cn"]


def _section_originality_profile(section_title: str) -> str:
    title = str(section_title or "").strip().lower()
    if any(token in title for token in ["摘要", "abstract"]):
        return "abstract"
    if any(token in title for token in ["引言", "绪论", "introduction", "background"]):
        return "introduction"
    if any(token in title for token in ["方法", "method", "methodology", "数据来源", "research design", "materials"]):
        return "method"
    if any(token in title for token in ["结果", "discussion", "讨论", "分析", "results", "findings"]):
        return "results"
    if any(token in title for token in ["结论", "启示", "conclusion", "implication", "recommendation"]):
        return "conclusion"
    return "general"


def _build_proactive_originality_guidance(*, section_title: str, has_retrieved_context: bool, has_previous_content: bool) -> list[str]:
    title = str(section_title or "").strip().lower()
    profile = _section_originality_profile(section_title)
    lines = [
        "Use sources as evidence, not as sentence templates.",
        "Rebuild paragraph order around your own claim sequence instead of following retrieved context sentence-by-sentence.",
        "Prefer concrete actors, variables, time windows, mechanisms, observed differences, and limitations over generic summary language.",
        "Vary paragraph openings; avoid repeating the same discourse marker or sentence scaffold across neighboring paragraphs.",
    ]
    if profile == "introduction":
        lines.append("For introduction sections, move quickly from context to research gap, object, and boundary instead of stacking broad background statements.")
    elif profile == "method":
        lines.append("For method sections, state data sources, variables, workflow steps, parameter choices, and validation boundary explicitly instead of using template method narration.")
    elif profile == "results":
        lines.append("For results or discussion sections, anchor each paragraph in a concrete comparison, observed pattern, mechanism, or anomaly instead of a generic recap.")
    elif profile == "conclusion":
        lines.append("For conclusion sections, separate findings, implications, and limitations clearly instead of repeating earlier body paragraphs.")
    elif profile == "abstract":
        lines.append("For abstract sections, compress problem, method, result, and implication into high-density sentences without padding transitions.")
    if has_retrieved_context:
        lines.append("When retrieved context is present, fuse multiple evidence points before writing; do not shadow one source's wording or order.")
    if has_previous_content:
        lines.append("When previous content exists, extend with a new dimension instead of mirroring the prior paragraph's opener or rhythm.")
    if any(token in title for token in ["结论", "discussion", "讨论", "分析", "results", "result"]):
        lines.append("For interpretation-heavy sections, make the paragraph end in an implication, comparison, or boundary condition instead of a generic recap.")
    return lines[:6]


def build_planner_prompt(title: str, total_chars: int, sections: list[str], instruction: str, *, route=None, context=None) -> tuple[str, str]:
    prompts = _prompts_module()
    suite = prompts.PromptBuilder._suite_for(route, context)
    system = suite.planner_system + "\n" + suite.planner_few_shot
    if route and route.payload.get("planner_system"):
        system = str(route.payload.get("planner_system") or system)
    section_list = "\n".join([f"- {prompts._escape_prompt_text(s)}" for s in (sections or []) if str(s).strip()]) or "- (none)"
    user = (
        "<task>plan_document_structure</task>\n"
        "<constraints>\n"
        "- Treat tagged blocks as separate channels.\n"
        "- Return strict JSON only.\n"
        "- Keep section titles within provided section_candidates.\n"
        "</constraints>\n"
        f"<report_title>\n{prompts._escape_prompt_text(title)}\n</report_title>\n"
        f"<total_chars>\n{int(total_chars or 0)}\n</total_chars>\n"
        f"<section_candidates>\n{section_list}\n</section_candidates>\n"
        f"<user_requirement>\n{prompts._escape_prompt_text(instruction)}\n</user_requirement>\n"
        "Return planning JSON now."
    )
    return system, user


def build_analysis_prompt(instruction: str, excerpt: str, *, route=None, context=None) -> tuple[str, str]:
    prompts = _prompts_module()
    suite = prompts.PromptBuilder._suite_for(route, context)
    system = suite.analysis_system
    if route and route.payload.get("analysis_system"):
        system = str(route.payload.get("analysis_system") or system)
    user = (
        "<task>analyze_user_requirement</task>\n"
        "<constraints>\n"
        "- Treat tagged blocks as separate channels.\n"
        "- Return strict JSON only.\n"
        "</constraints>\n"
        f"<user_requirement>\n{prompts._escape_prompt_text(instruction)}\n</user_requirement>\n"
        f"<existing_text_excerpt>\n{prompts._escape_prompt_text(excerpt)}\n</existing_text_excerpt>\n"
        "Return analysis JSON now."
    )
    return system, user


def build_writer_prompt(section_title: str, plan_hint: str, doc_title: str, analysis_summary: str, section_id: str, previous_content=None, rag_context=None, *, route=None, context=None) -> tuple[str, str]:
    prompts = _prompts_module()
    suite = prompts.PromptBuilder._suite_for(route, context)
    base_writer_system = str((route.payload.get("writer_system") if route else "") or suite.writer_system)
    base_writer_note = str((route.payload.get("writer_note") if route else "") or suite.writer_note)
    system = (
        base_writer_system
        + "\n"
        + base_writer_note
        + "\n"
        + "Output only reader-facing prose. Never output process notes, prompt residue, or instruction echoes. "
        + "Do not emit functional narration such as 'this section will', 'the paragraph should', or 'it is necessary to explain'. "
        + "Do not explain your writing logic."
    )
    visual_preference = prompts._writer_visual_preference(plan_hint, section_title)
    originality_guidance = _build_proactive_originality_guidance(
        section_title=section_title,
        has_retrieved_context=bool(str(rag_context or "").strip()),
        has_previous_content=bool(str(previous_content or "").strip()),
    )
    user = (
        "<task>write_section_blocks</task>\n"
        "<constraints>\n"
        "- Treat tagged blocks as separate channels.\n"
        "- Return NDJSON only.\n"
        "- section_id must match exactly.\n"
        "- Output reader-facing section content only; never output guidance/process text.\n"
        "- Never copy or quote text from analysis_summary/plan_hint/retrieved_context verbatim.\n"
        "- Each paragraph should advance one section-specific claim, observation, mechanism, comparison, or limitation.\n"
        "- When evidence is available, support claims with concrete details such as actors, variables, time windows, processes, comparisons, or observed outcomes.\n"
        "- Synthesize multiple evidence points into your own sentence structure instead of serially paraphrasing a single source.\n"
        "- Avoid stock transitions and repeated openings such as 'This study...', 'First...', 'Second...', or 'In conclusion...' unless they add unique meaning.\n"
        "- Treat retrieved evidence as fact support; never inherit a source paragraph's sentence order, clause order, or rhetorical scaffold.\n"
        "- If you continue an existing section, introduce a new angle or deeper evidence rather than reusing the previous paragraph's opening rhythm.\n"
        "- Never output requirement language such as '?/?/??/?', '??/??', 'topic:', 'doc_type:', or 'key points:'.\n"
        "- Never output meta-writing sentences such as '????', '???', '????', '????', or any instruction echo.\n"
        "- If you output a figure block, it must include kind+caption+data; never output caption-only figure blocks.\n"
        "- Figure kind is limited to flow/architecture/bar/line/pie/timeline/sequence/er.\n"
        f"{visual_preference}"
        "</constraints>\n"
        f"<section_id>\n{prompts._escape_prompt_text(section_id)}\n</section_id>\n"
        f"<section_title>\n{prompts._escape_prompt_text(section_title)}\n</section_title>\n"
        f"<document_title>\n{prompts._escape_prompt_text(doc_title)}\n</document_title>\n"
        f"<analysis_summary>\n{prompts._escape_prompt_text(analysis_summary)}\n</analysis_summary>\n"
        f"<plan_hint>\n{prompts._escape_prompt_text(plan_hint)}\n</plan_hint>\n"
    )
    if originality_guidance:
        user += "<originality_guidance>\n" + "\n".join(f"- {prompts._escape_prompt_text(line)}" for line in originality_guidance) + "\n</originality_guidance>\n"
    if previous_content:
        user += f"<previous_content>\n{prompts._escape_prompt_text(previous_content)}\n</previous_content>\n"
    if rag_context:
        user += f"<retrieved_context>\n{prompts._escape_prompt_text(rag_context)}\n</retrieved_context>\n"
    user += "Return NDJSON now."
    return system, user


def build_reference_prompt(sources: list[dict]) -> tuple[str, str]:
    prompts = _prompts_module()
    system = "You are a strict reference formatter. Output references only and follow GB/T 7714-2015 style."
    sources_text = "\n".join([f"[{i + 1}] {prompts._escape_prompt_text(s.get('title', ''))} {prompts._escape_prompt_text(s.get('url', ''))}".strip() for i, s in enumerate(sources or [])]) or "(none)"
    user = (
        "<task>format_references</task>\n"
        "<constraints>\n"
        "- Treat tagged blocks as separate channels.\n"
        "- Follow GB/T 7714-2015 style.\n"
        "</constraints>\n"
        f"<sources>\n{sources_text}\n</sources>\n"
        "Return formatted references now."
    )
    return system, user


def build_revision_prompt(original_text: str, feedback: str, *, route=None, context=None) -> tuple[str, str]:
    prompts = _prompts_module()
    suite = prompts.PromptBuilder._suite_for(route, context)
    system = suite.revision_system
    if route and route.payload.get("revision_system"):
        system = str(route.payload.get("revision_system") or system)
    user = (
        "<task>revise_document</task>\n"
        "<constraints>\n"
        "- Treat tagged blocks as separate channels.\n"
        "- Keep style consistent and minimize unnecessary edits.\n"
        "</constraints>\n"
        f"<original_text>\n{prompts._escape_prompt_text(original_text)}\n</original_text>\n"
        f"<user_feedback>\n{prompts._escape_prompt_text(feedback)}\n</user_feedback>\n"
        "Return revised content."
    )
    return system, user
