"""Quality capability adapters for generate workflow."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from writing_agent.capabilities.contracts import GraphStatePatch


def review_draft(
    *,
    payload: GraphStatePatch,
    required_h2: list[str],
    config: Any,
    light_self_check_fn: Callable[..., list[str]],
    target_total_chars_fn: Callable[[Any], int],
    is_evidence_enabled_fn: Callable[[], bool],
) -> GraphStatePatch:
    draft = str(payload.get("draft") or "")
    issues = light_self_check_fn(
        text=draft,
        sections=list(required_h2 or []),
        target_chars=target_total_chars_fn(config),
        evidence_enabled=is_evidence_enabled_fn(),
        reference_sources=[],
    )
    return {
        "review": {"issues": issues},
        "fixups": [],
        "prompt_trace": list(payload.get("prompt_trace") or []),
        "terminal_status": str(payload.get("terminal_status") or ""),
        "failure_reason": str(payload.get("failure_reason") or ""),
        "quality_snapshot": dict(payload.get("quality_snapshot") or {}),
    }


def finalize_draft(*, payload: GraphStatePatch) -> GraphStatePatch:
    review = payload.get("review") if isinstance(payload.get("review"), dict) else {}
    problems = list(review.get("issues") or payload.get("problems") or [])
    terminal_status_raw = str(payload.get("terminal_status") or "").strip().lower()
    terminal_status = terminal_status_raw if terminal_status_raw in {"success", "failed", "interrupted"} else ""
    if not terminal_status:
        terminal_status = "success" if not problems else "failed"
    failure_reason = str(payload.get("failure_reason") or "").strip()
    if terminal_status != "success" and not failure_reason:
        failure_reason = "quality_gate_failed" if problems else "unknown_failure"
    quality_snapshot = dict(payload.get("quality_snapshot") or {})
    if not quality_snapshot:
        quality_snapshot = {
            "status": terminal_status,
            "problem_count": len(problems),
            "has_text": bool(str(payload.get("draft") or "").strip()),
        }
    return {
        "final_text": str(payload.get("draft") or ""),
        "problems": problems,
        "prompt_trace": list(payload.get("prompt_trace") or []),
        "terminal_status": terminal_status,
        "failure_reason": failure_reason,
        "quality_snapshot": quality_snapshot,
        "plan_feedback": dict(payload.get("plan_feedback") or {}),
    }


__all__ = [name for name in globals() if not name.startswith("__")]
