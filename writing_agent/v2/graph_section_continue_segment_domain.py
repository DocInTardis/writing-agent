"""Section continuation segmentation helpers."""

from __future__ import annotations

from writing_agent.v2 import graph_section_continue_segment_config_domain as config_domain
from writing_agent.v2 import graph_section_continue_segment_execute_domain as execute_domain
from writing_agent.v2 import graph_section_continue_segment_plan_domain as plan_domain


def _continue_domain_module():
    from writing_agent.v2 import graph_section_continue_domain as _continue_domain

    return _continue_domain


def _meta_firewall_scan(text: str) -> bool:
    return bool(_continue_domain_module()._meta_firewall_scan(text))


def _build_continue_prompt(**kwargs):
    return _continue_domain_module()._build_continue_prompt(**kwargs)


def _continue_once(**kwargs):
    return _continue_domain_module()._continue_once(**kwargs)


def _section_body_len(text: str) -> int:
    return int(_continue_domain_module()._section_body_len(text))


def _escape_prompt_text(raw: object) -> str:
    return str(_continue_domain_module()._escape_prompt_text(raw))


_continue_segment_enabled = config_domain._continue_segment_enabled
_continue_segment_threshold_chars = config_domain._continue_segment_threshold_chars
_continue_segment_target_chars = config_domain._continue_segment_target_chars
_continue_segment_max_segments = config_domain._continue_segment_max_segments
_split_integer_budget = config_domain._split_integer_budget
_split_list_evenly = config_domain._split_list_evenly
_focus_point_weight = plan_domain._focus_point_weight
_split_focus_points_balanced = plan_domain._split_focus_points_balanced
_split_integer_budget_weighted = plan_domain._split_integer_budget_weighted
_merge_continue_plan_hint = plan_domain._merge_continue_plan_hint
_append_incremental_text = plan_domain._append_incremental_text
_extend_continue_user_for_retry = plan_domain._extend_continue_user_for_retry
_plan_continue_segments = plan_domain._plan_continue_segments
_drain_continue_segment_events = execute_domain._drain_continue_segment_events
_continue_with_optional_segments = execute_domain._continue_with_optional_segments


__all__ = [name for name in globals() if not name.startswith("__")]
