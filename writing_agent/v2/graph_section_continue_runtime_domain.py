"""Section continuation runtime orchestration helpers."""

from __future__ import annotations

import os
import queue
from collections.abc import Callable

from writing_agent.v2.graph_section_continue_segment_domain import _continue_with_optional_segments
from writing_agent.v2 import graph_section_continue_helpers_domain as helpers_domain
from writing_agent.v2 import graph_section_continue_prompt_domain as prompt_domain

normalize_section_id = helpers_domain.normalize_section_id
_section_body_len = helpers_domain._section_body_len
_has_incomplete_paragraph = helpers_domain._has_incomplete_paragraph
_ensure_paragraph_integrity = helpers_domain._ensure_paragraph_integrity
_section_minimum_satisfied = helpers_domain._section_minimum_satisfied

def ensure_section_minimums_stream(
    *,
    base_url: str,
    model: str,
    title: str,
    section: str,
    parent_section: str,
    instruction: str,
    analysis_summary: str,
    evidence_summary: str,
    allowed_urls: list[str],
    plan_hint: str,
    dimension_hints: list[str] | None,
    draft: str,
    min_paras: int,
    min_chars: int,
    max_chars: int,
    min_tables: int,
    min_figures: int,
    out_queue: queue.Queue[dict],
    postprocess_section: Callable[..., str],
    stream_structured_blocks: Callable[..., str],
    normalize_section_id: Callable[[str], str],
    predict_num_tokens: Callable[[int, int, bool], int],
    is_reference_section: Callable[[str], bool],
    section_timeout_s: Callable[[], float],
    provider_factory: Callable[..., object],
) -> str:
    _ = base_url
    txt = postprocess_section(
        section,
        draft,
        min_paras=min_paras,
        min_chars=min_chars,
        max_chars=max_chars,
        min_tables=min_tables,
        min_figures=min_figures,
    )
    incomplete = _has_incomplete_paragraph(txt)
    if _section_minimum_satisfied(text=txt, min_paras=min_paras, min_chars=min_chars) and not incomplete:
        return _ensure_paragraph_integrity(txt)

    rounds = max(0, min(4, int(os.environ.get("WRITING_AGENT_SECTION_CONTINUE_ROUNDS", "3"))))
    if rounds <= 0:
        return _ensure_paragraph_integrity(txt)

    section_id = normalize_section_id(section)
    for attempt in range(1, rounds + 1):
        body_len = _section_body_len(txt)
        missing_chars = max(0, int(min_chars) - body_len) if min_chars > 0 else 0
        txt = _continue_with_optional_segments(
            model=model,
            title=title,
            section=section,
            parent_section=parent_section,
            instruction=instruction,
            analysis_summary=analysis_summary,
            evidence_summary=evidence_summary,
            allowed_urls=allowed_urls,
            plan_hint=plan_hint,
            dimension_hints=dimension_hints,
            txt=txt,
            section_id=section_id,
            min_paras=min_paras,
            min_chars=min_chars,
            max_chars=max_chars,
            min_tables=min_tables,
            min_figures=min_figures,
            out_queue=out_queue,
            stream_structured_blocks=stream_structured_blocks,
            predict_num_tokens=predict_num_tokens,
            is_reference_section=is_reference_section,
            section_timeout_s=section_timeout_s,
            provider_factory=provider_factory,
            missing_chars=missing_chars,
        )
        txt = postprocess_section(
            section,
            txt,
            min_paras=min_paras,
            min_chars=min_chars,
            max_chars=max_chars,
            min_tables=min_tables,
            min_figures=min_figures,
        )
        incomplete = _has_incomplete_paragraph(txt)
        if _section_minimum_satisfied(text=txt, min_paras=min_paras, min_chars=min_chars) and not incomplete:
            break
        body_len = _section_body_len(txt)
        need_retry_for_length = body_len > 0 and body_len < min_chars
        need_retry_for_integrity = incomplete
        if attempt >= rounds and (need_retry_for_length or need_retry_for_integrity):
            retry_missing = max(0, min_chars - body_len)
            if retry_missing > 100 or need_retry_for_integrity:
                retry_reason = (
                    f"content below target ({body_len}/{min_chars}); continue generation."
                    if need_retry_for_length
                    else "detected incomplete paragraph tail, continue generation."
                )
                out_queue.put(
                    {
                        "event": "section",
                        "phase": "retry",
                        "section": section,
                        "message": (
                            f"content below target ({body_len}/{min_chars}), continuing..."
                            if need_retry_for_length
                            else "detected incomplete paragraph tail, continuing..."
                        ),
                    }
                )
                txt = _continue_with_optional_segments(
                    model=model,
                    title=title,
                    section=section,
                    parent_section=parent_section,
                    instruction=instruction,
                    analysis_summary=analysis_summary,
                    evidence_summary=evidence_summary,
                    allowed_urls=allowed_urls,
                    plan_hint=plan_hint,
                    dimension_hints=dimension_hints,
                    txt=txt,
                    section_id=section_id,
                    min_paras=min_paras,
                    min_chars=min_chars,
                    max_chars=max_chars,
                    min_tables=min_tables,
                    min_figures=min_figures,
                    out_queue=out_queue,
                    stream_structured_blocks=stream_structured_blocks,
                    predict_num_tokens=predict_num_tokens,
                    is_reference_section=is_reference_section,
                    section_timeout_s=section_timeout_s,
                    provider_factory=provider_factory,
                    missing_chars=retry_missing,
                    retry_reason=retry_reason,
                )
                if _section_body_len(txt) >= min_chars and not _has_incomplete_paragraph(txt):
                    break
    return _ensure_paragraph_integrity(txt)

__all__ = [name for name in globals() if not name.startswith("__")]
