"""Runtime module.

This module belongs to `writing_agent.state_engine` in the writing-agent codebase.
"""

from __future__ import annotations

from typing import Any

from .context import StateContext, StateEvent


class StateRuntime:
    def __init__(self, context: StateContext) -> None:
        self.context = context
        self.events: list[StateEvent] = []

    def transition(
        self,
        *,
        to_state: str,
        trigger: str,
        guard: str = "",
        action: str = "",
        status: str = "ok",
        context_patch: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> StateEvent:
        from_state = self.context.state
        if context_patch:
            self._patch_context(context_patch)
        self.context.state = to_state
        self.context.last_trigger = trigger
        self.context.touch()
        ev = StateEvent.create(
            trace_id=self.context.trace_id,
            from_state=from_state,
            to_state=to_state,
            trigger=trigger,
            guard=guard,
            action=action,
            status=status,
            context_patch=context_patch or {},
            error=error,
        )
        self.context.transition_id = ev.event_id
        self.events.append(ev)
        return ev

    def _patch_context(self, patch: dict[str, Any]) -> None:
        for k, v in patch.items():
            if not hasattr(self.context, k):
                continue
            cur = getattr(self.context, k)
            if hasattr(cur, "__dict__") and isinstance(v, dict):
                for inner_k, inner_v in v.items():
                    if hasattr(cur, inner_k):
                        setattr(cur, inner_k, inner_v)
            else:
                setattr(self.context, k, v)

    def event_dicts(self) -> list[dict[str, Any]]:
        return [x.to_dict() for x in self.events]

