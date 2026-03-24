"""Figure quality semantic scoring helpers."""

from __future__ import annotations

from typing import Any

from writing_agent.v2.diagram_design import enrich_figure_spec, extract_semantic_tokens, infer_preferred_diagram_kind
from writing_agent.v2 import figure_render_quality_data_domain as data_domain


def _figure_semantic_text(kind: str, data: dict) -> str:
    payload = data if isinstance(data, dict) else {}
    chunks: list[str] = []
    if kind in {"flow", "flowchart", "architecture"}:
        for node in data_domain._as_list_safe(payload.get("nodes")):
            if isinstance(node, dict):
                chunks.extend([str(node.get("label") or node.get("text") or ""), str(node.get("subtitle") or "")])
        for edge in data_domain._as_list_safe(payload.get("edges")):
            if isinstance(edge, dict):
                chunks.append(str(edge.get("label") or edge.get("text") or ""))
    elif kind == "sequence":
        chunks.extend([str(item) for item in data_domain._as_list_safe(payload.get("participants"))])
        for msg in data_domain._as_list_safe(payload.get("messages")):
            if isinstance(msg, dict):
                chunks.append(str(msg.get("label") or msg.get("text") or ""))
    elif kind == "er":
        for entity in data_domain._as_list_safe(payload.get("entities")):
            if isinstance(entity, dict):
                chunks.append(str(entity.get("name") or ""))
                chunks.extend([str(attr) for attr in data_domain._as_list_safe(entity.get("attributes"))])
        for rel in data_domain._as_list_safe(payload.get("relations")):
            if isinstance(rel, dict):
                chunks.extend([str(rel.get("label") or ""), str(rel.get("cardinality") or "")])
    elif kind == "bar":
        chunks.extend([str(item) for item in data_domain._as_list_safe(payload.get("labels"))])
    elif kind == "line":
        chunks.extend([str(item) for item in data_domain._as_list_safe(payload.get("labels"))])
        for row in data_domain._as_list_safe(payload.get("series")):
            if isinstance(row, dict):
                chunks.append(str(row.get("name") or ""))
    elif kind == "pie":
        for seg in data_domain._as_list_safe(payload.get("segments")):
            if isinstance(seg, dict):
                chunks.append(str(seg.get("label") or ""))
    elif kind == "timeline":
        for event in data_domain._as_list_safe(payload.get("events")):
            if isinstance(event, dict):
                chunks.extend([str(event.get("time") or ""), str(event.get("label") or "")])
    return " ".join(part for part in chunks if str(part or "").strip())


def _score_render_output(*, svg: str, png_rendered: bool) -> tuple[int, list[str]]:
    issues: list[str] = []
    score = 0
    svg_text = str(svg or "")
    if svg_text.startswith("<svg") and len(svg_text) >= 200:
        score += 10
    elif svg_text:
        issues.append("svg_too_small")
        score += 5
    else:
        issues.append("svg_missing")
    if png_rendered:
        score += 5
    elif data_domain._figure_render_module().figure_png_renderer_available():
        issues.append("png_not_rendered")
        score += 1
    return min(15, score), issues


def _score_grade(score: int) -> str:
    if score >= 85:
        return "A"
    if score >= 70:
        return "B"
    if score >= 55:
        return "C"
    return "D"


def _score_caption_consistency(kind: str, caption: str, data: dict, issues: list[str]) -> int:
    expected_kind = infer_preferred_diagram_kind(caption)
    semantic_text = _figure_semantic_text(kind, data)
    caption_tokens = set(extract_semantic_tokens(caption))
    data_tokens = set(extract_semantic_tokens(semantic_text))
    score = 6
    if expected_kind:
        if expected_kind == kind:
            score += 5
        elif expected_kind in {"bar", "line", "pie"} and kind in {"bar", "line", "pie"}:
            score += 2
            issues.append("caption_kind_near_mismatch")
        else:
            score = max(0, score - 4)
            issues.append("caption_kind_mismatch")
    if caption_tokens and data_tokens:
        overlap = caption_tokens & data_tokens
        if overlap:
            score += 4
        elif len(caption_tokens) >= 2 and len(data_tokens) >= 2:
            score = max(0, score - 3)
            issues.append("caption_data_low_overlap")
    return max(0, min(15, score))


def score_figure_spec(spec: dict, *, svg: str = "", png_rendered: bool = False) -> dict[str, Any]:
    spec = enrich_figure_spec(spec if isinstance(spec, dict) else {})
    kind = data_domain._normalize_figure_type(spec)
    caption = str((spec or {}).get("caption") or "").strip()
    data = (spec or {}).get("data") or {}
    issues: list[str] = []
    type_score = data_domain._score_supported_type(kind, issues)
    caption_score = data_domain._score_caption(caption, issues)
    data_score = data_domain._score_figure_data(kind, data if isinstance(data, dict) else {}, issues)
    consistency_score = _score_caption_consistency(kind, caption, data if isinstance(data, dict) else {}, issues)
    render_score, render_issues = _score_render_output(svg=str(svg or ""), png_rendered=bool(png_rendered))
    issues.extend(render_issues)
    score = max(0, min(100, type_score + caption_score + data_score + render_score + consistency_score))
    grade = _score_grade(score)
    recommendation = "keep" if score >= 75 else ("review" if score >= 55 else "drop")
    return {
        "score": int(score),
        "grade": grade,
        "passed": bool(score >= 60),
        "recommendation": recommendation,
        "breakdown": {
            "type": int(type_score),
            "caption": int(caption_score),
            "data": int(data_score),
            "consistency": int(consistency_score),
            "render": int(render_score),
        },
        "issues": sorted({str(x).strip() for x in issues if str(x).strip()}),
    }


__all__ = [name for name in globals() if not name.startswith("__")]
