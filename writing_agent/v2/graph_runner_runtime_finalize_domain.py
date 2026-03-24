"""Runtime finalization and prompt-trace helpers for graph_runner_runtime_session_domain.py."""

from __future__ import annotations

from typing import Any


def capture_prompt_trace(prompt_trace: list[dict], prompt_events: list[dict], row: dict) -> None:
    if not isinstance(row, dict):
        return
    prompt_trace.append(dict(row))
    if row.get("event") == "prompt_route":
        prompt_events.append(dict(row))



def build_final_event(
    *,
    provider_snapshot: dict,
    text: str,
    problems: list[str],
    status: str,
    failure_reason: str,
    quality_snapshot: dict | None = None,
    runtime_status: str = "",
    runtime_failure_reason: str = "",
    quality_passed: bool | None = None,
    quality_failure_reason: str = "",
    extra_fields: dict | None = None,
) -> dict:
    final_status = status if status in {"success", "failed", "interrupted"} else "failed"
    final_runtime_status = runtime_status if runtime_status in {"success", "failed", "interrupted"} else final_status
    final_quality_passed = bool(final_status == "success") if quality_passed is None else bool(quality_passed)
    snapshot = dict(quality_snapshot or {})
    snapshot["status"] = final_status
    snapshot["reason"] = str(failure_reason or "")
    snapshot.setdefault("provider", provider_snapshot)
    snapshot["runtime_status"] = final_runtime_status
    snapshot["runtime_failure_reason"] = str(runtime_failure_reason or "")
    snapshot["quality_passed"] = final_quality_passed
    snapshot["quality_failure_reason"] = str(quality_failure_reason or "")
    snapshot["quality_status"] = "passed" if final_quality_passed else "failed"
    payload = {
        "event": "final",
        "text": str(text or ""),
        "problems": list(problems or []),
        "status": final_status,
        "failure_reason": str(failure_reason or ""),
        "runtime_status": final_runtime_status,
        "runtime_failure_reason": str(runtime_failure_reason or ""),
        "quality_passed": final_quality_passed,
        "quality_failure_reason": str(quality_failure_reason or ""),
        "quality_snapshot": snapshot,
    }
    if isinstance(extra_fields, dict):
        payload.update(extra_fields)
    return payload



def resolve_terminal_quality(
    *,
    problems: list[str],
    reference_item_count: int,
    configured_min_ref_items: int,
    enforce_meta: bool,
    meta_residue_hits: list[str],
    enforce_reference_min: bool,
    enforce_final_validation: bool,
    final_validation: dict,
) -> tuple[bool, str, str]:
    quality_passed = True
    quality_failure_reason = ""
    if enforce_reference_min and reference_item_count < configured_min_ref_items:
        quality_passed = False
        quality_failure_reason = "reference_items_insufficient"
    if enforce_meta and meta_residue_hits:
        quality_passed = False
        quality_failure_reason = quality_failure_reason or "meta_residue_detected"
    if enforce_final_validation and (not bool(final_validation.get("passed", True))):
        quality_passed = False
        quality_failure_reason = quality_failure_reason or str(final_validation.get("failure_reason") or "final_validation_failed")
    if problems and (not quality_failure_reason):
        quality_passed = False
        quality_failure_reason = str(problems[0])
    terminal_status = "success" if quality_passed else "failed"
    return quality_passed, quality_failure_reason, terminal_status



def build_quality_snapshot(
    *,
    merged: str,
    problems: list[str],
    requested_min_total_chars: int,
    effective_min_total_chars: int,
    reference_item_count: int,
    contract_slot_violations: list[str],
    reference_format_violations: list[str],
    meta_residue_hits: list[str],
    rag_gate_dropped: list[dict[str, Any]],
    data_starvation_rows: list[dict[str, Any]],
    data_starvation_gate: dict[str, Any],
    evidence_fact_rows: list[dict[str, Any]],
    section_missing_rows: list[dict[str, Any]],
    section_specs: list[Any],
    assembly_map: Any,
    interrupted_sections: list[str],
    final_validation: dict[str, Any],
    originality_summary: dict[str, Any],
    body_len_fn,
) -> dict[str, Any]:
    return {
        "problem_count": len(problems),
        "has_text": bool(str(merged or "").strip()),
        "compact_chars": len(str(merged or "").strip()),
        "body_chars": int(body_len_fn(merged)),
        "requested_min_total_chars": requested_min_total_chars,
        "effective_min_total_chars": effective_min_total_chars,
        "reference_item_count": reference_item_count,
        "contract_slot_violation_count": len(contract_slot_violations),
        "contract_slot_violations": contract_slot_violations[:24],
        "reference_format_violation_count": len(reference_format_violations),
        "reference_format_violations": reference_format_violations[:12],
        "meta_residue_count": len(meta_residue_hits),
        "meta_residue_hits": list(meta_residue_hits[:8]),
        "rag_gate_dropped_count": len(rag_gate_dropped),
        "rag_gate_dropped": rag_gate_dropped[:12],
        "rag_data_starvation_count": len(data_starvation_rows),
        "rag_data_starvation_rows": data_starvation_rows[:12],
        "rag_data_starvation_gate": data_starvation_gate,
        "rag_data_starvation_ratio": float(data_starvation_gate.get("ratio") or 0.0),
        "rag_data_starvation_fail_ratio": float(data_starvation_gate.get("threshold") or 0.0),
        "rag_data_starvation_gate_triggered": bool(data_starvation_gate.get("triggered")),
        "evidence_fact_rows": evidence_fact_rows[:20],
        "section_missing_count": len(section_missing_rows),
        "section_missing_rows": section_missing_rows[:12],
        "section_specs": [spec.to_dict() for spec in section_specs[:40]],
        "assembly_map": assembly_map.to_dict(),
        "interrupted_sections": interrupted_sections[:12],
        "figure_count": int(final_validation.get("figure_count") or 0),
        "figure_score_avg": float(final_validation.get("figure_score_avg") or 0.0),
        "figure_pass_ratio": float(final_validation.get("figure_pass_ratio") or 0.0),
        "figure_review_count": int(final_validation.get("figure_review_count") or 0),
        "figure_drop_count": int(final_validation.get("figure_drop_count") or 0),
        "figure_gate_passed": bool(final_validation.get("figure_gate_passed", True)),
        "section_originality_hot_sample": originality_summary,
        "final_validation": final_validation,
    }


__all__ = [name for name in globals() if not name.startswith("__")]
