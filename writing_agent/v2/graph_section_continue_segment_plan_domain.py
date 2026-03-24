"""Section continuation segmentation planning helpers."""

from __future__ import annotations

import json
import re
from collections.abc import Callable

from writing_agent.v2 import graph_section_continue_segment_config_domain as config_domain


def _base():
    from writing_agent.v2 import graph_section_continue_segment_domain as base

    return base


def _escape_prompt_text(raw: object) -> str:
    return str(_base()._escape_prompt_text(raw))


def _continue_segment_enabled() -> bool:
    return bool(config_domain._continue_segment_enabled())


def _continue_segment_threshold_chars() -> int:
    return int(config_domain._continue_segment_threshold_chars())


def _continue_segment_target_chars() -> int:
    return int(config_domain._continue_segment_target_chars())


def _continue_segment_max_segments() -> int:
    return int(config_domain._continue_segment_max_segments())


def _split_integer_budget(total: int, parts: int) -> list[int]:
    return list(config_domain._split_integer_budget(total, parts))


def _split_list_evenly(items: list[str], parts: int) -> list[list[str]]:
    return list(config_domain._split_list_evenly(items, parts))

def _focus_point_weight(text: str) -> int:
    token = str(text or "").strip()
    if not token:
        return 1
    weight = max(1, len(re.sub(r"\s+", "", token)))
    if re.search(r"(架构|框架|流程|机制|路径|方法|实现|模块|交互|architecture|framework|workflow|process|method|implementation)", token, flags=re.IGNORECASE):
        weight += 8
    if re.search(r"(数据|指标|样本|证据|评估|政策|风险|区域|data|metric|sample|evidence|policy|risk|regional)", token, flags=re.IGNORECASE):
        weight += 4
    return weight

def _split_focus_points_balanced(items: list[str], parts: int) -> list[list[str]]:
    count = max(1, int(parts or 1))
    values = [str(x).strip() for x in (items or []) if str(x).strip()]
    if not values:
        return [[] for _ in range(count)]
    if count <= 1:
        return [values]
    buckets: list[list[str]] = [[] for _ in range(count)]
    bucket_weights = [0 for _ in range(count)]
    weighted_points = sorted(values, key=_focus_point_weight, reverse=True)
    for token in weighted_points:
        bucket_idx = min(range(count), key=lambda i: (bucket_weights[i], len(buckets[i]), i))
        buckets[bucket_idx].append(token)
        bucket_weights[bucket_idx] += _focus_point_weight(token)
    return buckets

def _split_integer_budget_weighted(total: int, weights: list[int]) -> list[int]:
    value = max(0, int(total or 0))
    clean_weights = [max(1, int(w or 1)) for w in (weights or [])]
    if not clean_weights:
        return [value]
    assigned = [int(value * w / sum(clean_weights)) for w in clean_weights]
    remainder = max(0, value - sum(assigned))
    order = sorted(range(len(clean_weights)), key=lambda i: clean_weights[i], reverse=True)
    for idx in order[:remainder]:
        assigned[idx] += 1
    return assigned

def _merge_continue_plan_hint(plan_hint: str, payload: dict[str, object]) -> str:
    seg_hint = json.dumps(payload, ensure_ascii=False)
    base = str(plan_hint or "").strip()
    if not base:
        return seg_hint
    return base + "\n" + seg_hint

def _append_incremental_text(base_text: str, extra_text: str) -> str:
    base = str(base_text or "").strip()
    extra = str(extra_text or "").strip()
    if not extra:
        return base
    if not base:
        return extra
    return base + "\n\n" + extra

def _extend_continue_user_for_retry(*, user: str, txt: str, body_len: int, min_chars: int, retry_reason: str, missing_chars: int, min_figures: int = 0) -> str:
    if not str(retry_reason or "").strip():
        return user
    retry_lines = [
        f"{user}",
        "<retry_reason>",
        f"{_escape_prompt_text(retry_reason)}",
        f"content below target ({body_len}/{min_chars}); continue generation.",
        "Also complete truncated paragraph tails.",
        "</retry_reason>",
        f"<latest_draft>\n{_escape_prompt_text(txt)}\n</latest_draft>",
        f"Please continue and add around {max(120, int(missing_chars or 0))} more characters.",
    ]
    if int(min_figures or 0) > 0:
        retry_lines.append(
            "If you emit any figure blocks during retry, they must use type=figure with valid kind+caption+data; never emit caption-only figure blocks."
        )
    return "\n".join(retry_lines)

def _plan_continue_segments(
    *,
    section: str,
    missing_chars: int,
    min_paras: int,
    min_tables: int,
    min_figures: int,
    dimension_hints: list[str] | None,
    is_reference_section: Callable[[str], bool],
) -> list[dict[str, object]]:
    if not _continue_segment_enabled():
        return []
    if is_reference_section(section):
        return []
    hints = [str(x).strip() for x in (dimension_hints or []) if str(x).strip()]
    if len(hints) < 2:
        return []
    threshold = _continue_segment_threshold_chars()
    semantic_trigger = int(missing_chars or 0) >= 240 and len(hints) >= 4 and (
        int(min_tables or 0) > 0 or int(min_figures or 0) > 0 or int(min_paras or 0) >= 3
    )
    if int(missing_chars or 0) < threshold and not semantic_trigger:
        return []
    workload_score = max(int(missing_chars or 0), int(missing_chars or 0) + max(0, len(hints) - 3) * 100, threshold if semantic_trigger else 0)
    desired = max(2, (workload_score + _continue_segment_target_chars() - 1) // _continue_segment_target_chars())
    segment_count = max(2, min(_continue_segment_max_segments(), desired, len(hints)))
    focus_groups = _split_focus_points_balanced(hints, segment_count)
    if any(not group for group in focus_groups):
        return []
    group_weights = [sum(_focus_point_weight(item) for item in group) for group in focus_groups]
    char_parts = _split_integer_budget_weighted(max(120, int(missing_chars or 0)), group_weights)
    out: list[dict[str, object]] = []
    for idx, focus_points in enumerate(focus_groups):
        payload = {
            "segment_index": idx + 1,
            "segment_total": segment_count,
            "focus_points": list(focus_points),
            "missing_chars": int(char_parts[idx] or 0),
        }
        out.append(
            {
                "index": idx,
                "segment_index": idx + 1,
                "segment_total": segment_count,
                "focus_points": list(focus_points),
                "missing_chars": int(char_parts[idx] or 0),
                "min_paras": 1,
                "plan_hint": payload,
            }
        )
    return out

__all__ = [name for name in globals() if not name.startswith("__")]
