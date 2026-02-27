"""Figure Render module.

This module belongs to `writing_agent.v2` in the writing-agent codebase.
"""

from __future__ import annotations

import html
import json
import math
import re
from dataclasses import dataclass

from writing_agent.diagrams import render_er_svg, render_flowchart_svg
from writing_agent.diagrams.spec import (
    DiagramSpec,
    ErEntity,
    ErRelation,
    ErSpec,
    FlowEdge,
    FlowNode,
    FlowchartSpec,
)


def render_figure_svg(spec: dict) -> tuple[str, str]:
    t = str((spec or {}).get("type") or "").strip().lower()
    caption = str((spec or {}).get("caption") or "").strip()
    data = (spec or {}).get("data") or {}

    if t in {"flow", "flowchart"}:
        ds = _to_flowchart(data, caption=caption)
        return render_flowchart_svg(ds), ds.caption
    if t == "er":
        ds = _to_er(data, caption=caption)
        return render_er_svg(ds), ds.caption
    if t in {"bar", "bar_chart"}:
        return _render_bar_svg(data, caption=caption), caption or "柱状图"
    if t in {"line", "line_chart"}:
        return _render_line_svg(data, caption=caption), caption or "折线图"
    if t in {"pie", "pie_chart"}:
        return _render_pie_svg(data, caption=caption), caption or "饼图"
    if t in {"timeline"}:
        return _render_timeline_svg(data, caption=caption), caption or "时间线"
    if t in {"sequence", "sequence_diagram"}:
        return _render_sequence_svg(data, caption=caption), caption or "时序图"

    # fallback: render a framed placeholder
    return _render_placeholder_svg(caption or f"Figure({t or 'unknown'})"), caption or "图"


def _to_flowchart(data: dict, caption: str) -> DiagramSpec:
    nodes_in = (data or {}).get("nodes") or []
    edges_in = (data or {}).get("edges") or []

    nodes: list[FlowNode] = []
    for i, n in enumerate(nodes_in[:12]):
        if isinstance(n, dict):
            nid = str(n.get("id") or f"n{i+1}").strip()
            text = str(n.get("text") or "").strip() or f"步骤{i+1}"
        else:
            nid = f"n{i+1}"
            text = str(n).strip() or f"步骤{i+1}"
        nodes.append(FlowNode(id=nid, text=text[:28]))
    if not nodes:
        # derive from caption
        parts = [p.strip() for p in re.split(r"\s*(?:->|→|=>)\s*", caption or "") if p.strip()]
        nodes = [FlowNode(id=f"n{i+1}", text=p[:28]) for i, p in enumerate(parts[:10])] or [FlowNode(id="n1", text="开始")]

    edges: list[FlowEdge] = []
    for e in edges_in[:24]:
        if not isinstance(e, dict):
            continue
        src = str(e.get("src") or "").strip()
        dst = str(e.get("dst") or "").strip()
        if not src or not dst:
            continue
        edges.append(FlowEdge(src=src, dst=dst, label=str(e.get("label") or "").strip()[:18]))
    if not edges and len(nodes) > 1:
        edges = [FlowEdge(src=f"n{i+1}", dst=f"n{i+2}") for i in range(len(nodes) - 1)]

    return DiagramSpec(
        type="flowchart",
        title="Flowchart",
        caption=caption or "流程图",
        flowchart=FlowchartSpec(nodes=nodes, edges=edges),
    )


def _to_er(data: dict, caption: str) -> DiagramSpec:
    entities_in = (data or {}).get("entities") or []
    relations_in = (data or {}).get("relations") or []

    entities: list[ErEntity] = []
    for e in entities_in[:8]:
        if not isinstance(e, dict):
            continue
        name = str(e.get("name") or "").strip()
        if not name:
            continue
        attrs = [str(a) for a in (e.get("attributes") or [])[:10]]
        entities.append(ErEntity(name=name[:20], attributes=attrs or ["[待补充]"]))
    if len(entities) < 2:
        entities = [ErEntity(name="EntityA", attributes=["[待补充]"]), ErEntity(name="EntityB", attributes=["[待补充]"])]

    relations: list[ErRelation] = []
    for r in relations_in[:12]:
        if not isinstance(r, dict):
            continue
        left = str(r.get("left") or "").strip()
        right = str(r.get("right") or "").strip()
        if not left or not right:
            continue
        relations.append(
            ErRelation(
                left=left[:20],
                right=right[:20],
                label=str(r.get("label") or "").strip()[:18],
                cardinality=str(r.get("cardinality") or "").strip()[:10],
            )
        )
    if not relations:
        relations = [ErRelation(left=entities[0].name, right=entities[1].name, label="[待补充]", cardinality="")]

    return DiagramSpec(type="er", title="ER Diagram", caption=caption or "ER图", er=ErSpec(entities=entities, relations=relations))


def _svg_wrap(inner: str, w: int, h: int, label: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'role="img" aria-label="{html.escape(label)}">'
        '<rect x="0" y="0" width="100%" height="100%" fill="rgba(10,14,26,0.18)"/>'
        + inner
        + "</svg>"
    )


def _text(x: float, y: float, s: str, size: int = 12, anchor: str = "start", fill: str = "#E7ECFF") -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-size="{size}" '
        f'fill="{fill}" font-family="ui-sans-serif,system-ui,Segoe UI,Arial">{html.escape(s or "")}</text>'
    )


def _render_placeholder_svg(caption: str, w: int = 760, h: int = 220) -> str:
    inner = (
        '<rect x="18" y="18" width="724" height="184" rx="14" ry="14" '
        'fill="rgba(18,25,45,0.55)" stroke="rgba(255,255,255,0.14)" stroke-width="1"/>'
        + _text(w / 2, h / 2, caption or "Figure", size=14, anchor="middle", fill="#A9C5FF")
    )
    return _svg_wrap(inner, w, h, caption or "figure")


def _as_list(x):
    return x if isinstance(x, list) else []


def _render_bar_svg(data: dict, caption: str, w: int = 760, h: int = 320) -> str:
    labels = [str(x) for x in _as_list((data or {}).get("labels"))][:12]
    values = _as_list((data or {}).get("values"))[:12]
    vals: list[float] = []
    for v in values:
        try:
            vals.append(float(v))
        except Exception:
            vals.append(0.0)
    if not labels:
        labels = ["A", "B", "C", "D"]
    if not vals:
        vals = [1, 2, 3, 2]
    n = min(len(labels), len(vals))
    labels, vals = labels[:n], vals[:n]

    max_v = max(vals) if vals else 1
    max_v = max(1.0, max_v)

    pad = 44
    plot_w = w - pad * 2
    plot_h = h - pad * 2
    bar_w = plot_w / max(1, n) * 0.68
    gap = plot_w / max(1, n) * 0.32

    inner = []
    inner.append('<rect x="18" y="18" width="724" height="284" rx="14" ry="14" fill="rgba(18,25,45,0.45)" stroke="rgba(255,255,255,0.10)"/>')
    # axes
    inner.append(f'<line x1="{pad}" y1="{h-pad}" x2="{w-pad}" y2="{h-pad}" stroke="rgba(169,197,255,0.35)" />')
    inner.append(f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{h-pad}" stroke="rgba(169,197,255,0.35)" />')
    for i, (lab, v) in enumerate(zip(labels, vals)):
        x = pad + i * (bar_w + gap) + gap / 2
        bh = (v / max_v) * (plot_h - 10)
        y = h - pad - bh
        inner.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" rx="10" ry="10" '
            'fill="rgba(38,214,255,0.35)" stroke="rgba(38,214,255,0.65)" stroke-width="1"/>'
        )
        inner.append(_text(x + bar_w / 2, h - pad + 18, lab[:8], size=11, anchor="middle", fill="#D7DEFF"))
    if caption:
        inner.append(_text(w / 2, 34, caption, size=13, anchor="middle", fill="#A9C5FF"))
    return _svg_wrap("".join(inner), w, h, caption or "bar chart")


def _render_line_svg(data: dict, caption: str, w: int = 760, h: int = 320) -> str:
    labels = [str(x) for x in _as_list((data or {}).get("labels"))][:24]
    series = (data or {}).get("series") or {}
    if isinstance(series, dict):
        name = str(series.get("name") or "S1")
        values = _as_list(series.get("values"))
        series_list = [{"name": name, "values": values}]
    elif isinstance(series, list):
        series_list = series[:3]
    else:
        series_list = []

    if not labels:
        labels = ["1", "2", "3", "4", "5"]
    if not series_list:
        series_list = [{"name": "S1", "values": [1, 2, 3, 2, 4]}]

    n = len(labels)
    pad = 44
    plot_w = w - pad * 2
    plot_h = h - pad * 2

    all_vals: list[float] = []
    norm_series: list[tuple[str, list[float]]] = []
    for s in series_list[:3]:
        if not isinstance(s, dict):
            continue
        nm = str(s.get("name") or "S")[:10]
        vals_in = _as_list(s.get("values"))[:n]
        vals: list[float] = []
        for v in vals_in:
            try:
                vals.append(float(v))
            except Exception:
                vals.append(0.0)
        if len(vals) < n:
            vals.extend([0.0] * (n - len(vals)))
        all_vals.extend(vals)
        norm_series.append((nm, vals))
    if not norm_series:
        norm_series = [("S1", [1, 2, 3, 2, 4])]
        all_vals = norm_series[0][1]

    min_v = min(all_vals) if all_vals else 0.0
    max_v = max(all_vals) if all_vals else 1.0
    if math.isclose(max_v, min_v):
        max_v = min_v + 1.0

    def xy(i: int, v: float) -> tuple[float, float]:
        x = pad + (i / max(1, n - 1)) * plot_w
        y = pad + (1 - (v - min_v) / (max_v - min_v)) * plot_h
        return x, y

    colors = ["rgba(38,214,255,0.85)", "rgba(124,92,255,0.85)", "rgba(255,77,109,0.85)"]
    inner = []
    inner.append('<rect x="18" y="18" width="724" height="284" rx="14" ry="14" fill="rgba(18,25,45,0.45)" stroke="rgba(255,255,255,0.10)"/>')
    inner.append(f'<line x1="{pad}" y1="{h-pad}" x2="{w-pad}" y2="{h-pad}" stroke="rgba(169,197,255,0.35)" />')
    inner.append(f'<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{h-pad}" stroke="rgba(169,197,255,0.35)" />')

    for si, (nm, vals) in enumerate(norm_series):
        pts = [xy(i, vals[i]) for i in range(n)]
        d = "M " + " L ".join([f"{x:.1f},{y:.1f}" for x, y in pts])
        inner.append(f'<path d="{d}" fill="none" stroke="{colors[si % len(colors)]}" stroke-width="3" />')
        for x, y in pts:
            inner.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{colors[si % len(colors)]}" />')
        inner.append(_text(w - pad - 8, pad + 18 + si * 16, nm, size=11, anchor="end", fill="#D7DEFF"))

    for i, lab in enumerate(labels[:10]):
        x = pad + (i / max(1, n - 1)) * plot_w
        inner.append(_text(x, h - pad + 18, lab[:6], size=10, anchor="middle", fill="#D7DEFF"))
    if caption:
        inner.append(_text(w / 2, 34, caption, size=13, anchor="middle", fill="#A9C5FF"))
    return _svg_wrap("".join(inner), w, h, caption or "line chart")


def _render_pie_svg(data: dict, caption: str, w: int = 760, h: int = 320) -> str:
    segs = _as_list((data or {}).get("segments"))[:10]
    if not segs:
        segs = [{"label": "A", "value": 40}, {"label": "B", "value": 30}, {"label": "C", "value": 30}]
    items: list[tuple[str, float]] = []
    for s in segs:
        if isinstance(s, dict):
            lab = str(s.get("label") or "")[:10] or "X"
            try:
                val = float(s.get("value") or 0)
            except Exception:
                val = 0.0
        else:
            lab = "X"
            val = 0.0
        items.append((lab, max(0.0, val)))
    total = sum(v for _, v in items) or 1.0

    cx, cy = w * 0.33, h * 0.56
    r = 110
    colors = ["rgba(38,214,255,0.65)", "rgba(124,92,255,0.65)", "rgba(255,77,109,0.65)", "rgba(255,212,93,0.65)"]

    def arc_path(start_a: float, end_a: float) -> str:
        x1 = cx + r * math.cos(start_a)
        y1 = cy + r * math.sin(start_a)
        x2 = cx + r * math.cos(end_a)
        y2 = cy + r * math.sin(end_a)
        large = 1 if (end_a - start_a) % (2 * math.pi) > math.pi else 0
        return f"M {cx:.1f},{cy:.1f} L {x1:.1f},{y1:.1f} A {r},{r} 0 {large} 1 {x2:.1f},{y2:.1f} Z"

    inner = []
    inner.append('<rect x="18" y="18" width="724" height="284" rx="14" ry="14" fill="rgba(18,25,45,0.45)" stroke="rgba(255,255,255,0.10)"/>')
    angle = -math.pi / 2
    for i, (lab, val) in enumerate(items):
        frac = val / total
        end = angle + frac * 2 * math.pi
        inner.append(f'<path d="{arc_path(angle, end)}" fill="{colors[i % len(colors)]}" stroke="rgba(255,255,255,0.10)"/>')
        angle = end
        inner.append(_text(w * 0.62, 96 + i * 18, f"{lab}  {int(frac*100)}%", size=11, anchor="start", fill="#D7DEFF"))
        inner.append(f'<rect x="{w*0.58:.1f}" y="{88 + i*18:.1f}" width="10" height="10" rx="2" fill="{colors[i % len(colors)]}"/>')
    if caption:
        inner.append(_text(w / 2, 34, caption, size=13, anchor="middle", fill="#A9C5FF"))
    return _svg_wrap("".join(inner), w, h, caption or "pie chart")


def _render_timeline_svg(data: dict, caption: str, w: int = 760, h: int = 260) -> str:
    events = _as_list((data or {}).get("events"))[:8]
    if not events:
        events = [{"time": "T1", "label": "事件1"}, {"time": "T2", "label": "事件2"}, {"time": "T3", "label": "事件3"}]
    items: list[tuple[str, str]] = []
    for e in events:
        if isinstance(e, dict):
            tm = str(e.get("time") or "")[:12] or "[待补充]"
            lab = str(e.get("label") or "")[:26] or "[待补充]"
            items.append((tm, lab))
    n = len(items) or 1
    pad = 50
    y = h * 0.55
    inner = []
    inner.append('<rect x="18" y="18" width="724" height="224" rx="14" ry="14" fill="rgba(18,25,45,0.45)" stroke="rgba(255,255,255,0.10)"/>')
    inner.append(f'<line x1="{pad}" y1="{y:.1f}" x2="{w-pad}" y2="{y:.1f}" stroke="rgba(169,197,255,0.45)" stroke-width="2"/>')
    for i, (tm, lab) in enumerate(items):
        x = pad + (i / max(1, n - 1)) * (w - 2 * pad)
        inner.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="6" fill="rgba(38,214,255,0.65)" stroke="rgba(38,214,255,0.95)" />')
        up = i % 2 == 0
        ty = y - 26 if up else y + 34
        inner.append(_text(x, ty, tm, size=11, anchor="middle", fill="#D7DEFF"))
        inner.append(_text(x, ty + 16, lab, size=11, anchor="middle", fill="#E7ECFF"))
        inner.append(f'<line x1="{x:.1f}" y1="{y:.1f}" x2="{x:.1f}" y2="{(y - 14) if up else (y + 14):.1f}" stroke="rgba(169,197,255,0.35)"/>')
    if caption:
        inner.append(_text(w / 2, 34, caption, size=13, anchor="middle", fill="#A9C5FF"))
    return _svg_wrap("".join(inner), w, h, caption or "timeline")


def _render_sequence_svg(data: dict, caption: str, w: int = 760, h: int = 360) -> str:
    parts = [str(p)[:12] for p in _as_list((data or {}).get("participants"))][:6]
    msgs = _as_list((data or {}).get("messages"))[:12]
    if not parts:
        parts = ["Client", "Server", "DB"]
    norm_msgs: list[tuple[str, str, str]] = []
    for m in msgs:
        if not isinstance(m, dict):
            continue
        src = str(m.get("from") or "").strip()
        dst = str(m.get("to") or "").strip()
        txt = str(m.get("text") or "").strip()[:28]
        if src and dst:
            norm_msgs.append((src, dst, txt or "[待补充]"))
    if not norm_msgs:
        norm_msgs = [(parts[0], parts[1], "request"), (parts[1], parts[2], "query"), (parts[2], parts[1], "result")]

    pad_x = 60
    top = 70
    bottom = h - 30
    n = len(parts)
    xs = [pad_x + (i / max(1, n - 1)) * (w - 2 * pad_x) for i in range(n)]
    pos = {p: xs[i] for i, p in enumerate(parts)}

    inner = []
    inner.append('<rect x="18" y="18" width="724" height="324" rx="14" ry="14" fill="rgba(18,25,45,0.45)" stroke="rgba(255,255,255,0.10)"/>')
    for p, x in zip(parts, xs):
        inner.append(_text(x, 52, p, size=12, anchor="middle", fill="#D7DEFF"))
        inner.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{bottom}" stroke="rgba(169,197,255,0.25)" stroke-dasharray="6,6"/>')

    y = top + 20
    for src, dst, txt in norm_msgs:
        x1 = pos.get(src, xs[0])
        x2 = pos.get(dst, xs[-1])
        arrow = "url(#arrow)"
        inner.append(_defs_arrow())
        inner.append(
            f'<line x1="{x1:.1f}" y1="{y:.1f}" x2="{x2:.1f}" y2="{y:.1f}" '
            f'marker-end="{arrow}" stroke="rgba(38,214,255,0.75)" stroke-width="2"/>'
        )
        inner.append(_text((x1 + x2) / 2, y - 6, txt, size=11, anchor="middle", fill="#E7ECFF"))
        y += 26

    if caption:
        inner.append(_text(w / 2, 34, caption, size=13, anchor="middle", fill="#A9C5FF"))
    return _svg_wrap("".join(inner), w, h, caption or "sequence")


def _defs_arrow() -> str:
    return (
        '<defs>'
        '<marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth">'
        '<path d="M0,0 L0,6 L9,3 z" fill="rgba(169,197,255,0.9)"/>'
        "</marker>"
        "</defs>"
    )


def safe_figure_spec_from_text(raw: str) -> dict:
    try:
        d = json.loads(raw)
        return d if isinstance(d, dict) else {"raw": raw}
    except Exception:
        return {"raw": raw}

