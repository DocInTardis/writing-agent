"""Section continuation and minimum-satisfaction helpers for draft generation."""

from __future__ import annotations

from writing_agent.v2.graph_section_continue_segment_domain import (
    _append_incremental_text,
    _continue_segment_enabled,
    _continue_segment_max_segments,
    _continue_segment_target_chars,
    _continue_segment_threshold_chars,
    _continue_with_optional_segments,
    _drain_continue_segment_events,
    _extend_continue_user_for_retry,
    _focus_point_weight,
    _merge_continue_plan_hint,
    _plan_continue_segments,
    _split_focus_points_balanced,
    _split_integer_budget,
    _split_integer_budget_weighted,
    _split_list_evenly,
)
from writing_agent.v2 import graph_section_continue_helpers_domain as helpers_domain
from writing_agent.v2 import graph_section_continue_prompt_domain as prompt_domain
from writing_agent.v2 import graph_section_continue_runtime_domain as runtime_domain

_escape_prompt_text = helpers_domain._escape_prompt_text
normalize_section_id = helpers_domain.normalize_section_id
_section_body_len = helpers_domain._section_body_len
_section_paragraphs = helpers_domain._section_paragraphs
_is_reference_or_list_paragraph = helpers_domain._is_reference_or_list_paragraph
_paragraph_looks_complete = helpers_domain._paragraph_looks_complete
_has_incomplete_paragraph = helpers_domain._has_incomplete_paragraph
_ensure_paragraph_integrity = helpers_domain._ensure_paragraph_integrity
_section_minimum_satisfied = helpers_domain._section_minimum_satisfied
_build_continue_prompt = prompt_domain._build_continue_prompt
_continue_once = prompt_domain._continue_once
ensure_section_minimums_stream = runtime_domain.ensure_section_minimums_stream

__all__ = [name for name in globals() if not name.startswith("__")]
