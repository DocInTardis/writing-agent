"""App V2 Textops Runtime Part3 module."""

from __future__ import annotations

# ruff: noqa: F821

import time
import uuid
from functools import wraps
from typing import Any

from fastapi import Request

from writing_agent.agents.citations import CitationAgent
from writing_agent.models import Citation, CitationStyle
from writing_agent.storage import VersionNode
from writing_agent.v2.doc_ir import diff_blocks as doc_ir_diff
from writing_agent.v2.doc_ir import from_dict as doc_ir_from_dict
from writing_agent.v2.doc_ir import from_text as doc_ir_from_text
from writing_agent.v2.doc_ir import to_dict as doc_ir_to_dict
from writing_agent.v2.doc_ir import to_text as doc_ir_to_text
from writing_agent.v2.graph_reference_domain import ReferenceAgent, extract_year, format_authors
from writing_agent.v2.graph_runner_post_domain import (
    _generic_fill_paragraph,
    _is_reference_section,
    _merge_sections_text,
    _plan_title,
)
from writing_agent.v2.rag.search import search_papers
from writing_agent.web.domains import (
    citation_render_domain,
    doc_state_domain,
    export_structure_domain,
    fallback_content_domain,
    section_edit_ops_domain,
    version_state_domain,
)
from writing_agent.web.text_export import convert_to_latex as _convert_to_latex_base
from writing_agent.web.text_export import default_title as _default_title_base
from writing_agent.web.text_export import extract_title as _extract_title_base
from writing_agent.web.text_export import render_blocks_to_html as _render_blocks_to_html_base

_BIND_SKIP_NAMES = {
    "__builtins__",
    "__cached__",
    "__doc__",
    "__file__",
    "__loader__",
    "__name__",
    "__package__",
    "__spec__",
    "_BIND_SKIP_NAMES",
    "_proxy_factory",
    "bind",
    "install",
}


FALLBACK_DEFAULT_SECTIONS = [
    "??",
    "????",
    "????",
    "?????",
    "?????",
    "??",
    "????",
]


EXPORTED_FUNCTIONS = [
    "_has_toc_heading",
    "_has_reference_heading",
    "_collect_toc_titles",
    "_ensure_toc_section",
    "_reference_lines_from_session",
    "_ensure_reference_section",
    "_reference_section_last",
    "_move_reference_section_to_end",
    "_extract_citation_keys_from_text",
    "_has_reference_requirement",
    "_citation_export_issues",
    "_export_quality_report",
    "_insert_reference_section",
    "_apply_citations_for_export",
    "_apply_citations_to_doc_ir",
    "_normalize_doc_ir_for_export",
    "_safe_doc_text",
    "_validate_docx_bytes",
    "_set_doc_text",
    "_safe_doc_ir_payload",
    "_fallback_sections_from_session",
    "_fallback_reference_items",
    "_build_fallback_text",
    "_augment_instruction",
    "_doc_ir_has_styles",
    "api_version_commit",
    "_version_kind_from_tags",
    "_version_diff_summary",
    "api_version_log",
    "api_version_tree",
    "api_version_checkout",
    "api_version_branch",
    "api_version_diff",
    "api_version_tag",
    "_get_current_branch",
    "_auto_commit_version",
    "_convert_to_latex",
    "_render_blocks_to_html",
    "_default_title",
    "_extract_title",
]


def bind(namespace: dict) -> None:
    for key, value in namespace.items():
        if key in _BIND_SKIP_NAMES:
            continue
        globals()[key] = value


def _proxy_factory(fn_name: str, namespace: dict):
    fn = globals()[fn_name]

    @wraps(fn)
    def _proxy(*args, **kwargs):
        bind(namespace)
        return fn(*args, **kwargs)

    _proxy._wa_runtime_proxy = True
    _proxy._wa_runtime_proxy_target_module = __name__
    _proxy._wa_runtime_proxy_target_name = fn_name
    return _proxy


def install(namespace: dict) -> None:
    bind(namespace)
    for fn_name in EXPORTED_FUNCTIONS:
        namespace[fn_name] = _proxy_factory(fn_name, namespace)


def _format_reference_items(sources: list[dict[str, Any]]) -> list[str]:
    agent = ReferenceAgent(
        extract_year_fn=extract_year,
        format_authors_fn=format_authors,
    )
    return agent.build(sources)


def _has_toc_heading(text: str) -> bool:
    return export_structure_domain.has_toc_heading(text)


def _has_reference_heading(text: str) -> bool:
    return export_structure_domain.has_reference_heading(text)


def _collect_toc_titles(text: str) -> list[str]:
    return export_structure_domain.collect_toc_titles(
        text,
        extract_sections=_extract_sections,
        is_reference_section=_is_reference_section,
    )


def _ensure_toc_section(text: str) -> str:
    return export_structure_domain.ensure_toc_section(
        text,
        extract_sections=_extract_sections,
        is_reference_section=_is_reference_section,
        split_lines=_split_lines,
    )


def _reference_lines_from_session(session) -> list[str]:
    citer = CitationAgent()
    return export_structure_domain.reference_lines_from_session(
        session,
        citation_style_from_session=_citation_style_from_session,
        format_reference=lambda cite, style: citer.format_reference(cite, style),
    )


def _ensure_reference_section(text: str, session) -> str:
    return export_structure_domain.ensure_reference_section(
        text,
        session,
        has_reference_heading_fn=_has_reference_heading,
        reference_lines_from_session_fn=_reference_lines_from_session,
        insert_reference_section=_insert_reference_section,
    )


def _reference_section_last(text: str) -> bool:
    return export_structure_domain.reference_section_last(
        text,
        extract_sections=_extract_sections,
        is_reference_section=_is_reference_section,
    )


def _move_reference_section_to_end(text: str) -> str:
    return export_structure_domain.move_reference_section_to_end(
        text,
        extract_sections=_extract_sections,
        is_reference_section=_is_reference_section,
        apply_move_section_op=lambda value, title, anchor, position="after": section_edit_ops_domain.apply_move_section_op(
            value,
            title,
            anchor,
            position=position,
            normalize_heading_text=_normalize_heading_text,
        ),
    )


def _extract_citation_keys_from_text(text: str) -> list[str]:
    return export_structure_domain.extract_citation_keys_from_text(text)


def _has_reference_requirement(session, text: str) -> bool:
    return export_structure_domain.has_reference_requirement(
        session,
        text,
        has_reference_heading_fn=_has_reference_heading,
        reference_lines_from_session_fn=_reference_lines_from_session,
    )


def _citation_export_issues(session, text: str) -> list[dict]:
    return export_structure_domain.citation_export_issues(
        session,
        text,
        strict_citation_verify_enabled=_strict_citation_verify_enabled,
        get_internal_pref=_get_internal_pref,
        citation_verify_key=_CITATION_VERIFY_KEY,
        allow_possible_citation_status=_allow_possible_citation_status,
    )


def _export_quality_report(session, text: str, *, auto_fix: bool = False) -> dict:
    return export_structure_domain.export_quality_report(
        session,
        text,
        auto_fix=auto_fix,
        export_gate_policy=_export_gate_policy,
        strict_doc_format_enabled=_strict_doc_format_enabled,
        has_reference_requirement_fn=_has_reference_requirement,
        normalize_export_text=_normalize_export_text,
        ensure_toc_section_fn=_ensure_toc_section,
        ensure_reference_section_fn=_ensure_reference_section,
        move_reference_section_to_end_fn=_move_reference_section_to_end,
        has_toc_heading_fn=_has_toc_heading,
        has_reference_heading_fn=_has_reference_heading,
        reference_section_last_fn=_reference_section_last,
        citation_export_issues_fn=_citation_export_issues,
    )


def _insert_reference_section(text: str, ref_lines: list[str]) -> str:
    return citation_render_domain.insert_reference_section(text, ref_lines)


def _apply_citations_for_export(text: str, citations: dict[str, Citation], style: CitationStyle) -> str:
    return citation_render_domain.apply_citations_for_export(text, citations, style)


def _apply_citations_to_doc_ir(doc_ir, citations: dict[str, Citation], style: CitationStyle):
    return citation_render_domain.apply_citations_to_doc_ir(doc_ir, citations, style)


def _normalize_doc_ir_for_export(doc_ir, session):
    return doc_state_domain.normalize_doc_ir_for_export(
        doc_ir,
        session,
        ensure_mcp_citations=_ensure_mcp_citations,
        doc_ir_from_dict=doc_ir_from_dict,
        doc_ir_to_text=doc_ir_to_text,
        doc_ir_from_text=doc_ir_from_text,
        doc_ir_has_styles=_doc_ir_has_styles,
        normalize_export_text=_normalize_export_text,
    )


def _safe_doc_text(session) -> str:
    return doc_state_domain.safe_doc_text(
        session,
        plan_title=_plan_title,
        fallback_sections_from_session=_fallback_sections_from_session,
        build_fallback_text=_build_fallback_text,
        store_put=store.put,
        doc_ir_to_text=doc_ir_to_text,
        doc_ir_from_dict=doc_ir_from_dict,
        set_doc_text=_set_doc_text,
    )


def _validate_docx_bytes(docx_bytes: bytes) -> list[str]:
    return doc_state_domain.validate_docx_bytes(docx_bytes)


def _set_doc_text(session, text: str) -> None:
    return doc_state_domain.set_doc_text(
        session,
        text,
        doc_ir_to_dict=doc_ir_to_dict,
        doc_ir_from_text=doc_ir_from_text,
    )


def _safe_doc_ir_payload(text: str) -> dict:
    return doc_state_domain.safe_doc_ir_payload(
        text,
        doc_ir_to_dict=doc_ir_to_dict,
        doc_ir_from_text=doc_ir_from_text,
    )


def _fallback_sections_from_session(session) -> list[str]:
    return fallback_content_domain.fallback_sections_from_session(
        session,
        default_sections=FALLBACK_DEFAULT_SECTIONS,
    )


def _fallback_reference_items(session, query: str) -> list[str]:
    return fallback_content_domain.fallback_reference_items(
        session,
        query,
        rag_list_papers=rag_store.list_papers,
        search_papers=search_papers,
        format_reference_items=_format_reference_items,
    )


def _build_fallback_text(title: str, sections: list[str], session=None) -> str:
    return fallback_content_domain.build_fallback_text(
        title,
        sections,
        session,
        is_reference_section=_is_reference_section,
        generic_fill_paragraph=_generic_fill_paragraph,
        merge_sections_text=_merge_sections_text,
        default_title=_default_title,
        fallback_reference_items_fn=_fallback_reference_items,
    )


def _augment_instruction(instruction: str, *, formatting: dict, generation_prefs: dict) -> str:
    return fallback_content_domain.augment_instruction(
        instruction,
        formatting=formatting,
        generation_prefs=generation_prefs,
    )


def _doc_ir_has_styles(doc_ir) -> bool:
    return doc_state_domain.doc_ir_has_styles(doc_ir, doc_ir_to_dict=doc_ir_to_dict)


async def api_version_commit(doc_id: str, request: Request) -> dict:
    from writing_agent.web.api.version_flow import version_commit

    return await version_commit(doc_id, request)


def _version_kind_from_tags(tags) -> str:
    return version_state_domain.version_kind_from_tags(tags)


def _version_diff_summary(prev_doc_ir: dict, next_doc_ir: dict) -> dict:
    return version_state_domain.version_diff_summary(
        prev_doc_ir,
        next_doc_ir,
        doc_ir_from_dict=doc_ir_from_dict,
        doc_ir_diff=doc_ir_diff,
    )


def api_version_log(doc_id: str, branch: str = "main", limit: int = 50) -> dict:
    from writing_agent.web.api.version_flow import version_log

    return version_log(doc_id, branch=branch, limit=limit)


def api_version_tree(doc_id: str) -> dict:
    from writing_agent.web.api.version_flow import version_tree

    return version_tree(doc_id)


async def api_version_checkout(doc_id: str, request: Request) -> dict:
    from writing_agent.web.api.version_flow import version_checkout

    return await version_checkout(doc_id, request)


async def api_version_branch(doc_id: str, request: Request) -> dict:
    from writing_agent.web.api.version_flow import version_branch

    return await version_branch(doc_id, request)


def api_version_diff(doc_id: str, from_version: str, to_version: str) -> dict:
    from writing_agent.web.api.version_flow import version_diff

    return version_diff(doc_id, from_version=from_version, to_version=to_version)


async def api_version_tag(doc_id: str, request: Request) -> dict:
    from writing_agent.web.api.version_flow import version_tag

    return await version_tag(doc_id, request)


def _get_current_branch(session) -> str:
    return version_state_domain.get_current_branch(session)


def _auto_commit_version(session, message: str, *, author: str = "system", tags: list[str] | None = None) -> str | None:
    return version_state_domain.auto_commit_version(
        session,
        message,
        author=author,
        tags=tags,
        get_current_branch_fn=_get_current_branch,
        version_node_cls=VersionNode,
        version_id_factory=lambda: uuid.uuid4().hex[:12],
        now_ts=time.time,
    )


def _convert_to_latex(text: str, title: str) -> str:
    return _convert_to_latex_base(text, title)


def _render_blocks_to_html(blocks) -> str:
    return _render_blocks_to_html_base(blocks)


def _default_title() -> str:
    return _default_title_base()


def _extract_title(text: str) -> str:
    return _extract_title_base(text)
