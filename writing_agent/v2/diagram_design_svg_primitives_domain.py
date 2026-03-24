"""Shared SVG primitive helpers for academic diagram rendering."""

from __future__ import annotations

import html
import re
from typing import Any

from writing_agent.v2 import diagram_design_render_domain as render_base

_FONT_STACK = render_base._FONT_STACK
_clean_text = render_base._clean_text
_KIND_BADGE = render_base._KIND_BADGE
_KIND_STYLE = render_base._KIND_STYLE

def _char_units(ch: str) -> float:
    return 1.8 if re.match(r"[\u4E00-\u9FFF]", ch) else 1.0

def _wrap_text(text: str, *, max_units: float = 12.0, max_lines: int = 3) -> list[str]:
    raw = _clean_text(text, max_chars=60)
    if not raw:
        return []
    word_mode = bool(" " in raw and re.search(r"[A-Za-z]", raw))
    words = raw.split(" ") if word_mode else list(raw)
    lines: list[str] = []
    current = ""
    current_units = 0.0
    for token in words:
        token_units = sum(_char_units(ch) for ch in token)
        spacer = 1.0 if current and word_mode else 0.0
        if current and current_units + spacer + token_units > max_units:
            lines.append(current)
            current = token
            current_units = token_units
            if len(lines) >= max_lines - 1:
                break
        else:
            if current and word_mode:
                current += " " + token
                current_units += spacer + token_units
            else:
                current += token
                current_units += token_units
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    if len(lines) == max_lines and (len("".join(lines)) < len(raw)):
        lines[-1] = lines[-1].rstrip("…") + "…"
    return lines[:max_lines]

def _svg_start(width: int, height: int, caption: str) -> str:
    title = html.escape(caption or "diagram")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{title}">'
        "<defs>"
        '<marker id="arrow-solid" markerWidth="12" markerHeight="12" refX="10" refY="4" orient="auto" markerUnits="strokeWidth">'
        '<path d="M0,0 L0,8 L10,4 z" fill="#556B7D"/></marker>'
        '<marker id="arrow-dashed" markerWidth="12" markerHeight="12" refX="10" refY="4" orient="auto" markerUnits="strokeWidth">'
        '<path d="M0,0 L0,8 L10,4 z" fill="#8B7B55"/></marker>'
        "</defs>"
        f"<style>text,tspan{{font-family:{_FONT_STACK};}} .small{{font-size:12px;fill:#4B5868}} .label{{font-size:15px;font-weight:600;fill:#1F2D3D}} .subtitle{{font-size:11px;fill:#556270}} .lane{{font-size:14px;font-weight:700;fill:#34495E}} .caption{{font-size:16px;font-weight:700;fill:#24364A}}</style>"
        '<rect x="0" y="0" width="100%" height="100%" fill="#FFFFFF"/>'
        f'<rect x="20" y="20" width="{width-40}" height="{height-40}" rx="20" ry="20" fill="#FFFFFF" stroke="#C8D2DC" stroke-width="1.3"/>'
        f'<text x="{width/2:.1f}" y="48" text-anchor="middle" class="caption">{title}</text>'
    )

def _svg_end() -> str:
    return "</svg>"

def _multiline_text(x: float, y: float, lines: list[str], *, css_class: str, anchor: str = "middle", line_gap: int = 16) -> str:
    if not lines:
        return ""
    escaped = [html.escape(line) for line in lines]
    out = [f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" class="{css_class}">']
    for idx, line in enumerate(escaped):
        dy = 0 if idx == 0 else line_gap
        out.append(f'<tspan x="{x:.1f}" dy="{dy}">{line}</tspan>')
    out.append("</text>")
    return "".join(out)

def _render_node(box: dict[str, float], node: dict[str, Any]) -> str:
    kind = str(node.get("kind") or "process")
    style = _KIND_STYLE.get(kind, _KIND_STYLE["process"])
    x = float(box["x"])
    y = float(box["y"])
    w = float(box["w"])
    h = float(box["h"])
    cx = float(box["cx"])
    cy = float(box["cy"])
    label_lines = _wrap_text(str(node.get("label") or ""), max_units=16.0, max_lines=2)
    subtitle_lines = _wrap_text(str(node.get("subtitle") or ""), max_units=18.0, max_lines=2)
    badge = _KIND_BADGE.get(kind, _KIND_BADGE["process"])
    out: list[str] = []
    if kind == "data":
        out.append(f'<rect x="{x:.1f}" y="{y+12:.1f}" width="{w:.1f}" height="{h-24:.1f}" rx="18" ry="18" fill="{style["fill"]}" stroke="{style["stroke"]}" stroke-width="1.8"/>')
        out.append(f'<ellipse cx="{cx:.1f}" cy="{y+12:.1f}" rx="{w/2:.1f}" ry="12" fill="{style["fill"]}" stroke="{style["stroke"]}" stroke-width="1.8"/>')
        out.append(f'<ellipse cx="{cx:.1f}" cy="{y+h-12:.1f}" rx="{w/2:.1f}" ry="12" fill="none" stroke="{style["stroke"]}" stroke-width="1.5"/>')
    elif kind == "decision":
        points = f"{cx:.1f},{y:.1f} {x+w:.1f},{cy:.1f} {cx:.1f},{y+h:.1f} {x:.1f},{cy:.1f}"
        out.append(f'<polygon points="{points}" fill="{style["fill"]}" stroke="{style["stroke"]}" stroke-width="1.8"/>')
    else:
        dash = ' stroke-dasharray="6,4"' if kind == "control" else ""
        rx = h / 2 if kind == "actor" else 18
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx:.1f}" ry="{rx:.1f}" fill="{style["fill"]}" stroke="{style["stroke"]}" stroke-width="1.8"{dash}/>')
        out.append(f'<line x1="{x+16:.1f}" y1="{y+32:.1f}" x2="{x+w-16:.1f}" y2="{y+32:.1f}" stroke="{style["accent"]}" stroke-width="1.2" opacity="0.35"/>')
    badge_w = max(42, min(68, 22 + len(badge) * 14))
    out.append(f'<rect x="{x+12:.1f}" y="{y+10:.1f}" width="{badge_w:.1f}" height="20" rx="10" ry="10" fill="{style["accent"]}" opacity="0.12" stroke="{style["accent"]}" stroke-width="0.8"/>')
    out.append(f'<text x="{x+12+badge_w/2:.1f}" y="{y+24:.1f}" text-anchor="middle" class="small" fill="{style["accent"]}">{html.escape(badge)}</text>')
    label_y = y + (h * 0.48 if kind == "decision" else 48)
    out.append(_multiline_text(cx, label_y, label_lines, css_class="label", anchor="middle", line_gap=16))
    if subtitle_lines and kind != "decision":
        out.append(_multiline_text(cx, y + h - 20, subtitle_lines, css_class="subtitle", anchor="middle", line_gap=14))
    return "".join(out)

def _edge_points(src: dict[str, float], dst: dict[str, float]) -> tuple[tuple[float, float], tuple[float, float]]:
    if abs(src["cy"] - dst["cy"]) < 18:
        if src["cx"] <= dst["cx"]:
            return (src["x"] + src["w"], src["cy"]), (dst["x"], dst["cy"])
        return (src["x"], src["cy"]), (dst["x"] + dst["w"], dst["cy"])
    if src["cy"] <= dst["cy"]:
        return (src["cx"], src["y"] + src["h"]), (dst["cx"], dst["y"])
    return (src["cx"], src["y"]), (dst["cx"], dst["y"] + dst["h"])

def _route_edge(src: dict[str, float], dst: dict[str, float]) -> tuple[str, tuple[float, float]]:
    (sx, sy), (tx, ty) = _edge_points(src, dst)
    if abs(sy - ty) < 24:
        midx = (sx + tx) / 2
        path = f"M {sx:.1f} {sy:.1f} L {midx:.1f} {sy:.1f} L {midx:.1f} {ty:.1f} L {tx:.1f} {ty:.1f}"
        label_pos = ((sx + tx) / 2, sy - 8)
    else:
        midy = (sy + ty) / 2
        path = f"M {sx:.1f} {sy:.1f} L {sx:.1f} {midy:.1f} L {tx:.1f} {midy:.1f} L {tx:.1f} {ty:.1f}"
        label_pos = ((sx + tx) / 2, midy - 8)
    return path, label_pos

def _render_edge(edge: dict[str, str], positions: dict[str, dict[str, float]]) -> str:
    src = positions.get(str(edge.get("from") or ""))
    dst = positions.get(str(edge.get("to") or ""))
    if not src or not dst:
        return ""
    path, (lx, ly) = _route_edge(src, dst)
    dashed = str(edge.get("style") or "").lower() == "dashed"
    stroke = "#8B7B55" if dashed else "#556B7D"
    marker = "url(#arrow-dashed)" if dashed else "url(#arrow-solid)"
    dash_attr = ' stroke-dasharray="6,4"' if dashed else ""
    label = _clean_text(edge.get("label") or "", max_chars=28)
    out = [f'<path d="{path}" fill="none" stroke="{stroke}" stroke-width="2.2" marker-end="{marker}"{dash_attr}/>' ]
    if label:
        pill_w = max(56, min(180, 20 + len(label) * 11))
        out.append(f'<rect x="{lx-pill_w/2:.1f}" y="{ly-16:.1f}" width="{pill_w:.1f}" height="20" rx="10" ry="10" fill="#FFFFFF" stroke="#D4DCE4" stroke-width="0.9"/>')
        out.append(f'<text x="{lx:.1f}" y="{ly-2:.1f}" text-anchor="middle" class="small">{html.escape(label)}</text>')
    return "".join(out)

def _chart_number(value: float) -> str:
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")

def _chart_card(width: int, height: int, caption: str) -> list[str]:
    return [_svg_start(width, height, caption)]

__all__ = [name for name in globals() if not name.startswith('__')]
