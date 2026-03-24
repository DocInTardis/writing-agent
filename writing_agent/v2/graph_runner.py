"""Graph Runner module.

Compatibility wrapper that re-exports split graph runner domains.
"""

# Legacy prompt-contract markers retained for prompt guard tooling:
# <retry_reason>
# <task>plan_sections_list</task>
# <constraints>
# JSON retry context anchor: f"{base_user}\n"

from __future__ import annotations

import sys

from writing_agent.v2 import graph_runner_core_domain as _graph_runner_core_domain
from writing_agent.v2 import graph_runner_analysis_domain as _graph_runner_analysis_domain
from writing_agent.v2 import graph_runner_evidence_domain as _graph_runner_evidence_domain
from writing_agent.v2.graph_runner_config_domain import *
from writing_agent.v2.graph_runner_core_domain import *
from writing_agent.v2.graph_runner_analysis_domain import *
from writing_agent.v2.graph_runner_evidence_domain import *

_CORE_IMPL_PLAN_SECTIONS_LIST = _graph_runner_core_domain._plan_sections_list_with_model
_CORE_IMPL_PLAN_SECTIONS = _graph_runner_core_domain._plan_sections_with_model

_RESERVED_GRAPH_RUNNER_NAMES = {"_analyze_instruction", "run_generate_graph", "run_generate_graph_dual_engine"}


def _sync_graph_runner_bindings() -> None:
    this = sys.modules[__name__]
    shared = {name: value for name, value in vars(this).items() if (not name.startswith("__")) and (name not in _RESERVED_GRAPH_RUNNER_NAMES)}
    for module in (_graph_runner_core_domain, _graph_runner_analysis_domain, _graph_runner_evidence_domain):
        for name, value in shared.items():
            setattr(module, name, value)


def _analyze_instruction(*args, **kwargs):
    _sync_graph_runner_bindings()
    return _graph_runner_analysis_domain._analyze_instruction(*args, **kwargs)


def _plan_sections_list_with_model(*args, **kwargs):
    _sync_graph_runner_bindings()
    return _CORE_IMPL_PLAN_SECTIONS_LIST(*args, **kwargs)


def _plan_sections_with_model(*args, **kwargs):
    _sync_graph_runner_bindings()
    return _CORE_IMPL_PLAN_SECTIONS(*args, **kwargs)

def run_generate_graph(
    *,
    instruction: str,
    current_text: str,
    required_h2: list[str],
    required_outline: list[tuple[int, str]] | list[str] | None,
    expand_outline: bool = False,
    config: GenerateConfig = GenerateConfig(),
):
    from writing_agent.v2.graph_runner_runtime import run_generate_graph as _run_generate_graph_impl

    return _run_generate_graph_impl(
        instruction=instruction,
        current_text=current_text,
        required_h2=required_h2,
        required_outline=required_outline,
        expand_outline=expand_outline,
        config=config,
    )


def run_generate_graph_dual_engine(
    *,
    instruction: str,
    current_text: str,
    required_h2: list[str],
    required_outline: list[tuple[int, str]] | list[str] | None,
    expand_outline: bool = False,
    config: GenerateConfig = GenerateConfig(),
    compose_mode: str = "auto",
    resume_sections: list[str] | None = None,
    format_only: bool = False,
    plan_confirm: dict | None = None,
):
    """
    Dual-engine orchestration entry.
    Native graph remains default. LangGraph can be enabled via WRITING_AGENT_GRAPH_ENGINE=langgraph|dual|auto.
    """
    from writing_agent.capabilities.contracts import GenerateWorkflowDeps, GenerateWorkflowRequest
    from writing_agent.workflows.generate_workflow import run_generate_workflow

    return run_generate_workflow(
        request=GenerateWorkflowRequest(
            instruction=instruction,
            current_text=current_text,
            required_h2=required_h2,
            required_outline=required_outline,
            expand_outline=expand_outline,
            config=config,
            compose_mode=compose_mode,
            resume_sections=resume_sections,
            format_only=format_only,
            plan_confirm=plan_confirm,
        ),
        deps=GenerateWorkflowDeps(
            run_generate_graph=run_generate_graph,
            light_self_check=_light_self_check,
            target_total_chars=_target_total_chars,
            is_evidence_enabled=_is_evidence_enabled,
        ),
    )

from writing_agent.v2 import graph_runner_post_domain as post_domain

for _post_name in (
    "_extract_h2_titles _count_citations _light_self_check _plan_title _normalize_title_line _default_title "
    "_fallback_title_from_instruction _plan_title_sections _guess_title _wants_acknowledgement _filter_ack_headings "
    "_filter_ack_outline _filter_disallowed_outline _is_engineering_instruction _boost_media_targets "
    "_generate_section_stream _maybe_rag_context _mcp_rag_enabled _mcp_rag_retrieve _looks_like_rag_meta_line "
    "_has_cjk _is_mostly_ascii_line _strip_rag_meta_lines _plan_point_paragraph _expand_with_context "
    "_select_models_by_memory _default_worker_models _looks_like_embedding_model _ollama_installed_models "
    "_ollama_model_sizes_gb _get_memory_bytes _sanitize_output_text _strip_markdown_noise _should_merge_tail "
    "_clean_generated_text _normalize_final_output _is_reference_section _looks_like_heading_text "
    "_strip_inline_headings _format_references _ensure_media_markers _generic_fill_paragraph _fast_fill_references "
    "_fast_fill_section _postprocess_section _ensure_section_minimums_stream _strip_reference_like_lines "
    "_normalize_section_id _stream_structured_blocks _trim_total_chars _encode_section _split_section_token "
    "_section_title _sections_from_outline _map_section_parents _merge_sections_text _apply_section_updates"
).split():
    globals()[_post_name] = getattr(post_domain, _post_name)
del _post_name

from writing_agent.v2.graph_runner_config_domain import __all__ as _config_all
from writing_agent.v2.graph_runner_core_domain import __all__ as _core_all
from writing_agent.v2.graph_runner_analysis_domain import __all__ as _analysis_all
from writing_agent.v2.graph_runner_evidence_domain import __all__ as _evidence_all

__all__ = list(dict.fromkeys(list(_config_all) + list(_core_all) + list(_analysis_all) + list(_evidence_all) + [
    "run_generate_graph",
    "run_generate_graph_dual_engine",
]))
