"""SVG rendering backend for academic diagram design."""

from __future__ import annotations

import html
import math
import re
from typing import Any

from writing_agent.v2 import diagram_design as design_base

_FONT_STACK = design_base._FONT_STACK
_clean_text = design_base._clean_text
_normalize_flowish_data = design_base._normalize_flowish_data
_normalize_sequence_data = design_base._normalize_sequence_data

normalize_diagram_kind = design_base.normalize_diagram_kind
suggest_diagram_spec = design_base.suggest_diagram_spec
_KIND_BADGE = design_base._KIND_BADGE
_KIND_STYLE = design_base._KIND_STYLE
_LANE_BG = design_base._LANE_BG
_LANE_PROFILES = design_base._LANE_PROFILES
_lane_title = design_base._lane_title

from writing_agent.v2 import diagram_design_svg_support_domain as svg_support_domain

def _char_units(ch: str) -> float:
    return svg_support_domain._char_units(ch)


def _wrap_text(text: str, *, max_units: float = 12.0, max_lines: int = 3) -> list[str]:
    return svg_support_domain._wrap_text(text, max_units=max_units, max_lines=max_lines)


def _svg_start(width: int, height: int, caption: str) -> str:
    return svg_support_domain._svg_start(width, height, caption)


def _svg_end() -> str:
    return svg_support_domain._svg_end()


def _multiline_text(x: float, y: float, lines: list[str], *, css_class: str, anchor: str = "middle", line_gap: int = 16) -> str:
    return svg_support_domain._multiline_text(x, y, lines, css_class=css_class, anchor=anchor, line_gap=line_gap)


def _render_node(box: dict[str, float], node: dict[str, Any]) -> str:
    return svg_support_domain._render_node(box, node)


def _edge_points(src: dict[str, float], dst: dict[str, float]) -> tuple[tuple[float, float], tuple[float, float]]:
    return svg_support_domain._edge_points(src, dst)


def _route_edge(src: dict[str, float], dst: dict[str, float]) -> tuple[str, tuple[float, float]]:
    return svg_support_domain._route_edge(src, dst)


def _render_edge(edge: dict[str, str], positions: dict[str, dict[str, float]]) -> str:
    return svg_support_domain._render_edge(edge, positions)


def render_flow_or_architecture_svg(kind: str, caption: str, data: dict[str, Any]) -> str:
    return svg_support_domain.render_flow_or_architecture_svg(kind, caption, data)


def render_professional_sequence_svg(caption: str, data: dict[str, Any]) -> str:
    return svg_support_domain.render_professional_sequence_svg(caption, data)


def _normalize_er_data(data: dict[str, Any]) -> dict[str, Any]:
    return svg_support_domain._normalize_er_data(data)


def _chart_number(value: float) -> str:
    return svg_support_domain._chart_number(value)


def _chart_card(width: int, height: int, caption: str) -> list[str]:
    return svg_support_domain._chart_card(width, height, caption)


def _cardinality_parts(cardinality: str) -> tuple[str, str]:
    return svg_support_domain._cardinality_parts(cardinality)


def _cardinality_marker(kind: str, x: float, y: float, direction: int) -> str:
    return svg_support_domain._cardinality_marker(kind, x, y, direction)


def render_professional_er_svg(caption: str, data: dict[str, Any]) -> str:
    return svg_support_domain.render_professional_er_svg(caption, data)


def render_professional_bar_svg(caption: str, data: dict[str, Any]) -> str:
    return svg_support_domain.render_professional_bar_svg(caption, data)


def render_professional_line_svg(caption: str, data: dict[str, Any]) -> str:
    return svg_support_domain.render_professional_line_svg(caption, data)


def render_professional_pie_svg(caption: str, data: dict[str, Any]) -> str:
    return svg_support_domain.render_professional_pie_svg(caption, data)


def render_professional_timeline_svg(caption: str, data: dict[str, Any]) -> str:
    return svg_support_domain.render_professional_timeline_svg(caption, data)

