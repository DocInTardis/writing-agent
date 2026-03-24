"""Adapter helpers for graph runner post text processing."""

from __future__ import annotations

import queue

from writing_agent.sections_catalog import find_section_description
from writing_agent.v2 import graph_section_draft_domain
from writing_agent.v2.graph_runner_post_sections_domain import _SECTION_TOKEN_RE, _encode_section, _is_reference_section, _section_title
from writing_agent.v2.graph_runner_post_text_sanitize_domain import _looks_like_heading_text, _sanitize_output_text, _strip_markdown_noise
from writing_agent.v2.text_store import TextStore


def _strip_inline_headings(text: str, section_title: str) -> str:
    return graph_section_draft_domain.strip_inline_headings(
        text,
        section_title,
        looks_like_heading_text=_looks_like_heading_text,
    )


def _format_references(text: str) -> str:
    return graph_section_draft_domain.format_references(
        text,
        strip_markdown_noise=_strip_markdown_noise,
    )


def _ensure_media_markers(text: str, *, section_title: str, min_tables: int, min_figures: int) -> str:
    return graph_section_draft_domain.ensure_media_markers(
        text,
        section_title=section_title,
        min_tables=min_tables,
        min_figures=min_figures,
        is_reference_section=_is_reference_section,
    )


def _generic_fill_paragraph(section: str, *, idx: int = 1) -> str:
    return graph_section_draft_domain.generic_fill_paragraph(
        section,
        idx=idx,
        section_title=_section_title,
        is_reference_section=_is_reference_section,
        _find_section_description=find_section_description,
    )


def _fast_fill_references(topic: str) -> str:
    return graph_section_draft_domain.fast_fill_references(topic)


def _fast_fill_section(section: str, *, min_paras: int, min_chars: int, min_tables: int, min_figures: int) -> str:
    return graph_section_draft_domain.fast_fill_section(
        section,
        min_paras=min_paras,
        min_chars=min_chars,
        min_tables=min_tables,
        min_figures=min_figures,
        section_title=_section_title,
        is_reference_section=_is_reference_section,
        generic_fill_paragraph=lambda sec, i: _generic_fill_paragraph(sec, idx=i),
    )


def _postprocess_section(section: str, txt: str, *, min_paras: int, min_chars: int, max_chars: int, min_tables: int, min_figures: int) -> str:
    return graph_section_draft_domain.postprocess_section(
        section,
        txt,
        min_paras=min_paras,
        min_chars=min_chars,
        max_chars=max_chars,
        min_tables=min_tables,
        min_figures=min_figures,
        section_title=_section_title,
        is_reference_section=_is_reference_section,
        format_references=_format_references,
        strip_reference_like_lines=_strip_reference_like_lines,
        strip_inline_headings=_strip_inline_headings,
        generic_fill_paragraph=lambda sec, i: _generic_fill_paragraph(sec, idx=i),
        sanitize_output_text=_sanitize_output_text,
        ensure_media_markers=lambda content, sec_title, tables, figures: _ensure_media_markers(
            content,
            section_title=sec_title,
            min_tables=tables,
            min_figures=figures,
        ),
    )


def _ensure_section_minimums_stream(*, base_url: str, model: str, title: str, section: str, parent_section: str, instruction: str, analysis_summary: str, evidence_summary: str, allowed_urls: list[str], plan_hint: str, dimension_hints: list[str] | None, draft: str, min_paras: int, min_chars: int, max_chars: int, min_tables: int, min_figures: int, out_queue: queue.Queue[dict]) -> str:
    from writing_agent.v2.graph_runner_runtime import _ensure_section_minimums_stream as _impl

    return _impl(
        base_url=base_url,
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
        draft=draft,
        min_paras=min_paras,
        min_chars=min_chars,
        max_chars=max_chars,
        min_tables=min_tables,
        min_figures=min_figures,
        out_queue=out_queue,
    )


def _strip_reference_like_lines(text: str) -> str:
    return graph_section_draft_domain.strip_reference_like_lines(text)


def _normalize_section_id(section: str) -> str:
    return graph_section_draft_domain.normalize_section_id(
        section,
        section_token_re=_SECTION_TOKEN_RE,
        encode_section=_encode_section,
    )


def _stream_structured_blocks(*, client, system: str, user: str, out_queue: queue.Queue[dict], section: str, section_id: str, is_reference: bool, num_predict: int, deadline: float, max_chars: int = 0, strict_json: bool = True, text_store: TextStore | None = None) -> str:
    return graph_section_draft_domain.stream_structured_blocks(
        client=client,
        system=system,
        user=user,
        out_queue=out_queue,
        section=section,
        section_id=section_id,
        is_reference=is_reference,
        num_predict=num_predict,
        deadline=deadline,
        max_chars=max_chars,
        strict_json=strict_json,
        text_store=text_store,
    )


__all__ = [name for name in globals() if not name.startswith('__')]
