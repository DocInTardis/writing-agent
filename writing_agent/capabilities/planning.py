"""Planning capability adapters for generate workflow."""

from __future__ import annotations

from writing_agent.capabilities.contracts import GenerateWorkflowRequest, GraphStatePatch


def build_plan_patch(*, request: GenerateWorkflowRequest) -> GraphStatePatch:
    return {
        "required_h2": list(request.required_h2 or []),
        "required_outline": list(request.required_outline or []),
        "plan": {
            "compose_mode": str(request.compose_mode or "auto"),
            "resume_sections": list(request.resume_sections or []),
        },
    }


def confirm_plan(*, payload: GraphStatePatch) -> GraphStatePatch:
    raw = payload.get("plan_confirm") if isinstance(payload.get("plan_confirm"), dict) else {}
    decision_raw = str(raw.get("decision") or "").strip().lower()
    if decision_raw in {"stop", "terminate", "cancel", "reject"}:
        decision = "interrupted"
    elif decision_raw in {"approved", "interrupted"}:
        decision = decision_raw
    else:
        decision = "approved"
    try:
        score = int(raw.get("score") or 0)
    except Exception:
        score = 0
    score = max(0, min(5, score))
    note = str(raw.get("note") or "").strip()[:300]
    feedback = {
        "decision": decision,
        "score": score,
        "note": note,
    }
    if decision == "interrupted":
        return {
            "plan_confirmed": False,
            "plan_feedback": feedback,
            "terminal_status": "interrupted",
            "failure_reason": "plan_not_confirmed_by_user",
            "quality_snapshot": {
                "status": "interrupted",
                "reason": "plan_not_confirmed_by_user",
                "problem_count": 1,
            },
        }
    return {"plan_confirmed": True, "plan_feedback": feedback}


__all__ = [name for name in globals() if not name.startswith("__")]
