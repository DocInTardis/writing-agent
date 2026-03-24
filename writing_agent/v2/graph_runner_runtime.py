"""Compatibility wrapper for split graph runner runtime domains."""

# Runtime prompt-contract markers retained in wrapper:
# <available_sources>
# _runtime_escape_prompt_text

from __future__ import annotations

import inspect
import sys

from writing_agent.llm.factory import get_default_provider, get_provider_name, get_provider_snapshot
from writing_agent.v2.graph_runner import *  # noqa: F401,F403
from writing_agent.v2 import graph_runner as _graph_runner_module
from writing_agent.v2 import graph_runner_runtime_common_domain as _common_domain
from writing_agent.v2 import graph_runner_runtime_section_domain as _section_domain
from writing_agent.v2.graph_runner_runtime_session_domain import run_generate_graph_impl

for _name in dir(_graph_runner_module):
    if _name.startswith("__"):
        continue
    if _name not in globals():
        globals()[_name] = getattr(_graph_runner_module, _name)


_RESERVED_IMPL_NAMES = {"run_generate_graph", "ModelPool", "SectionTargets", "PlanSection", "_GENERATION_SLOT_MAP"}
_COMMON_IMPLS: dict[str, object] = {}
_SECTION_IMPLS: dict[str, object] = {}


def _sync_runtime_bindings() -> None:
    this = sys.modules[__name__]
    shared = {name: value for name, value in vars(this).items() if (not name.startswith("__")) and (name not in _RESERVED_IMPL_NAMES)}
    for module in (_common_domain, _section_domain):
        for name, value in shared.items():
            setattr(module, name, value)


def _bind_impl(module, name: str):
    impl = (_COMMON_IMPLS if module is _common_domain else _SECTION_IMPLS)[name]

    def _wrapper(*args, **kwargs):
        _sync_runtime_bindings()
        return impl(*args, **kwargs)

    _wrapper.__name__ = name
    _wrapper.__qualname__ = name
    return _wrapper


_COMMON_EXPORTS = [
    "_runtime_escape_prompt_text",
    "_derive_reference_query",
    "_should_synthesize_analysis",
    "_synthesize_topic_and_keywords",
    "_synthesize_analysis_from_requirements",
    "_plan_detail_skip_decision",
    "_should_skip_plan_detail",
    "_fast_plan_sections_for_instruction",
    "_validate_plan_detail",
    "_is_starvation_scored_section",
    "_starvation_section_key",
    "_starvation_failure_decision",
    "_provider_default_model",
    "_provider_timeout_s",
    "_provider_default_per_model_concurrency",
    "_generation_slot_enabled",
    "_generation_slot_limit",
    "_generation_slot",
    "_call_with_generation_slot",
    "_guarded_stream_structured_blocks",
    "_provider_default_evidence_workers",
    "_runtime_json_cache_enabled",
    "_default_evidence_pack",
    "_normalize_evidence_pack",
    "_runtime_evidence_cache_key",
    "_load_evidence_pack_cached",
    "_is_keywords_section_runtime",
    "_section_cache_min_chars",
    "_count_runtime_cjk",
    "_count_runtime_latin1_noise",
    "_repair_mixed_cached_mojibake",
    "_decode_cache_literal_escapes",
    "_normalize_cached_keywords",
    "_sanitize_cached_section_text",
    "_usable_cached_section_text",
    "_prime_cached_sections",
    "_runtime_json_cache_key",
    "_runtime_json_cache_get",
    "_runtime_json_cache_put",
    "_serialize_plan_map",
    "_deserialize_plan_map",
    "_provider_preflight",
]

_SECTION_EXPORTS = [
    "_compute_section_targets",
    "_generate_section_stream",
    "_section_segment_enabled",
    "_section_segment_threshold_chars",
    "_section_segment_target_chars",
    "_section_segment_max_segments",
    "_split_integer_budget",
    "_split_list_evenly",
    "_is_segment_candidate_title",
    "_collect_section_segment_hints",
    "_plan_section_segments",
    "_drain_segment_trace_events",
    "_assemble_section_segment_texts",
    "_draft_section_with_optional_segments",
    "_runtime_split_sentences",
    "_runtime_sentence_is_unsupported_claim",
    "_prune_unsupported_claim_paragraphs",
    "_normalize_final_output",
    "_ensure_section_minimums_stream",
]

_COMMON_IMPLS.update({name: getattr(_common_domain, name) for name in _COMMON_EXPORTS})
_SECTION_IMPLS.update({name: getattr(_section_domain, name) for name in _SECTION_EXPORTS})
for _name in _COMMON_EXPORTS:
    globals()[_name] = _bind_impl(_common_domain, _name)
for _name in _SECTION_EXPORTS:
    globals()[_name] = _bind_impl(_section_domain, _name)

for _name in ("ModelPool", "SectionTargets", "PlanSection"):
    globals()[_name] = getattr(_section_domain, _name)

_GENERATION_SLOT_MAP = _common_domain._GENERATION_SLOT_MAP


def run_generate_graph(
    *,
    instruction: str,
    current_text: str,
    required_h2: list[str] | None,
    required_outline: list[tuple[int, str]] | None = None,
    expand_outline: bool = False,
    config: GenerateConfig,
):
    _sync_runtime_bindings()
    return run_generate_graph_impl(
        sys.modules[__name__],
        instruction=instruction,
        current_text=current_text,
        required_h2=required_h2,
        required_outline=required_outline,
        expand_outline=expand_outline,
        config=config,
    )


__all__ = [name for name in globals() if not name.startswith("__")]
