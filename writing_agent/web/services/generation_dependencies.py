"""Compose workflow dependencies at the Web boundary, not in agent workflows.

This adapter is the temporary bridge to the legacy composition root. Workflows
receive only their declared capabilities; they cannot discover app globals.
"""

from collections.abc import Callable
from typing import Any

from writing_agent.web.domains import route_graph_metrics_domain
from writing_agent.workflows.generate_request_workflow import GenerateGraphDeps
from writing_agent.workflows.generate_section_request_workflow import GenerateSectionDeps


def _missing_dependency(name: str) -> Callable[..., Any]:
    def missing(*_args: Any, **_kwargs: Any) -> Any:
        raise AttributeError(f"Generate workflow dependency '{name}' is unavailable")

    return missing


def _fallback_exception(**kwargs: Any) -> Exception:
    return RuntimeError(str(kwargs.get("detail") or "generation failed"))


def build_generate_graph_deps(app: Any) -> GenerateGraphDeps:
    exception_factory = getattr(app, "HTTPException", None)
    return GenerateGraphDeps(
        environ=dict(getattr(getattr(app, "os", None), "environ", {})),
        record_route_metric=route_graph_metrics_domain.record_route_graph_metric,
        should_inject_route_graph_failure=route_graph_metrics_domain.should_inject_route_graph_failure,
        run_generate_graph_dual_engine=getattr(app, "run_generate_graph_dual_engine", None),
        run_generate_graph=getattr(app, "run_generate_graph", _missing_dependency("run_generate_graph")),
        iter_with_timeout=getattr(app, "_iter_with_timeout", _missing_dependency("_iter_with_timeout")),
        single_pass_generate=getattr(app, "_single_pass_generate", _missing_dependency("_single_pass_generate")),
        extract_error_code=route_graph_metrics_domain.extract_error_code,
        http_exception_factory=exception_factory if callable(exception_factory) else _fallback_exception,
    )


def build_generate_section_deps(app: Any) -> GenerateSectionDeps:
    return GenerateSectionDeps(
        environ=dict(getattr(getattr(app, "os", None), "environ", {})),
        run_generate_graph=getattr(app, "run_generate_graph", _missing_dependency("run_generate_graph")),
        run_generate_graph_dual_engine=getattr(app, "run_generate_graph_dual_engine", None),
    )
