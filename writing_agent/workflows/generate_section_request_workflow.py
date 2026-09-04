"""Service-facing section generation workflow facade."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .orchestration_backend import (
    build_legacy_graph_kwargs,
    build_route_graph_kwargs,
    build_route_graph_meta,
    route_graph_enabled,
)


@dataclass(frozen=True)
class GenerateSectionRequest:
    section: str
    instruction: str
    current_text: str
    cfg: Any


@dataclass(frozen=True)
class GenerateSectionDeps:
    environ: Mapping[str, str]
    run_generate_graph: Callable[..., Iterable[Mapping[str, Any]]]
    run_generate_graph_dual_engine: Callable[..., dict[str, Any]] | None = None


def run_generate_section_graph(
    *, request: GenerateSectionRequest, deps: GenerateSectionDeps
) -> tuple[str, dict[str, Any] | None]:
    section = str(request.section or "").strip()
    instruction = str(request.instruction or "").strip()
    current_text = str(request.current_text or "")
    cfg = request.cfg

    final_text: str | None = None
    graph_meta: dict[str, Any] | None = None

    use_route_graph = route_graph_enabled(
        environ=deps.environ,
        dual_engine_runner=deps.run_generate_graph_dual_engine,
    )
    if use_route_graph:
        out = deps.run_generate_graph_dual_engine(
            **build_route_graph_kwargs(
                instruction=instruction,
                current_text=current_text,
                required_h2=[section],
                required_outline=[],
                expand_outline=False,
                config=cfg,
                compose_mode="continue",
                resume_sections=[section],
                format_only=False,
            )
        )
        if isinstance(out, dict):
            final_text = str(out.get("text") or "")
            graph_meta = build_route_graph_meta(out)
    else:
        gen = deps.run_generate_graph(
            **build_legacy_graph_kwargs(
                instruction=instruction,
                current_text=current_text,
                required_h2=[section],
                required_outline=[],
                expand_outline=False,
                config=cfg,
            )
        )
        try:
            for ev in gen:
                if ev.get("event") == "final":
                    final_text = str(ev.get("text") or "")
                    break
        finally:
            close = getattr(gen, "close", None)
            if callable(close):
                close()

    return str(final_text or ""), graph_meta


__all__ = ["GenerateSectionRequest", "GenerateSectionDeps", "run_generate_section_graph"]
