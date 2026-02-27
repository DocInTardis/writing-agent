"""Render Svg module.

This module belongs to `writing_agent.diagrams` in the writing-agent codebase.
"""

from __future__ import annotations

import html
import math
from dataclasses import dataclass

from writing_agent.diagrams.spec import DiagramSpec, ErEntity, ErRelation, FlowEdge, FlowNode


def render_flowchart_svg(spec: DiagramSpec, width: int = 760) -> str:
    fc = spec.flowchart
    if fc is None or not fc.nodes:
        return _empty_svg(spec.caption, width=width)

    node_w = 260
    node_h = 54
    v_gap = 34
    x = (width - node_w) // 2

    nodes = fc.nodes[:12]
    y0 = 20
    positions: dict[str, tuple[int, int]] = {}
    for i, n in enumerate(nodes):
        y = y0 + i * (node_h + v_gap)
        positions[n.id] = (x, y)

    height = y0 + len(nodes) * (node_h + v_gap) + 20
    out = [_svg_start(width, height)]
    out.append(_defs_arrow())

    # edges first (behind)
    for e in fc.edges[:24]:
        if e.src not in positions or e.dst not in positions:
            continue
        sx, sy = positions[e.src]
        dx, dy = positions[e.dst]
        x1, y1 = sx + node_w // 2, sy + node_h
        x2, y2 = dx + node_w // 2, dy
        out.append(_line(x1, y1, x2, y2, arrow=True))
        if e.label:
            lx, ly = (x1 + x2) // 2, (y1 + y2) // 2 - 6
            out.append(_text(lx, ly, e.label, anchor="middle", size=12, fill="#A9C5FF"))

    for n in nodes:
        nx, ny = positions[n.id]
        out.append(_rect(nx, ny, node_w, node_h, r=14))
        out.append(_text(nx + node_w // 2, ny + node_h // 2 + 4, n.text, anchor="middle", size=14))

    out.append(_svg_end())
    return "".join(out)


def render_er_svg(spec: DiagramSpec, width: int = 760) -> str:
    er = spec.er
    if er is None or not er.entities:
        return _empty_svg(spec.caption, width=width)

    entities = er.entities[:8]
    cols = 2 if len(entities) > 1 else 1
    col_w = width // cols
    box_w = min(320, col_w - 40)
    header_h = 34
    line_h = 20

    # simple grid placement
    positions: dict[str, tuple[int, int, int]] = {}  # name -> x,y,h
    x_pad = 20
    y = 20
    heights: list[int] = []
    for ent in entities:
        h = header_h + max(2, min(10, len(ent.attributes))) * line_h + 18
        heights.append(h)
    max_h = max(heights) if heights else 140
    rows = math.ceil(len(entities) / cols)
    height = 20 + rows * (max_h + 24) + 20

    out = [_svg_start(width, height)]
    out.append(_defs_arrow())

    for i, ent in enumerate(entities):
        c = i % cols
        r = i // cols
        x = c * col_w + x_pad
        y = 20 + r * (max_h + 24)
        h = header_h + max(2, min(10, len(ent.attributes))) * line_h + 18
        positions[ent.name] = (x, y, h)
        out.append(_rect(x, y, box_w, h, r=14))
        out.append(_text(x + 14, y + 24, ent.name, anchor="start", size=14))
        out.append(_line(x, y + header_h, x + box_w, y + header_h, arrow=False))
        attrs = (ent.attributes or [])[:10]
        if not attrs:
            attrs = ["[待补充]"]
        for j, a in enumerate(attrs):
            out.append(_text(x + 14, y + header_h + 18 + j * line_h, a, anchor="start", size=12, fill="#D7DEFF"))

    # relations
    for rel in er.relations[:12]:
        if rel.left not in positions or rel.right not in positions:
            continue
        lx, ly, lh = positions[rel.left]
        rx, ry, rh = positions[rel.right]
        x1, y1 = lx + box_w, ly + lh // 2
        x2, y2 = rx, ry + rh // 2
        out.append(_line(x1, y1, x2, y2, arrow=True))
        label = " ".join([t for t in [rel.label, rel.cardinality] if t])
        if label:
            out.append(_text((x1 + x2) // 2, (y1 + y2) // 2 - 6, label, anchor="middle", size=12, fill="#A9C5FF"))

    out.append(_svg_end())
    return "".join(out)


def _empty_svg(caption: str, width: int = 760) -> str:
    height = 160
    out = [_svg_start(width, height)]
    out.append(_rect(20, 20, width - 40, height - 40, r=14))
    out.append(_text(width // 2, height // 2, caption or "Diagram", anchor="middle", size=14))
    out.append(_svg_end())
    return "".join(out)


def _svg_start(w: int, h: int) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" aria-label="diagram">'
        '<rect x="0" y="0" width="100%" height="100%" fill="rgba(10,14,26,0.20)"/>'
    )


def _svg_end() -> str:
    return "</svg>"


def _defs_arrow() -> str:
    return (
        '<defs>'
        '<marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">'
        '<path d="M0,0 L0,6 L9,3 z" fill="rgba(169,197,255,0.9)"/>'
        "</marker>"
        "</defs>"
    )


def _rect(x: int, y: int, w: int, h: int, r: int = 12) -> str:
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" ry="{r}" '
        'fill="rgba(18,25,45,0.55)" stroke="rgba(255,255,255,0.14)" stroke-width="1"/>'
    )


def _line(x1: int, y1: int, x2: int, y2: int, arrow: bool) -> str:
    marker = ' marker-end="url(#arrow)"' if arrow else ""
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"{marker} '
        'stroke="rgba(169,197,255,0.75)" stroke-width="2"/>'
    )


def _text(x: int, y: int, s: str, anchor: str = "start", size: int = 12, fill: str = "#E7ECFF") -> str:
    esc = html.escape(s or "")
    return (
        f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{size}" '
        f'fill="{fill}" font-family="ui-sans-serif,system-ui,Segoe UI,Arial">{esc}</text>'
    )

