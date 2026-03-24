"""Chart and timeline SVG renderers."""

from __future__ import annotations

import html
import math
from typing import Any

from writing_agent.v2 import diagram_design_render_domain as render_base
from writing_agent.v2 import diagram_design_svg_primitives_domain as primitives_domain

_clean_text = render_base._clean_text
_wrap_text = primitives_domain._wrap_text
_svg_end = primitives_domain._svg_end
_multiline_text = primitives_domain._multiline_text
_chart_number = primitives_domain._chart_number
_chart_card = primitives_domain._chart_card

def render_professional_bar_svg(caption: str, data: dict[str, Any]) -> str:
    labels = [_clean_text(item, max_chars=20) for item in (data.get("labels") if isinstance(data.get("labels"), list) else [])[:10]]
    labels = [item for item in labels if item]
    raw_values = (data.get("values") if isinstance(data.get("values"), list) else [])[:10]
    values: list[float] = []
    for item in raw_values:
        try:
            values.append(float(item))
        except Exception:
            values.append(0.0)
    if min(len(labels), len(values)) < 2:
        labels = ["EntityA", "EntityB", "??C", "??D"]
        values = [18, 26, 22, 31]
    n = min(len(labels), len(values))
    labels = labels[:n]
    values = values[:n]
    width = 980
    height = 520
    left = 90
    top = 100
    plot_w = width - 160
    plot_h = 320
    max_v = max(values) if values else 1.0
    max_v = max(1.0, max_v)
    out = _chart_card(width, height, caption or "Bar Chart")
    out.append(f'<rect x="{left:.1f}" y="{top:.1f}" width="{plot_w:.1f}" height="{plot_h:.1f}" fill="#F8FAFC" stroke="#D6DEE6" stroke-width="1.0" rx="14" ry="14"/>')
    for grid in range(6):
        gy = top + plot_h - grid * (plot_h / 5)
        value = max_v * grid / 5
        out.append(f'<line x1="{left:.1f}" y1="{gy:.1f}" x2="{left+plot_w:.1f}" y2="{gy:.1f}" stroke="#DCE4EC" stroke-width="1.0"/>')
        out.append(f'<text x="{left-12:.1f}" y="{gy+4:.1f}" text-anchor="end" class="small">{html.escape(_chart_number(value))}</text>')
    step = plot_w / max(1, n)
    bar_w = min(70, step * 0.56)
    colors = ["#8EB7D9", "#5B8A61", "#A66A3F", "#7C8EA2", "#A97A12"]
    for idx, (label, value) in enumerate(zip(labels, values, strict=False)):
        x = left + idx * step + (step - bar_w) / 2
        bar_h = (value / max_v) * (plot_h - 12)
        y = top + plot_h - bar_h
        out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" rx="12" ry="12" fill="{colors[idx % len(colors)]}" opacity="0.88"/>')
        out.append(f'<text x="{x+bar_w/2:.1f}" y="{y-8:.1f}" text-anchor="middle" class="small">{html.escape(_chart_number(value))}</text>')
        label_lines = _wrap_text(label, max_units=10.5, max_lines=2)
        out.append(_multiline_text(x + bar_w / 2, top + plot_h + 24, label_lines, css_class="small", anchor="middle", line_gap=14))
    out.append(_svg_end())
    return "".join(out)

def render_professional_line_svg(caption: str, data: dict[str, Any]) -> str:
    labels = [_clean_text(item, max_chars=20) for item in (data.get("labels") if isinstance(data.get("labels"), list) else [])[:16]]
    labels = [item for item in labels if item]
    series_raw = data.get("series") if isinstance(data.get("series"), list) else []
    series: list[dict[str, Any]] = []
    for item in series_raw[:3]:
        if not isinstance(item, dict):
            continue
        name = _clean_text(item.get("name") or "Series", max_chars=18)
        vals: list[float] = []
        for raw in (item.get("values") if isinstance(item.get("values"), list) else [])[:16]:
            try:
                vals.append(float(raw))
            except Exception:
                vals.append(0.0)
        if len(vals) >= 2:
            series.append({"name": name or "Series", "values": vals})
    if not series:
        labels = labels or ["T1", "T2", "T3", "T4", "T5"]
        series = [{"name": "EntityA", "values": [12, 18, 20, 24, 29]}, {"name": "EntityB", "values": [8, 10, 14, 17, 21]}]
    if not labels:
        labels = [f"T{i+1}" for i in range(max(len(s['values']) for s in series))]
    target_len = min(len(labels), min(len(s["values"]) for s in series))
    labels = labels[:target_len]
    for item in series:
        item["values"] = item["values"][:target_len]
    width = 980
    height = 520
    left = 92
    top = 96
    plot_w = width - 170
    plot_h = 320
    all_vals = [value for item in series for value in item["values"]]
    min_v = min(all_vals) if all_vals else 0.0
    max_v = max(all_vals) if all_vals else 1.0
    if math.isclose(min_v, max_v):
        max_v = min_v + 1.0
    out = _chart_card(width, height, caption or "Line Chart")
    out.append(f'<rect x="{left:.1f}" y="{top:.1f}" width="{plot_w:.1f}" height="{plot_h:.1f}" fill="#F8FAFC" stroke="#D6DEE6" stroke-width="1.0" rx="14" ry="14"/>')
    for grid in range(6):
        gy = top + plot_h - grid * (plot_h / 5)
        value = min_v + (max_v - min_v) * grid / 5
        out.append(f'<line x1="{left:.1f}" y1="{gy:.1f}" x2="{left+plot_w:.1f}" y2="{gy:.1f}" stroke="#DCE4EC" stroke-width="1.0"/>')
        out.append(f'<text x="{left-12:.1f}" y="{gy+4:.1f}" text-anchor="end" class="small">{html.escape(_chart_number(value))}</text>')
    colors = ["#2D5F8B", "#A66A3F", "#5B8A61"]
    for idx, item in enumerate(series):
        coords: list[tuple[float, float]] = []
        for point_idx, value in enumerate(item["values"]):
            x = left + (point_idx / max(1, target_len - 1)) * plot_w
            y = top + (1 - (value - min_v) / (max_v - min_v)) * plot_h
            coords.append((x, y))
        if not coords:
            continue
        path = " M ".join([f"{x:.1f} {y:.1f}" if i == 0 else f"L {x:.1f} {y:.1f}" for i, (x, y) in enumerate(coords)])
        out.append(f'<path d="M {path}" fill="none" stroke="{colors[idx % len(colors)]}" stroke-width="3.0" stroke-linejoin="round" stroke-linecap="round"/>')
        for x, y in coords:
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" fill="#FFFFFF" stroke="{colors[idx % len(colors)]}" stroke-width="2.0"/>')
        legend_x = left + plot_w + 24
        legend_y = top + 28 + idx * 28
        out.append(f'<line x1="{legend_x:.1f}" y1="{legend_y:.1f}" x2="{legend_x+26:.1f}" y2="{legend_y:.1f}" stroke="{colors[idx % len(colors)]}" stroke-width="3.0"/>')
        out.append(f'<circle cx="{legend_x+13:.1f}" cy="{legend_y:.1f}" r="4.2" fill="#FFFFFF" stroke="{colors[idx % len(colors)]}" stroke-width="2.0"/>')
        out.append(f'<text x="{legend_x+34:.1f}" y="{legend_y+4:.1f}" text-anchor="start" class="small">{html.escape(str(item["name"]))}</text>')
    for idx, label in enumerate(labels):
        x = left + (idx / max(1, target_len - 1)) * plot_w
        out.append(f'<line x1="{x:.1f}" y1="{top+plot_h:.1f}" x2="{x:.1f}" y2="{top+plot_h+6:.1f}" stroke="#A9B6C3" stroke-width="1.0"/>')
        out.append(_multiline_text(x, top + plot_h + 24, _wrap_text(label, max_units=10.5, max_lines=2), css_class="small", anchor="middle", line_gap=14))
    out.append(_svg_end())
    return "".join(out)

def render_professional_pie_svg(caption: str, data: dict[str, Any]) -> str:
    raw_segments = data.get("segments") if isinstance(data.get("segments"), list) else []
    segments: list[tuple[str, float]] = []
    for item in raw_segments[:8]:
        if not isinstance(item, dict):
            continue
        label = _clean_text(item.get("label"), max_chars=20)
        try:
            value = float(item.get("value"))
        except Exception:
            value = 0.0
        if label:
            segments.append((label, max(0.0, value)))
    if len(segments) < 2:
        segments = [("EntityA", 34.0), ("EntityB", 27.0), ("??C", 21.0), ("??D", 18.0)]
    total = sum(value for _, value in segments) or 1.0
    width = 980
    height = 520
    cx = 300
    cy = 280
    r = 138
    inner_r = 68
    colors = ["#2D5F8B", "#5B8A61", "#A66A3F", "#A97A12", "#7C8EA2", "#8C6BB1"]
    out = _chart_card(width, height, caption or "Pie Chart")
    out.append('<rect x="74" y="96" width="460" height="320" fill="#F8FAFC" stroke="#D6DEE6" stroke-width="1.0" rx="16" ry="16"/>')
    angle = -math.pi / 2
    for idx, (_label, value) in enumerate(segments):
        frac = value / total
        end = angle + frac * math.pi * 2
        x1 = cx + r * math.cos(angle)
        y1 = cy + r * math.sin(angle)
        x2 = cx + r * math.cos(end)
        y2 = cy + r * math.sin(end)
        large = 1 if (end - angle) > math.pi else 0
        arc = f'M {cx:.1f},{cy:.1f} L {x1:.1f},{y1:.1f} A {r:.1f},{r:.1f} 0 {large} 1 {x2:.1f},{y2:.1f} Z'
        out.append(f'<path d="{arc}" fill="{colors[idx % len(colors)]}" opacity="0.92" stroke="#FFFFFF" stroke-width="2.0"/>')
        angle_mid = (angle + end) / 2
        label_x = cx + (r + 26) * math.cos(angle_mid)
        label_y = cy + (r + 26) * math.sin(angle_mid)
        pct = f"{frac*100:.1f}%"
        out.append(f'<text x="{label_x:.1f}" y="{label_y:.1f}" text-anchor="middle" class="small">{html.escape(pct)}</text>')
        angle = end
    out.append(f'<circle cx="{cx}" cy="{cy}" r="{inner_r}" fill="#FFFFFF" stroke="#E4EAF0" stroke-width="1.2"/>')
    out.append(f'<text x="{cx:.1f}" y="{cy-4:.1f}" text-anchor="middle" class="label">{html.escape(_chart_number(total))}</text>')
    out.append(f'<text x="{cx:.1f}" y="{cy+18:.1f}" text-anchor="middle" class="small">Total</text>')
    legend_x = 590
    legend_y = 140
    for idx, (label, value) in enumerate(segments):
        y = legend_y + idx * 34
        pct = value / total * 100
        out.append(f'<rect x="{legend_x:.1f}" y="{y-11:.1f}" width="16" height="16" rx="4" ry="4" fill="{colors[idx % len(colors)]}"/>')
        out.append(f'<text x="{legend_x+28:.1f}" y="{y+2:.1f}" text-anchor="start" class="small">{html.escape(label)}</text>')
        out.append(f'<text x="{legend_x+220:.1f}" y="{y+2:.1f}" text-anchor="end" class="small">{html.escape(_chart_number(value))} / {pct:.1f}%</text>')
    out.append(_svg_end())
    return "".join(out)

def render_professional_timeline_svg(caption: str, data: dict[str, Any]) -> str:
    raw_events = data.get("events") if isinstance(data.get("events"), list) else []
    events: list[dict[str, str]] = []
    for item in raw_events[:8]:
        if not isinstance(item, dict):
            continue
        tm = _clean_text(item.get("time"), max_chars=16)
        label = _clean_text(item.get("label"), max_chars=30)
        if tm and label:
            events.append({"time": tm, "label": label})
    if len(events) < 2:
        events = [
            {"time": "Stage 1", "label": "Problem Scoping"},
            {"time": "Stage 2", "label": "Evidence Collection"},
            {"time": "Stage 3", "label": "Analysis and Discussion"},
            {"time": "Stage 4", "label": "Conclusion and Delivery"},
        ]
    width = 1120
    height = 460
    left = 90
    right = width - 90
    axis_y = 250
    out = _chart_card(width, height, caption or "Timeline")
    out.append(f'<line x1="{left:.1f}" y1="{axis_y:.1f}" x2="{right:.1f}" y2="{axis_y:.1f}" stroke="#6D8297" stroke-width="3.0"/>')
    count = len(events)
    for idx, event in enumerate(events):
        x = left + (idx / max(1, count - 1)) * (right - left)
        up = idx % 2 == 0
        box_y = 112 if up else 286
        out.append(f'<line x1="{x:.1f}" y1="{axis_y:.1f}" x2="{x:.1f}" y2="{box_y + (62 if up else -10):.1f}" stroke="#9FB0C1" stroke-width="1.4" stroke-dasharray="4,4"/>')
        out.append(f'<circle cx="{x:.1f}" cy="{axis_y:.1f}" r="8" fill="#FFFFFF" stroke="#2D5F8B" stroke-width="3.0"/>')
        out.append(f'<rect x="{x-92:.1f}" y="{box_y:.1f}" width="184" height="62" rx="16" ry="16" fill="#F8FAFC" stroke="#D6DEE6" stroke-width="1.0"/>')
        out.append(f'<rect x="{x-76:.1f}" y="{box_y+10:.1f}" width="72" height="18" rx="9" ry="9" fill="#EAF2FB" stroke="#C7D3DF" stroke-width="0.8"/>')
        out.append(f'<text x="{x-40:.1f}" y="{box_y+23:.1f}" text-anchor="middle" class="small">{html.escape(str(event["time"]))}</text>')
        out.append(_multiline_text(x, box_y + 42, _wrap_text(str(event["label"]), max_units=14.0, max_lines=2), css_class="small", anchor="middle", line_gap=14))
    out.append(_svg_end())
    return "".join(out)

__all__ = [name for name in globals() if not name.startswith('__')]
