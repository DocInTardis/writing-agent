"""Flow and sequence SVG renderers."""

from __future__ import annotations

import html
import math
from typing import Any

from writing_agent.v2 import diagram_design_render_domain as render_base
from writing_agent.v2 import diagram_design_svg_primitives_domain as primitives_domain

_clean_text = render_base._clean_text
_normalize_flowish_data = render_base._normalize_flowish_data
_normalize_sequence_data = render_base._normalize_sequence_data
normalize_diagram_kind = render_base.normalize_diagram_kind
suggest_diagram_spec = render_base.suggest_diagram_spec
_LANE_BG = render_base._LANE_BG
_LANE_PROFILES = render_base._LANE_PROFILES
_lane_title = render_base._lane_title
_svg_start = primitives_domain._svg_start
_svg_end = primitives_domain._svg_end
_multiline_text = primitives_domain._multiline_text
_render_node = primitives_domain._render_node
_render_edge = primitives_domain._render_edge

def render_flow_or_architecture_svg(kind: str, caption: str, data: dict[str, Any]) -> str:
    diagram_kind = normalize_diagram_kind(kind) or "flow"
    normalized = _normalize_flowish_data(data if isinstance(data, dict) else {}, kind=diagram_kind)
    nodes = list(normalized.get("nodes") or [])
    if len(nodes) < 2:
        normalized = suggest_diagram_spec(diagram_kind, caption=caption, prompt=caption)
        normalized = _normalize_flowish_data(normalized.get("data") or {}, kind=diagram_kind)
        nodes = list(normalized.get("nodes") or [])
    lanes = list(normalized.get("lanes") or [])
    if not lanes:
        lanes = [{"id": "core", "title": "Core Flow"}]
        for node in nodes:
            node["lane"] = "core"
    lane_priority = {item["id"]: idx for idx, item in enumerate(_LANE_PROFILES)}
    lane_index = {lane["id"]: idx for idx, lane in enumerate(lanes)}
    lanes.sort(key=lambda lane: (lane_priority.get(lane["id"], 99), lane_index.get(lane["id"], 99), str(lane["title"])))
    lane_nodes: dict[str, list[dict[str, Any]]] = {lane["id"]: [] for lane in lanes}
    for node in nodes:
        lane_id = str(node.get("lane") or lanes[0]["id"])
        if lane_id not in lane_nodes:
            lane_nodes[lane_id] = []
            lanes.append({"id": lane_id, "title": _lane_title(lane_id)})
        lane_nodes[lane_id].append(node)
    width = 1180 if diagram_kind == "architecture" else 1080
    margin_x = 36
    lane_x = margin_x
    lane_w = width - margin_x * 2
    y_cursor = 74.0
    lane_frames: list[dict[str, float | str]] = []
    positions: dict[str, dict[str, float]] = {}
    for lane_idx, lane in enumerate(lanes):
        items = lane_nodes.get(lane["id"], [])
        if not items:
            continue
        cols = min(4, max(1, len(items))) if diagram_kind == "architecture" else min(3, max(1, math.ceil(math.sqrt(len(items)))))
        rows = max(1, math.ceil(len(items) / cols))
        lane_h = 54 + rows * 118 + 18
        lane_frames.append({"x": lane_x, "y": y_cursor, "w": lane_w, "h": lane_h, "title": str(lane["title"]), "fill": _LANE_BG[lane_idx % len(_LANE_BG)]})
        cell_w = (lane_w - 36) / cols
        start_y = y_cursor + 48
        for idx, node in enumerate(items):
            row = idx // cols
            col = idx % cols
            node_w = min(210, max(156, cell_w - 26))
            node_h = 96 if str(node.get("kind") or "") == "data" else 88
            x = lane_x + 18 + col * cell_w + (cell_w - node_w) / 2
            y = start_y + row * 112
            positions[str(node["id"])] = {"x": x, "y": y, "w": node_w, "h": node_h, "cx": x + node_w / 2, "cy": y + node_h / 2}
        y_cursor += lane_h + 18
    height = int(max(320, y_cursor + 22))
    out = [_svg_start(width, height, caption or ("System Architecture" if diagram_kind == "architecture" else "Process Diagram"))]
    for frame in lane_frames:
        out.append(f'<rect x="{frame["x"]:.1f}" y="{frame["y"]:.1f}" width="{frame["w"]:.1f}" height="{frame["h"]:.1f}" rx="18" ry="18" fill="{frame["fill"]}" stroke="#D6DEE6" stroke-width="1.0"/>')
        out.append(f'<rect x="{frame["x"]+14:.1f}" y="{frame["y"]+12:.1f}" width="108" height="24" rx="12" ry="12" fill="#E3EBF4" stroke="#C7D3DF" stroke-width="0.8"/>')
        out.append(f'<text x="{frame["x"]+68:.1f}" y="{frame["y"]+28:.1f}" text-anchor="middle" class="lane">{html.escape(str(frame["title"]))}</text>')
    for edge in normalized.get("edges") or []:
        out.append(_render_edge(edge, positions))
    for node in nodes:
        box = positions.get(str(node.get("id") or ""))
        if box:
            out.append(_render_node(box, node))
    out.append(_svg_end())
    return "".join(out)

def render_professional_sequence_svg(caption: str, data: dict[str, Any]) -> str:
    normalized = _normalize_sequence_data(data if isinstance(data, dict) else {})
    participants = list(normalized.get("participants") or [])
    messages = list(normalized.get("messages") or [])
    if len(participants) < 2:
        suggested = suggest_diagram_spec("sequence", caption=caption, prompt=caption)
        normalized = _normalize_sequence_data(suggested.get("data") or {})
        participants = list(normalized.get("participants") or [])
        messages = list(normalized.get("messages") or [])
    width = max(980, 140 * max(4, len(participants)) + 80)
    band_w = (width - 80) / max(1, len(participants))
    centers = {participant: 40 + idx * band_w + band_w / 2 for idx, participant in enumerate(participants)}
    y0 = 92
    message_gap = 44
    height = int(max(320, 150 + len(messages) * message_gap + 70))
    out = [_svg_start(width, height, caption or "Sequence Diagram")]
    for idx, participant in enumerate(participants):
        x = 40 + idx * band_w
        fill = "#FAFBFC" if idx % 2 == 0 else "#F4F7FA"
        out.append(f'<rect x="{x:.1f}" y="68" width="{band_w:.1f}" height="{height-112:.1f}" fill="{fill}" stroke="none"/>')
        out.append(f'<rect x="{x+18:.1f}" y="72" width="{band_w-36:.1f}" height="30" rx="15" ry="15" fill="#E8EFF6" stroke="#C7D3DF" stroke-width="1.0"/>')
        out.append(f'<text x="{centers[participant]:.1f}" y="91" text-anchor="middle" class="label">{html.escape(participant)}</text>')
        out.append(f'<line x1="{centers[participant]:.1f}" y1="106" x2="{centers[participant]:.1f}" y2="{height-46:.1f}" stroke="#A9B6C3" stroke-width="1.5" stroke-dasharray="6,6"/>')
    y = y0 + 26
    for _idx, message in enumerate(messages):
        frm = str(message.get("from") or "")
        to = str(message.get("to") or "")
        label = _clean_text(message.get("label") or message.get("text") or "", max_chars=36) or "message"
        dashed = str(message.get("style") or "").lower() == "dashed"
        color = "#8B7B55" if dashed else "#556B7D"
        marker = "url(#arrow-dashed)" if dashed else "url(#arrow-solid)"
        dash_attr = ' stroke-dasharray="6,4"' if dashed else ""
        x1 = centers.get(frm, list(centers.values())[0])
        x2 = centers.get(to, list(centers.values())[-1])
        if frm == to:
            loop_w = 34
            out.append(f'<path d="M {x1:.1f} {y:.1f} h {loop_w:.1f} v 22 h {-loop_w:.1f}" fill="none" stroke="{color}" stroke-width="2.0" marker-end="{marker}"{dash_attr}/>')
            label_x = x1 + loop_w / 2
        else:
            out.append(f'<line x1="{x1:.1f}" y1="{y:.1f}" x2="{x2:.1f}" y2="{y:.1f}" stroke="{color}" stroke-width="2.0" marker-end="{marker}"{dash_attr}/>' )
            label_x = (x1 + x2) / 2
            out.append(f'<rect x="{x2-5:.1f}" y="{y-8:.1f}" width="10" height="20" rx="3" ry="3" fill="#D6E2EE" stroke="#9FB0C1" stroke-width="0.8"/>')
        pill_w = max(62, min(220, 24 + len(label) * 11))
        out.append(f'<rect x="{label_x-pill_w/2:.1f}" y="{y-18:.1f}" width="{pill_w:.1f}" height="20" rx="10" ry="10" fill="#FFFFFF" stroke="#D4DCE4" stroke-width="0.8"/>')
        out.append(f'<text x="{label_x:.1f}" y="{y-4:.1f}" text-anchor="middle" class="small">{html.escape(label)}</text>')
        y += message_gap
    out.append(_svg_end())
    return "".join(out)

__all__ = [name for name in globals() if not name.startswith('__')]
