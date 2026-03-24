"""Composition capability adapters for generate workflow."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from writing_agent.capabilities.contracts import GenerateWorkflowRequest, GraphStatePatch


def compose_draft(
    *,
    payload: GraphStatePatch,
    request: GenerateWorkflowRequest,
    run_generate_graph_fn: Callable[..., Iterable[dict[str, Any]]],
) -> GraphStatePatch:
    if not bool(payload.get("plan_confirmed", True)):
        reason = str(payload.get("failure_reason") or "plan_not_confirmed_by_user")
        return {
            "draft": str(request.current_text or ""),
            "problems": [reason],
            "prompt_trace": list(payload.get("prompt_trace") or []),
            "terminal_status": "interrupted",
            "failure_reason": reason,
            "quality_snapshot": dict(payload.get("quality_snapshot") or {}),
        }

    generator = run_generate_graph_fn(
        instruction=request.instruction,
        current_text=request.current_text,
        required_h2=list(payload.get("required_h2") or request.required_h2 or []),
        required_outline=list(payload.get("required_outline") or request.required_outline or []),
        expand_outline=bool(request.expand_outline),
        config=request.config,
    )
    final_text = ""
    problems: list[str] = []
    prompt_trace: list[dict[str, Any]] = []
    final_event: dict[str, Any] = {}
    for event in generator:
        if not isinstance(event, dict):
            continue
        if event.get("event") == "prompt_route":
            meta = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
            prompt_trace.append(
                {
                    "stage": str(event.get("stage") or ""),
                    "metadata": dict(meta),
                }
            )
            continue
        if event.get("event") == "final":
            final_event = dict(event)
            final_text = str(event.get("text") or "")
            problems = list(event.get("problems") or [])
            break

    terminal_status_raw = str(final_event.get("status") or "").strip().lower()
    terminal_status = terminal_status_raw if terminal_status_raw in {"success", "failed", "interrupted"} else ""
    if not terminal_status:
        terminal_status = "success" if final_text.strip() else "failed"
    failure_reason = str(final_event.get("failure_reason") or "").strip()
    if terminal_status != "success" and not failure_reason:
        failure_reason = "empty_draft"

    quality_snapshot = (
        dict(final_event.get("quality_snapshot") or {})
        if isinstance(final_event.get("quality_snapshot"), dict)
        else {}
    )
    if not quality_snapshot:
        quality_snapshot = {
            "status": terminal_status,
            "problem_count": len(problems),
            "has_text": bool(final_text.strip()),
        }

    return {
        "draft": final_text,
        "problems": problems,
        "prompt_trace": prompt_trace[-24:],
        "terminal_status": terminal_status,
        "failure_reason": failure_reason,
        "quality_snapshot": quality_snapshot,
        "runtime_status": str(final_event.get("runtime_status") or quality_snapshot.get("runtime_status") or terminal_status),
        "runtime_failure_reason": str(
            final_event.get("runtime_failure_reason") or quality_snapshot.get("runtime_failure_reason") or ""
        ),
        "quality_passed": bool(
            final_event.get("quality_passed", quality_snapshot.get("quality_passed", terminal_status == "success"))
        ),
        "quality_failure_reason": str(
            final_event.get("quality_failure_reason") or quality_snapshot.get("quality_failure_reason") or ""
        ),
    }


__all__ = [name for name in globals() if not name.startswith("__")]
