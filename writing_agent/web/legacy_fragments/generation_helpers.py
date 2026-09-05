"""Compatibility helpers injected into ``app_v2``.

<task>full_document_generation</task>
<constraints>
- Treat prompt content as tagged channels.
- Escape user-provided text before inserting it into generation prompts.
- Return Markdown content only from generation helpers.
</constraints>
"""

from __future__ import annotations

import re
import time
import uuid
from typing import Any

from writing_agent.capabilities.fallback_generation import (
    single_pass_generate,
    single_pass_generate_stream,
)
from writing_agent.capabilities.generation_policy import should_use_fast_generate, system_pressure_high
from writing_agent.capabilities.generation_quality import check_generation_quality, looks_like_prompt_echo
from writing_agent.llm import OllamaClient, OllamaError, get_default_provider, get_ollama_settings
from writing_agent.llm.factory import get_provider_snapshot
from writing_agent.llm.provider_compat import provider_or_ollama
from writing_agent.storage import VersionNode
from writing_agent.web.domains import (
    fallback_content_domain,
    prefs_extract_domain,
    revision_edit_common_domain,
    revision_edit_plan_domain,
    revision_selected_edit_domain,
    route_graph_metrics_domain,
    section_edit_ops_domain,
)
from writing_agent.web.model_runtime_support import ensure_ollama_ready, ensure_ollama_ready_iter
from writing_agent.web import text_export


def _app_v2():
    from writing_agent.web import app_v2

    return app_v2


def _ensure_ollama_ready() -> tuple[bool, str]:
    app_v2 = _app_v2()
    return ensure_ollama_ready(
        get_ollama_settings_fn=app_v2.get_ollama_settings,
        ollama_client_cls=app_v2.OllamaClient,
        start_ollama_serve_fn=app_v2._start_ollama_serve,
        wait_until_fn=app_v2._wait_until,
        get_provider_snapshot_fn=get_provider_snapshot,
        get_default_provider_fn=get_default_provider,
    )


def _ensure_ollama_ready_iter():
    app_v2 = _app_v2()
    return ensure_ollama_ready_iter(
        get_ollama_settings_fn=app_v2.get_ollama_settings,
        ollama_client_cls=app_v2.OllamaClient,
        start_ollama_serve_fn=app_v2._start_ollama_serve,
        wait_until_fn=app_v2._wait_until,
        get_provider_snapshot_fn=get_provider_snapshot,
        get_default_provider_fn=get_default_provider,
    )


def _sanitize_output_text(text: str) -> str:
    src = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    src = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", src.strip())
    src = re.sub(r"\s*```$", "", src).strip()
    return src


def _postprocess_output_text(
    session,
    text: str,
    instruction: str,
    *,
    current_text: str = "",
    base_text: str = "",
) -> str:
    _ = session, instruction, current_text, base_text
    cleaned = prefs_extract_domain.replace_question_headings(_sanitize_output_text(text))
    return cleaned.strip()


def _check_generation_quality(text: str, target_chars: int = 0) -> list[str]:
    return check_generation_quality(text, target_chars=target_chars)


def _looks_like_prompt_echo(text: str, instruction: str) -> bool:
    return looks_like_prompt_echo(text, instruction)


def _augment_instruction(instruction: str, *, formatting: dict, generation_prefs: dict) -> str:
    return fallback_content_domain.augment_instruction(
        instruction,
        formatting=formatting,
        generation_prefs=generation_prefs,
    )


def _default_llm_provider(settings):
    app_v2 = _app_v2()
    return provider_or_ollama(app_v2, timeout_s=float(getattr(settings, "timeout_s", 60.0) or 60.0))


def _single_pass_generate(session, *, instruction: str, current_text: str, target_chars: int = 0) -> str:
    app_v2 = _app_v2()
    return single_pass_generate(
        session=session,
        instruction=instruction,
        current_text=current_text,
        target_chars=target_chars,
        get_ollama_settings_fn=app_v2.get_ollama_settings,
        default_llm_provider_fn=_default_llm_provider,
        sanitize_output_text_fn=app_v2._sanitize_output_text,
        ollama_error_cls=OllamaError,
    )


def _single_pass_generate_stream(session, *, instruction: str, current_text: str, target_chars: int = 0):
    app_v2 = _app_v2()
    return single_pass_generate_stream(
        session=session,
        instruction=instruction,
        current_text=current_text,
        target_chars=target_chars,
        get_ollama_settings_fn=app_v2.get_ollama_settings,
        default_llm_provider_fn=_default_llm_provider,
        sanitize_output_text_fn=app_v2._sanitize_output_text,
        ollama_error_cls=OllamaError,
    )


def _should_use_fast_generate(raw_instruction: str, target_chars: int, prefs: dict | None) -> bool:
    app_v2 = _app_v2()
    return should_use_fast_generate(
        raw_instruction=raw_instruction,
        target_chars=target_chars,
        prefs=prefs or {},
        os_module=app_v2.os,
        system_pressure_high_fn=lambda: system_pressure_high(os_module=app_v2.os),
    )


def _get_current_branch(session) -> str:
    branches = getattr(session, "branches", None)
    if isinstance(branches, dict):
        for name, version_id in branches.items():
            if version_id and version_id == getattr(session, "current_version_id", None):
                return str(name or "main") or "main"
    return "main"


def _auto_commit_version(session, message: str) -> None:
    version_id = uuid.uuid4().hex[:12]
    branch = _get_current_branch(session)
    session.versions[version_id] = VersionNode(
        version_id=version_id,
        parent_id=getattr(session, "current_version_id", None),
        timestamp=time.time(),
        message=str(message or "auto"),
        author="system",
        doc_text=str(getattr(session, "doc_text", "") or ""),
        doc_ir=dict(getattr(session, "doc_ir", {}) or {}),
        tags=["auto"],
        branch_name=branch,
    )
    session.current_version_id = version_id
    session.branches[branch] = version_id


def _try_quick_edit(text: str, instruction: str, confirm_apply: bool = False):
    app_v2 = _app_v2()
    return revision_edit_plan_domain.try_quick_edit(
        text,
        instruction,
        looks_like_modify_instruction=app_v2._looks_like_modify_instruction,
        confirm_apply=confirm_apply,
        provider_factory=get_default_provider,
    )


def _try_ai_intent_edit(text: str, instruction: str, analysis: dict | None = None, confirm_apply: bool = False):
    app_v2 = _app_v2()
    return revision_edit_plan_domain.try_ai_intent_edit(
        text,
        instruction,
        analysis,
        looks_like_modify_instruction=app_v2._looks_like_modify_instruction,
        confirm_apply=confirm_apply,
        provider_factory=get_default_provider,
    )


def _try_revision_edit(
    *,
    session,
    instruction: str,
    text: str,
    selection: object = "",
    analysis: dict | None = None,
    context_policy: object | None = None,
    report_status=None,
):
    app_v2 = _app_v2()
    return revision_selected_edit_domain.try_revision_edit(
        session=session,
        instruction=instruction,
        text=text,
        selection=selection,
        analysis=analysis,
        context_policy=context_policy,
        report_status=report_status,
        sanitize_output_text=app_v2._sanitize_output_text,
        replace_question_headings=app_v2._replace_question_headings,
        provider_factory=get_default_provider,
    )


def _extract_sections(text: str, *, prefer_levels: tuple[int, ...] = (2, 3)):
    return section_edit_ops_domain.extract_sections(text, prefer_levels=prefer_levels)


def _normalize_heading_text(text: object) -> str:
    return revision_edit_common_domain._normalize_heading_text(str(text or ""))


def _default_outline_from_instruction(text: str) -> list[str]:
    from writing_agent.v2.graph_runner_policy_domain import _default_outline_from_instruction as _impl

    return _impl(text)


def _revision_hard_constraints(session, instruction: str, text: str) -> dict:
    _ = instruction
    required_h2 = [str(x).strip() for x in (getattr(session, "template_required_h2", []) or []) if str(x).strip()]
    return {
        "min_chars": min(1200, max(120, len(str(text or "").strip()) // 2)),
        "required_h2": required_h2,
        "min_refs": 0,
        "min_tables": 0,
        "min_figures": 0,
        "epsilon": 10.0,
    }


def _revision_decision_with_model(**_kwargs) -> dict:
    return {"should_apply": True, "plan": []}


def _record_stream_route_metric(event: str, **kwargs: Any) -> None:
    route_graph_metrics_domain.record_route_graph_metric(event, phase="generate_stream", **kwargs)


def _extract_error_code(value: object, *, default: str = "E_RUNTIME") -> str:
    return route_graph_metrics_domain.extract_error_code(value, default=default)


def _should_inject_route_graph_failure(*, phase: str = "") -> bool:
    return route_graph_metrics_domain.should_inject_route_graph_failure(phase=phase)


def _parse_unicode_formatting(raw: str) -> dict:
    text = str(raw or "")
    fmt: dict[str, object] = {}
    font_match = re.search(
        r"字体\s*(?:改成|改为|改到|设置为|设为|使用|:|：)?\s*([\u4e00-\u9fffA-Za-z ]{2,20})",
        text,
    )
    if font_match:
        font = re.split(r"[，,。；;\s]", str(font_match.group(1) or "").strip())[0]
        if font:
            fmt["font_name_east_asia"] = font
    size_map = {"小四": 12, "五号": 10.5, "四号": 14, "小三": 15, "三号": 16, "小二": 18, "二号": 22}
    size_match = re.search(r"字号\s*(?:改成|改为|设置为|设为|:|：)?\s*(小四|五号|四号|小三|三号|小二|二号)", text)
    if size_match:
        size = str(size_match.group(1) or "")
        fmt["font_size_name"] = size
        fmt["font_size_pt"] = size_map[size]
    line_match = re.search(r"行距\s*(?:改成|改为|设置为|设为|:|：)?\s*(\d+(?:\.\d+)?)\s*倍?", text)
    if line_match:
        fmt["line_spacing"] = float(line_match.group(1))
    return fmt


def install(g: dict) -> None:
    g.update(
        {
            "_ensure_ollama_ready": _ensure_ollama_ready,
            "_ensure_ollama_ready_iter": _ensure_ollama_ready_iter,
            "_sanitize_output_text": _sanitize_output_text,
            "_postprocess_output_text": _postprocess_output_text,
            "_check_generation_quality": _check_generation_quality,
            "_looks_like_prompt_echo": _looks_like_prompt_echo,
            "_augment_instruction": _augment_instruction,
            "_single_pass_generate": _single_pass_generate,
            "_single_pass_generate_stream": _single_pass_generate_stream,
            "_should_use_fast_generate": _should_use_fast_generate,
            "_get_current_branch": _get_current_branch,
            "_auto_commit_version": _auto_commit_version,
            "_try_quick_edit": _try_quick_edit,
            "_try_ai_intent_edit": _try_ai_intent_edit,
            "_try_revision_edit": _try_revision_edit,
            "_extract_sections": _extract_sections,
            "_normalize_heading_text": _normalize_heading_text,
            "_default_outline_from_instruction": _default_outline_from_instruction,
            "_revision_hard_constraints": _revision_hard_constraints,
            "_revision_decision_with_model": _revision_decision_with_model,
            "_extract_error_code": _extract_error_code,
            "_should_inject_route_graph_failure": _should_inject_route_graph_failure,
        }
    )

    def _extract_format_only_updates(raw, analysis=None):
        parsed = g["_extract_format_only_updates_base"](
            raw,
            analysis,
            parse_prefs=g["_fast_extract_prefs"],
            normalize_formatting=g["_normalize_ai_formatting"],
            normalize_prefs=g["_normalize_ai_prefs"],
        )
        extra_fmt = _parse_unicode_formatting(str(raw or ""))
        if parsed is None and extra_fmt:
            parsed = {"formatting": {}, "generation_prefs": {}, "has_values": True}
        if isinstance(parsed, dict) and extra_fmt:
            merged = dict(parsed.get("formatting") if isinstance(parsed.get("formatting"), dict) else {})
            merged.update(extra_fmt)
            parsed["formatting"] = merged
            parsed["has_values"] = True
        return parsed

    g["_extract_format_only_updates"] = _extract_format_only_updates
    g["_try_format_only_update"] = lambda session, instruction, analysis=None: g["_try_format_only_update_base"](
        session,
        instruction,
        analysis,
        extract_updates=g["_extract_format_only_updates"],
    )
    g["_should_route_to_revision"] = lambda raw, text, analysis=None: g["_should_route_to_revision_base"](
        raw,
        text,
        analysis,
        is_format_only=lambda r, a=None: g["_extract_format_only_updates"](r, a) is not None,
    )
    g["_looks_like_modify_instruction"] = g["_looks_like_modify_instruction_base"]
    g["_render_blocks_to_html"] = text_export.render_blocks_to_html
    g["_convert_to_latex"] = text_export.convert_to_latex
    def _try_handle_format_only_request(**kwargs):
        app_v2 = _app_v2()
        return g["_try_handle_format_only_request_base"](
            **kwargs,
            set_doc_text=app_v2._set_doc_text,
            save_session=app_v2.store.put,
            safe_doc_ir=app_v2._safe_doc_ir_payload,
            apply_format_only_update=g["_try_format_only_update"],
        )

    g["_try_handle_format_only_request"] = _try_handle_format_only_request

    from writing_agent.web.legacy_fragments import generation_stream

    generation_stream.install(g)
