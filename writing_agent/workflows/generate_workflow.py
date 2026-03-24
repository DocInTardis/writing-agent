"""Generate workflow assembly over runtime backends and business capabilities."""

from __future__ import annotations

import time
from typing import Any

from writing_agent.capabilities import composition, planning, quality
from writing_agent.capabilities.contracts import GenerateWorkflowDeps, GenerateWorkflowRequest, GraphHandler
from writing_agent.state_engine import DualGraphEngine, should_use_langgraph


def _resolve_engine_name(events: list[dict[str, Any]], *, use_langgraph: bool) -> str:
    for row in reversed(list(events or [])):
        if not isinstance(row, dict):
            continue
        meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        candidate = str(meta.get("engine") or "").strip()
        if candidate:
            return candidate
    return "langgraph" if use_langgraph else "native"


def _build_handlers(*, request: GenerateWorkflowRequest, deps: GenerateWorkflowDeps) -> dict[str, GraphHandler]:
    return {
        "planner": lambda _payload: planning.build_plan_patch(request=request),
        "plan_confirm": lambda payload: planning.confirm_plan(payload=payload),
        "writer": lambda payload: composition.compose_draft(
            payload=payload,
            request=request,
            run_generate_graph_fn=deps.run_generate_graph,
        ),
        "reviewer": lambda payload: quality.review_draft(
            payload=payload,
            required_h2=request.required_h2,
            config=request.config,
            light_self_check_fn=deps.light_self_check,
            target_total_chars_fn=deps.target_total_chars,
            is_evidence_enabled_fn=deps.is_evidence_enabled,
        ),
        "qa": lambda payload: quality.finalize_draft(payload=payload),
    }


def run_generate_workflow(*, request: GenerateWorkflowRequest, deps: GenerateWorkflowDeps) -> dict[str, Any]:
    use_langgraph = should_use_langgraph()
    engine = DualGraphEngine(use_langgraph=use_langgraph)
    run_id = f"graph_{int(time.time() * 1000)}"
    state, events = engine.run(
        run_id=run_id,
        payload={
            "instruction": request.instruction,
            "current_text": request.current_text,
            "compose_mode": request.compose_mode,
            "resume_sections": list(request.resume_sections or []),
            "format_only": bool(request.format_only),
            "plan_confirm": dict(request.plan_confirm or {}),
        },
        handlers=_build_handlers(request=request, deps=deps),
    )
    route = state.get("_route") if isinstance(state.get("_route"), dict) else {}
    return {
        "ok": 1,
        "text": str(state.get("final_text") or ""),
        "problems": list(state.get("problems") or []),
        "prompt_trace": list(state.get("prompt_trace") or []),
        "terminal_status": str(state.get("terminal_status") or "failed"),
        "failure_reason": str(state.get("failure_reason") or ""),
        "quality_snapshot": dict(state.get("quality_snapshot") or {}),
        "plan_feedback": dict(state.get("plan_feedback") or {}),
        "trace_id": str(state.get("trace_id") or ""),
        "engine": _resolve_engine_name(events, use_langgraph=use_langgraph),
        "route_id": str(route.get("id") or ""),
        "route_entry": str(route.get("entry_node") or ""),
    }


__all__ = [name for name in globals() if not name.startswith("__")]
