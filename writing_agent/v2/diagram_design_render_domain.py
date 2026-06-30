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
_normalize_state_data = design_base._normalize_state_data
_normalize_class_data = design_base._normalize_class_data
_normalize_gantt_data = design_base._normalize_gantt_data
_normalize_mindmap_data = design_base._normalize_mindmap_data
_normalize_quadrant_data = design_base._normalize_quadrant_data
_normalize_radar_data = design_base._normalize_radar_data
_normalize_scatter_data = design_base._normalize_scatter_data
_normalize_heatmap_data = design_base._normalize_heatmap_data
_normalize_funnel_data = design_base._normalize_funnel_data
_normalize_sankey_data = design_base._normalize_sankey_data
_normalize_swot_data = design_base._normalize_swot_data

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


def render_professional_state_svg(caption: str, data: dict[str, Any]) -> str:
    normalized = _normalize_state_data(data if isinstance(data, dict) else {})
    states = normalized.get("states") or []
    transitions = normalized.get("transitions") or []
    if len(states) < 2:
        fallback = suggest_diagram_spec("state", caption=caption, prompt=caption)
        normalized = _normalize_state_data((fallback.get("data") if isinstance(fallback, dict) else {}) or {})
        states = normalized.get("states") or []
        transitions = normalized.get("transitions") or []
    width = 820
    height = 240 + max(0, len(states) - 4) * 18
    margin_x = 72
    card_w = 136
    card_h = 60
    gap = 36
    out = [_svg_start(width, height, caption or "状态图")]
    out.append(
        '<defs><marker id="stateArrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">'
        '<path d="M0,0 L0,6 L9,3 z" fill="#4A6785"/></marker></defs>'
    )
    pos: dict[str, tuple[float, float]] = {}
    cols = max(2, min(4, len(states)))
    rows = max(1, math.ceil(len(states) / cols))
    x_gap = (width - 2 * margin_x - card_w * cols) / max(1, cols - 1)
    y_gap = 42
    for idx, state in enumerate(states[:12]):
        row = idx // cols
        col = idx % cols
        x = margin_x + col * (card_w + x_gap)
        y = 62 + row * (card_h + y_gap)
        pos[str(state.get("id"))] = (x, y)
        state_kind = str(state.get("kind") or "").lower()
        fill = "#EDF5FE" if state_kind not in {"start", "end"} else ("#EAF5EC" if state_kind == "start" else "#FDF0E8")
        stroke = "#4A6785" if state_kind not in {"start", "end"} else ("#4E8A61" if state_kind == "start" else "#B96B3A")
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{card_w}" height="{card_h}" rx="18" ry="18" fill="{fill}" stroke="{stroke}" stroke-width="1.6"/>')
        lines = _wrap_text(str(state.get("label") or "State"), max_units=12.5, max_lines=2)
        out.append(_multiline_text(x + card_w / 2, y + 28, lines, css_class="state-label"))
    for edge in transitions[:24]:
        src = pos.get(str(edge.get("from")))
        dst = pos.get(str(edge.get("to")))
        if not src or not dst:
            continue
        x1, y1 = src[0] + card_w, src[1] + card_h / 2
        x2, y2 = dst[0], dst[1] + card_h / 2
        if x2 <= x1:
            x1 = src[0] + card_w / 2
            y1 = src[1] + card_h
            x2 = dst[0] + card_w / 2
            y2 = dst[1]
        out.append(f'<path d="M{x1:.1f},{y1:.1f} C{x1 + 26:.1f},{y1:.1f} {x2 - 26:.1f},{y2:.1f} {x2:.1f},{y2:.1f}" fill="none" stroke="#4A6785" stroke-width="2" marker-end="url(#stateArrow)"/>')
        label = _clean_text(edge.get("label"), max_chars=24)
        if label:
            mid_x = (x1 + x2) / 2
            mid_y = (y1 + y2) / 2 - 8
            out.append(f'<text x="{mid_x:.1f}" y="{mid_y:.1f}" text-anchor="middle" font-size="11" fill="#48617B" font-family="{_FONT_STACK}">{html.escape(label)}</text>')
    out.append(_svg_end())
    return "".join(out)


def render_professional_class_svg(caption: str, data: dict[str, Any]) -> str:
    normalized = _normalize_class_data(data if isinstance(data, dict) else {})
    classes = normalized.get("classes") or []
    relations = normalized.get("relations") or []
    if len(classes) < 2:
        fallback = suggest_diagram_spec("class", caption=caption, prompt=caption)
        normalized = _normalize_class_data((fallback.get("data") if isinstance(fallback, dict) else {}) or {})
        classes = normalized.get("classes") or []
        relations = normalized.get("relations") or []
    width = 860
    card_w = 180
    row_h = 140
    cols = max(2, min(3, len(classes)))
    rows = max(1, math.ceil(len(classes) / cols))
    height = 120 + rows * row_h
    margin_x = 54
    gap_x = (width - 2 * margin_x - cols * card_w) / max(1, cols - 1)
    out = [_svg_start(width, height, caption or "类图")]
    out.append(
        '<defs><marker id="classArrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto">'
        '<path d="M0,0 L0,6 L9,3 z" fill="#6A6E7F"/></marker></defs>'
    )
    pos: dict[str, dict[str, float]] = {}
    for idx, item in enumerate(classes[:8]):
        row = idx // cols
        col = idx % cols
        x = margin_x + col * (card_w + gap_x)
        y = 58 + row * row_h
        pos[str(item.get("name"))] = {"x": x, "y": y}
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{card_w}" height="108" rx="12" ry="12" fill="#F8FAFD" stroke="#7A8AA0" stroke-width="1.4"/>')
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{card_w}" height="28" rx="12" ry="12" fill="#EAF1F9" stroke="#7A8AA0" stroke-width="1.0"/>')
        out.append(f'<text x="{x + card_w / 2:.1f}" y="{y + 18:.1f}" text-anchor="middle" font-size="13" font-weight="600" fill="#294A6E" font-family="{_FONT_STACK}">{html.escape(str(item.get("name") or "Class"))}</text>')
        out.append(f'<line x1="{x:.1f}" y1="{y + 48:.1f}" x2="{x + card_w:.1f}" y2="{y + 48:.1f}" stroke="#CBD5E1"/>')
        out.append(f'<line x1="{x:.1f}" y1="{y + 78:.1f}" x2="{x + card_w:.1f}" y2="{y + 78:.1f}" stroke="#CBD5E1"/>')
        attrs = (item.get("attributes") if isinstance(item.get("attributes"), list) else [])[:2]
        methods = (item.get("methods") if isinstance(item.get("methods"), list) else [])[:2]
        for line_idx, text in enumerate(attrs):
            out.append(f'<text x="{x + 12:.1f}" y="{y + 40 + line_idx * 12:.1f}" font-size="11" fill="#44556B" font-family="{_FONT_STACK}">{html.escape(_clean_text(text, max_chars=24))}</text>')
        for line_idx, text in enumerate(methods):
            out.append(f'<text x="{x + 12:.1f}" y="{y + 96 + line_idx * 12:.1f}" font-size="11" fill="#44556B" font-family="{_FONT_STACK}">{html.escape(_clean_text(text, max_chars=24))}</text>')
    for relation in relations[:16]:
        src = pos.get(str(relation.get("from")))
        dst = pos.get(str(relation.get("to")))
        if not src or not dst:
            continue
        x1 = src["x"] + card_w
        y1 = src["y"] + 54
        x2 = dst["x"]
        y2 = dst["y"] + 54
        style = "6,4" if str(relation.get("kind") or "").lower() in {"dependency", "realization"} else ""
        dash = f' stroke-dasharray="{style}"' if style else ""
        out.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#6A6E7F" stroke-width="1.8"{dash} marker-end="url(#classArrow)"/>')
        label = _clean_text(relation.get("label") or relation.get("kind"), max_chars=20)
        if label:
            out.append(f'<text x="{(x1 + x2) / 2:.1f}" y="{(y1 + y2) / 2 - 6:.1f}" text-anchor="middle" font-size="10" fill="#667085" font-family="{_FONT_STACK}">{html.escape(label)}</text>')
    out.append(_svg_end())
    return "".join(out)


def render_professional_gantt_svg(caption: str, data: dict[str, Any]) -> str:
    normalized = _normalize_gantt_data(data if isinstance(data, dict) else {})
    tasks = normalized.get("tasks") or []
    if len(tasks) < 2:
        fallback = suggest_diagram_spec("gantt", caption=caption, prompt=caption)
        normalized = _normalize_gantt_data((fallback.get("data") if isinstance(fallback, dict) else {}) or {})
        tasks = normalized.get("tasks") or []
    width = 880
    row_h = 42
    header_h = 62
    height = header_h + 46 + row_h * max(2, len(tasks))
    label_x = 38
    grid_x = 260
    grid_w = width - grid_x - 36
    labels: list[str] = []
    for task in tasks[:12]:
        start = _clean_text(task.get("start"), max_chars=16)
        end = _clean_text(task.get("end"), max_chars=16)
        if start and start not in labels:
            labels.append(start)
        if end and end not in labels:
            labels.append(end)
    if len(labels) < 4:
        labels = ["M1", "M2", "M3", "M4", "M5"]
    col_w = grid_w / max(1, len(labels))
    out = [_svg_start(width, height, caption or "甘特图")]
    out.append('<rect x="24" y="24" width="832" height="{0}" rx="18" ry="18" fill="#FFFFFF" stroke="#D5DCE6"/>'.format(height - 48))
    for idx, label in enumerate(labels):
        x = grid_x + idx * col_w
        out.append(f'<text x="{x + col_w / 2:.1f}" y="58" text-anchor="middle" font-size="11" fill="#5F6B7A" font-family="{_FONT_STACK}">{html.escape(label)}</text>')
        out.append(f'<line x1="{x:.1f}" y1="72" x2="{x:.1f}" y2="{height - 28:.1f}" stroke="#E6EBF2"/>')
    out.append(f'<line x1="{grid_x + grid_w:.1f}" y1="72" x2="{grid_x + grid_w:.1f}" y2="{height - 28:.1f}" stroke="#E6EBF2"/>')
    status_color = {"done": "#5B8A61", "active": "#2D6AA6", "planned": "#A66A3F", "blocked": "#B54747"}
    for idx, task in enumerate(tasks[:12]):
        y = 92 + idx * row_h
        out.append(f'<text x="{label_x:.1f}" y="{y + 16:.1f}" font-size="12" fill="#25364A" font-family="{_FONT_STACK}">{html.escape(_clean_text(task.get("task"), max_chars=26))}</text>')
        owner = _clean_text(task.get("owner"), max_chars=18)
        if owner:
            out.append(f'<text x="{label_x:.1f}" y="{y + 31:.1f}" font-size="10" fill="#7A8798" font-family="{_FONT_STACK}">{html.escape(owner)}</text>')
        start = _clean_text(task.get("start"), max_chars=16)
        end = _clean_text(task.get("end"), max_chars=16)
        start_idx = labels.index(start) if start in labels else min(idx, len(labels) - 1)
        end_idx = labels.index(end) if end in labels else min(start_idx + 1, len(labels) - 1)
        if end_idx < start_idx:
            end_idx = start_idx
        bar_x = grid_x + start_idx * col_w + 8
        bar_w = max(28.0, (end_idx - start_idx + 1) * col_w - 16)
        color = status_color.get(str(task.get("status") or "").lower(), "#2D6AA6")
        out.append(f'<rect x="{bar_x:.1f}" y="{y + 4:.1f}" width="{bar_w:.1f}" height="18" rx="9" ry="9" fill="{color}" opacity="0.88"/>')
        status = _clean_text(task.get("status"), max_chars=14)
        if status:
            out.append(f'<text x="{bar_x + bar_w + 8:.1f}" y="{y + 18:.1f}" font-size="10" fill="#5F6B7A" font-family="{_FONT_STACK}">{html.escape(status)}</text>')
        out.append(f'<line x1="28" y1="{y + 32:.1f}" x2="{width - 28:.1f}" y2="{y + 32:.1f}" stroke="#EEF2F7"/>')
    out.append(_svg_end())
    return "".join(out)


def render_professional_mindmap_svg(caption: str, data: dict[str, Any]) -> str:
    normalized = _normalize_mindmap_data(data if isinstance(data, dict) else {})
    branches = normalized.get("branches") or []
    center = _clean_text(normalized.get("center"), max_chars=28) or (caption or "思维导图")
    if len(branches) < 2:
        fallback = suggest_diagram_spec("mindmap", caption=caption, prompt=caption)
        normalized = _normalize_mindmap_data((fallback.get("data") if isinstance(fallback, dict) else {}) or {})
        branches = normalized.get("branches") or []
        center = _clean_text(normalized.get("center"), max_chars=28) or center
    width = 900
    height = 520
    center_x = width / 2
    center_y = height / 2
    out = [_svg_start(width, height, caption or "思维导图")]
    out.append(f'<rect x="{center_x - 90:.1f}" y="{center_y - 28:.1f}" width="180" height="56" rx="18" ry="18" fill="#EAF2FB" stroke="#2D5F8B" stroke-width="1.8"/>')
    out.append(f'<text x="{center_x:.1f}" y="{center_y + 6:.1f}" text-anchor="middle" font-size="16" font-weight="600" fill="#244E78" font-family="{_FONT_STACK}">{html.escape(center)}</text>')
    radius = 170
    for idx, branch in enumerate(branches[:8]):
        angle = (2 * math.pi * idx / max(1, len(branches))) - math.pi / 2
        x = center_x + radius * math.cos(angle)
        y = center_y + radius * math.sin(angle)
        out.append(f'<path d="M{center_x:.1f},{center_y:.1f} Q{(center_x + x)/2:.1f},{(center_y + y)/2:.1f} {x:.1f},{y:.1f}" fill="none" stroke="#6C8EB6" stroke-width="2.2"/>')
        out.append(f'<rect x="{x - 68:.1f}" y="{y - 18:.1f}" width="136" height="36" rx="14" ry="14" fill="#F8FBFF" stroke="#8AA5C2"/>')
        out.append(f'<text x="{x:.1f}" y="{y + 5:.1f}" text-anchor="middle" font-size="12" fill="#375474" font-family="{_FONT_STACK}">{html.escape(_clean_text(branch.get("label"), max_chars=18))}</text>')
        children = branch.get("children") if isinstance(branch, dict) and isinstance(branch.get("children"), list) else []
        for child_idx, child in enumerate(children[:3]):
            child_angle = angle + (-0.22 + 0.22 * child_idx)
            cx = center_x + (radius + 92) * math.cos(child_angle)
            cy = center_y + (radius + 92) * math.sin(child_angle)
            out.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{cx:.1f}" y2="{cy:.1f}" stroke="#B4C5D9" stroke-width="1.4"/>')
            out.append(f'<text x="{cx:.1f}" y="{cy:.1f}" text-anchor="middle" font-size="10" fill="#60758D" font-family="{_FONT_STACK}">{html.escape(_clean_text(child, max_chars=14))}</text>')
    out.append(_svg_end())
    return "".join(out)


def render_professional_quadrant_svg(caption: str, data: dict[str, Any]) -> str:
    normalized = _normalize_quadrant_data(data if isinstance(data, dict) else {})
    items = normalized.get("items") or []
    if len(items) < 2:
        fallback = suggest_diagram_spec("quadrant", caption=caption, prompt=caption)
        normalized = _normalize_quadrant_data((fallback.get("data") if isinstance(fallback, dict) else {}) or {})
        items = normalized.get("items") or []
    width = 820
    height = 560
    left = 120
    top = 80
    size = 360
    out = [_svg_start(width, height, caption or "四象限图")]
    out.append(f'<rect x="{left:.1f}" y="{top:.1f}" width="{size}" height="{size}" fill="#FCFDFE" stroke="#CBD5E1"/>')
    out.append(f'<line x1="{left + size / 2:.1f}" y1="{top:.1f}" x2="{left + size / 2:.1f}" y2="{top + size:.1f}" stroke="#94A3B8" stroke-width="1.4"/>')
    out.append(f'<line x1="{left:.1f}" y1="{top + size / 2:.1f}" x2="{left + size:.1f}" y2="{top + size / 2:.1f}" stroke="#94A3B8" stroke-width="1.4"/>')
    out.append(f'<text x="{left + size / 2:.1f}" y="{top + size + 34:.1f}" text-anchor="middle" font-size="13" fill="#475569" font-family="{_FONT_STACK}">{html.escape(str(normalized.get("x_axis") or "Impact"))}</text>')
    out.append(f'<text x="{left - 52:.1f}" y="{top + size / 2:.1f}" text-anchor="middle" font-size="13" fill="#475569" font-family="{_FONT_STACK}" transform="rotate(-90 {left - 52:.1f},{top + size / 2:.1f})">{html.escape(str(normalized.get("y_axis") or "Feasibility"))}</text>')
    quadrant_labels = [("Q1", left + size * 0.75, top + size * 0.25), ("Q2", left + size * 0.25, top + size * 0.25), ("Q3", left + size * 0.25, top + size * 0.75), ("Q4", left + size * 0.75, top + size * 0.75)]
    for label, x, y in quadrant_labels:
        out.append(f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" font-size="28" fill="#E2E8F0" font-family="{_FONT_STACK}">{label}</text>')
    colors = ["#2D6AA6", "#5B8A61", "#A66A3F", "#A8557E"]
    for idx, item in enumerate(items[:12]):
        x = left + float(item.get("x", 0.5)) * size
        y = top + (1 - float(item.get("y", 0.5))) * size
        color = colors[idx % len(colors)]
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="8" fill="{color}" opacity="0.88"/>')
        out.append(f'<text x="{x + 12:.1f}" y="{y + 4:.1f}" font-size="11" fill="#334155" font-family="{_FONT_STACK}">{html.escape(_clean_text(item.get("label"), max_chars=18))}</text>')
    out.append(_svg_end())
    return "".join(out)


def render_professional_radar_svg(caption: str, data: dict[str, Any]) -> str:
    normalized = _normalize_radar_data(data if isinstance(data, dict) else {})
    axes = normalized.get("axes") or []
    series = normalized.get("series") or []
    if len(axes) < 3 or not series:
        fallback = suggest_diagram_spec("radar", caption=caption, prompt=caption)
        normalized = _normalize_radar_data((fallback.get("data") if isinstance(fallback, dict) else {}) or {})
        axes = normalized.get("axes") or []
        series = normalized.get("series") or []
    width = 820
    height = 560
    cx = width / 2
    cy = height / 2 + 10
    radius = 170
    out = [_svg_start(width, height, caption or "雷达图")]
    for level in range(1, 6):
        points: list[str] = []
        r = radius * level / 5
        for idx in range(len(axes)):
            angle = -math.pi / 2 + 2 * math.pi * idx / len(axes)
            points.append(f"{cx + r * math.cos(angle):.1f},{cy + r * math.sin(angle):.1f}")
        out.append(f'<polygon points="{" ".join(points)}" fill="none" stroke="#D5DCE6" stroke-width="1"/>')
    for idx, axis in enumerate(axes):
        angle = -math.pi / 2 + 2 * math.pi * idx / len(axes)
        x = cx + radius * math.cos(angle)
        y = cy + radius * math.sin(angle)
        out.append(f'<line x1="{cx:.1f}" y1="{cy:.1f}" x2="{x:.1f}" y2="{y:.1f}" stroke="#CBD5E1"/>')
        out.append(f'<text x="{cx + (radius + 26) * math.cos(angle):.1f}" y="{cy + (radius + 26) * math.sin(angle):.1f}" text-anchor="middle" font-size="11" fill="#475569" font-family="{_FONT_STACK}">{html.escape(_clean_text(axis, max_chars=16))}</text>')
    palette = [("#2D6AA6", "rgba(45,106,166,0.18)"), ("#B45309", "rgba(180,83,9,0.16)")]
    for idx, row in enumerate(series[:2]):
        color, fill = palette[idx]
        values = row.get("values") if isinstance(row, dict) and isinstance(row.get("values"), list) else []
        points: list[str] = []
        for axis_idx, value in enumerate(values[: len(axes)]):
            angle = -math.pi / 2 + 2 * math.pi * axis_idx / len(axes)
            r = radius * max(0.0, min(100.0, float(value))) / 100
            px = cx + r * math.cos(angle)
            py = cy + r * math.sin(angle)
            points.append(f"{px:.1f},{py:.1f}")
            out.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.5" fill="{color}"/>')
        out.append(f'<polygon points="{" ".join(points)}" fill="{fill}" stroke="{color}" stroke-width="2"/>')
        out.append(f'<text x="{620:.1f}" y="{88 + idx * 20:.1f}" font-size="11" fill="{color}" font-family="{_FONT_STACK}">{html.escape(_clean_text(row.get("name"), max_chars=16))}</text>')
    out.append(_svg_end())
    return "".join(out)


def render_professional_scatter_svg(caption: str, data: dict[str, Any]) -> str:
    normalized = _normalize_scatter_data(data if isinstance(data, dict) else {})
    points = normalized.get("points") or []
    if len(points) < 2:
        fallback = suggest_diagram_spec("scatter", caption=caption, prompt=caption)
        normalized = _normalize_scatter_data((fallback.get("data") if isinstance(fallback, dict) else {}) or {})
        points = normalized.get("points") or []
    width = 840
    height = 560
    left = 110
    top = 70
    plot_w = 560
    plot_h = 360
    out = [_svg_start(width, height, caption or "散点图")]
    out.append(f'<rect x="{left:.1f}" y="{top:.1f}" width="{plot_w}" height="{plot_h}" fill="#FFFFFF" stroke="#D8E0EA"/>')
    xs = [float(item.get("x", 0.0)) for item in points]
    ys = [float(item.get("y", 0.0)) for item in points]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    if x_max == x_min:
        x_max += 1.0
    if y_max == y_min:
        y_max += 1.0
    for idx in range(6):
        gy = top + plot_h * idx / 5
        gx = left + plot_w * idx / 5
        out.append(f'<line x1="{left:.1f}" y1="{gy:.1f}" x2="{left + plot_w:.1f}" y2="{gy:.1f}" stroke="#EEF2F7"/>')
        out.append(f'<line x1="{gx:.1f}" y1="{top:.1f}" x2="{gx:.1f}" y2="{top + plot_h:.1f}" stroke="#EEF2F7"/>')
    color_map = {"baseline": "#64748B", "improved": "#2D6AA6", "outlier": "#B45309"}
    for item in points[:24]:
        px = left + (float(item.get("x", 0.0)) - x_min) / (x_max - x_min) * plot_w
        py = top + plot_h - (float(item.get("y", 0.0)) - y_min) / (y_max - y_min) * plot_h
        color = color_map.get(str(item.get("group") or "").lower(), "#2D6AA6")
        out.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="6" fill="{color}" opacity="0.9"/>')
        label = _clean_text(item.get("label"), max_chars=12)
        if label:
            out.append(f'<text x="{px + 10:.1f}" y="{py - 8:.1f}" font-size="10" fill="#334155" font-family="{_FONT_STACK}">{html.escape(label)}</text>')
    out.append(f'<text x="{left + plot_w / 2:.1f}" y="{top + plot_h + 36:.1f}" text-anchor="middle" font-size="13" fill="#475569" font-family="{_FONT_STACK}">{html.escape(str(normalized.get("x_label") or "X"))}</text>')
    out.append(f'<text x="{left - 56:.1f}" y="{top + plot_h / 2:.1f}" text-anchor="middle" font-size="13" fill="#475569" font-family="{_FONT_STACK}" transform="rotate(-90 {left - 56:.1f},{top + plot_h / 2:.1f})">{html.escape(str(normalized.get("y_label") or "Y"))}</text>')
    out.append(_svg_end())
    return "".join(out)


def render_professional_heatmap_svg(caption: str, data: dict[str, Any]) -> str:
    normalized = _normalize_heatmap_data(data if isinstance(data, dict) else {})
    rows = normalized.get("rows") or []
    cols = normalized.get("cols") or []
    values = normalized.get("values") or []
    if len(rows) < 2 or len(cols) < 2:
        fallback = suggest_diagram_spec("heatmap", caption=caption, prompt=caption)
        normalized = _normalize_heatmap_data((fallback.get("data") if isinstance(fallback, dict) else {}) or {})
        rows = normalized.get("rows") or []
        cols = normalized.get("cols") or []
        values = normalized.get("values") or []
    width = 860
    height = 520
    left = 160
    top = 90
    cell_w = 82
    cell_h = 56
    out = [_svg_start(width, height, caption or "热力图")]
    max_value = max((max(row) for row in values if row), default=100.0) or 100.0
    for col_idx, col in enumerate(cols[:8]):
        out.append(f'<text x="{left + col_idx * cell_w + cell_w/2:.1f}" y="{top - 18:.1f}" text-anchor="middle" font-size="11" fill="#475569" font-family="{_FONT_STACK}">{html.escape(_clean_text(col, max_chars=14))}</text>')
    for row_idx, row_name in enumerate(rows[:8]):
        out.append(f'<text x="{left - 18:.1f}" y="{top + row_idx * cell_h + cell_h/2 + 4:.1f}" text-anchor="end" font-size="11" fill="#475569" font-family="{_FONT_STACK}">{html.escape(_clean_text(row_name, max_chars=14))}</text>')
        row_values = values[row_idx] if row_idx < len(values) and isinstance(values[row_idx], list) else []
        for col_idx in range(min(len(cols), len(row_values))):
            value = float(row_values[col_idx])
            alpha = max(0.12, min(0.92, value / max_value))
            x = left + col_idx * cell_w
            y = top + row_idx * cell_h
            out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell_w - 6}" height="{cell_h - 6}" rx="8" ry="8" fill="#2D6AA6" opacity="{alpha:.2f}"/>')
            out.append(f'<text x="{x + (cell_w - 6)/2:.1f}" y="{y + (cell_h - 6)/2 + 4:.1f}" text-anchor="middle" font-size="11" fill="#FFFFFF" font-family="{_FONT_STACK}">{value:.0f}</text>')
    out.append(_svg_end())
    return "".join(out)


def render_professional_funnel_svg(caption: str, data: dict[str, Any]) -> str:
    normalized = _normalize_funnel_data(data if isinstance(data, dict) else {})
    stages = normalized.get("stages") or []
    if len(stages) < 2:
        fallback = suggest_diagram_spec("funnel", caption=caption, prompt=caption)
        normalized = _normalize_funnel_data((fallback.get("data") if isinstance(fallback, dict) else {}) or {})
        stages = normalized.get("stages") or []
    width = 820
    height = 520
    top = 80
    center_x = width / 2
    max_value = max((float(item.get("value", 0.0)) for item in stages), default=1.0) or 1.0
    out = [_svg_start(width, height, caption or "漏斗图")]
    for idx, item in enumerate(stages[:6]):
        value = float(item.get("value", 0.0))
        upper = 320 * (value / max_value)
        next_value = float(stages[idx + 1].get("value", value)) if idx + 1 < len(stages) else value * 0.72
        lower = 320 * (next_value / max_value)
        y1 = top + idx * 62
        y2 = y1 + 46
        color = ["#2D6AA6", "#4C84BA", "#6A9CCC", "#8AB2DA", "#AAC8E8", "#C7DCF1"][idx % 6]
        points = f"{center_x - upper/2:.1f},{y1:.1f} {center_x + upper/2:.1f},{y1:.1f} {center_x + lower/2:.1f},{y2:.1f} {center_x - lower/2:.1f},{y2:.1f}"
        out.append(f'<polygon points="{points}" fill="{color}" stroke="#FFFFFF" stroke-width="1.5"/>')
        out.append(f'<text x="{center_x:.1f}" y="{y1 + 28:.1f}" text-anchor="middle" font-size="12" fill="#FFFFFF" font-family="{_FONT_STACK}">{html.escape(_clean_text(item.get("label"), max_chars=18))} {value:.0f}</text>')
    out.append(_svg_end())
    return "".join(out)


def render_professional_sankey_svg(caption: str, data: dict[str, Any]) -> str:
    normalized = _normalize_sankey_data(data if isinstance(data, dict) else {})
    nodes = normalized.get("nodes") or []
    links = normalized.get("links") or []
    if len(nodes) < 2 or not links:
        fallback = suggest_diagram_spec("sankey", caption=caption, prompt=caption)
        normalized = _normalize_sankey_data((fallback.get("data") if isinstance(fallback, dict) else {}) or {})
        nodes = normalized.get("nodes") or []
        links = normalized.get("links") or []
    width = 900
    height = 520
    left_x = 110
    right_x = 620
    node_w = 120
    node_h = 34
    out = [_svg_start(width, height, caption or "桑基图")]
    positions: dict[str, tuple[float, float]] = {}
    for idx, node in enumerate(nodes[:8]):
        x = left_x if idx < max(1, len(nodes) // 2) else right_x
        y = 80 + (idx % max(1, (len(nodes)+1)//2)) * 72
        positions[node] = (x, y)
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{node_w}" height="{node_h}" rx="8" ry="8" fill="#EAF2FB" stroke="#6A8CB3"/>')
        out.append(f'<text x="{x + node_w/2:.1f}" y="{y + 21:.1f}" text-anchor="middle" font-size="11" fill="#2F4B68" font-family="{_FONT_STACK}">{html.escape(_clean_text(node, max_chars=14))}</text>')
    max_value = max((float(item.get("value", 0.0)) for item in links), default=1.0) or 1.0
    for item in links[:16]:
        src = positions.get(str(item.get("source")))
        dst = positions.get(str(item.get("target")))
        if not src or not dst:
            continue
        stroke_w = 3 + 18 * float(item.get("value", 0.0)) / max_value
        x1, y1 = src[0] + node_w, src[1] + node_h / 2
        x2, y2 = dst[0], dst[1] + node_h / 2
        out.append(f'<path d="M{x1:.1f},{y1:.1f} C{x1 + 120:.1f},{y1:.1f} {x2 - 120:.1f},{y2:.1f} {x2:.1f},{y2:.1f}" fill="none" stroke="#79A7D3" stroke-width="{stroke_w:.1f}" opacity="0.55"/>')
    out.append(_svg_end())
    return "".join(out)


def render_professional_swot_svg(caption: str, data: dict[str, Any]) -> str:
    normalized = _normalize_swot_data(data if isinstance(data, dict) else {})
    if not any(normalized.get(key) for key in ("strengths", "weaknesses", "opportunities", "threats")):
        fallback = suggest_diagram_spec("swot", caption=caption, prompt=caption)
        normalized = _normalize_swot_data((fallback.get("data") if isinstance(fallback, dict) else {}) or {})
    width = 860
    height = 560
    boxes = [
        ("优势 Strengths", 60, 90, "#EAF5EC", "#4E8A61", normalized.get("strengths") or []),
        ("劣势 Weaknesses", 440, 90, "#FDF0E8", "#B96B3A", normalized.get("weaknesses") or []),
        ("机会 Opportunities", 60, 310, "#EAF2FB", "#2D6AA6", normalized.get("opportunities") or []),
        ("威胁 Threats", 440, 310, "#F7EAF0", "#A8557E", normalized.get("threats") or []),
    ]
    out = [_svg_start(width, height, caption or "SWOT图")]
    for title, x, y, fill, stroke, items in boxes:
        out.append(f'<rect x="{x}" y="{y}" width="320" height="170" rx="16" ry="16" fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>')
        out.append(f'<text x="{x + 18}" y="{y + 28}" font-size="14" font-weight="600" fill="{stroke}" font-family="{_FONT_STACK}">{html.escape(title)}</text>')
        for idx, item in enumerate((items if isinstance(items, list) else [])[:5]):
            out.append(f'<text x="{x + 22}" y="{y + 58 + idx*22}" font-size="11" fill="#334155" font-family="{_FONT_STACK}">• {html.escape(_clean_text(item, max_chars=22))}</text>')
    out.append(_svg_end())
    return "".join(out)

