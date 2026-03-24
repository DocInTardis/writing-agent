"""Service-facing section generation workflow facade."""

from __future__ import annotations

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
    app_v2: Any
    session: Any
    section: str
    instruction: str
    current_text: str
    cfg: Any


def run_generate_section_graph(*, request: GenerateSectionRequest) -> tuple[str, dict[str, Any] | None]:
    app_v2 = request.app_v2
    section = str(request.section or "").strip()
    instruction = str(request.instruction or "").strip()
    current_text = str(request.current_text or "")
    cfg = request.cfg

    final_text: str | None = None
    graph_meta: dict[str, Any] | None = None

    use_route_graph = route_graph_enabled(
        environ=app_v2.os.environ,
        dual_engine_runner=getattr(app_v2, "run_generate_graph_dual_engine", None),
    )
    if use_route_graph:
        out = app_v2.run_generate_graph_dual_engine(
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
        gen = app_v2.run_generate_graph(
            **build_legacy_graph_kwargs(
                instruction=instruction,
                current_text=current_text,
                required_h2=[section],
                required_outline=[],
                expand_outline=False,
                config=cfg,
            )
        )
        for ev in gen:
            if ev.get("event") == "final":
                final_text = str(ev.get("text") or "")
                break

    return str(final_text or ""), graph_meta


__all__ = [name for name in globals() if not name.startswith("__")]
