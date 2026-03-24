"""Runtime helpers for planning section segmentation."""

from __future__ import annotations

import json


def _base():
    from writing_agent.v2 import graph_runner_runtime_segment_domain as base

    return base


def _collect_section_segment_hints(*, plan: PlanSection | None, contract) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    def _push(raw: object) -> None:
        token = str(raw or "").strip()
        if not token:
            return
        if _base()._meta_firewall_scan(token):
            return
        key = token.casefold()
        if key in seen:
            return
        seen.add(key)
        out.append(token)

    if plan:
        for item in list(plan.key_points or []):
            _push(item)
        for item in list(plan.evidence_queries or []):
            _push(item)
    if contract is not None:
        for item in list(getattr(contract, "dimension_hints", []) or []):
            _push(item)
    return out


def _plan_section_segments(
    *,
    section_key: str,
    section_title: str,
    plan: PlanSection | None,
    contract,
    targets: SectionTargets,
) -> list[dict[str, object]]:
    _ = section_key
    base = _base()
    sec_title = str(section_title or "").strip()
    if not base._section_segment_enabled():
        return []
    if not sec_title or base._is_reference_section(sec_title):
        return []
    threshold = base._section_segment_threshold_chars()
    target_chars = max(
        int(getattr(plan, "target_chars", 0) or 0),
        int(getattr(targets, "min_chars", 0) or 0),
        int(getattr(contract, "min_chars", 0) or 0),
    )
    hints = _collect_section_segment_hints(plan=plan, contract=contract)
    if len(hints) < 2:
        return []
    semantic_trigger = (
        target_chars >= 400
        and len(hints) >= 6
        and (
            int(getattr(targets, "min_tables", 0) or 0) > 0
            or int(getattr(targets, "min_figures", 0) or 0) > 0
            or base._is_segment_candidate_title(sec_title)
        )
    )
    if target_chars < threshold and not semantic_trigger:
        return []
    workload_score = max(target_chars, target_chars + max(0, len(hints) - 4) * 180, 1200 if semantic_trigger else 0)
    desired = max(2, (workload_score + base._section_segment_target_chars() - 1) // base._section_segment_target_chars())
    segment_count = max(2, min(base._section_segment_max_segments(), desired, len(hints)))
    if segment_count <= 1:
        return []

    focus_groups = base._split_list_evenly(hints, segment_count)
    if any(not group for group in focus_groups):
        return []

    min_chars_parts = base._split_integer_budget(int(getattr(targets, "min_chars", 0) or 0), segment_count)
    max_chars_value = int(getattr(targets, "max_chars", 0) or 0)
    max_chars_parts = base._split_integer_budget(max_chars_value, segment_count) if max_chars_value > 0 else [0] * segment_count
    para_seed = max(segment_count, int(getattr(targets, "min_paras", 0) or 0))
    min_paras_parts = base._split_integer_budget(para_seed, segment_count)

    out: list[dict[str, object]] = []
    for idx in range(segment_count):
        focus_points = focus_groups[idx]
        payload: dict[str, object] = {
            "section_title": sec_title,
            "segment_index": idx + 1,
            "segment_total": segment_count,
            "target_chars": int(min_chars_parts[idx] or 0),
            "key_points": list(focus_points),
        }
        evidence_queries = list(getattr(plan, "evidence_queries", []) or [])
        if evidence_queries:
            payload["evidence_queries"] = evidence_queries[: min(4, len(evidence_queries))]
        out.append(
            {
                "index": idx,
                "segment_index": idx + 1,
                "segment_total": segment_count,
                "focus_points": list(focus_points),
                "min_chars": int(min_chars_parts[idx] or 0),
                "max_chars": int(max_chars_parts[idx] or 0),
                "min_paras": max(1, int(min_paras_parts[idx] or 0)),
                "min_tables": int(getattr(targets, "min_tables", 0) or 0) if idx == 0 else 0,
                "min_figures": int(getattr(targets, "min_figures", 0) or 0) if idx == 0 else 0,
                "workload_score": int(workload_score),
                "plan_hint": json.dumps(payload, ensure_ascii=False),
            }
        )
    return out


__all__ = [name for name in globals() if not name.startswith("__")]
