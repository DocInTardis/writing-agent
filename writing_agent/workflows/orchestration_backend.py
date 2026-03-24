"""Workflow-layer orchestration backend helpers."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, MutableMapping
from typing import Any

_ROUTE_GRAPH_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_PROMPT_TRACE_LIMIT = 24
_NO_SEMANTIC_FAILOVER_REASONS = frozenset(
    {
        "analysis_needs_clarification",
        "analysis_guard_failed",
        "section_language_mismatch",
        "section_hierarchy_insufficient",
        "must_include_missing",
        "keyword_domain_mismatch",
        "missing_section_headings",
        "section_content_missing",
    }
)


def sync_route_metric_meta(
    route_metric_meta: MutableMapping[str, object],
    meta: Mapping[str, Any] | None,
) -> MutableMapping[str, object]:
    if isinstance(meta, Mapping):
        route_metric_meta["route_id"] = str(meta.get("route_id") or "")
        route_metric_meta["route_entry"] = str(meta.get("route_entry") or "")
        route_metric_meta["engine"] = str(meta.get("engine") or "")
    return route_metric_meta



def sync_trace_context(
    trace_context: MutableMapping[str, object],
    *,
    route_path: str | None = None,
    fallback_trigger: str | None = None,
    fallback_recovered: bool | None = None,
    preserve_existing_trigger: bool = False,
) -> MutableMapping[str, object]:
    if route_path is not None:
        trace_context["route_path"] = str(route_path)
    if fallback_trigger is not None:
        has_existing = str(trace_context.get("fallback_trigger") or "").strip()
        if not (preserve_existing_trigger and has_existing):
            trace_context["fallback_trigger"] = str(fallback_trigger)
    if fallback_recovered is not None:
        trace_context["fallback_recovered"] = bool(fallback_recovered)
    return trace_context



def should_skip_semantic_failover(*, terminal_status: str, failure_reason: str) -> bool:
    status = str(terminal_status or "").strip().lower()
    reason = str(failure_reason or "").strip()
    return status in {"failed", "interrupted"} and reason in _NO_SEMANTIC_FAILOVER_REASONS



def text_requires_failover(text: object, *, min_chars: int = 20) -> bool:
    return len(str(text or "").strip()) < max(1, int(min_chars or 20))



def build_route_metric_extra(*, compose_mode: str = "", resume_sections: list[str] | None = None) -> dict[str, Any]:
    return {
        "compose_mode": str(compose_mode or "").strip(),
        "resume_sections_count": int(len(resume_sections or [])),
    }



def record_orchestration_metric(
    recorder_fn,
    *,
    event: str,
    phase: str,
    path: str,
    meta: Mapping[str, Any] | None = None,
    fallback_triggered: bool | None = None,
    fallback_recovered: bool | None = None,
    error_code: str = "",
    elapsed_ms: float | None = None,
    compose_mode: str = "",
    resume_sections: list[str] | None = None,
) -> None:
    data = meta if isinstance(meta, Mapping) else {}
    recorder_fn(
        event,
        phase=phase,
        path=path,
        route_id=str(data.get("route_id") or ""),
        route_entry=str(data.get("route_entry") or ""),
        engine=str(data.get("engine") or ""),
        fallback_triggered=fallback_triggered,
        fallback_recovered=fallback_recovered,
        error_code=error_code,
        elapsed_ms=elapsed_ms,
        extra=build_route_metric_extra(compose_mode=compose_mode, resume_sections=resume_sections),
    )



def route_graph_enabled(*, environ: Mapping[str, object] | None, dual_engine_runner: object = None) -> bool:
    if dual_engine_runner is None:
        return False
    raw = "0"
    if environ is not None:
        try:
            raw = str(environ.get("WRITING_AGENT_USE_ROUTE_GRAPH", "0") or "0")
        except Exception:
            raw = "0"
    return raw.strip().lower() in _ROUTE_GRAPH_TRUE_VALUES



def build_route_graph_kwargs(
    *,
    instruction: str,
    current_text: str,
    required_h2: list[str],
    required_outline: list[Any],
    expand_outline: bool,
    config: Any,
    compose_mode: str = "",
    resume_sections: list[str] | None = None,
    format_only: bool = False,
    plan_confirm: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "instruction": instruction,
        "current_text": current_text,
        "required_h2": list(required_h2 or []),
        "required_outline": list(required_outline or []),
        "expand_outline": bool(expand_outline),
        "config": config,
        "format_only": bool(format_only),
    }
    if compose_mode:
        payload["compose_mode"] = str(compose_mode)
    if resume_sections is not None:
        payload["resume_sections"] = list(resume_sections or [])
    if plan_confirm is not None:
        payload["plan_confirm"] = dict(plan_confirm or {})
    return payload



def build_legacy_graph_kwargs(
    *,
    instruction: str,
    current_text: str,
    required_h2: list[str],
    required_outline: list[Any],
    expand_outline: bool,
    config: Any,
) -> dict[str, Any]:
    return {
        "instruction": str(instruction or ""),
        "current_text": str(current_text or ""),
        "required_h2": list(required_h2 or []),
        "required_outline": list(required_outline or []),
        "expand_outline": bool(expand_outline),
        "config": config,
    }



def normalize_prompt_trace(raw_prompt_trace: object, *, limit: int = _PROMPT_TRACE_LIMIT) -> list[dict[str, Any]]:
    if not isinstance(raw_prompt_trace, list):
        return []
    normalized = [dict(item) for item in raw_prompt_trace if isinstance(item, dict)]
    return normalized[-max(1, int(limit or _PROMPT_TRACE_LIMIT)) :]



def attach_prompt_trace(
    meta: dict[str, Any],
    prompt_trace: list[dict[str, Any]] | None,
    *,
    limit: int = _PROMPT_TRACE_LIMIT,
) -> dict[str, Any]:
    if prompt_trace:
        meta["prompt_trace"] = list(prompt_trace)[-max(1, int(limit or _PROMPT_TRACE_LIMIT)) :]
    return meta



def build_route_graph_meta(
    result: Mapping[str, Any] | None,
    *,
    path: str = "route_graph",
    include_plan_feedback: bool = False,
    include_terminal_state: bool = False,
) -> dict[str, Any]:
    data = result if isinstance(result, Mapping) else {}
    meta: dict[str, Any] = {
        "path": path,
        "trace_id": str(data.get("trace_id") or ""),
        "engine": str(data.get("engine") or ""),
        "route_id": str(data.get("route_id") or ""),
        "route_entry": str(data.get("route_entry") or ""),
    }
    if include_plan_feedback:
        meta["plan_feedback"] = dict(data.get("plan_feedback") or {})
    if include_terminal_state:
        meta["terminal_status"] = str(data.get("terminal_status") or "success")
        meta["failure_reason"] = str(data.get("failure_reason") or "")
        meta["quality_snapshot"] = dict(data.get("quality_snapshot") or {})
    return meta



def prepare_generate_route_graph_outcome(result: Mapping[str, Any] | None) -> dict[str, Any]:
    data = result if isinstance(result, Mapping) else {}
    final_text = str(data.get("text") or "")
    problems = list(data.get("problems") or [])
    terminal_status = "success"
    status_raw = str(data.get("terminal_status") or "").strip().lower()
    if status_raw in {"success", "failed", "interrupted"}:
        terminal_status = status_raw
    failure_reason = str(data.get("failure_reason") or "").strip()
    quality_snapshot = dict(data.get("quality_snapshot") or {}) if isinstance(data.get("quality_snapshot"), Mapping) else {}
    prompt_trace = normalize_prompt_trace(data.get("prompt_trace"))
    graph_meta = build_route_graph_meta(data, include_plan_feedback=True)
    if terminal_status != "success" and failure_reason and failure_reason not in problems:
        problems.append(failure_reason)
    return {
        "final_text": final_text,
        "problems": problems,
        "terminal_status": terminal_status,
        "failure_reason": failure_reason,
        "quality_snapshot": quality_snapshot,
        "prompt_trace": prompt_trace,
        "graph_meta": graph_meta,
        "record_success_metric": bool(str(final_text).strip()),
    }



def prepare_generate_legacy_event_observation(
    event: Mapping[str, Any] | None,
    *,
    prompt_trace: list[dict[str, Any]],
) -> dict[str, Any]:
    data = event if isinstance(event, Mapping) else {}
    event_name = str(data.get("event") or "")
    if event_name == "prompt_route":
        meta = data.get("metadata") if isinstance(data.get("metadata"), Mapping) else {}
        prompt_trace.append(
            {
                "stage": str(data.get("stage") or ""),
                "metadata": dict(meta),
            }
        )
        return {
            "skip_event": True,
            "is_final": False,
            "final_text": "",
            "problems": [],
            "terminal_status": "success",
            "failure_reason": "",
            "quality_snapshot": {},
        }

    problems = list(data.get("problems") or [])
    terminal_status = "success"
    status_raw = str(data.get("status") or "").strip().lower()
    if status_raw in {"success", "failed", "interrupted"}:
        terminal_status = status_raw
    failure_reason = str(data.get("failure_reason") or "").strip()
    quality_snapshot = dict(data.get("quality_snapshot") or {}) if isinstance(data.get("quality_snapshot"), Mapping) else {}
    if event_name == "final" and terminal_status != "success" and failure_reason and failure_reason not in problems:
        problems.append(failure_reason)
    return {
        "skip_event": False,
        "is_final": event_name == "final",
        "final_text": str(data.get("text") or ""),
        "problems": problems,
        "terminal_status": terminal_status,
        "failure_reason": failure_reason,
        "quality_snapshot": quality_snapshot,
    }


def prepare_stream_route_graph_terminal_payload(
    result: Mapping[str, Any] | None,
    *,
    route_metric_meta: MutableMapping[str, object],
    safe_doc_ir_payload_fn,
    text: str,
    problems: list[str] | None = None,
    status: str = "",
    failure_reason: str = "",
    quality_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    data = result if isinstance(result, Mapping) else {}
    graph_meta = build_route_graph_meta(
        data,
        include_plan_feedback=True,
        include_terminal_state=True,
    )
    prompt_trace = normalize_prompt_trace(data.get("prompt_trace"))
    if status:
        graph_meta["terminal_status"] = str(status)
    if failure_reason:
        graph_meta["failure_reason"] = str(failure_reason)
    if prompt_trace:
        attach_prompt_trace(graph_meta, prompt_trace)
    sync_route_metric_meta(route_metric_meta, graph_meta)

    final_text = str(text or "")
    payload: dict[str, Any] = {
        "text": final_text,
        "problems": list(problems or []),
        "doc_ir": safe_doc_ir_payload_fn(final_text),
    }
    if graph_meta:
        payload["graph_meta"] = graph_meta
    if status:
        payload["status"] = str(status)
        payload["failure_reason"] = str(failure_reason)
        payload["quality_snapshot"] = dict(quality_snapshot or {})
    return payload



def prepare_stream_route_graph_outcome_plan(
    result: Mapping[str, Any] | None,
    *,
    session: Any,
    raw_instruction: str,
    current_text: str,
    route_metric_meta: MutableMapping[str, object],
    postprocess_output_text_fn,
    safe_doc_ir_payload_fn,
) -> dict[str, Any]:
    data = result if isinstance(result, Mapping) else {}
    candidate = str(data.get("text") or "")
    terminal_status = str(data.get("terminal_status") or "").strip().lower()
    failure_reason = str(data.get("failure_reason") or "").strip()
    no_semantic_failover = should_skip_semantic_failover(
        terminal_status=terminal_status,
        failure_reason=failure_reason,
    )

    if candidate.strip():
        final_text = postprocess_output_text_fn(
            session,
            candidate,
            raw_instruction,
            current_text=current_text,
        )
        problems = list(data.get("problems") or [])
        payload = prepare_stream_route_graph_terminal_payload(
            data,
            route_metric_meta=route_metric_meta,
            safe_doc_ir_payload_fn=safe_doc_ir_payload_fn,
            text=final_text,
            problems=problems,
        )
        return {
            "action": "emit_success",
            "payload": payload,
            "final_text": final_text,
            "skip_insufficient_failover": False,
            "metric_event": "route_graph_success",
            "with_terminal": True,
            "with_reason_codes": False,
            "stop": False,
        }

    if no_semantic_failover:
        problems = [failure_reason] if failure_reason else list(data.get("problems") or [])
        payload = prepare_stream_route_graph_terminal_payload(
            data,
            route_metric_meta=route_metric_meta,
            safe_doc_ir_payload_fn=safe_doc_ir_payload_fn,
            text="",
            problems=problems,
            status=terminal_status or "failed",
            failure_reason=failure_reason,
            quality_snapshot=dict(data.get("quality_snapshot") or {}),
        )
        return {
            "action": "emit_semantic_failure",
            "payload": payload,
            "final_text": None,
            "skip_insufficient_failover": True,
            "metric_event": "route_graph_semantic_failed",
            "with_terminal": True,
            "with_reason_codes": True,
            "stop": True,
        }

    return {
        "action": "continue",
        "payload": None,
        "final_text": None,
        "skip_insufficient_failover": False,
        "metric_event": "",
        "with_terminal": False,
        "with_reason_codes": False,
        "stop": False,
    }



def build_failover_quality_snapshot(
    *,
    terminal_status: str,
    failure_reason: str,
    problem_count: int,
    needs_review: bool = True,
) -> dict[str, Any]:
    return {
        "status": str(terminal_status or "failed"),
        "reason": str(failure_reason or ""),
        "problem_count": max(0, int(problem_count or 0)),
        "needs_review": bool(needs_review),
    }



def finalize_graph_meta(
    meta: Mapping[str, Any] | None,
    *,
    terminal_status: str,
    failure_reason: str,
    quality_snapshot: Mapping[str, Any] | None,
    engine_failover: bool,
    prompt_trace: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload = dict(meta or {})
    status = str(terminal_status or "").strip().lower()
    payload["terminal_status"] = status if status in {"success", "failed", "interrupted"} else "failed"
    payload["failure_reason"] = str(failure_reason or "")
    payload["quality_snapshot"] = dict(quality_snapshot or {})
    payload["engine_failover"] = bool(engine_failover)
    payload["needs_review"] = bool(engine_failover)
    return attach_prompt_trace(payload, prompt_trace)



def run_single_pass_stream_recovery(
    *,
    stream: Iterable[Mapping[str, Any]],
    session: Any,
    raw_instruction: str,
    current_text: str,
    target_chars: int,
    prompt_trace: list[dict[str, Any]] | None,
    postprocess_output_text_fn,
    check_generation_quality_fn,
    safe_doc_ir_payload_fn,
    path: str = "single_pass_stream",
    terminal_status: str = "interrupted",
    section: str = "fallback",
) -> dict[str, Any]:
    emit_events: list[dict[str, Any]] = []
    saw_stream_delta = False
    raw_final_text: str | None = None

    for raw_event in stream:
        event = dict(raw_event) if isinstance(raw_event, Mapping) else {}
        event_name = str(event.get("event") or "")
        if event_name == "heartbeat":
            emit_events.append({"event": "delta", "payload": {"delta": event.get("message", "")}})
            continue
        if event_name == "section":
            saw_stream_delta = True
            emit_events.append({"event": "section", "payload": event})
            continue
        if event_name == "result":
            raw_final_text = str(event.get("text") or "")

    recovery = None
    final_text = raw_final_text
    if raw_final_text:
        recovery = prepare_single_pass_stream_recovery_result(
            raw_text=raw_final_text,
            session=session,
            raw_instruction=raw_instruction,
            current_text=current_text,
            target_chars=target_chars,
            prompt_trace=prompt_trace,
            postprocess_output_text_fn=postprocess_output_text_fn,
            check_generation_quality_fn=check_generation_quality_fn,
            safe_doc_ir_payload_fn=safe_doc_ir_payload_fn,
            path=path,
            terminal_status=terminal_status,
            section=section,
        )
        final_text = str(recovery["final_text"])

    return {
        "emit_events": emit_events,
        "saw_stream_delta": saw_stream_delta,
        "raw_final_text": raw_final_text,
        "final_text": final_text,
        "recovery": recovery,
    }


def prepare_single_pass_stream_recovery_emission_plan(
    recovery_result: Mapping[str, Any] | None,
) -> dict[str, Any]:
    data = recovery_result if isinstance(recovery_result, Mapping) else {}
    passthrough_events: list[dict[str, Any]] = []
    completion_events: list[dict[str, Any]] = []
    for item in list(data.get("emit_events") or []):
        if not isinstance(item, Mapping):
            continue
        payload = item.get("payload")
        passthrough_events.append(
            {
                "event": str(item.get("event") or "message"),
                "payload": dict(payload) if isinstance(payload, Mapping) else {},
            }
        )

    final_text_raw = data.get("final_text")
    final_text = None if final_text_raw is None else str(final_text_raw)
    recovery = data.get("recovery")
    recovered = isinstance(recovery, Mapping)
    if recovered:
        recovery_payload = dict(recovery or {})
        if not bool(data.get("saw_stream_delta")):
            section_payload = recovery_payload.get("section_payload")
            if isinstance(section_payload, Mapping):
                completion_events.append({"event": "section", "payload": dict(section_payload)})
        final_payload = recovery_payload.get("final_payload")
        terminal_payload = dict(final_payload) if isinstance(final_payload, Mapping) else {}
        completion_events.append({"event": "final", "payload": terminal_payload})

    return {
        "passthrough_events": passthrough_events,
        "completion_events": completion_events,
        "emit_events": [*passthrough_events, *completion_events],
        "final_text": final_text,
        "recovered": recovered,
    }


def prepare_single_pass_stream_recovery_success_plan(
    recovery_plan: Mapping[str, Any] | None,
    *,
    trace_context: MutableMapping[str, object],
    with_terminal_fn,
    total_s: float,
    max_gap_s: float,
    path: str = "single_pass_stream",
) -> dict[str, Any]:
    data = recovery_plan if isinstance(recovery_plan, Mapping) else {}
    passthrough_events: list[dict[str, Any]] = []
    for item in list(data.get("passthrough_events") or []):
        if not isinstance(item, Mapping):
            continue
        payload = item.get("payload")
        passthrough_events.append(
            {
                "event": str(item.get("event") or "message"),
                "payload": dict(payload) if isinstance(payload, Mapping) else {},
            }
        )

    final_text_raw = data.get("final_text")
    final_text = None if final_text_raw is None else str(final_text_raw)
    recovered = bool(data.get("recovered"))
    completion_events: list[dict[str, Any]] = []
    timing_payload = None
    metric_payload = None
    if recovered:
        sync_trace_context(trace_context, route_path=path, fallback_recovered=True)
        for item in list(data.get("completion_events") or []):
            if not isinstance(item, Mapping):
                continue
            event_name = str(item.get("event") or "message")
            payload = item.get("payload")
            event_payload = dict(payload) if isinstance(payload, Mapping) else {}
            if event_name == "final":
                event_payload = dict(with_terminal_fn(event_payload))
            completion_events.append({"event": event_name, "payload": event_payload})
        timing_payload = {"total_s": float(total_s), "max_gap_s": float(max_gap_s)}
        metric_payload = {
            "event": "fallback_recovered",
            "kwargs": {
                "path": path,
                "fallback_triggered": True,
                "fallback_recovered": True,
            },
        }

    return {
        "emit_events": [*passthrough_events, *completion_events],
        "passthrough_events": passthrough_events,
        "completion_events": completion_events,
        "timing_payload": timing_payload,
        "metric_payload": metric_payload,
        "final_text": final_text,
        "recovered": recovered,
    }


def prepare_stream_graph_failure_fallback_trigger(
    *,
    exc: Exception,
    trace_context: MutableMapping[str, object],
    truncate_reason_codes: set[str],
    record_route_metric_fn,
    extract_error_code_fn,
    graph_path: str,
) -> dict[str, Any]:
    error_code = str(extract_error_code_fn(exc, default="E_GRAPH_FAILED") or "E_GRAPH_FAILED")
    sync_trace_context(
        trace_context,
        fallback_trigger=error_code,
        fallback_recovered=False,
    )
    message = str(exc).lower()
    if isinstance(exc, TimeoutError) or "timeout" in message or "stalled" in message:
        truncate_reason_codes.add("timeout_fallback")
    metric_payload = {
        "event": "graph_failed",
        "kwargs": {
            "path": str(graph_path),
            "fallback_triggered": True,
            "fallback_recovered": False,
            "error_code": error_code,
        },
    }
    record_route_metric_fn(
        metric_payload["event"],
        **dict(metric_payload["kwargs"]),
    )
    return {
        "fallback_trigger": error_code,
        "metric_payload": metric_payload,
        "truncate_reason_codes": sorted(str(code) for code in truncate_reason_codes),
    }



def prepare_stream_insufficient_fallback_trigger(
    *,
    trace_context: MutableMapping[str, object],
    truncate_reason_codes: set[str],
    record_route_metric_fn,
    graph_path: str,
    fallback_trigger: str = "E_TEXT_INSUFFICIENT",
) -> dict[str, Any]:
    truncate_reason_codes.add("insufficient_output_fallback")
    sync_trace_context(
        trace_context,
        fallback_trigger=fallback_trigger,
        fallback_recovered=False,
        preserve_existing_trigger=True,
    )
    metric_payload = {
        "event": "graph_insufficient",
        "kwargs": {
            "path": str(graph_path),
            "fallback_triggered": True,
            "fallback_recovered": False,
            "error_code": str(fallback_trigger),
        },
    }
    record_route_metric_fn(
        metric_payload["event"],
        **dict(metric_payload["kwargs"]),
    )
    return {
        "fallback_trigger": str(fallback_trigger),
        "metric_payload": metric_payload,
        "truncate_reason_codes": sorted(str(code) for code in truncate_reason_codes),
    }



def resolve_stream_graph_path(*, use_route_graph: bool) -> str:
    return "route_graph" if bool(use_route_graph) else "legacy_graph"



def prepare_stream_fallback_trigger(
    *,
    kind: str,
    use_route_graph: bool,
    trace_context: MutableMapping[str, object],
    truncate_reason_codes: set[str],
    record_route_metric_fn,
    exc: Exception | None = None,
    extract_error_code_fn=None,
    fallback_trigger: str = "E_TEXT_INSUFFICIENT",
) -> dict[str, Any]:
    graph_path = resolve_stream_graph_path(use_route_graph=use_route_graph)
    trigger_kind = str(kind or "").strip().lower()
    if trigger_kind == "graph_failed":
        if exc is None:
            raise ValueError("exc is required when kind='graph_failed'")
        return prepare_stream_graph_failure_fallback_trigger(
            exc=exc,
            trace_context=trace_context,
            truncate_reason_codes=truncate_reason_codes,
            record_route_metric_fn=record_route_metric_fn,
            extract_error_code_fn=extract_error_code_fn,
            graph_path=graph_path,
        )
    if trigger_kind == "graph_insufficient":
        return prepare_stream_insufficient_fallback_trigger(
            trace_context=trace_context,
            truncate_reason_codes=truncate_reason_codes,
            record_route_metric_fn=record_route_metric_fn,
            graph_path=graph_path,
            fallback_trigger=fallback_trigger,
        )
    raise ValueError(f"unsupported stream fallback trigger kind: {kind}")


def drive_single_pass_stream_recovery(
    *,
    attempt_fn,
    finalize_success_fn,
    handle_failure_fn,
) -> dict[str, Any]:
    try:
        success_plan = finalize_success_fn(attempt_fn())
        payload = dict(success_plan) if isinstance(success_plan, Mapping) else {}
        payload.setdefault("emit_events", [])
        payload.setdefault("timing_payload", None)
        payload.setdefault("metric_payload", None)
        payload.setdefault("final_text", None)
        payload.setdefault("recovered", False)
        payload["failure"] = None
        payload["stop"] = False
        return payload
    except Exception as exc:
        failure = handle_failure_fn(exc)
        failure_payload = dict(failure) if isinstance(failure, Mapping) else {}
        event_name = str(failure_payload.get("event") or "error")
        payload = failure_payload.get("payload")
        return {
            "emit_events": [
                {
                    "event": event_name,
                    "payload": dict(payload) if isinstance(payload, Mapping) else {},
                }
            ],
            "timing_payload": None,
            "metric_payload": None,
            "final_text": None,
            "recovered": False,
            "failure": failure_payload,
            "stop": bool(failure_payload.get("stop")),
        }


def handle_single_pass_stream_recovery_failure(
    *,
    exc: Exception,
    trace_context: MutableMapping[str, object],
    record_route_metric_fn,
    extract_error_code_fn,
    error_message: str,
    path: str = "single_pass_stream",
    stop: bool = False,
) -> dict[str, Any]:
    sync_trace_context(trace_context, fallback_recovered=False)
    error_code = str(extract_error_code_fn(exc, default="E_FALLBACK_FAILED") or "E_FALLBACK_FAILED")
    record_route_metric_fn(
        "fallback_failed",
        path=path,
        fallback_triggered=True,
        fallback_recovered=False,
        error_code=error_code,
    )
    return {
        "event": "error",
        "payload": {"message": str(error_message)},
        "stop": bool(stop),
        "error_code": error_code,
    }


def prepare_single_pass_stream_recovery_result(
    *,
    raw_text: str,
    session: Any,
    raw_instruction: str,
    current_text: str,
    target_chars: int,
    prompt_trace: list[dict[str, Any]] | None,
    postprocess_output_text_fn,
    check_generation_quality_fn,
    safe_doc_ir_payload_fn,
    path: str = "single_pass_stream",
    terminal_status: str = "interrupted",
    section: str = "fallback",
) -> dict[str, Any]:
    graph_meta = build_single_pass_failover_meta(
        prompt_trace=prompt_trace,
        path=path,
        terminal_status=terminal_status,
    )
    final_text = postprocess_output_text_fn(
        session,
        raw_text,
        raw_instruction,
        current_text=current_text,
    )
    quality_issues = list(check_generation_quality_fn(final_text, target_chars) or [])
    final_payload = {
        "text": final_text,
        "problems": quality_issues,
        "doc_ir": safe_doc_ir_payload_fn(final_text),
        "graph_meta": graph_meta,
    }
    return {
        "final_text": final_text,
        "quality_issues": quality_issues,
        "graph_meta": graph_meta,
        "section_payload": {"section": section, "phase": "delta", "delta": final_text},
        "final_payload": final_payload,
    }



def build_single_pass_failover_meta(
    *,
    prompt_trace: list[dict[str, Any]] | None = None,
    path: str = "single_pass_stream",
    terminal_status: str = "interrupted",
) -> dict[str, Any]:
    meta = {
        "path": path,
        "trace_id": "",
        "engine": "single_pass",
        "route_id": "",
        "route_entry": "",
        "engine_failover": True,
        "terminal_status": str(terminal_status or "interrupted"),
        "needs_review": True,
    }
    return attach_prompt_trace(meta, prompt_trace)



def prepare_stream_legacy_terminal_payload(
    event: Mapping[str, Any] | None,
    *,
    route_metric_meta: MutableMapping[str, object],
    safe_doc_ir_payload_fn,
    text: str,
    prompt_trace: list[dict[str, Any]] | None = None,
    graph_meta: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(event or {})
    resolved_graph_meta = dict(graph_meta or {}) if isinstance(graph_meta, Mapping) else {}
    if not resolved_graph_meta:
        resolved_graph_meta = build_legacy_graph_meta(prompt_trace=prompt_trace)
    elif prompt_trace:
        attach_prompt_trace(resolved_graph_meta, prompt_trace)
    sync_route_metric_meta(route_metric_meta, resolved_graph_meta)

    final_text = str(text or "")
    payload["text"] = final_text
    payload["doc_ir"] = safe_doc_ir_payload_fn(final_text)
    if resolved_graph_meta:
        payload["graph_meta"] = resolved_graph_meta
    return payload



def prepare_stream_legacy_event_observation(
    event: Mapping[str, Any] | None,
    *,
    prompt_trace: list[dict[str, Any]],
    last_event_at: float,
    last_section_at: float | None,
    max_gap_s: float,
    section_stall_s: float,
    now_fn,
) -> dict[str, Any]:
    data = event if isinstance(event, Mapping) else {}
    event_name = str(data.get("event") or "")
    observed_at = float(now_fn())
    gap = observed_at - float(last_event_at)
    next_max_gap_s = max(float(max_gap_s), gap)
    next_last_event_at = observed_at
    next_last_section_at = last_section_at

    if event_name == "prompt_route":
        meta = data.get("metadata") if isinstance(data.get("metadata"), Mapping) else {}
        prompt_trace.append(
            {
                "stage": str(data.get("stage") or ""),
                "metadata": dict(meta),
            }
        )
        return {
            "event_name": event_name,
            "skip_event": True,
            "section_timeout": False,
            "last_event_at": next_last_event_at,
            "last_section_at": next_last_section_at,
            "max_gap_s": next_max_gap_s,
        }

    if event_name != "final":
        if event_name == "section" and data.get("phase") == "delta":
            next_last_section_at = float(now_fn())
        if float(section_stall_s) > 0 and next_last_section_at is not None:
            section_timeout = float(now_fn()) - float(next_last_section_at) > float(section_stall_s)
        else:
            section_timeout = False
    else:
        section_timeout = False

    return {
        "event_name": event_name,
        "skip_event": False,
        "section_timeout": section_timeout,
        "last_event_at": next_last_event_at,
        "last_section_at": next_last_section_at,
        "max_gap_s": next_max_gap_s,
    }



def build_legacy_graph_meta(*, prompt_trace: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    meta = {
        "path": "legacy_graph",
        "trace_id": "",
        "engine": "legacy",
        "route_id": "",
        "route_entry": "",
    }
    return attach_prompt_trace(meta, prompt_trace)


__all__ = [name for name in globals() if not name.startswith("__")]
