"""Context module.

This module belongs to `writing_agent.state_engine` in the writing-agent codebase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RouteScore:
    role_weight: float = 0.0
    intent_weight: float = 0.0
    scope_weight: float = 0.0
    final_score: float = 0.0


@dataclass
class RoutingDecision:
    route: str = "E22"
    score: RouteScore = field(default_factory=RouteScore)


@dataclass
class LockView:
    global_lock: bool = False
    partial_locks: list[dict[str, Any]] = field(default_factory=list)
    conflict_reason: str | None = None
    released: bool = False


@dataclass
class StreamingView:
    stream_id: str | None = None
    section_id: str | None = None
    section_key: str | None = None
    cursor: int = 0
    token_usage: dict[str, int] = field(default_factory=lambda: {"prompt": 0, "completion": 0})
    aborted: bool = False


@dataclass
class MediaView:
    unresolved_media_count: int = 0
    items: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class VerifyView:
    checks: list[dict[str, Any]] = field(default_factory=list)
    has_warning: bool = False
    has_error: bool = False


@dataclass
class RollbackView:
    failed_snapshot_id: str | None = None
    stable_snapshot_id: str | None = None
    incident_diff_id: str | None = None


@dataclass
class CleanupView:
    lock_release_done: bool = False
    temp_clean_done: bool = False
    log_flush_done: bool = False


@dataclass
class ErrorView:
    code: str | None = None
    message: str | None = None
    retryable: bool = False


@dataclass
class TelemetryView:
    retry_count: int = 0
    latency_ms: int = 0
    action_seq: int = 0
    idempotency_key: str = field(default_factory=lambda: uuid.uuid4().hex)


@dataclass
class StateContext:
    schema_version: str
    trace_id: str
    session_id: str
    doc_id: str
    request_id: str
    state: str
    state_rev: int
    created_at: str
    updated_at: str

    request: dict[str, Any]
    role: dict[str, Any]
    intent: dict[str, Any]
    scope: dict[str, Any]
    routing: RoutingDecision = field(default_factory=RoutingDecision)

    locks: LockView = field(default_factory=LockView)
    streaming: StreamingView = field(default_factory=StreamingView)
    media: MediaView = field(default_factory=MediaView)
    verify: VerifyView = field(default_factory=VerifyView)
    rollback: RollbackView = field(default_factory=RollbackView)
    cleanup: CleanupView = field(default_factory=CleanupView)
    error: ErrorView = field(default_factory=ErrorView)
    telemetry: TelemetryView = field(default_factory=TelemetryView)

    transition_id: str | None = None
    last_trigger: str | None = None

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        doc_id: str,
        request_source: str,
        instruction_raw: str,
        instruction_normalized: str,
        state: str = "S02_DOC_READY",
    ) -> "StateContext":
        now = _now_iso()
        return cls(
            schema_version="2.1",
            trace_id=uuid.uuid4().hex,
            session_id=session_id,
            doc_id=doc_id,
            request_id=uuid.uuid4().hex,
            state=state,
            state_rev=0,
            created_at=now,
            updated_at=now,
            request={
                "source": request_source,
                "instruction_raw": instruction_raw,
                "instruction_normalized": instruction_normalized,
                "user_id": None,
                "user_cancelled": False,
            },
            role={"role_type": "R04", "confidence": 0.0, "hard_constraints": ["none"], "soft_style_prompt": ""},
            intent={"intent_type": "I08", "confidence": 0.0, "reason": ""},
            scope={"scope_type": "C07", "target_ids": [], "selection_text": None},
        )

    def touch(self) -> None:
        self.updated_at = _now_iso()
        self.state_rev += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "doc_id": self.doc_id,
            "request_id": self.request_id,
            "state": self.state,
            "state_rev": self.state_rev,
            "transition_id": self.transition_id,
            "last_trigger": self.last_trigger,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "request": self.request,
            "role": self.role,
            "intent": self.intent,
            "scope": self.scope,
            "routing": {
                "route": self.routing.route,
                "score": {
                    "role_weight": self.routing.score.role_weight,
                    "intent_weight": self.routing.score.intent_weight,
                    "scope_weight": self.routing.score.scope_weight,
                    "final_score": self.routing.score.final_score,
                },
            },
            "locks": {
                "global_lock": self.locks.global_lock,
                "partial_locks": self.locks.partial_locks,
                "conflict_reason": self.locks.conflict_reason,
                "released": self.locks.released,
            },
            "streaming": {
                "stream_id": self.streaming.stream_id,
                "section_id": self.streaming.section_id,
                "section_key": self.streaming.section_key,
                "cursor": self.streaming.cursor,
                "token_usage": self.streaming.token_usage,
                "aborted": self.streaming.aborted,
            },
            "media": {
                "unresolved_media_count": self.media.unresolved_media_count,
                "items": self.media.items,
            },
            "verify": {
                "checks": self.verify.checks,
                "has_warning": self.verify.has_warning,
                "has_error": self.verify.has_error,
            },
            "rollback": {
                "failed_snapshot_id": self.rollback.failed_snapshot_id,
                "stable_snapshot_id": self.rollback.stable_snapshot_id,
                "incident_diff_id": self.rollback.incident_diff_id,
            },
            "cleanup": {
                "lock_release_done": self.cleanup.lock_release_done,
                "temp_clean_done": self.cleanup.temp_clean_done,
                "log_flush_done": self.cleanup.log_flush_done,
            },
            "error": {
                "code": self.error.code,
                "message": self.error.message,
                "retryable": self.error.retryable,
            },
            "telemetry": {
                "retry_count": self.telemetry.retry_count,
                "latency_ms": self.telemetry.latency_ms,
                "action_seq": self.telemetry.action_seq,
                "idempotency_key": self.telemetry.idempotency_key,
            },
        }


@dataclass
class StateEvent:
    event_id: str
    trace_id: str
    at: str
    from_state: str
    to_state: str
    trigger: str
    guard: str
    action: str
    status: str
    context_patch: dict[str, Any]
    error: dict[str, Any] | None = None

    @classmethod
    def create(
        cls,
        *,
        trace_id: str,
        from_state: str,
        to_state: str,
        trigger: str,
        guard: str,
        action: str,
        status: str,
        context_patch: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> "StateEvent":
        return cls(
            event_id=uuid.uuid4().hex,
            trace_id=trace_id,
            at=_now_iso(),
            from_state=from_state,
            to_state=to_state,
            trigger=trigger,
            guard=guard,
            action=action,
            status=status,
            context_patch=context_patch or {},
            error=error,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "trace_id": self.trace_id,
            "at": self.at,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "trigger": self.trigger,
            "guard": self.guard,
            "action": self.action,
            "status": self.status,
            "context_patch": self.context_patch,
            "error": self.error,
        }


@dataclass
class ActionResult:
    ok: bool
    context_patch: dict[str, Any] = field(default_factory=dict)
    emit_events: list[dict[str, Any]] = field(default_factory=list)
    next_state_override: str | None = None
    retryable: bool = False
    error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "context_patch": self.context_patch,
            "emit_events": self.emit_events,
            "next_state_override": self.next_state_override,
            "retryable": self.retryable,
            "error": self.error,
        }

