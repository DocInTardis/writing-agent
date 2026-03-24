"""Figure quality data scoring helpers."""

from __future__ import annotations

import re
from typing import Any


def _base():
    from writing_agent.v2 import figure_render_quality_domain as base

    return base


def _figure_render_module():
    return _base()._figure_render_module()


def _normalize_figure_type(spec: dict | None) -> str:
    return _base()._normalize_figure_type(spec)


def _slugify_figure_caption(text: str, *, fallback: str) -> str:
    value = _figure_render_module()._FILENAME_SANITIZE_RE.sub("_", str(text or "").strip())
    value = re.sub(r"_+", "_", value).strip("._")
    return (value or fallback)[:80]


def _is_generic_caption(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return False
    figure_render = _figure_render_module()
    if figure_render._GENERIC_CAPTION_RE.match(raw):
        return True
    normalized = re.sub(r"[\s_:\-\uFF1A]+", "", raw).casefold()
    for prefix in figure_render._GENERIC_CAPTION_PREFIXES:
        if normalized == prefix:
            return True
        if normalized.startswith(prefix) and normalized[len(prefix):].isdigit():
            return True
    return False


def _score_caption(caption: str, issues: list[str]) -> int:
    text = str(caption or "").strip()
    if not text:
        issues.append("missing_caption")
        return 4
    length = len(text)
    if 4 <= length <= 28:
        score = 20
    elif length <= 40:
        score = 16
    else:
        issues.append("caption_too_long")
        score = 13
    if _is_generic_caption(text):
        issues.append("generic_caption")
        score = min(score, 10)
    return min(20, score)


def _score_supported_type(kind: str, issues: list[str]) -> int:
    if kind in _figure_render_module()._SUPPORTED_FIGURE_TYPES:
        return 25
    issues.append("unsupported_type")
    return 6 if kind and kind != "figure" else 4


def _as_list_safe(value: object) -> list:
    return value if isinstance(value, list) else []


def _figure_payload_has_meaningful_data(kind: str, data: dict | None) -> bool:
    payload = data if isinstance(data, dict) else {}
    if kind in {"flow", "flowchart", "architecture"}:
        return len(_as_list_safe(payload.get("nodes"))) >= 2
    if kind == "er":
        return len(_as_list_safe(payload.get("entities"))) >= 2
    if kind == "bar":
        labels = _as_list_safe(payload.get("labels"))
        values = _as_list_safe(payload.get("values"))
        return min(len(labels), len(values)) >= 2 and len(labels) == len(values)
    if kind == "pie":
        segments = _as_list_safe(payload.get("segments"))
        if segments:
            valid = 0
            for item in segments:
                if isinstance(item, dict) and str(item.get("label") or "").strip() and item.get("value") is not None:
                    valid += 1
            return valid >= 2
        labels = _as_list_safe(payload.get("labels"))
        values = _as_list_safe(payload.get("values"))
        return min(len(labels), len(values)) >= 2 and len(labels) == len(values)
    if kind == "line":
        labels = _as_list_safe(payload.get("labels"))
        series = payload.get("series")
        if isinstance(series, dict):
            values_count = len(_as_list_safe(series.get("values")))
        elif isinstance(series, list):
            values_count = max((len(_as_list_safe((row or {}).get("values"))) for row in series if isinstance(row, dict)), default=0)
        else:
            values_count = 0
        return min(len(labels), values_count) >= 2
    if kind == "timeline":
        return len(_as_list_safe(payload.get("events"))) >= 2
    if kind == "sequence":
        return len(_as_list_safe(payload.get("participants"))) >= 2 and len(_as_list_safe(payload.get("messages"))) >= 1
    return False


def is_renderable_figure_spec(spec: dict | None) -> bool:
    payload = spec if isinstance(spec, dict) else {}
    kind = _normalize_figure_type(payload)
    if kind not in _figure_render_module()._SUPPORTED_FIGURE_TYPES:
        return False
    return _figure_payload_has_meaningful_data(kind, payload.get("data") if isinstance(payload, dict) else None)


def _score_figure_data(kind: str, data: dict, issues: list[str]) -> int:
    payload = data if isinstance(data, dict) else {}
    score = 0
    if kind in {"flow", "flowchart", "architecture"}:
        nodes = _as_list_safe(payload.get("nodes"))
        edges = _as_list_safe(payload.get("edges"))
        lanes = _as_list_safe(payload.get("lanes"))
        if len(nodes) >= 6:
            score += 30
        elif len(nodes) >= 4:
            score += 26
        elif len(nodes) >= 3:
            score += 20
        elif len(nodes) >= 2:
            score += 13
        else:
            issues.append("flow_nodes_insufficient")
            score += 5
        if len(edges) >= max(1, len(nodes) - 1):
            score += 10
        elif edges:
            score += 6
        else:
            issues.append("flow_edges_missing")
            score += 3
        node_labels: list[str] = []
        node_kinds: set[str] = set()
        subtitle_count = 0
        for node in nodes:
            if isinstance(node, dict):
                label = str(node.get("text") or node.get("label") or node.get("name") or "").strip()
                node_kind = str(node.get("kind") or "").strip().lower()
                subtitle = str(node.get("subtitle") or node.get("note") or "").strip()
            else:
                label = str(node or "").strip()
                node_kind = ""
                subtitle = ""
            if label:
                node_labels.append(label)
            if node_kind:
                node_kinds.add(node_kind)
            if subtitle:
                subtitle_count += 1
        if kind == "architecture":
            if len(lanes) >= 3:
                score += 7
            else:
                issues.append("architecture_lanes_missing")
        elif len(lanes) >= 2:
            score += 5
        if len(node_kinds) >= 3:
            score += 4
        if subtitle_count >= max(2, len(nodes) // 3):
            score += 3
        if node_labels:
            generic_count = sum(
                1
                for label in node_labels
                if re.fullmatch(r"(?:step|node|phase)\s*\d+|(?:\u6b65\u9aa4|\u9636\u6bb5)\s*\d+", label, flags=re.IGNORECASE)
            )
            if generic_count == len(node_labels):
                issues.append("flow_labels_generic")
                score = max(0, score - 12)
            elif generic_count >= max(1, len(node_labels) // 2):
                issues.append("flow_labels_partly_generic")
                score = max(0, score - 6)
        return min(40, score)
    if kind == "er":
        entities = _as_list_safe(payload.get("entities"))
        relations = _as_list_safe(payload.get("relations"))
        if len(entities) >= 3:
            score += 26
        elif len(entities) >= 2:
            score += 20
        else:
            issues.append("er_entities_insufficient")
            score += 5
        if len(relations) >= 2:
            score += 14
        elif len(relations) == 1:
            score += 8
        else:
            issues.append("er_relations_missing")
            score += 2
        return min(40, score)
    if kind in {"bar", "bar_chart"}:
        labels = _as_list_safe(payload.get("labels"))
        values = _as_list_safe(payload.get("values"))
        n = min(len(labels), len(values))
        if n >= 4:
            score += 34
        elif n >= 3:
            score += 28
        elif n >= 2:
            score += 18
        else:
            issues.append("chart_points_insufficient")
            score += 6
        if len(labels) != len(values):
            issues.append("chart_length_mismatch")
            score = max(0, score - 6)
        return min(40, score)
    if kind in {"pie", "pie_chart"}:
        segments = _as_list_safe(payload.get("segments"))
        if segments:
            valid_segments = [item for item in segments if isinstance(item, dict) and str(item.get("label") or "").strip()]
            n = len(valid_segments)
        else:
            labels = _as_list_safe(payload.get("labels"))
            values = _as_list_safe(payload.get("values"))
            n = min(len(labels), len(values))
        if n >= 4:
            score += 32
        elif n >= 3:
            score += 26
        elif n >= 2:
            score += 18
        else:
            issues.append("chart_points_insufficient")
            score += 6
        if segments and len(valid_segments) != len(segments):
            issues.append("pie_segments_incomplete")
            score = max(0, score - 4)
        return min(40, score)
    if kind in {"line", "line_chart"}:
        labels = _as_list_safe(payload.get("labels"))
        series = payload.get("series")
        if isinstance(series, dict):
            series_count = 1
            values_count = len(_as_list_safe(series.get("values")))
        elif isinstance(series, list):
            series_count = len([x for x in series if isinstance(x, dict)])
            values_count = max((len(_as_list_safe((x or {}).get("values"))) for x in series if isinstance(x, dict)), default=0)
        else:
            series_count = 0
            values_count = 0
        n = min(len(labels), values_count)
        if n >= 4:
            score += 28
        elif n >= 3:
            score += 22
        elif n >= 2:
            score += 14
        else:
            issues.append("line_points_insufficient")
            score += 5
        if series_count >= 2:
            score += 12
        elif series_count == 1:
            score += 8
        else:
            issues.append("line_series_missing")
            score += 2
        return min(40, score)
    if kind == "timeline":
        events = _as_list_safe(payload.get("events"))
        if len(events) >= 4:
            return 36
        if len(events) >= 3:
            return 30
        if len(events) >= 2:
            issues.append("timeline_events_sparse")
            return 18
        issues.append("timeline_events_missing")
        return 6
    if kind in {"sequence", "sequence_diagram"}:
        participants = _as_list_safe(payload.get("participants"))
        messages = _as_list_safe(payload.get("messages"))
        if len(participants) >= 3:
            score += 18
        elif len(participants) >= 2:
            score += 12
        else:
            issues.append("sequence_participants_missing")
            score += 4
        if len(messages) >= 3:
            score += 22
        elif len(messages) >= 2:
            score += 16
        elif len(messages) == 1:
            issues.append("sequence_messages_sparse")
            score += 8
        else:
            issues.append("sequence_messages_missing")
            score += 2
        return min(40, score)
    raw_payload = str(payload or "").strip()
    if raw_payload:
        issues.append("unknown_data_shape")
        return 10
    issues.append("missing_data")
    return 2


__all__ = [name for name in globals() if not name.startswith("__")]
