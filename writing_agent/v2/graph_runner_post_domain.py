"""Graph Runner Post Domain module.

This module belongs to `writing_agent.v2` in the writing-agent codebase.
"""

from __future__ import annotations

import queue
import re
from dataclasses import dataclass

from writing_agent.sections_catalog import find_section_description
from writing_agent.v2 import (
    graph_aggregate_domain,
    graph_plan_domain,
    graph_reference_domain,
    graph_runner_rag_context_domain,
    graph_runner_title_domain,
    graph_section_draft_domain,
    graph_text_sanitize_domain,
)
from writing_agent.v2.doc_format import DocBlock, parse_report_text
from writing_agent.v2.text_store import TextStore
from writing_agent.v2.graph_runner_post_sections_domain import *
from writing_agent.v2.graph_runner_post_text_domain import *
from writing_agent.v2 import graph_runner_post_quality_domain as post_quality_domain
from writing_agent.v2 import graph_runner_post_expand_domain as post_expand_domain


@dataclass(frozen=True)
class SectionTargets:
    weight: float
    min_paras: int
    min_chars: int
    max_chars: int
    min_tables: int
    min_figures: int


_maybe_rag_context = graph_runner_rag_context_domain._maybe_rag_context
_mcp_rag_enabled = graph_runner_rag_context_domain._mcp_rag_enabled
_mcp_rag_retrieve = graph_runner_rag_context_domain._mcp_rag_retrieve
_looks_like_rag_meta_line = graph_runner_rag_context_domain._looks_like_rag_meta_line
_has_cjk = graph_runner_rag_context_domain._has_cjk
_is_mostly_ascii_line = graph_runner_rag_context_domain._is_mostly_ascii_line
_strip_rag_meta_lines = graph_runner_rag_context_domain._strip_rag_meta_lines
_sanitize_rag_context = graph_runner_rag_context_domain._sanitize_rag_context
_normalize_title_line = graph_runner_title_domain._normalize_title_line
_default_title = graph_runner_title_domain._default_title
_fallback_title_from_instruction = graph_runner_title_domain._fallback_title_from_instruction
_guess_title = graph_runner_title_domain._guess_title
_wants_acknowledgement = graph_runner_title_domain._wants_acknowledgement
_filter_ack_headings = graph_runner_title_domain._filter_ack_headings
_filter_ack_outline = graph_runner_title_domain._filter_ack_outline
_is_engineering_instruction = graph_runner_title_domain._is_engineering_instruction


@dataclass(frozen=True)
class PlanSection:
    title: str
    target_chars: int
    min_chars: int
    max_chars: int
    min_tables: int
    min_figures: int
    key_points: list[str]
    figures: list[dict]
    tables: list[dict]
    evidence_queries: list[str]


def _extract_h2_titles(text: str) -> list[str]:
    return list(post_quality_domain._extract_h2_titles(text))


def _count_citations(text: str) -> int:
    return int(post_quality_domain._count_citations(text))


def _detect_prompt_contamination(text: str) -> list[str]:
    return list(post_quality_domain._detect_prompt_contamination(text))


def _detect_paragraph_repetition(text: str) -> int:
    return int(post_quality_domain._detect_paragraph_repetition(text))


def _reference_relevance_ratio(*, query: str, sources: list[dict]) -> float:
    return float(post_quality_domain._reference_relevance_ratio(query=query, sources=sources))


def _reference_rows_from_text(text: str) -> list[dict]:
    return list(post_quality_domain._reference_rows_from_text(text))


def _reference_relevance_ratio_from_text(*, query: str, text: str) -> tuple[float, int]:
    ratio, count = post_quality_domain._reference_relevance_ratio_from_text(query=query, text=text)
    return float(ratio), int(count)


def _light_self_check(
    *,
    text: str,
    sections: list[str],
    target_chars: int,
    evidence_enabled: bool,
    reference_sources: list[dict],
    reference_query: str = "",
) -> list[str]:
    return list(
        post_quality_domain._light_self_check(
            text=text,
            sections=sections,
            target_chars=target_chars,
            evidence_enabled=evidence_enabled,
            reference_sources=reference_sources,
            reference_query=reference_query,
        )
    )


def _plan_title(current_text: str, instruction: str) -> str:
    text = (current_text or "").strip()
    m = None
    for line in text.splitlines():
        if line.startswith("# "):
            m = line[2:].strip()
            break
    raw = m or _guess_title(instruction) or _fallback_title_from_instruction(instruction) or _default_title()
    if _is_reference_section(_clean_section_title(raw)):
        raw = _fallback_title_from_instruction(instruction) or _default_title()
    return _normalize_title_line(raw)

def _plan_title_sections(*, current_text: str, instruction: str, required_h2: list[str] | None) -> tuple[str, list[str]]:
    title = _plan_title(current_text=current_text, instruction=instruction)
    if required_h2:
        secs = _sanitize_planned_sections([s.strip() for s in required_h2 if s and s.strip()])
        if secs:
            return title, secs
    return title, []


def _filter_disallowed_outline(outline: list[tuple[int, str]]) -> list[tuple[int, str]]:
    return [(lvl, txt) for lvl, txt in outline if txt not in _DISALLOWED_SECTIONS]


def _boost_media_targets(targets: dict[str, SectionTargets], sections: list[str]) -> None:
    for sec in sections:
        t = targets.get(sec)
        if not t:
            continue
        title = (_section_title(sec) or sec).strip()
        if _is_reference_section(title) or "\u9644\u5f55" in title:
            continue
        min_tables = t.min_tables
        min_figures = t.min_figures
        if any(k in title for k in ["\u9700\u6c42", "\u8bbe\u8ba1", "\u5b9e\u73b0", "\u67b6\u6784", "\u6d4b\u8bd5", "\u7ed3\u679c", "\u5206\u6790", "requirement", "design"]):
            min_figures = max(min_figures, 1)
            min_tables = max(min_tables, 1)
        targets[sec] = SectionTargets(
            weight=t.weight,
            min_paras=t.min_paras,
            min_chars=t.min_chars,
            max_chars=t.max_chars,
            min_tables=min_tables,
            min_figures=min_figures,
        )

def _generate_section_stream(
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
    min_paras: int,
    min_chars: int,
    max_chars: int,
    min_tables: int,
    min_figures: int,
    out_queue: queue.Queue[dict],
    reference_items: list[dict],
    text_store: TextStore | None,
) -> str:
    from writing_agent.v2.graph_runner_runtime import _generate_section_stream as _impl

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
        min_paras=min_paras,
        min_chars=min_chars,
        max_chars=max_chars,
        min_tables=min_tables,
        min_figures=min_figures,
        out_queue=out_queue,
        reference_items=reference_items,
        text_store=text_store,
    )

def _plan_point_paragraph(section: str, plan: PlanSection | None, idx: int) -> str:
    return str(post_expand_domain._plan_point_paragraph(section, plan, idx))


def _expand_with_context(
    section: str,
    text: str,
    ctx: str,
    min_chars: int,
    min_paras: int,
    plan: PlanSection | None = None,
) -> str:
    return str(
        post_expand_domain._expand_with_context(
            section=section,
            text=text,
            ctx=ctx,
            min_chars=min_chars,
            min_paras=min_paras,
            plan=plan,
        )
    )


def _select_models_by_memory(models: list[str], *, fallback: str) -> list[str]:
    return graph_reference_domain.select_models_by_memory(
        models,
        fallback=fallback,
        looks_like_embedding_model=_looks_like_embedding_model,
        ollama_installed_models=_ollama_installed_models,
        get_memory_bytes=_get_memory_bytes,
        ollama_model_sizes_gb=_ollama_model_sizes_gb,
    )


from writing_agent.v2 import graph_runner_post_models_domain as post_models_domain


def _default_worker_models(*, preferred: str) -> list[str]:
    return list(post_models_domain._default_worker_models(preferred=preferred))


def _looks_like_embedding_model(name: str) -> bool:
    return bool(post_models_domain._looks_like_embedding_model(name))


def _ollama_installed_models() -> set[str]:
    return set(post_models_domain._ollama_installed_models())


def _ollama_model_sizes_gb() -> dict[str, float]:
    return dict(post_models_domain._ollama_model_sizes_gb())


def _get_memory_bytes() -> tuple[int, int]:
    total, avail = post_models_domain._get_memory_bytes()
    return int(total), int(avail)

def _apply_section_updates(base_text: str, updates, transitions) -> str:
    # compatibility: generation_service passes (current_text, final_text, [section])
    if isinstance(updates, str) and isinstance(transitions, list):
        return str(updates or "").strip() or base_text
    if not isinstance(updates, dict) or not isinstance(transitions, dict):
        return base_text
    return graph_aggregate_domain.apply_section_updates(base_text, updates, transitions)


__all__ = [name for name in globals() if not name.startswith("__")]
