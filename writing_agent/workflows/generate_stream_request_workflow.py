"""Service-facing stream generation workflow facade."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

from .orchestration_backend import (
    build_legacy_graph_kwargs,
    build_route_graph_kwargs,
    drive_single_pass_stream_recovery,
    handle_single_pass_stream_recovery_failure,
    prepare_single_pass_stream_recovery_emission_plan,
    prepare_single_pass_stream_recovery_success_plan,
    prepare_stream_fallback_trigger,
    prepare_stream_legacy_event_observation,
    prepare_stream_legacy_terminal_payload,
    prepare_stream_route_graph_outcome_plan,
    route_graph_enabled,
    run_single_pass_stream_recovery,
    sync_trace_context,
    text_requires_failover,
)


@dataclass(frozen=True)
class GenerateStreamRequest:
    session: Any
    raw_instruction: str
    instruction: str
    current_text: str
    graph_current_text: str
    compose_mode: str
    resume_sections: list[str]
    plan_confirm: dict[str, Any]
    cfg: Any
    target_chars: int
    required_h2: list[str]
    required_outline: list[Any]
    expand_outline: bool
    stall_s: float
    overall_s: float
    section_stall_s: float
    start_ts: float
    trace_context: dict[str, object]
    truncate_reason_codes: set[str]
    route_metric_meta: dict[str, str]


@dataclass(frozen=True)
class GenerateStreamDeps:
    environ: Mapping[str, str]
    emit: Callable[[str, dict[str, Any]], Any]
    with_terminal: Callable[[dict[str, Any]], dict[str, Any]]
    with_reason_codes: Callable[[dict[str, Any]], dict[str, Any]]
    record_route_metric: Callable[..., None]
    record_stream_timing: Callable[..., None]
    extract_error_code: Callable[..., str]
    should_inject_route_graph_failure: Callable[..., bool]
    run_generate_graph_dual_engine: Callable[..., dict[str, Any]] | None
    run_generate_graph: Callable[..., Iterable[dict[str, Any]]]
    iter_with_timeout: Callable[..., Iterable[dict[str, Any]]]
    postprocess_output_text: Callable[..., str]
    safe_doc_ir_payload: Callable[[str], dict[str, Any]]
    single_pass_generate_stream: Callable[..., Iterable[dict[str, Any]]]
    check_generation_quality: Callable[[str, int], list[str]]
    log_graph_error: Callable[[Exception], None]


def run_generate_stream_graph_with_fallback(
    *,
    request: GenerateStreamRequest,
    deps: GenerateStreamDeps,
) -> Iterator[Any]:
    final_text: str | None = None
    prompt_trace: list[dict[str, Any]] = []
    use_route_graph = False
    skip_insufficient_failover = False
    max_gap_s = 0.0

    def _attempt_single_pass_stream_recovery() -> dict[str, Any]:
        fallback = run_single_pass_stream_recovery(
            stream=deps.single_pass_generate_stream(
                request.session,
                instruction=request.instruction,
                current_text=request.current_text,
                target_chars=request.target_chars,
            ),
            session=request.session,
            raw_instruction=request.raw_instruction,
            current_text=request.current_text,
            target_chars=request.target_chars,
            prompt_trace=prompt_trace,
            postprocess_output_text_fn=deps.postprocess_output_text,
            check_generation_quality_fn=deps.check_generation_quality,
            safe_doc_ir_payload_fn=deps.safe_doc_ir_payload,
            path="single_pass_stream",
            terminal_status="interrupted",
            section="fallback",
        )
        return prepare_single_pass_stream_recovery_emission_plan(fallback)

    def _finalize_single_pass_stream_recovery_success(recovery_plan: dict[str, Any]) -> dict[str, Any]:
        return prepare_single_pass_stream_recovery_success_plan(
            recovery_plan,
            trace_context=request.trace_context,
            with_terminal_fn=deps.with_terminal,
            total_s=time.time() - request.start_ts,
            max_gap_s=max_gap_s,
        )

    def _run_single_pass_stream_recovery_driver(*, error_message: str, stop_on_failure: bool = False) -> dict[str, Any]:
        return drive_single_pass_stream_recovery(
            attempt_fn=_attempt_single_pass_stream_recovery,
            finalize_success_fn=_finalize_single_pass_stream_recovery_success,
            handle_failure_fn=lambda exc: handle_single_pass_stream_recovery_failure(
                exc=exc,
                trace_context=request.trace_context,
                record_route_metric_fn=deps.record_route_metric,
                extract_error_code_fn=deps.extract_error_code,
                error_message=error_message.format(exc=exc),
                stop=stop_on_failure,
            ),
        )

    def _apply_single_pass_stream_recovery_outcome(outcome: dict[str, Any]) -> Iterator[Any]:
        for event in list(outcome.get("emit_events") or []):
            if not isinstance(event, Mapping):
                continue
            payload = event.get("payload")
            yield deps.emit(
                str(event.get("event") or "message"),
                dict(payload) if isinstance(payload, Mapping) else {},
            )
        timing_payload = outcome.get("timing_payload")
        if isinstance(timing_payload, Mapping):
            deps.record_stream_timing(**dict(timing_payload))
        metric_payload = outcome.get("metric_payload")
        if isinstance(metric_payload, Mapping):
            deps.record_route_metric(
                str(metric_payload.get("event") or "fallback_recovered"),
                **dict(metric_payload.get("kwargs") or {}),
            )
        return {
            "final_text": outcome.get("final_text"),
            "stop": bool(outcome.get("stop")),
        }

    def _execute_single_pass_stream_recovery_branch(*, error_message: str, stop_on_failure: bool = False) -> Iterator[Any]:
        outcome = _run_single_pass_stream_recovery_driver(
            error_message=error_message,
            stop_on_failure=stop_on_failure,
        )
        applied = yield from _apply_single_pass_stream_recovery_outcome(outcome)
        return {
            "final_text": applied["final_text"],
            "stop": bool(applied["stop"]),
        }

    def _emit_stream_terminal_outcome(
        *,
        event: str,
        payload: dict[str, Any],
        metric_event: str,
        path: str,
        with_terminal: bool = False,
        with_reason_codes: bool = False,
    ) -> Iterator[Any]:
        final_payload = dict(payload)
        if with_terminal:
            final_payload = deps.with_terminal(final_payload)
        if with_reason_codes:
            final_payload = deps.with_reason_codes(final_payload)
        yield deps.emit(event, final_payload)
        deps.record_stream_timing(total_s=time.time() - request.start_ts, max_gap_s=max_gap_s)
        deps.record_route_metric(
            metric_event,
            path=path,
            fallback_triggered=False,
            fallback_recovered=False,
        )
        return None

    def _execute_route_graph_branch() -> Iterator[Any]:
        sync_trace_context(request.trace_context, route_path="route_graph")
        if deps.should_inject_route_graph_failure(phase="generate_stream"):
            raise RuntimeError("E_INJECTED_ROUTE_GRAPH_FAILURE")
        out = deps.run_generate_graph_dual_engine(
            **build_route_graph_kwargs(
                instruction=request.instruction,
                current_text=request.graph_current_text,
                required_h2=request.required_h2,
                required_outline=request.required_outline,
                expand_outline=request.expand_outline,
                config=request.cfg,
                compose_mode=request.compose_mode,
                resume_sections=request.resume_sections,
                format_only=False,
                plan_confirm=request.plan_confirm,
            )
        )
        branch_final_text = None
        branch_skip_insufficient = False
        if isinstance(out, dict):
            outcome_plan = prepare_stream_route_graph_outcome_plan(
                out,
                session=request.session,
                raw_instruction=request.raw_instruction,
                current_text=request.graph_current_text,
                route_metric_meta=request.route_metric_meta,
                postprocess_output_text_fn=deps.postprocess_output_text,
                safe_doc_ir_payload_fn=deps.safe_doc_ir_payload,
            )
            branch_final_text = outcome_plan.get("final_text")
            branch_skip_insufficient = bool(outcome_plan.get("skip_insufficient_failover"))
            payload = outcome_plan.get("payload")
            if isinstance(payload, dict):
                yield from _emit_stream_terminal_outcome(
                    event="final",
                    payload=payload,
                    metric_event=str(outcome_plan.get("metric_event") or ""),
                    path="route_graph",
                    with_terminal=bool(outcome_plan.get("with_terminal")),
                    with_reason_codes=bool(outcome_plan.get("with_reason_codes")),
                )
            return {
                "final_text": branch_final_text,
                "stop": bool(outcome_plan.get("stop")),
                "skip_insufficient_failover": branch_skip_insufficient,
            }
        return {
            "final_text": branch_final_text,
            "stop": False,
            "skip_insufficient_failover": branch_skip_insufficient,
        }

    def _execute_legacy_graph_branch() -> Iterator[Any]:
        nonlocal max_gap_s
        sync_trace_context(request.trace_context, route_path="legacy_graph")
        gen = deps.run_generate_graph(
            **build_legacy_graph_kwargs(
                instruction=request.instruction,
                current_text=request.graph_current_text,
                required_h2=request.required_h2,
                required_outline=request.required_outline,
                expand_outline=request.expand_outline,
                config=request.cfg,
            )
        )
        last_section_at: float | None = None
        last_event_at = request.start_ts
        branch_final_text = None
        for ev in deps.iter_with_timeout(gen, per_event=request.stall_s, overall=request.overall_s):
            observation = prepare_stream_legacy_event_observation(
                ev,
                prompt_trace=prompt_trace,
                last_event_at=last_event_at,
                last_section_at=last_section_at,
                max_gap_s=max_gap_s,
                section_stall_s=request.section_stall_s,
                now_fn=time.time,
            )
            last_event_at = float(observation["last_event_at"])
            last_section_at = observation["last_section_at"]
            max_gap_s = float(observation["max_gap_s"])
            if bool(observation["skip_event"]):
                continue
            if ev.get("event") == "final":
                branch_final_text = deps.postprocess_output_text(
                    request.session,
                    str(ev.get("text") or ""),
                    request.raw_instruction,
                    current_text=request.graph_current_text,
                )
                payload = prepare_stream_legacy_terminal_payload(
                    ev,
                    route_metric_meta=request.route_metric_meta,
                    safe_doc_ir_payload_fn=deps.safe_doc_ir_payload,
                    text=branch_final_text,
                    prompt_trace=prompt_trace,
                )
                yield from _emit_stream_terminal_outcome(
                    event=str(payload.get("event", "message")),
                    payload=payload,
                    metric_event="legacy_graph_success",
                    path="legacy_graph",
                    with_terminal=str(payload.get("event") or "").strip().lower() == "final",
                )
                break
            yield deps.emit(ev.get("event", "message"), ev)
            if bool(observation["section_timeout"]):
                raise TimeoutError("section stalled")
        return {
            "final_text": branch_final_text,
            "stop": False,
            "skip_insufficient_failover": False,
        }

    def _execute_stream_failover_flow(
        *,
        trigger_kind: str,
        error_message: str,
        stop_on_failure: bool = False,
        exc: Exception | None = None,
        log_graph_error: bool = False,
    ) -> Iterator[Any]:
        prepare_stream_fallback_trigger(
            kind=trigger_kind,
            use_route_graph=use_route_graph,
            exc=exc,
            trace_context=request.trace_context,
            truncate_reason_codes=request.truncate_reason_codes,
            record_route_metric_fn=deps.record_route_metric,
            extract_error_code_fn=deps.extract_error_code,
        )
        if log_graph_error and exc is not None:
            deps.log_graph_error(exc)
        applied = yield from _execute_single_pass_stream_recovery_branch(
            error_message=error_message,
            stop_on_failure=stop_on_failure,
        )
        return {
            "final_text": applied["final_text"],
            "stop": bool(applied["stop"]),
        }

    def _finalize_stream_workflow_result(
        *,
        final_text: str | None,
        stop: bool,
        skip_insufficient_failover: bool,
    ) -> Iterator[Any]:
        if bool(stop):
            return {"final_text": None, "stop": True}
        resolved_final_text = final_text
        if text_requires_failover(resolved_final_text, min_chars=20) and not skip_insufficient_failover:
            applied = yield from _execute_stream_failover_flow(
                trigger_kind="graph_insufficient",
                error_message="generation failed and fallback failed: {exc}",
                stop_on_failure=True,
            )
            resolved_final_text = applied["final_text"]
            if bool(applied["stop"]):
                return {"final_text": None, "stop": True}
        return {
            "final_text": resolved_final_text,
            "stop": False,
        }

    def _execute_stream_primary_branch() -> Iterator[Any]:
        selected_use_route_graph = route_graph_enabled(
            environ=deps.environ,
            dual_engine_runner=deps.run_generate_graph_dual_engine,
        )
        branch_result = yield from (
            _execute_route_graph_branch() if selected_use_route_graph else _execute_legacy_graph_branch()
        )
        return {
            "use_route_graph": selected_use_route_graph,
            "final_text": branch_result.get("final_text"),
            "skip_insufficient_failover": bool(branch_result.get("skip_insufficient_failover")),
            "stop": bool(branch_result.get("stop")),
        }

    stop = False
    try:
        primary_result = yield from _execute_stream_primary_branch()
        use_route_graph = bool(primary_result.get("use_route_graph"))
        final_text = primary_result.get("final_text")
        skip_insufficient_failover = bool(primary_result.get("skip_insufficient_failover"))
        stop = bool(primary_result.get("stop"))
    except Exception as e:
        applied = yield from _execute_stream_failover_flow(
            trigger_kind="graph_failed",
            error_message=f"generation failed: {e}; fallback failed: {{exc}}",
            exc=e,
            log_graph_error=True,
        )
        final_text = applied["final_text"]
        stop = bool(applied["stop"])

    return (yield from _finalize_stream_workflow_result(
        final_text=final_text,
        stop=stop,
        skip_insufficient_failover=skip_insufficient_failover,
    ))


__all__ = [name for name in globals() if not name.startswith("__")]
