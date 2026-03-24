"""Service-facing generate workflow with graph execution and fallback semantics."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from writing_agent.web.domains import route_graph_metrics_domain

from .generate_request_metrics import (
    GenerateFailoverExecutionPlan,
    GenerateMetricPlan,
    _current_generate_graph_path,
    _record_generate_metric_plan,
    build_generate_failover_execution_plan,
    build_generate_failover_failed_metric_plan,
    build_generate_failover_recovered_metric_plan,
    build_generate_primary_success_metric_plan,
)
from .orchestration_backend import (
    build_failover_quality_snapshot,
    build_legacy_graph_kwargs,
    build_route_graph_kwargs,
    finalize_graph_meta,
    prepare_generate_legacy_event_observation,
    prepare_generate_route_graph_outcome,
    route_graph_enabled,
    should_skip_semantic_failover,
    text_requires_failover,
)


@dataclass(frozen=True)
class GenerateGraphRequest:
    app_v2: Any
    session: Any
    instruction: str
    raw_instruction: str
    compose_mode: str
    resume_sections: list[str]
    base_text: str
    cfg: Any
    target_chars: int
    plan_confirm: dict[str, Any]


@dataclass(frozen=True)
class GenerateGraphDeps:
    environ: Mapping[str, str]
    record_route_metric: Callable[..., None]
    should_inject_route_graph_failure: Callable[..., bool]
    run_generate_graph_dual_engine: Callable[..., dict[str, Any]] | None
    run_generate_graph: Callable[..., Iterable[Mapping[str, Any]]]
    iter_with_timeout: Callable[..., Iterable[Mapping[str, Any]]]
    single_pass_generate: Callable[..., str]
    extract_error_code: Callable[..., str]
    http_exception_factory: Callable[..., Exception]


@dataclass(frozen=True)
class GenerateResolvedInputs:
    instruction: str
    base_text: str
    cfg: Any
    target_chars: int
    plan_confirm: dict[str, Any]
    compose_mode: str
    resume_sections: list[str]
    required_h2: list[str]
    required_outline: list[Any]
    expand_outline: bool


@dataclass
class GenerateGraphRuntimeState:
    final_text: str | None = None
    problems: list[str] = field(default_factory=list)
    graph_meta: dict[str, Any] | None = None
    prompt_trace: list[dict[str, Any]] = field(default_factory=list)
    terminal_status: str = 'success'
    failure_reason: str = ''
    quality_snapshot: dict[str, Any] = field(default_factory=dict)
    engine_failover: bool = False
    use_route_graph: bool = False


@dataclass
class GenerateExecutionContext:
    deps: GenerateGraphDeps
    session: Any
    inputs: GenerateResolvedInputs
    state: GenerateGraphRuntimeState = field(default_factory=GenerateGraphRuntimeState)
    started_at: float = 0.0


@dataclass(frozen=True)
class GenerateBranchSelection:
    use_route_graph: bool


@dataclass(frozen=True)
class GenerateLegacyTimeoutPolicy:
    stall_s: float
    overall_s: float


@dataclass(frozen=True)
class GenerateRouteGraphRunRequest:
    kwargs: dict[str, Any]


@dataclass(frozen=True)
class GenerateLegacyGraphRunRequest:
    kwargs: dict[str, Any]
    timeout_policy: GenerateLegacyTimeoutPolicy


@dataclass(frozen=True)
class GenerateSinglePassRequest:
    instruction: str
    current_text: str
    target_chars: int


@dataclass(frozen=True)
class GenerateFailoverRequest:
    trigger_event: str
    use_route_graph: bool
    failover_reason: str
    failure_detail: str
    graph_path: str = ''
    error_code: str = ''
    exc: Exception | None = None
    default_error_code: str = ''


@dataclass(frozen=True)
class GenerateFinalizationPlan:
    final_text: str | None
    requires_failover: bool = False
    failover_request: GenerateFailoverRequest | None = None


@dataclass(frozen=True)
class GenerateRouteGraphBranchExecutionPlan:
    inject_failure: bool
    run_request: GenerateRouteGraphRunRequest


@dataclass(frozen=True)
class GenerateLegacyEventLoopRequest:
    generator: Iterable[Mapping[str, Any]]
    stall_s: float
    overall_s: float
    prompt_trace: list[dict[str, Any]]


@dataclass(frozen=True)
class GenerateLegacyEventLoopResult:
    final_observation: dict[str, Any] | None
    prompt_trace: list[dict[str, Any]]


@dataclass(frozen=True)
class GenerateLegacyBranchExecutionPlan:
    run_request: GenerateLegacyGraphRunRequest
    event_loop_request: GenerateLegacyEventLoopRequest


@dataclass(frozen=True)
class GeneratePrimaryBranchExecutionPlan:
    use_route_graph: bool
    path: str


@dataclass(frozen=True)
class GeneratePrimaryStatePlan:
    use_route_graph: bool
    final_text: str | None
    problems: list[str]
    terminal_status: str
    failure_reason: str
    quality_snapshot: dict[str, Any]
    prompt_trace: list[dict[str, Any]]
    graph_meta: dict[str, Any] | None
    success_metric: GenerateMetricPlan | None = None


@dataclass(frozen=True)
class GenerateFailoverStatePlan:
    final_text: str
    problems: list[str]
    terminal_status: str
    failure_reason: str
    quality_snapshot: dict[str, Any]
    engine_failover: bool = True


@dataclass(frozen=True)
class GenerateGraphMetaFinalizationRequest:
    graph_meta: dict[str, Any] | None
    terminal_status: str
    failure_reason: str
    quality_snapshot: dict[str, Any]
    engine_failover: bool
    prompt_trace: list[dict[str, Any]]


@dataclass
class GeneratePrimaryOutcome:
    use_route_graph: bool = False
    final_text: str | None = None
    problems: list[str] = field(default_factory=list)
    terminal_status: str = 'success'
    failure_reason: str = ''
    quality_snapshot: dict[str, Any] = field(default_factory=dict)
    prompt_trace: list[dict[str, Any]] = field(default_factory=list)
    graph_meta: dict[str, Any] | None = None
    success_metric: GenerateMetricPlan | None = None


@dataclass(frozen=True)
class GenerateFinalizedResult:
    final_text: str | None
    graph_meta: dict[str, Any] | None


@dataclass(frozen=True)
class GenerateExecutionResult:
    final_text: str | None
    problems: list[str]
    graph_meta: dict[str, Any] | None


@dataclass(frozen=True)
class GenerateExecutionDriverDeps:
    execute_primary_fn: Callable[[], GeneratePrimaryOutcome]
    apply_primary_result_fn: Callable[[GeneratePrimaryOutcome], Any]
    execute_graph_failed_failover_fn: Callable[[Exception], str]
    finalize_result_fn: Callable[[], GenerateFinalizedResult]


@dataclass(frozen=True)
class GenerateDriverRunRequest:
    state: GenerateGraphRuntimeState
    driver_deps: GenerateExecutionDriverDeps


@dataclass(frozen=True)
class GenerateWorkflowBootstrap:
    deps: GenerateGraphDeps
    inputs: GenerateResolvedInputs
    context: GenerateExecutionContext
    driver_run_request: GenerateDriverRunRequest



def _missing_generate_dependency(name: str) -> Callable[..., Any]:
    def _missing(*_args: Any, **_kwargs: Any) -> Any:
        raise AttributeError(f"Generate workflow dependency '{name}' is unavailable")

    return _missing



def _default_http_exception_factory(app_v2: Any) -> Callable[..., Exception]:
    factory = getattr(app_v2, 'HTTPException', None)
    if callable(factory):
        return factory
    return lambda **kwargs: RuntimeError(str(kwargs.get('detail') or 'generation failed'))



def build_generate_graph_deps(app_v2: Any) -> GenerateGraphDeps:
    return GenerateGraphDeps(
        environ=getattr(getattr(app_v2, 'os', None), 'environ', {}),
        record_route_metric=route_graph_metrics_domain.record_route_graph_metric,
        should_inject_route_graph_failure=route_graph_metrics_domain.should_inject_route_graph_failure,
        run_generate_graph_dual_engine=getattr(app_v2, 'run_generate_graph_dual_engine', None),
        run_generate_graph=getattr(app_v2, 'run_generate_graph', _missing_generate_dependency('run_generate_graph')),
        iter_with_timeout=getattr(app_v2, '_iter_with_timeout', _missing_generate_dependency('_iter_with_timeout')),
        single_pass_generate=getattr(app_v2, '_single_pass_generate', _missing_generate_dependency('_single_pass_generate')),
        extract_error_code=route_graph_metrics_domain.extract_error_code,
        http_exception_factory=_default_http_exception_factory(app_v2),
    )



def build_generate_resolved_inputs(request: GenerateGraphRequest) -> GenerateResolvedInputs:
    session = request.session
    resume_sections = list(request.resume_sections or [])
    return GenerateResolvedInputs(
        instruction=str(request.instruction or ''),
        base_text=str(request.base_text or ''),
        cfg=request.cfg,
        target_chars=int(request.target_chars),
        plan_confirm=dict(request.plan_confirm or {}),
        compose_mode=str(request.compose_mode or ''),
        resume_sections=resume_sections,
        required_h2=list(resume_sections) if resume_sections else list(session.template_required_h2 or []),
        required_outline=[] if resume_sections else list(session.template_outline or []),
        expand_outline=bool((session.generation_prefs or {}).get('expand_outline', False)),
    )



def build_generate_execution_context(
    *,
    request: GenerateGraphRequest,
    deps: GenerateGraphDeps,
    inputs: GenerateResolvedInputs,
    state: GenerateGraphRuntimeState | None = None,
    started_at: float | None = None,
) -> GenerateExecutionContext:
    return GenerateExecutionContext(
        deps=deps,
        session=request.session,
        inputs=inputs,
        state=state or GenerateGraphRuntimeState(),
        started_at=time.time() if started_at is None else float(started_at),
    )



def build_generate_branch_selection(*, deps: GenerateGraphDeps) -> GenerateBranchSelection:
    return GenerateBranchSelection(
        use_route_graph=bool(
            route_graph_enabled(
                environ=deps.environ,
                dual_engine_runner=deps.run_generate_graph_dual_engine,
            )
        )
    )



def build_generate_legacy_timeout_policy(*, environ: Mapping[str, str]) -> GenerateLegacyTimeoutPolicy:
    return GenerateLegacyTimeoutPolicy(
        stall_s=float(
            environ.get(
                'WRITING_AGENT_NONSTREAM_EVENT_TIMEOUT_S',
                environ.get('WRITING_AGENT_STREAM_EVENT_TIMEOUT_S', '90'),
            )
        ),
        overall_s=float(
            environ.get(
                'WRITING_AGENT_NONSTREAM_MAX_S',
                environ.get('WRITING_AGENT_STREAM_MAX_S', '180'),
            )
        ),
    )



def build_generate_route_graph_run_request(*, context: GenerateExecutionContext) -> GenerateRouteGraphRunRequest:
    inputs = context.inputs
    return GenerateRouteGraphRunRequest(
        kwargs=build_route_graph_kwargs(
            instruction=inputs.instruction,
            current_text=inputs.base_text,
            required_h2=inputs.required_h2,
            required_outline=inputs.required_outline,
            expand_outline=inputs.expand_outline,
            config=inputs.cfg,
            compose_mode=inputs.compose_mode,
            resume_sections=inputs.resume_sections,
            format_only=False,
            plan_confirm=inputs.plan_confirm,
        )
    )



def build_generate_legacy_graph_run_request(*, context: GenerateExecutionContext) -> GenerateLegacyGraphRunRequest:
    inputs = context.inputs
    return GenerateLegacyGraphRunRequest(
        kwargs=build_legacy_graph_kwargs(
            instruction=inputs.instruction,
            current_text=inputs.base_text,
            required_h2=inputs.required_h2,
            required_outline=inputs.required_outline,
            expand_outline=inputs.expand_outline,
            config=inputs.cfg,
        ),
        timeout_policy=build_generate_legacy_timeout_policy(environ=context.deps.environ),
    )



def build_generate_single_pass_request(*, context: GenerateExecutionContext) -> GenerateSinglePassRequest:
    return GenerateSinglePassRequest(
        instruction=context.inputs.instruction,
        current_text=context.inputs.base_text,
        target_chars=context.inputs.target_chars,
    )



def build_generate_route_graph_branch_execution_plan(
    *,
    context: GenerateExecutionContext,
) -> GenerateRouteGraphBranchExecutionPlan:
    return GenerateRouteGraphBranchExecutionPlan(
        inject_failure=bool(context.deps.should_inject_route_graph_failure(phase='generate')),
        run_request=build_generate_route_graph_run_request(context=context),
    )



def build_generate_legacy_event_loop_request(
    *,
    context: GenerateExecutionContext,
    run_request: GenerateLegacyGraphRunRequest,
) -> GenerateLegacyEventLoopRequest:
    return GenerateLegacyEventLoopRequest(
        generator=context.deps.run_generate_graph(**run_request.kwargs),
        stall_s=float(run_request.timeout_policy.stall_s),
        overall_s=float(run_request.timeout_policy.overall_s),
        prompt_trace=context.state.prompt_trace,
    )



def drive_generate_legacy_event_loop(
    *,
    context: GenerateExecutionContext,
    request: GenerateLegacyEventLoopRequest,
) -> GenerateLegacyEventLoopResult:
    for ev in context.deps.iter_with_timeout(
        request.generator,
        per_event=request.stall_s,
        overall=request.overall_s,
    ):
        observation = prepare_generate_legacy_event_observation(ev, prompt_trace=request.prompt_trace)
        if bool(observation.get('skip_event')):
            continue
        if bool(observation.get('is_final')):
            return GenerateLegacyEventLoopResult(
                final_observation=dict(observation),
                prompt_trace=list(request.prompt_trace),
            )
    return GenerateLegacyEventLoopResult(
        final_observation=None,
        prompt_trace=list(request.prompt_trace),
    )



def build_generate_legacy_branch_execution_plan(
    *,
    context: GenerateExecutionContext,
) -> GenerateLegacyBranchExecutionPlan:
    run_request = build_generate_legacy_graph_run_request(context=context)
    return GenerateLegacyBranchExecutionPlan(
        run_request=run_request,
        event_loop_request=build_generate_legacy_event_loop_request(
            context=context,
            run_request=run_request,
        ),
    )



def build_generate_primary_branch_execution_plan(
    *,
    context: GenerateExecutionContext,
) -> GeneratePrimaryBranchExecutionPlan:
    branch_selection = build_generate_branch_selection(deps=context.deps)
    return GeneratePrimaryBranchExecutionPlan(
        use_route_graph=bool(branch_selection.use_route_graph),
        path=_current_generate_graph_path(use_route_graph=branch_selection.use_route_graph),
    )



def build_generate_route_graph_primary_outcome(
    *,
    route_result: Mapping[str, Any] | None,
) -> GeneratePrimaryOutcome:
    outcome = GeneratePrimaryOutcome(use_route_graph=True)
    if isinstance(route_result, Mapping):
        parsed = prepare_generate_route_graph_outcome(route_result)
        outcome.final_text = parsed.get('final_text')
        outcome.problems = list(parsed.get('problems') or [])
        outcome.terminal_status = str(parsed.get('terminal_status') or outcome.terminal_status)
        outcome.failure_reason = str(parsed.get('failure_reason') or '')
        outcome.quality_snapshot = dict(parsed.get('quality_snapshot') or {})
        outcome.prompt_trace = list(parsed.get('prompt_trace') or [])
        outcome.graph_meta = dict(parsed.get('graph_meta') or {}) or None
        if bool(parsed.get('record_success_metric')):
            outcome.success_metric = build_generate_primary_success_metric_plan(use_route_graph=True)
    return outcome



def build_generate_legacy_primary_outcome(
    *,
    observation: Mapping[str, Any] | None,
    prompt_trace: list[dict[str, Any]],
) -> GeneratePrimaryOutcome:
    data = observation if isinstance(observation, Mapping) else {}
    outcome = GeneratePrimaryOutcome(use_route_graph=False)
    outcome.final_text = str(data.get('final_text') or '')
    outcome.problems = list(data.get('problems') or [])
    outcome.terminal_status = str(data.get('terminal_status') or outcome.terminal_status)
    outcome.failure_reason = str(data.get('failure_reason') or '')
    outcome.quality_snapshot = dict(data.get('quality_snapshot') or {})
    outcome.prompt_trace = list(prompt_trace)
    outcome.success_metric = build_generate_primary_success_metric_plan(use_route_graph=False)
    return outcome



def build_generate_primary_state_plan(*, primary_result: GeneratePrimaryOutcome) -> GeneratePrimaryStatePlan:
    return GeneratePrimaryStatePlan(
        use_route_graph=bool(primary_result.use_route_graph),
        final_text=primary_result.final_text,
        problems=list(primary_result.problems or []),
        terminal_status=str(primary_result.terminal_status or 'success'),
        failure_reason=str(primary_result.failure_reason or ''),
        quality_snapshot=dict(primary_result.quality_snapshot or {}),
        prompt_trace=list(primary_result.prompt_trace or []),
        graph_meta=dict(primary_result.graph_meta or {}) or None,
        success_metric=primary_result.success_metric,
    )



def apply_generate_primary_state_plan(
    *,
    context: GenerateExecutionContext,
    state_plan: GeneratePrimaryStatePlan,
) -> GenerateGraphRuntimeState:
    context.state.use_route_graph = bool(state_plan.use_route_graph)
    context.state.final_text = state_plan.final_text
    context.state.problems = list(state_plan.problems or [])
    context.state.terminal_status = str(state_plan.terminal_status or context.state.terminal_status)
    context.state.failure_reason = str(state_plan.failure_reason or '')
    context.state.quality_snapshot = dict(state_plan.quality_snapshot or {})
    context.state.prompt_trace = list(state_plan.prompt_trace or [])
    context.state.graph_meta = dict(state_plan.graph_meta or {}) or None
    _record_generate_metric_plan(context=context, metric_plan=state_plan.success_metric)
    return context.state



def build_generate_failover_state_plan(
    *,
    recovered_text: str,
    failover_reason: str,
    existing_problems: list[str],
) -> GenerateFailoverStatePlan:
    problems = list(existing_problems or [])
    resolved_reason = str(failover_reason or '')
    quality_snapshot = build_failover_quality_snapshot(
        terminal_status='interrupted',
        failure_reason=resolved_reason,
        problem_count=len(existing_problems or []),
    )
    if resolved_reason and resolved_reason not in problems:
        problems.append(resolved_reason)
    return GenerateFailoverStatePlan(
        final_text=str(recovered_text),
        problems=problems,
        terminal_status='interrupted',
        failure_reason=resolved_reason,
        quality_snapshot=quality_snapshot,
        engine_failover=True,
    )



def apply_generate_failover_state_plan(
    *,
    context: GenerateExecutionContext,
    state_plan: GenerateFailoverStatePlan,
) -> GenerateGraphRuntimeState:
    context.state.final_text = state_plan.final_text
    context.state.problems = list(state_plan.problems or [])
    context.state.terminal_status = str(state_plan.terminal_status or context.state.terminal_status)
    context.state.failure_reason = str(state_plan.failure_reason or '')
    context.state.quality_snapshot = dict(state_plan.quality_snapshot or {})
    context.state.engine_failover = bool(state_plan.engine_failover)
    return context.state



def build_generate_graph_meta_finalization_request(
    *,
    context: GenerateExecutionContext,
) -> GenerateGraphMetaFinalizationRequest:
    return GenerateGraphMetaFinalizationRequest(
        graph_meta=dict(context.state.graph_meta or {}) or None,
        terminal_status=str(context.state.terminal_status or ''),
        failure_reason=str(context.state.failure_reason or ''),
        quality_snapshot=dict(context.state.quality_snapshot or {}),
        engine_failover=bool(context.state.engine_failover),
        prompt_trace=list(context.state.prompt_trace or []),
    )



def build_generate_finalized_graph_meta(
    *,
    request: GenerateGraphMetaFinalizationRequest,
) -> dict[str, Any] | None:
    return finalize_graph_meta(
        request.graph_meta,
        terminal_status=request.terminal_status,
        failure_reason=request.failure_reason,
        quality_snapshot=dict(request.quality_snapshot or {}),
        engine_failover=bool(request.engine_failover),
        prompt_trace=list(request.prompt_trace or []),
    )



def _execute_generate_single_pass_failover(
    context: GenerateExecutionContext,
    *,
    failover_reason: str,
    failure_detail: str,
) -> str:
    try:
        single_pass_request = build_generate_single_pass_request(context=context)
        recovered_text = context.deps.single_pass_generate(
            context.session,
            instruction=single_pass_request.instruction,
            current_text=single_pass_request.current_text,
            target_chars=single_pass_request.target_chars,
        )
        state_plan = build_generate_failover_state_plan(
            recovered_text=str(recovered_text),
            failover_reason=failover_reason,
            existing_problems=context.state.problems,
        )
        apply_generate_failover_state_plan(context=context, state_plan=state_plan)
        _record_generate_metric_plan(
            context=context,
            metric_plan=build_generate_failover_recovered_metric_plan(
                use_route_graph=context.state.use_route_graph,
            ),
        )
        return state_plan.final_text
    except Exception as failover_exc:
        _record_generate_metric_plan(
            context=context,
            metric_plan=build_generate_failover_failed_metric_plan(context=context, exc=failover_exc),
        )
        raise context.deps.http_exception_factory(
            status_code=500,
            detail=failure_detail.format(exc=failover_exc),
        ) from failover_exc



def _execute_route_graph_branch(*, context: GenerateExecutionContext) -> GeneratePrimaryOutcome:
    execution_plan = build_generate_route_graph_branch_execution_plan(context=context)
    if execution_plan.inject_failure:
        raise RuntimeError('E_INJECTED_ROUTE_GRAPH_FAILURE')
    out = context.deps.run_generate_graph_dual_engine(**execution_plan.run_request.kwargs)
    return build_generate_route_graph_primary_outcome(route_result=out)



def _execute_legacy_graph_branch(*, context: GenerateExecutionContext) -> GeneratePrimaryOutcome:
    execution_plan = build_generate_legacy_branch_execution_plan(context=context)
    loop_result = drive_generate_legacy_event_loop(
        context=context,
        request=execution_plan.event_loop_request,
    )
    if loop_result.final_observation is not None:
        return build_generate_legacy_primary_outcome(
            observation=loop_result.final_observation,
            prompt_trace=loop_result.prompt_trace,
        )
    outcome = GeneratePrimaryOutcome(use_route_graph=False)
    outcome.prompt_trace = list(loop_result.prompt_trace)
    return outcome



def _execute_generate_primary_branch(*, context: GenerateExecutionContext) -> GeneratePrimaryOutcome:
    execution_plan = build_generate_primary_branch_execution_plan(context=context)
    context.state.use_route_graph = bool(execution_plan.use_route_graph)
    return (
        _execute_route_graph_branch(context=context)
        if execution_plan.use_route_graph
        else _execute_legacy_graph_branch(context=context)
    )



def _apply_generate_primary_result(
    *,
    context: GenerateExecutionContext,
    primary_result: GeneratePrimaryOutcome,
) -> GenerateGraphRuntimeState:
    return apply_generate_primary_state_plan(
        context=context,
        state_plan=build_generate_primary_state_plan(primary_result=primary_result),
    )



def build_generate_graph_failed_failover_request(
    *,
    context: GenerateExecutionContext,
    exc: Exception,
) -> GenerateFailoverRequest:
    return GenerateFailoverRequest(
        trigger_event='graph_failed',
        use_route_graph=context.state.use_route_graph,
        failover_reason='engine_failover_graph_failed',
        failure_detail=f'generation failed: {exc}; fallback failed: {{exc}}',
        exc=exc,
        default_error_code='E_GRAPH_FAILED',
    )



def build_generate_insufficient_output_failover_request(
    *,
    context: GenerateExecutionContext,
) -> GenerateFailoverRequest:
    return GenerateFailoverRequest(
        trigger_event='graph_insufficient',
        use_route_graph=context.state.use_route_graph,
        failover_reason='engine_failover_insufficient_output',
        failure_detail='generation produced insufficient text: {exc}',
        error_code='E_TEXT_INSUFFICIENT',
    )



def build_generate_finalization_plan(*, context: GenerateExecutionContext) -> GenerateFinalizationPlan:
    resolved_final_text = context.state.final_text
    no_semantic_failover = should_skip_semantic_failover(
        terminal_status=str(context.state.terminal_status or ''),
        failure_reason=str(context.state.failure_reason or ''),
    )
    requires_failover = text_requires_failover(resolved_final_text, min_chars=20) and not no_semantic_failover
    return GenerateFinalizationPlan(
        final_text=resolved_final_text,
        requires_failover=requires_failover,
        failover_request=(
            build_generate_insufficient_output_failover_request(context=context)
            if requires_failover
            else None
        ),
    )



def build_generate_failover_trigger_metric_plan(
    *,
    context: GenerateExecutionContext,
    failover_request: GenerateFailoverRequest,
) -> GenerateMetricPlan:
    return build_generate_failover_execution_plan(
        context=context,
        failover_request=failover_request,
    ).trigger_metric


def _execute_generate_failover(
    *,
    context: GenerateExecutionContext,
    failover_plan: GenerateFailoverExecutionPlan,
) -> str:
    _record_generate_metric_plan(
        context=context,
        metric_plan=failover_plan.trigger_metric,
    )
    return str(
        _execute_generate_single_pass_failover(
            context,
            failover_reason=failover_plan.failover_reason,
            failure_detail=failover_plan.failure_detail,
        )
    )



def _build_generate_execution_driver_deps(*, context: GenerateExecutionContext) -> GenerateExecutionDriverDeps:
    return GenerateExecutionDriverDeps(
        execute_primary_fn=lambda: _execute_generate_primary_branch(context=context),
        apply_primary_result_fn=lambda primary_result: _apply_generate_primary_result(
            context=context,
            primary_result=primary_result,
        ),
        execute_graph_failed_failover_fn=lambda exc: _execute_generate_failover(
            context=context,
            failover_plan=build_generate_failover_execution_plan(
                context=context,
                failover_request=build_generate_graph_failed_failover_request(context=context, exc=exc),
            ),
        ),
        finalize_result_fn=lambda: _finalize_generate_workflow_result(context=context),
    )



def build_generate_driver_run_request(*, context: GenerateExecutionContext) -> GenerateDriverRunRequest:
    return GenerateDriverRunRequest(
        state=context.state,
        driver_deps=_build_generate_execution_driver_deps(context=context),
    )



def _execute_generate_workflow_driver(
    *,
    request: GenerateDriverRunRequest,
) -> GenerateExecutionResult:
    try:
        primary_result = request.driver_deps.execute_primary_fn()
        request.driver_deps.apply_primary_result_fn(primary_result)
    except Exception as exc:
        request.state.final_text = request.driver_deps.execute_graph_failed_failover_fn(exc)
    finalized = request.driver_deps.finalize_result_fn()
    request.state.final_text = finalized.final_text
    request.state.graph_meta = finalized.graph_meta
    return GenerateExecutionResult(
        final_text=request.state.final_text,
        problems=list(request.state.problems),
        graph_meta=request.state.graph_meta,
    )



def _finalize_generate_workflow_result(*, context: GenerateExecutionContext) -> GenerateFinalizedResult:
    finalization_plan = build_generate_finalization_plan(context=context)
    resolved_final_text = finalization_plan.final_text
    if finalization_plan.requires_failover and finalization_plan.failover_request is not None:
        resolved_final_text = _execute_generate_failover(
            context=context,
            failover_plan=build_generate_failover_execution_plan(
                context=context,
                failover_request=finalization_plan.failover_request,
            ),
        )
        context.state.final_text = resolved_final_text
    context.state.graph_meta = build_generate_finalized_graph_meta(
        request=build_generate_graph_meta_finalization_request(context=context),
    )
    return GenerateFinalizedResult(
        final_text=resolved_final_text,
        graph_meta=context.state.graph_meta,
    )



def build_generate_workflow_bootstrap(
    *,
    request: GenerateGraphRequest,
    deps: GenerateGraphDeps | None = None,
) -> GenerateWorkflowBootstrap:
    resolved_deps = deps or build_generate_graph_deps(request.app_v2)
    inputs = build_generate_resolved_inputs(request)
    context = build_generate_execution_context(
        request=request,
        deps=resolved_deps,
        inputs=inputs,
    )
    return GenerateWorkflowBootstrap(
        deps=resolved_deps,
        inputs=inputs,
        context=context,
        driver_run_request=build_generate_driver_run_request(context=context),
    )



def build_generate_workflow_response(
    *,
    execution: GenerateExecutionResult,
) -> tuple[str, list[str], dict | None]:
    return str(execution.final_text), list(execution.problems), execution.graph_meta



def run_generate_graph_with_fallback(
    *,
    request: GenerateGraphRequest,
    deps: GenerateGraphDeps | None = None,
) -> tuple[str, list[str], dict | None]:
    """Run graph generation with single-pass fallback on failure or insufficient output."""
    bootstrap = build_generate_workflow_bootstrap(request=request, deps=deps)
    execution = _execute_generate_workflow_driver(
        request=bootstrap.driver_run_request,
    )
    return build_generate_workflow_response(execution=execution)


__all__ = [name for name in globals() if not name.startswith('__')]
