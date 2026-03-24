"""Metric and failover planning helpers for generate request workflow."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .orchestration_backend import record_orchestration_metric


@dataclass(frozen=True)
class GenerateMetricPlan:
    event: str
    path: str
    fallback_triggered: bool | None = None
    fallback_recovered: bool | None = None
    error_code: str = ""


@dataclass(frozen=True)
class GenerateFailoverExecutionPlan:
    trigger_metric: GenerateMetricPlan
    failover_reason: str
    failure_detail: str


def _current_generate_graph_path(*, use_route_graph: bool) -> str:
    return "route_graph" if use_route_graph else "legacy_graph"


def _elapsed_generate_execution_ms(*, started_at: float) -> float:
    return max(0.0, (time.time() - float(started_at)) * 1000.0)


def _record_generate_metric(
    *,
    record_route_metric,
    graph_meta: dict[str, Any] | None,
    event: str,
    path: str,
    compose_mode: str,
    resume_sections: list[str],
    started_at: float,
    fallback_triggered: bool | None = None,
    fallback_recovered: bool | None = None,
    error_code: str = "",
) -> None:
    record_orchestration_metric(
        record_route_metric,
        event=event,
        phase="generate",
        path=path,
        meta=graph_meta,
        fallback_triggered=fallback_triggered,
        fallback_recovered=fallback_recovered,
        error_code=error_code,
        elapsed_ms=_elapsed_generate_execution_ms(started_at=started_at),
        compose_mode=compose_mode,
        resume_sections=resume_sections,
    )


def _prepare_generate_metric_plan(
    *,
    event: str,
    use_route_graph: bool,
    path: str = "",
    fallback_triggered: bool | None = None,
    fallback_recovered: bool | None = None,
    error_code: str = "",
    exc: Exception | None = None,
    extract_error_code_fn=None,
    default_error_code: str = "",
) -> GenerateMetricPlan:
    resolved_path = str(path or _current_generate_graph_path(use_route_graph=use_route_graph))
    resolved_error_code = str(error_code or "")
    if exc is not None:
        default_code = str(default_error_code or "E_GRAPH_FAILED")
        if callable(extract_error_code_fn):
            resolved_error_code = str(extract_error_code_fn(exc, default=default_code) or default_code)
        elif not resolved_error_code:
            resolved_error_code = default_code
    return GenerateMetricPlan(
        event=str(event or ""),
        path=resolved_path,
        fallback_triggered=fallback_triggered,
        fallback_recovered=fallback_recovered,
        error_code=resolved_error_code,
    )


def _record_generate_metric_plan(*, context: Any, metric_plan: GenerateMetricPlan | None) -> None:
    if metric_plan is None:
        return
    _record_generate_metric(
        record_route_metric=context.deps.record_route_metric,
        graph_meta=context.state.graph_meta,
        event=metric_plan.event,
        path=metric_plan.path,
        compose_mode=context.inputs.compose_mode,
        resume_sections=context.inputs.resume_sections,
        started_at=context.started_at,
        fallback_triggered=metric_plan.fallback_triggered,
        fallback_recovered=metric_plan.fallback_recovered,
        error_code=metric_plan.error_code,
    )


def build_generate_primary_success_metric_plan(*, use_route_graph: bool) -> GenerateMetricPlan:
    return _prepare_generate_metric_plan(
        event="route_graph_success" if use_route_graph else "legacy_graph_success",
        use_route_graph=use_route_graph,
        path=_current_generate_graph_path(use_route_graph=use_route_graph),
        fallback_triggered=False,
        fallback_recovered=False,
    )


def build_generate_failover_recovered_metric_plan(*, use_route_graph: bool) -> GenerateMetricPlan:
    return _prepare_generate_metric_plan(
        event="fallback_recovered",
        use_route_graph=use_route_graph,
        path="single_pass",
        fallback_triggered=True,
        fallback_recovered=True,
    )


def build_generate_failover_failed_metric_plan(*, context: Any, exc: Exception) -> GenerateMetricPlan:
    return _prepare_generate_metric_plan(
        event="fallback_failed",
        use_route_graph=context.state.use_route_graph,
        path="single_pass",
        fallback_triggered=True,
        fallback_recovered=False,
        exc=exc,
        extract_error_code_fn=context.deps.extract_error_code,
        default_error_code="E_FALLBACK_FAILED",
    )


def build_generate_failover_execution_plan(*, context: Any, failover_request: Any) -> GenerateFailoverExecutionPlan:
    return GenerateFailoverExecutionPlan(
        trigger_metric=_prepare_generate_metric_plan(
            event=failover_request.trigger_event,
            use_route_graph=failover_request.use_route_graph,
            path=failover_request.graph_path,
            fallback_triggered=True,
            fallback_recovered=False,
            error_code=failover_request.error_code,
            exc=failover_request.exc,
            extract_error_code_fn=context.deps.extract_error_code,
            default_error_code=failover_request.default_error_code,
        ),
        failover_reason=str(failover_request.failover_reason or ""),
        failure_detail=str(failover_request.failure_detail or ""),
    )
