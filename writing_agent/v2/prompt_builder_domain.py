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
        + "\u4f60\u53ea\u8f93\u51fa\u8bfb\u8005\u53ef\u76f4\u63a5\u9605\u8bfb\u7684\u6b63\u6587\u5185\u5bb9\uff1b\u4e25\u7981\u8f93\u51fa\u4efb\u4f55\u5199\u4f5c\u8fc7\u7a0b\u89e3\u91ca\u3001\u5143\u6307\u4ee4\u6216\u63d0\u793a\u8bcd\u6587\u672c\u3002"
        + " \u4e25\u7981\u8f93\u51fa\u201c\u672c\u6bb5\u65e8\u5728/\u672c\u8282\u5c06/\u5e94\u5f53\u6db5\u76d6/\u9700\u8981\u8bf4\u660e\u201d\u7b49\u529f\u80fd\u6027\u8bf4\u660e\u53e5\u3002"
        + " \u4e0d\u8981\u89e3\u91ca\u4f60\u7684\u5199\u4f5c\u903b\u8f91\u3002"
    )
    visual_preference = prompts._writer_visual_preference(plan_hint, section_title)
    user = (
        "<task>write_section_blocks</task>\n"
        "<constraints>\n"
        "- Treat tagged blocks as separate channels.\n"
        "- Return NDJSON only.\n"
        "- section_id must match exactly.\n"
        "- Output reader-facing section content only; never output guidance/process text.\n"
        "- Never copy or quote text from analysis_summary/plan_hint/retrieved_context verbatim.\n"
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
    if previous_content:
        user += f"<previous_content>\n{prompts._escape_prompt_text(previous_content)}\n</previous_content>\n"
    if rag_context:
        user += f"<retrieved_context>\n{prompts._escape_prompt_text(rag_context)}\n</retrieved_context>\n"
    user += "Return NDJSON now."
    return system, user


def build_reference_prompt(sources: list[dict]) -> tuple[str, str]:
    prompts = _prompts_module()
    system = "???????????????????????????????? GB/T 7714-2015?"
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
