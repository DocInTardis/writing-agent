"""Render Svg module.

This module belongs to `writing_agent.diagrams` in the writing-agent codebase.
"""

from __future__ import annotations

import html
import math
from dataclasses import dataclass

from writing_agent.diagrams.spec import DiagramSpec, ErEntity, ErRelation, FlowEdge, FlowNode
from writing_agent.v2.diagram_design import render_flow_or_architecture_svg, render_professional_er_svg


_FONT_STACK = "Microsoft YaHei, PingFang SC, Hiragino Sans GB, Noto Sans CJK SC, SimHei, SimSun, Arial Unicode MS, Segoe UI, Arial, sans-serif"


def render_flowchart_svg(spec: DiagramSpec, width: int = 760) -> str:
    _ = width
    fc = spec.flowchart
    if fc is None or not fc.nodes:
        return _empty_svg(spec.caption, width=width)
    data = {
        "nodes": [{"id": node.id, "label": node.text} for node in fc.nodes[:16]],
        "edges": [{"from": edge.src, "to": edge.dst, "label": edge.label} for edge in fc.edges[:32]],
    }
    return render_flow_or_architecture_svg("flow", spec.caption or "Flow Diagram", data)


def render_er_svg(spec: DiagramSpec, width: int = 760) -> str:
    _ = width
    er = spec.er
    if er is None or not er.entities:
        return _empty_svg(spec.caption, width=width)
    data = {
        "entities": [{"name": entity.name, "attributes": list(entity.attributes or [])} for entity in er.entities[:12]],
        "relations": [
            {"left": rel.left, "right": rel.right, "label": rel.label, "cardinality": rel.cardinality}
            for rel in er.relations[:24]
        ],
    }
    return render_professional_er_svg(spec.caption or "ER Diagram", data)


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
        f'<style>text,tspan{{font-family:{_FONT_STACK};}}</style>'
        '<rect x="0" y="0" width="100%" height="100%" fill="#FFFFFF"/>'
    )


def _svg_end() -> str:
    return "</svg>"


def _defs_arrow() -> str:
    return (
        '<defs>'
        '<marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">'
        '<path d="M0,0 L0,6 L9,3 z" fill="#5B6B88"/>'
        "</marker>"
        "</defs>"
    )


def _rect(x: int, y: int, w: int, h: int, r: int = 12) -> str:
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" ry="{r}" '
        'fill="#F6F8FC" stroke="#AEBBCD" stroke-width="1.2"/>'
    )


def _line(x1: int, y1: int, x2: int, y2: int, arrow: bool) -> str:
    marker = ' marker-end="url(#arrow)"' if arrow else ""
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"{marker} '
        'stroke="#5B6B88" stroke-width="2"/>'
    )


def _text(x: int, y: int, s: str, anchor: str = "start", size: int = 12, fill: str = "#1F2D3D") -> str:
    esc = html.escape(s or "")
    return (
        f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{size}" '
        f'fill="{fill}" font-family="{_FONT_STACK}">{esc}</text>'
    )

