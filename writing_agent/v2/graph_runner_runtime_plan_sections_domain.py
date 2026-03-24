"""Runtime helpers for resolving section plan state."""

from __future__ import annotations

def _base():
    from writing_agent.v2 import graph_runner_runtime_session_domain as base

    return base


def resolve_section_plan_state(
    runtime_api,
    *,
    instruction: str,
    current_text: str,
    required_h2: list[str] | None,
    required_outline: list[tuple[int, str]] | None,
    expand_outline: bool,
    analysis: dict,
    analysis_summary: str,
    paradigm_decision: dict,
    forced_sections: list[str],
    settings,
    agg_model: str,
    capture_prompt_trace,
    prompt_events: list[dict],
):
    base = _base()
    wants_ack = runtime_api._wants_acknowledgement(instruction)
    if required_outline:
        required_outline = runtime_api._filter_ack_outline(required_outline, allow_ack=wants_ack)
        required_outline = runtime_api._filter_disallowed_outline(required_outline)
        required_outline = runtime_api._sanitize_outline(required_outline)
    if required_h2:
        required_h2 = runtime_api._filter_ack_headings(required_h2, allow_ack=wants_ack)
        required_h2 = runtime_api._filter_disallowed_sections(required_h2)

    title = runtime_api._plan_title(current_text=current_text, instruction=instruction)
    sections: list[str] = []
    plan_sections_fallback_emitted = False
    if required_outline:
        sections, required_h2_effective = runtime_api._sections_from_outline(required_outline, expand=expand_outline)
        if required_h2_effective:
            required_h2 = [
                runtime_api._clean_outline_title(x)
                for x in required_h2_effective
                if runtime_api._clean_outline_title(x)
            ]
        sections = runtime_api._sanitize_section_tokens(sections, keep_full_titles=True)
    if (not sections) and required_h2:
        _title, sections = runtime_api._plan_title_sections(
            current_text=current_text,
            instruction=instruction,
            required_h2=required_h2,
        )
    if forced_sections:
        sections = runtime_api._sanitize_section_tokens(forced_sections, keep_full_titles=True)
    if not sections:
        fast_plan_sections = runtime_api._sanitize_section_tokens(
            list(runtime_api._fast_plan_sections_for_instruction(instruction) or []),
            keep_full_titles=True,
        )
        used_plan_fallback = False
        if base._env_flag("WRITING_AGENT_FAST_PLAN", "0"):
            sections = fast_plan_sections
            used_plan_fallback = True
        else:
            try:
                sections = runtime_api._sanitize_section_tokens(
                    list(
                        runtime_api._plan_sections_list_with_model(
                            base_url=settings.base_url,
                            model=agg_model,
                            title=title,
                            instruction=analysis_summary or instruction,
                            trace_hook=capture_prompt_trace,
                        )
                        or []
                    ),
                    keep_full_titles=True,
                )
            except Exception as exc:
                sections = fast_plan_sections
                used_plan_fallback = True
                plan_sections_fallback_emitted = True
                yield {
                    "event": "plan_sections_fallback",
                    "reason": str(exc)[:240],
                    "sections": [
                        str(runtime_api._section_title(s) or s).strip()
                        for s in sections
                        if str(runtime_api._section_title(s) or s).strip()
                    ],
                }
            if (not used_plan_fallback) and sections == fast_plan_sections:
                plan_sections_fallback_emitted = True
                yield {
                    "event": "plan_sections_fallback",
                    "reason": "planner_defaulted_to_fast_outline",
                    "sections": [
                        str(runtime_api._section_title(s) or s).strip()
                        for s in sections
                        if str(runtime_api._section_title(s) or s).strip()
                    ],
                }
        yield from base._flush_trace(prompt_events)

    if (
        (not plan_sections_fallback_emitted)
        and (not required_outline)
        and (not required_h2)
        and (not base._env_flag("WRITING_AGENT_FAST_PLAN", "0"))
    ):
        fast_plan_sections_probe = runtime_api._sanitize_section_tokens(
            list(runtime_api._fast_plan_sections_for_instruction(instruction) or []),
            keep_full_titles=True,
        )
        if sections == fast_plan_sections_probe:
            yield {
                "event": "plan_sections_fallback",
                "reason": "post_plan_fast_outline_match",
                "sections": [
                    str(runtime_api._section_title(s) or s).strip()
                    for s in sections
                    if str(runtime_api._section_title(s) or s).strip()
                ],
            }

    paradigm_name = str(analysis.get("_paradigm") or paradigm_decision.get("paradigm") or "").strip()
    force_required_outline_only = bool(required_outline or required_h2) and any(
        base._env_flag(name, "0")
        for name in ("WRITING_AGENT_FORCE_REQUIRED_OUTLINE_ONLY", "WRITING_AGENT_REQUIRED_OUTLINE_ONLY")
    )
    if force_required_outline_only:
        locked_sections = runtime_api._sanitize_section_tokens(list(sections or []), keep_full_titles=True)
        analysis["must_include"] = [
            str(runtime_api._section_title(sec) or sec).strip()
            for sec in locked_sections
            if str(runtime_api._section_title(sec) or sec).strip()
        ]
        analysis["_force_required_outline_only"] = True
        sections = locked_sections
        yield {
            "event": "required_outline_lock",
            "enabled": True,
            "sections": [
                str(runtime_api._section_title(sec) or sec).strip()
                for sec in sections
                if str(runtime_api._section_title(sec) or sec).strip()
            ],
        }
    else:
        sections = runtime_api._merge_required_sections_from_analysis(
            sections=sections,
            analysis=analysis,
            instruction=instruction,
        )
        if paradigm_name:
            sections = runtime_api._enforce_paradigm_sections(
                sections=sections,
                paradigm=paradigm_name,
                instruction=instruction,
            )

    return {
        "required_h2": list(required_h2 or []),
        "required_outline": list(required_outline or []),
        "title": title,
        "sections": list(sections or []),
        "paradigm_name": paradigm_name,
        "force_required_outline_only": force_required_outline_only,
    }



__all__ = [name for name in globals() if not name.startswith("__")]
