"""Shared SVG primitives and renderers for academic diagram design."""

from __future__ import annotations

from writing_agent.v2 import diagram_design_svg_chart_domain as chart_domain
from writing_agent.v2 import diagram_design_svg_er_domain as er_domain
from writing_agent.v2 import diagram_design_svg_flow_domain as flow_domain
from writing_agent.v2 import diagram_design_svg_primitives_domain as primitives_domain

_char_units = primitives_domain._char_units
_wrap_text = primitives_domain._wrap_text
_svg_start = primitives_domain._svg_start
_svg_end = primitives_domain._svg_end
_multiline_text = primitives_domain._multiline_text
_render_node = primitives_domain._render_node
_edge_points = primitives_domain._edge_points
_route_edge = primitives_domain._route_edge
_render_edge = primitives_domain._render_edge
_chart_number = primitives_domain._chart_number
_chart_card = primitives_domain._chart_card
render_flow_or_architecture_svg = flow_domain.render_flow_or_architecture_svg
render_professional_sequence_svg = flow_domain.render_professional_sequence_svg
_normalize_er_data = er_domain._normalize_er_data
_cardinality_parts = er_domain._cardinality_parts
_cardinality_marker = er_domain._cardinality_marker
render_professional_er_svg = er_domain.render_professional_er_svg
render_professional_bar_svg = chart_domain.render_professional_bar_svg
render_professional_line_svg = chart_domain.render_professional_line_svg
render_professional_pie_svg = chart_domain.render_professional_pie_svg
render_professional_timeline_svg = chart_domain.render_professional_timeline_svg

__all__ = [name for name in globals() if not name.startswith('__')]
