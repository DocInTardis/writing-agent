"""Entity-relationship SVG renderers."""

from __future__ import annotations

import html
import math
from typing import Any

from writing_agent.v2 import diagram_design_render_domain as render_base
from writing_agent.v2 import diagram_design_svg_primitives_domain as primitives_domain

_clean_text = render_base._clean_text
_svg_end = primitives_domain._svg_end
_chart_number = primitives_domain._chart_number
_chart_card = primitives_domain._chart_card

def _normalize_er_data(data: dict[str, Any]) -> dict[str, Any]:
    entities_out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in data.get("entities") if isinstance(data.get("entities"), list) else []:
        if not isinstance(item, dict):
            continue
        name = _clean_text(item.get("name") or item.get("label") or "", max_chars=24)
        if not name or name in seen:
            continue
        seen.add(name)
        attrs_raw = item.get("attributes") if isinstance(item.get("attributes"), list) else []
        attrs = [_clean_text(attr, max_chars=22) for attr in attrs_raw[:8]]
        attrs = [attr for attr in attrs if attr]
        entities_out.append({"name": name, "attributes": attrs or ["id", "core_attribute"]})
    relations_out: list[dict[str, str]] = []
    entity_names = {entity["name"] for entity in entities_out}
    for item in data.get("relations") if isinstance(data.get("relations"), list) else []:
        if not isinstance(item, dict):
            continue
        left = _clean_text(item.get("left"), max_chars=24)
        right = _clean_text(item.get("right"), max_chars=24)
        if not left or not right or left not in entity_names or right not in entity_names:
            continue
        relations_out.append(
            {
                "left": left,
                "right": right,
                "label": _clean_text(item.get("label"), max_chars=20),
                "cardinality": _clean_text(item.get("cardinality"), max_chars=12),
            }
        )
    if len(entities_out) < 2:
        entities_out = [
            {"name": "EntityA", "attributes": ["id", "core_attribute"]},
            {"name": "EntityB", "attributes": ["id", "core_attribute"]},
        ]
    if not relations_out:
        relations_out = [{"left": entities_out[0]["name"], "right": entities_out[1]["name"], "label": "relates", "cardinality": "1:N"}]
    return {"entities": entities_out, "relations": relations_out}

def _cardinality_parts(cardinality: str) -> tuple[str, str]:
    raw = str(cardinality or "").strip().replace("..", ":").replace("-", ":")
    if not raw:
        return "", ""
    if ":" in raw:
        left, right = raw.split(":", 1)
        return left.strip().upper(), right.strip().upper()
    token = raw.strip().upper()
    return token, token

def _cardinality_marker(kind: str, x: float, y: float, direction: int) -> str:
    stroke = "#556B7D"
    if kind in {"1", "ONE"}:
        x1 = x - direction * 8
        x2 = x + direction * 8
        return f'<line class="crow-one" x1="{x1:.1f}" y1="{y-10:.1f}" x2="{x2:.1f}" y2="{y+10:.1f}" stroke="{stroke}" stroke-width="1.8"/>'
    if kind in {"0", "O", "ZERO", "OPTIONAL"}:
        return f'<circle class="crow-zero" cx="{x:.1f}" cy="{y:.1f}" r="6.0" fill="#FFFFFF" stroke="{stroke}" stroke-width="1.6"/>'
    if kind in {"N", "M", "MANY", "*"}:
        a = x - direction * 12
        b = x + direction * 4
        return (
            f'<path class="crow-many" d="M {a:.1f} {y-10:.1f} L {b:.1f} {y:.1f} L {a:.1f} {y+10:.1f}" '
            f'fill="none" stroke="{stroke}" stroke-width="1.8" stroke-linejoin="round"/>'
        )
    return ""

def render_professional_er_svg(caption: str, data: dict[str, Any]) -> str:
    normalized = _normalize_er_data(data if isinstance(data, dict) else {})
    entities = list(normalized.get("entities") or [])
    relations = list(normalized.get("relations") or [])
    cols = 2 if len(entities) <= 4 else 3
    width = 1120 if cols == 3 else 980
    card_w = 280 if cols == 3 else 320
    gap_x = 34
    row_heights: list[int] = []
    for entity in entities:
        attr_count = max(2, min(6, len(entity.get("attributes") or [])))
        row_heights.append(72 + attr_count * 24)
    max_card_h = max(row_heights) if row_heights else 180
    rows = max(1, math.ceil(len(entities) / cols))
    height = 120 + rows * (max_card_h + 42)
    start_x = (width - (cols * card_w + (cols - 1) * gap_x)) / 2
    out = _chart_card(width, height, caption or "ER Diagram")
    positions: dict[str, dict[str, float]] = {}
    for idx, entity in enumerate(entities):
        row = idx // cols
        col = idx % cols
        attrs = list(entity.get("attributes") or [])[:6]
        card_h = 72 + max(2, len(attrs)) * 24
        x = start_x + col * (card_w + gap_x)
        y = 82 + row * (max_card_h + 42)
        cx = x + card_w / 2
        positions[str(entity["name"])] = {"x": x, "y": y, "w": card_w, "h": card_h, "cx": cx, "cy": y + card_h / 2}
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{card_w:.1f}" height="{card_h:.1f}" rx="18" ry="18" fill="#F7FAFC" stroke="#8FA7BD" stroke-width="1.5"/>')
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{card_w:.1f}" height="48" rx="18" ry="18" fill="#EAF2FB" stroke="#8FA7BD" stroke-width="1.2"/>')
        out.append(f'<text x="{cx:.1f}" y="{y+30:.1f}" text-anchor="middle" class="label">{html.escape(str(entity["name"]))}</text>')
        out.append(f'<line x1="{x+16:.1f}" y1="{y+56:.1f}" x2="{x+card_w-16:.1f}" y2="{y+56:.1f}" stroke="#C6D4E2" stroke-width="1.0"/>')
        for attr_idx, attr in enumerate(attrs or ["core_attribute"]):
            yy = y + 82 + attr_idx * 24
            bullet_fill = "#A66A3F" if attr_idx == 0 else "#7C8EA2"
            out.append(f'<circle cx="{x+22:.1f}" cy="{yy-4:.1f}" r="3.2" fill="{bullet_fill}"/>')
            out.append(f'<text x="{x+34:.1f}" y="{yy:.1f}" text-anchor="start" class="small">{html.escape(str(attr))}</text>')
    for rel in relations:
        left = positions.get(str(rel.get("left") or ""))
        right = positions.get(str(rel.get("right") or ""))
        if not left or not right:
            continue
        x1 = left["x"] + left["w"]
        y1 = left["cy"]
        x2 = right["x"]
        y2 = right["cy"]
        midx = (x1 + x2) / 2
        path = f"M {x1:.1f} {y1:.1f} C {midx:.1f} {y1:.1f}, {midx:.1f} {y2:.1f}, {x2:.1f} {y2:.1f}"
        out.append(f'<path d="{path}" fill="none" stroke="#556B7D" stroke-width="2.0"/>')
        left_card, right_card = _cardinality_parts(str(rel.get("cardinality") or ""))
        if left_card:
            out.append(_cardinality_marker(left_card, x1 + 10, y1, direction=1))
        if right_card:
            out.append(_cardinality_marker(right_card, x2 - 10, y2, direction=-1))
        out.append(f'<line x1="{x2-10:.1f}" y1="{y2:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#556B7D" stroke-width="1.8" marker-end="url(#arrow-solid)"/>')
        relation_label = str(rel.get("label") or "").strip()
        cardinality = str(rel.get("cardinality") or "").strip()
        label = " ".join([part for part in [relation_label, cardinality] if part]).strip()
        if label:
            pill_w = max(74, min(190, 28 + len(label) * 11))
            ly = (y1 + y2) / 2 - 8
            out.append(f'<rect x="{midx-pill_w/2:.1f}" y="{ly-12:.1f}" width="{pill_w:.1f}" height="22" rx="11" ry="11" fill="#FFFFFF" stroke="#D4DCE4" stroke-width="0.9"/>')
            out.append(f'<text x="{midx:.1f}" y="{ly+3:.1f}" text-anchor="middle" class="small">{html.escape(label)}</text>')
    out.append(_svg_end())
    return "".join(out)

__all__ = [name for name in globals() if not name.startswith('__')]
