"""Diagram generation capability helpers."""

from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

from typing import Any

from writing_agent.diagram_skills import (
    allowed_diagram_aliases,
    allowed_diagram_types,
    get_diagram_skill_bundle,
    normalize_diagram_kind,
)
from writing_agent.llm import get_default_provider
from writing_agent.llm.provider_compat import provider_or_ollama
from writing_agent.v2.diagram_design import enrich_figure_spec, resolve_requested_diagram_kind, suggest_diagram_spec

_ALLOWED_DIAGRAM_TYPES = allowed_diagram_types()
_ALLOWED_DIAGRAM_TYPE_ALIASES = allowed_diagram_aliases()
_PROMPT_KIND_ORDER = (
    "flow",
    "architecture",
    "er",
    "sequence",
    "state",
    "class",
    "gantt",
    "mindmap",
    "quadrant",
    "radar",
    "scatter",
    "heatmap",
    "funnel",
    "sankey",
    "swot",
    "timeline",
    "bar",
    "line",
    "pie",
)


def extract_json_payload(*, app_v2: Any, raw: str):
    if not raw:
        return None
    raw = raw.strip()
    if raw.startswith("```"):
        raw = app_v2.re.sub(r"^```[a-zA-Z0-9_-]*", "", raw).strip()
        raw = raw.strip("`")
    try:
        data = app_v2.json.loads(raw)
        return data if isinstance(data, dict) else None
    except Exception as _exc:
        logger.debug("Ignored error in diagramming.py: %s", _exc, exc_info=True)

    match = app_v2.re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return None
    try:
        data = app_v2.json.loads(match.group(0))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _escape_tag_text(raw: object) -> str:
    text = str(raw or "")
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _clean_text(raw: object, *, max_chars: int = 48) -> str:
    text = str(raw or "").strip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip()
    return text


def _to_float(value: object) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _fallback_spec(kind: str, caption: str) -> dict[str, Any]:
    return enrich_figure_spec(suggest_diagram_spec(kind, caption=caption, prompt=caption))


def _normalize_flowish_payload(payload: dict[str, Any], *, type_raw: str, caption: str) -> dict[str, Any] | None:
    nodes_out: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for idx, item in enumerate(payload.get("nodes") if isinstance(payload.get("nodes"), list) else []):
        if isinstance(item, dict):
            node_id = _clean_text(item.get("id") or item.get("name") or item.get("label") or f"n{idx+1}", max_chars=24)
            label = _clean_text(item.get("label") or item.get("text") or item.get("name") or node_id, max_chars=48)
            subtitle = _clean_text(item.get("subtitle") or item.get("note") or item.get("desc"), max_chars=48)
            lane = _clean_text(item.get("lane") or item.get("group") or item.get("layer"), max_chars=24)
            node_kind = _clean_text(item.get("kind") or item.get("role") or item.get("category"), max_chars=16).lower()
        else:
            node_id = f"n{idx+1}"
            label = _clean_text(item, max_chars=48)
            subtitle = ""
            lane = ""
            node_kind = ""
        if not node_id or not label or node_id in seen_ids:
            continue
        seen_ids.add(node_id)
        node: dict[str, object] = {"id": node_id, "label": label}
        if subtitle:
            node["subtitle"] = subtitle
        if lane:
            node["lane"] = lane
        if node_kind:
            node["kind"] = node_kind
        nodes_out.append(node)
        if len(nodes_out) >= 24:
            break
    if len(nodes_out) < 2:
        return _fallback_spec(type_raw, caption)

    node_ids = {str(item["id"]) for item in nodes_out}
    edges_out: list[dict[str, str]] = []
    for item in payload.get("edges") if isinstance(payload.get("edges"), list) else []:
        if not isinstance(item, dict):
            continue
        src = _clean_text(item.get("src") or item.get("from") or item.get("source"), max_chars=24)
        dst = _clean_text(item.get("dst") or item.get("to") or item.get("target"), max_chars=24)
        if src not in node_ids or dst not in node_ids:
            continue
        edge: dict[str, str] = {"from": src, "to": dst}
        label = _clean_text(item.get("label"), max_chars=32)
        style = _clean_text(item.get("style"), max_chars=16).lower()
        if label:
            edge["label"] = label
        if style:
            edge["style"] = style
        edges_out.append(edge)
        if len(edges_out) >= 40:
            break
    if not edges_out and len(nodes_out) >= 2:
        for idx in range(len(nodes_out) - 1):
            edges_out.append({"from": str(nodes_out[idx]["id"]), "to": str(nodes_out[idx + 1]["id"])})

    lanes_out: list[dict[str, str]] = []
    seen_lanes: set[str] = set()
    for item in payload.get("lanes") if isinstance(payload.get("lanes"), list) else []:
        if isinstance(item, dict):
            lane_id = _clean_text(item.get("id") or item.get("title"), max_chars=24)
            title = _clean_text(item.get("title") or lane_id, max_chars=24)
        else:
            lane_id = _clean_text(item, max_chars=24)
            title = lane_id
        if lane_id and lane_id not in seen_lanes:
            seen_lanes.add(lane_id)
            lanes_out.append({"id": lane_id, "title": title or lane_id})
    return {"type": type_raw, "caption": caption, "data": {"nodes": nodes_out, "edges": edges_out, "lanes": lanes_out}}


def _normalize_er_payload(payload: dict[str, Any], *, caption: str) -> dict[str, Any] | None:
    entities_out: list[dict[str, object]] = []
    seen_names: set[str] = set()
    for item in payload.get("entities") if isinstance(payload.get("entities"), list) else []:
        if not isinstance(item, dict):
            continue
        name = _clean_text(item.get("name") or item.get("title"), max_chars=30)
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        attrs = [_clean_text(attr, max_chars=28) for attr in (item.get("attributes") if isinstance(item.get("attributes"), list) else [])[:10]]
        attrs = [attr for attr in attrs if attr]
        entities_out.append({"name": name, "attributes": attrs})
        if len(entities_out) >= 12:
            break
    if len(entities_out) < 2:
        return _fallback_spec("er", caption)

    entity_names = {str(item["name"]) for item in entities_out}
    relations_out: list[dict[str, str]] = []
    for item in payload.get("relations") if isinstance(payload.get("relations"), list) else []:
        if not isinstance(item, dict):
            continue
        left = _clean_text(item.get("left") or item.get("from"), max_chars=30)
        right = _clean_text(item.get("right") or item.get("to"), max_chars=30)
        if left not in entity_names or right not in entity_names:
            continue
        rel: dict[str, str] = {"left": left, "right": right}
        label = _clean_text(item.get("label"), max_chars=24)
        cardinality = _clean_text(item.get("cardinality"), max_chars=10)
        if label:
            rel["label"] = label
        if cardinality:
            rel["cardinality"] = cardinality
        relations_out.append(rel)
        if len(relations_out) >= 24:
            break
    return {"type": "er", "caption": caption, "data": {"entities": entities_out, "relations": relations_out}}


def _normalize_sequence_payload(payload: dict[str, Any], *, caption: str) -> dict[str, Any] | None:
    participants = [_clean_text(item, max_chars=24) for item in (payload.get("participants") if isinstance(payload.get("participants"), list) else [])[:12]]
    participants = [item for item in participants if item]
    messages_out: list[dict[str, str]] = []
    for item in payload.get("messages") if isinstance(payload.get("messages"), list) else []:
        if not isinstance(item, dict):
            continue
        src = _clean_text(item.get("from") or item.get("src"), max_chars=24)
        dst = _clean_text(item.get("to") or item.get("dst"), max_chars=24)
        label = _clean_text(item.get("label"), max_chars=36)
        style = _clean_text(item.get("style"), max_chars=16).lower()
        if src and dst:
            message: dict[str, str] = {"from": src, "to": dst, "label": label or "消息"}
            if style:
                message["style"] = style
            messages_out.append(message)
    if len(participants) < 2 or not messages_out:
        return _fallback_spec("sequence", caption)
    return {"type": "sequence", "caption": caption, "data": {"participants": participants, "messages": messages_out[:24]}}


def _normalize_state_payload(payload: dict[str, Any], *, caption: str) -> dict[str, Any] | None:
    states_out: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for idx, item in enumerate(payload.get("states") if isinstance(payload.get("states"), list) else []):
        if isinstance(item, dict):
            state_id = _clean_text(item.get("id") or item.get("name") or item.get("label") or f"s{idx+1}", max_chars=24)
            label = _clean_text(item.get("label") or item.get("name") or state_id, max_chars=32)
            kind = _clean_text(item.get("kind"), max_chars=12).lower()
        else:
            state_id = f"s{idx+1}"
            label = _clean_text(item, max_chars=32)
            kind = ""
        if not state_id or not label or state_id in seen_ids:
            continue
        seen_ids.add(state_id)
        state = {"id": state_id, "label": label}
        if kind:
            state["kind"] = kind
        states_out.append(state)
        if len(states_out) >= 16:
            break
    if len(states_out) < 2:
        return _fallback_spec("state", caption)

    state_ids = {str(item["id"]) for item in states_out}
    transitions_out: list[dict[str, str]] = []
    for item in payload.get("transitions") if isinstance(payload.get("transitions"), list) else []:
        if not isinstance(item, dict):
            continue
        src = _clean_text(item.get("from") or item.get("src"), max_chars=24)
        dst = _clean_text(item.get("to") or item.get("dst"), max_chars=24)
        label = _clean_text(item.get("label"), max_chars=28)
        if src in state_ids and dst in state_ids:
            edge = {"from": src, "to": dst}
            if label:
                edge["label"] = label
            transitions_out.append(edge)
    if not transitions_out:
        for idx in range(len(states_out) - 1):
            transitions_out.append({"from": str(states_out[idx]["id"]), "to": str(states_out[idx + 1]["id"])})
    return {"type": "state", "caption": caption, "data": {"states": states_out, "transitions": transitions_out[:24]}}


def _normalize_class_payload(payload: dict[str, Any], *, caption: str) -> dict[str, Any] | None:
    classes_out: list[dict[str, object]] = []
    seen_names: set[str] = set()
    for item in payload.get("classes") if isinstance(payload.get("classes"), list) else []:
        if not isinstance(item, dict):
            continue
        name = _clean_text(item.get("name") or item.get("title"), max_chars=28)
        if not name or name in seen_names:
            continue
        seen_names.add(name)
        attributes = [_clean_text(attr, max_chars=28) for attr in (item.get("attributes") if isinstance(item.get("attributes"), list) else [])[:8]]
        methods = [_clean_text(method, max_chars=28) for method in (item.get("methods") if isinstance(item.get("methods"), list) else [])[:8]]
        classes_out.append(
            {
                "name": name,
                "attributes": [attr for attr in attributes if attr],
                "methods": [method for method in methods if method],
            }
        )
        if len(classes_out) >= 8:
            break
    if len(classes_out) < 2:
        return _fallback_spec("class", caption)

    class_names = {str(item["name"]) for item in classes_out}
    relations_out: list[dict[str, str]] = []
    for item in payload.get("relations") if isinstance(payload.get("relations"), list) else []:
        if not isinstance(item, dict):
            continue
        src = _clean_text(item.get("from") or item.get("src") or item.get("left"), max_chars=28)
        dst = _clean_text(item.get("to") or item.get("dst") or item.get("right"), max_chars=28)
        label = _clean_text(item.get("label"), max_chars=24)
        kind = _clean_text(item.get("kind") or item.get("type"), max_chars=16).lower()
        if src in class_names and dst in class_names:
            relation = {"from": src, "to": dst}
            if label:
                relation["label"] = label
            if kind:
                relation["kind"] = kind
            relations_out.append(relation)
    return {"type": "class", "caption": caption, "data": {"classes": classes_out, "relations": relations_out[:16]}}


def _normalize_gantt_payload(payload: dict[str, Any], *, caption: str) -> dict[str, Any] | None:
    tasks_out: list[dict[str, str]] = []
    for idx, item in enumerate(payload.get("tasks") if isinstance(payload.get("tasks"), list) else []):
        if not isinstance(item, dict):
            continue
        task = _clean_text(item.get("task") or item.get("name") or item.get("label") or f"Task {idx+1}", max_chars=32)
        start = _clean_text(item.get("start") or item.get("begin"), max_chars=16)
        end = _clean_text(item.get("end") or item.get("finish"), max_chars=16)
        owner = _clean_text(item.get("owner"), max_chars=20)
        status = _clean_text(item.get("status"), max_chars=16)
        if not task:
            continue
        row = {"task": task, "start": start or f"P{idx+1}", "end": end or f"P{idx+2}"}
        if owner:
            row["owner"] = owner
        if status:
            row["status"] = status
        tasks_out.append(row)
        if len(tasks_out) >= 12:
            break
    if len(tasks_out) < 2:
        return _fallback_spec("gantt", caption)
    return {"type": "gantt", "caption": caption, "data": {"tasks": tasks_out}}


def _normalize_mindmap_payload(payload: dict[str, Any], *, caption: str) -> dict[str, Any] | None:
    center = _clean_text(payload.get("center") or payload.get("root") or payload.get("topic"), max_chars=28) or caption
    branches_out: list[dict[str, object]] = []
    for item in payload.get("branches") if isinstance(payload.get("branches"), list) else []:
        if isinstance(item, dict):
            label = _clean_text(item.get("label") or item.get("name"), max_chars=24)
            children = [_clean_text(child, max_chars=18) for child in (item.get("children") if isinstance(item.get("children"), list) else [])[:4]]
            children = [child for child in children if child]
        else:
            label = _clean_text(item, max_chars=24)
            children = []
        if label:
            branches_out.append({"label": label, "children": children})
    return {"type": "mindmap", "caption": caption, "data": {"center": center, "branches": branches_out[:8]}} if len(branches_out) >= 2 else _fallback_spec("mindmap", caption)


def _normalize_quadrant_payload(payload: dict[str, Any], *, caption: str) -> dict[str, Any] | None:
    items_out: list[dict[str, object]] = []
    for item in payload.get("items") if isinstance(payload.get("items"), list) else []:
        if not isinstance(item, dict):
            continue
        label = _clean_text(item.get("label") or item.get("name"), max_chars=20)
        if not label:
            continue
        x = _to_float(item.get("x"))
        y = _to_float(item.get("y"))
        if x is None or y is None:
            continue
        items_out.append({"label": label, "x": max(0.0, min(1.0, x)), "y": max(0.0, min(1.0, y)), "quadrant": _clean_text(item.get("quadrant"), max_chars=18)})
    data = {"x_axis": _clean_text(payload.get("x_axis") or payload.get("xLabel"), max_chars=18) or "影响力", "y_axis": _clean_text(payload.get("y_axis") or payload.get("yLabel"), max_chars=18) or "可行性", "items": items_out[:12]}
    return {"type": "quadrant", "caption": caption, "data": data} if len(items_out) >= 2 else _fallback_spec("quadrant", caption)


def _normalize_radar_payload(payload: dict[str, Any], *, caption: str) -> dict[str, Any] | None:
    axes = [_clean_text(item, max_chars=18) for item in (payload.get("axes") if isinstance(payload.get("axes"), list) else [])[:8]]
    axes = [item for item in axes if item]
    series_out: list[dict[str, object]] = []
    for item in payload.get("series") if isinstance(payload.get("series"), list) else []:
        if not isinstance(item, dict):
            continue
        name = _clean_text(item.get("name") or item.get("label") or "序列", max_chars=18)
        values: list[float] = []
        for raw_value in (item.get("values") if isinstance(item.get("values"), list) else [])[: len(axes) or 8]:
            number = _to_float(raw_value)
            if number is not None:
                values.append(max(0.0, min(100.0, number)))
        if name and len(values) >= 3:
            series_out.append({"name": name, "values": values})
    return {"type": "radar", "caption": caption, "data": {"axes": axes, "series": series_out[:3]}} if len(axes) >= 3 and series_out else _fallback_spec("radar", caption)


def _normalize_scatter_payload(payload: dict[str, Any], *, caption: str) -> dict[str, Any] | None:
    points_out: list[dict[str, object]] = []
    for item in payload.get("points") if isinstance(payload.get("points"), list) else []:
        if not isinstance(item, dict):
            continue
        x = _to_float(item.get("x"))
        y = _to_float(item.get("y"))
        if x is None or y is None:
            continue
        points_out.append({"label": _clean_text(item.get("label") or item.get("name"), max_chars=18), "x": x, "y": y, "group": _clean_text(item.get("group"), max_chars=16)})
    data = {"x_label": _clean_text(payload.get("x_label") or payload.get("xLabel"), max_chars=18) or "X", "y_label": _clean_text(payload.get("y_label") or payload.get("yLabel"), max_chars=18) or "Y", "points": points_out[:24]}
    return {"type": "scatter", "caption": caption, "data": data} if len(points_out) >= 2 else _fallback_spec("scatter", caption)


def _normalize_heatmap_payload(payload: dict[str, Any], *, caption: str) -> dict[str, Any] | None:
    rows = [_clean_text(item, max_chars=16) for item in (payload.get("rows") if isinstance(payload.get("rows"), list) else [])[:8]]
    cols = [_clean_text(item, max_chars=16) for item in (payload.get("cols") if isinstance(payload.get("cols"), list) else [])[:8]]
    rows = [item for item in rows if item]
    cols = [item for item in cols if item]
    values_in = payload.get("values") if isinstance(payload.get("values"), list) else []
    values: list[list[float]] = []
    for row in values_in[: len(rows) or 8]:
        if not isinstance(row, list):
            continue
        row_out: list[float] = []
        for item in row[: len(cols) or 8]:
            number = _to_float(item)
            row_out.append(max(0.0, min(100.0, number if number is not None else 0.0)))
        if row_out:
            values.append(row_out)
    data = {"rows": rows, "cols": cols, "values": values}
    return {"type": "heatmap", "caption": caption, "data": data} if len(rows) >= 2 and len(cols) >= 2 else _fallback_spec("heatmap", caption)


def _normalize_funnel_payload(payload: dict[str, Any], *, caption: str) -> dict[str, Any] | None:
    stages_out: list[dict[str, object]] = []
    for item in payload.get("stages") if isinstance(payload.get("stages"), list) else []:
        if not isinstance(item, dict):
            continue
        label = _clean_text(item.get("label") or item.get("name"), max_chars=20)
        value = _to_float(item.get("value"))
        if label and value is not None:
            stages_out.append({"label": label, "value": max(0.0, value)})
    return {"type": "funnel", "caption": caption, "data": {"stages": stages_out[:8]}} if len(stages_out) >= 2 else _fallback_spec("funnel", caption)


def _normalize_sankey_payload(payload: dict[str, Any], *, caption: str) -> dict[str, Any] | None:
    nodes = [_clean_text(item, max_chars=18) for item in (payload.get("nodes") if isinstance(payload.get("nodes"), list) else [])[:10]]
    nodes = [item for item in nodes if item]
    links_out: list[dict[str, object]] = []
    for item in payload.get("links") if isinstance(payload.get("links"), list) else []:
        if not isinstance(item, dict):
            continue
        source = _clean_text(item.get("source") or item.get("from"), max_chars=18)
        target = _clean_text(item.get("target") or item.get("to"), max_chars=18)
        value = _to_float(item.get("value"))
        if source and target and value is not None:
            links_out.append({"source": source, "target": target, "value": max(0.0, value)})
    return {"type": "sankey", "caption": caption, "data": {"nodes": nodes, "links": links_out[:16]}} if len(nodes) >= 2 and links_out else _fallback_spec("sankey", caption)


def _normalize_swot_payload(payload: dict[str, Any], *, caption: str) -> dict[str, Any] | None:
    def _items(name: str) -> list[str]:
        raw = payload.get(name) if isinstance(payload.get(name), list) else []
        out = [_clean_text(item, max_chars=24) for item in raw[:6]]
        return [item for item in out if item]

    data = {
        "strengths": _items("strengths"),
        "weaknesses": _items("weaknesses"),
        "opportunities": _items("opportunities"),
        "threats": _items("threats"),
    }
    return {"type": "swot", "caption": caption, "data": data} if any(data.values()) else _fallback_spec("swot", caption)


def normalize_diagram_spec_payload(spec: object, *, kind: str) -> dict[str, Any] | None:
    if not isinstance(spec, dict):
        return None
    explicit_type = str(spec.get("type") or "").strip().lower()
    if explicit_type and explicit_type not in _ALLOWED_DIAGRAM_TYPES and explicit_type not in _ALLOWED_DIAGRAM_TYPE_ALIASES:
        return None
    type_raw = normalize_diagram_kind(explicit_type or kind or "flow")
    if type_raw not in _ALLOWED_DIAGRAM_TYPES:
        return None
    payload = spec.get("data")
    if not isinstance(payload, dict):
        return None

    caption = _clean_text(spec.get("caption") or kind or "diagram", max_chars=60) or "diagram"
    if type_raw in {"flow", "architecture"}:
        return _normalize_flowish_payload(payload, type_raw=type_raw, caption=caption)
    if type_raw == "er":
        return _normalize_er_payload(payload, caption=caption)
    if type_raw == "sequence":
        return _normalize_sequence_payload(payload, caption=caption)
    if type_raw == "state":
        return _normalize_state_payload(payload, caption=caption)
    if type_raw == "class":
        return _normalize_class_payload(payload, caption=caption)
    if type_raw == "gantt":
        return _normalize_gantt_payload(payload, caption=caption)
    if type_raw == "mindmap":
        return _normalize_mindmap_payload(payload, caption=caption)
    if type_raw == "quadrant":
        return _normalize_quadrant_payload(payload, caption=caption)
    if type_raw == "radar":
        return _normalize_radar_payload(payload, caption=caption)
    if type_raw == "scatter":
        return _normalize_scatter_payload(payload, caption=caption)
    if type_raw == "heatmap":
        return _normalize_heatmap_payload(payload, caption=caption)
    if type_raw == "funnel":
        return _normalize_funnel_payload(payload, caption=caption)
    if type_raw == "sankey":
        return _normalize_sankey_payload(payload, caption=caption)
    if type_raw == "swot":
        return _normalize_swot_payload(payload, caption=caption)
    if type_raw == "timeline":
        events_out: list[dict[str, str]] = []
        for item in payload.get("events") if isinstance(payload.get("events"), list) else []:
            if not isinstance(item, dict):
                continue
            time = _clean_text(item.get("time") or item.get("date") or item.get("stage"), max_chars=18)
            label = _clean_text(item.get("label") or item.get("event") or item.get("name"), max_chars=36)
            if time and label:
                events_out.append({"time": time, "label": label})
        return {"type": "timeline", "caption": caption, "data": {"events": events_out}} if len(events_out) >= 2 else _fallback_spec("timeline", caption)
    if type_raw == "bar":
        labels = [_clean_text(item, max_chars=24) for item in (payload.get("labels") if isinstance(payload.get("labels"), list) else [])[:20]]
        labels = [item for item in labels if item]
        values: list[float] = []
        for item in (payload.get("values") if isinstance(payload.get("values"), list) else [])[:20]:
            number = _to_float(item)
            if number is not None:
                values.append(number)
        return {"type": "bar", "caption": caption, "data": {"labels": labels[: len(values)], "values": values[: len(labels)]}} if min(len(labels), len(values)) >= 2 else _fallback_spec("bar", caption)
    if type_raw == "line":
        labels = [_clean_text(item, max_chars=20) for item in (payload.get("labels") if isinstance(payload.get("labels"), list) else [])[:16]]
        labels = [item for item in labels if item]
        series_out: list[dict[str, object]] = []
        for item in payload.get("series") if isinstance(payload.get("series"), list) else []:
            if not isinstance(item, dict):
                continue
            name = _clean_text(item.get("name") or item.get("label") or "序列", max_chars=24)
            values: list[float] = []
            for raw_value in (item.get("values") if isinstance(item.get("values"), list) else [])[:16]:
                number = _to_float(raw_value)
                if number is not None:
                    values.append(number)
            if len(values) >= 2:
                series_out.append({"name": name, "values": values})
        if not series_out:
            return _fallback_spec("line", caption)
        if not labels:
            labels = [f"T{i + 1}" for i in range(len(series_out[0]["values"]))]
        target_len = min(len(labels), min(len(item["values"]) for item in series_out))
        if target_len < 2:
            return _fallback_spec("line", caption)
        return {
            "type": "line",
            "caption": caption,
            "data": {
                "labels": labels[:target_len],
                "series": [{"name": item["name"], "values": item["values"][:target_len]} for item in series_out],
            },
        }

    segments_out: list[dict[str, object]] = []
    for item in payload.get("segments") if isinstance(payload.get("segments"), list) else []:
        if not isinstance(item, dict):
            continue
        label = _clean_text(item.get("label"), max_chars=24)
        value = _to_float(item.get("value"))
        if label and value is not None:
            segments_out.append({"label": label, "value": value})
    return {"type": "pie", "caption": caption, "data": {"segments": segments_out}} if len(segments_out) >= 2 else _fallback_spec("pie", caption)


def _skill_context(kind: str) -> str:
    bundle = get_diagram_skill_bundle(kind)
    selected = bundle.selected
    academic = bundle.academic
    use_cases = ", ".join(selected.use_cases)
    return (
        "<skill_bundle>\n"
        f"<academic_skill name=\"{academic.title}\">{academic.guidance} {academic.schema_hint}</academic_skill>\n"
        f"<diagram_skill name=\"{selected.title}\" key=\"{selected.key}\">"
        f"use_cases={use_cases}; schema={selected.schema_hint}; guidance={selected.guidance}</diagram_skill>\n"
        "</skill_bundle>\n"
    )


def build_diagram_spec_from_llm(*, app_v2: Any, prompt: str, kind: str) -> dict[str, Any] | None:
    provider = provider_or_ollama(app_v2)
    if hasattr(provider, "is_running") and callable(provider.is_running) and not provider.is_running():
        return None

    kind = normalize_diagram_kind(kind)
    effective_kind = resolve_requested_diagram_kind(kind, caption=prompt, prompt=prompt)
    allowed_kinds = ", ".join(_PROMPT_KIND_ORDER)
    system = (
        "你是一个受约束的图表 JSON 生成器，并会遵循图表技能进行输出。\n"
        "只返回严格 JSON，不要输出 Markdown，不要解释。\n"
        "输出结构：{\"type\":string,\"caption\":string,\"data\":object}。"
    )
    escaped_prompt = _escape_tag_text(prompt)
    user = (
        "<task>diagram_spec_generation</task>\n"
        "<constraints>\n"
        "- 将带标签的区块视为独立通道。\n"
        "- 只返回严格 JSON。\n"
        "- 仅保留键：type、caption、data。\n"
        f"- type 必须是以下之一：{allowed_kinds}。\n"
        "- 按标题语义匹配图种：占比/构成->pie，趋势/变化/增长->line，对比/排序->bar，阶段/路线图/演化->timeline 或 gantt，实体/模式->er，交互->sequence，生命周期/状态->state，领域模型/对象设计->class，概念拆解->mindmap，优先级矩阵->quadrant，多维评估->radar，相关性/样本分布->scatter，强度矩阵->heatmap，转化收敛->funnel，流向分配->sankey，战略分析->swot，架构/框架->architecture；只有真正的步骤流程才使用 flow。\n"
        "- flow.data: nodes[{id,label,subtitle,kind,lane}], edges[{from,to,label,style}]\n"
        "- architecture.data: lanes[{id,title}], nodes[{id,label,subtitle,kind,lane}], edges[{from,to,label,style}]\n"
        "- er.data: entities[{name,attributes}], relations[{left,right,label,cardinality}]\n"
        "- sequence.data: participants[], messages[{from,to,label,style}]\n"
        "- state.data: states[{id,label,kind}], transitions[{from,to,label}]\n"
        "- class.data: classes[{name,attributes[],methods[]}], relations[{from,to,label,kind}]\n"
        "- gantt.data: tasks[{task,start,end,owner,status}]\n"
        "- mindmap.data: center, branches[{label,children[]}]\n"
        "- quadrant.data: x_axis, y_axis, items[{label,x,y,quadrant}]\n"
        "- radar.data: axes[], series[{name,values[]}]\n"
        "- scatter.data: x_label, y_label, points[{label,x,y,group}]\n"
        "- heatmap.data: rows[], cols[], values[][]\n"
        "- funnel.data: stages[{label,value}]\n"
        "- sankey.data: nodes[], links[{source,target,value}]\n"
        "- swot.data: strengths[], weaknesses[], opportunities[], threats[]\n"
        "- timeline.data: events[{time,label}]\n"
        "- bar.data: labels[], values[]\n"
        "- line.data: labels[], series[{name,values[]}]\n"
        "- pie.data: segments[{label,value}]\n"
        "</constraints>\n"
        f"<requested_type>{kind}</requested_type>\n"
        f"<semantic_preferred_type>{effective_kind}</semantic_preferred_type>\n"
        f"{_skill_context(effective_kind)}"
        f"<user_request>{escaped_prompt}</user_request>\n"
        "现在返回严格 JSON。"
    )
    try:
        raw = provider.chat(system=system, user=user, temperature=0.2)
    except Exception:
        return None
    data = extract_json_payload(app_v2=app_v2, raw=raw)
    return normalize_diagram_spec_payload(data, kind=effective_kind)


def build_diagram_spec_fallback(*, prompt: str, kind: str) -> dict[str, Any]:
    raw_prompt = str(prompt or "")
    kind = normalize_diagram_kind((kind or "flow").strip().lower())
    caption = raw_prompt.strip()[:32] or "diagram"
    effective_kind = resolve_requested_diagram_kind(kind, caption=caption, prompt=raw_prompt)
    return enrich_figure_spec(suggest_diagram_spec(effective_kind, caption=caption or effective_kind, prompt=raw_prompt))


def build_diagram_spec_from_prompt(*, app_v2: Any, prompt: str, kind: str) -> dict[str, Any]:
    prompt = str(prompt or "").strip()
    kind = normalize_diagram_kind(kind)
    effective_kind = resolve_requested_diagram_kind(kind, caption=prompt, prompt=prompt)
    spec = build_diagram_spec_from_llm(app_v2=app_v2, prompt=prompt, kind=effective_kind)
    if not spec:
        return build_diagram_spec_fallback(prompt=prompt, kind=effective_kind)
    normalized = normalize_diagram_spec_payload(spec, kind=effective_kind)
    return enrich_figure_spec(normalized) if normalized else build_diagram_spec_fallback(prompt=prompt, kind=effective_kind)


__all__ = [name for name in globals() if not name.startswith("__")]
