"""Diagram generation capability helpers."""

from __future__ import annotations

from typing import Any

from writing_agent.v2.diagram_design import enrich_figure_spec, resolve_requested_diagram_kind, suggest_diagram_spec

_ALLOWED_DIAGRAM_TYPES = {"flow", "architecture", "er", "sequence", "timeline", "bar", "line", "pie"}

_ALLOWED_DIAGRAM_TYPE_ALIASES = {
    "flowchart",
    "architecture_diagram",
    "arch",
    "sequence_diagram",
    "bar_chart",
    "line_chart",
    "pie_chart",
}


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
    except Exception:
        pass
    match = app_v2.re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return None
    try:
        data = app_v2.json.loads(match.group(0))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def normalize_diagram_kind(kind: str) -> str:
    value = str(kind or "flow").strip().lower()
    if value == "flowchart":
        value = "flow"
    if value in {"architecture_diagram", "arch"}:
        value = "architecture"
    return value if value in _ALLOWED_DIAGRAM_TYPES else "flow"


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
        nodes_out: list[dict[str, object]] = []
        seen_ids: set[str] = set()
        nodes = payload.get("nodes")
        if isinstance(nodes, list):
            for idx, item in enumerate(nodes):
                if isinstance(item, dict):
                    node_id = _clean_text(
                        item.get("id") or item.get("name") or item.get("label") or f"n{idx+1}",
                        max_chars=24,
                    )
                    label = _clean_text(
                        item.get("label") or item.get("text") or item.get("name") or node_id,
                        max_chars=48,
                    )
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
            return enrich_figure_spec(suggest_diagram_spec(type_raw, caption=caption, prompt=caption))

        node_ids = {str(item["id"]) for item in nodes_out}
        edges_out: list[dict[str, str]] = []
        edges = payload.get("edges")
        if isinstance(edges, list):
            for item in edges:
                if isinstance(item, dict):
                    src = _clean_text(item.get("src") or item.get("from") or item.get("source"), max_chars=24)
                    dst = _clean_text(item.get("dst") or item.get("to") or item.get("target"), max_chars=24)
                    label = _clean_text(item.get("label") or item.get("text"), max_chars=48)
                    style = _clean_text(item.get("style"), max_chars=12).lower()
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    src = _clean_text(item[0], max_chars=24)
                    dst = _clean_text(item[1], max_chars=24)
                    label = _clean_text(item[2] if len(item) >= 3 else "", max_chars=48)
                    style = ""
                else:
                    continue
                if not src or not dst or src not in node_ids or dst not in node_ids:
                    continue
                edge: dict[str, str] = {"from": src, "to": dst}
                if label:
                    edge["label"] = label
                if style:
                    edge["style"] = style
                edges_out.append(edge)
                if len(edges_out) >= 40:
                    break
        if not edges_out:
            for idx in range(len(nodes_out) - 1):
                edges_out.append({"from": str(nodes_out[idx]["id"]), "to": str(nodes_out[idx + 1]["id"])})

        result: dict[str, object] = {"type": type_raw, "caption": caption, "data": {"nodes": nodes_out, "edges": edges_out}}
        lanes_raw = payload.get("lanes")
        if isinstance(lanes_raw, list):
            lanes_out: list[dict[str, str]] = []
            for idx, lane in enumerate(lanes_raw):
                if isinstance(lane, dict):
                    lane_id = _clean_text(lane.get("id") or lane.get("title") or f"lane_{idx+1}", max_chars=24)
                    title = _clean_text(lane.get("title") or lane_id, max_chars=24)
                else:
                    title = _clean_text(lane, max_chars=24)
                    lane_id = title or f"lane_{idx+1}"
                if lane_id and title:
                    lanes_out.append({"id": lane_id, "title": title})
            if lanes_out:
                result["data"]["lanes"] = lanes_out
        return enrich_figure_spec(result)

    if type_raw == "er":
        entities_out: list[dict[str, object]] = []
        relations_out: list[dict[str, str]] = []
        entities = payload.get("entities")
        if isinstance(entities, list):
            seen_names: set[str] = set()
            for item in entities:
                if not isinstance(item, dict):
                    continue
                name = _clean_text(item.get("name"), max_chars=24)
                if not name or name in seen_names:
                    continue
                seen_names.add(name)
                attrs_raw = item.get("attributes")
                attrs = []
                if isinstance(attrs_raw, list):
                    for attr in attrs_raw[:10]:
                        txt = _clean_text(attr, max_chars=24)
                        if txt:
                            attrs.append(txt)
                entities_out.append({"name": name, "attributes": attrs or ["attr"]})
        if len(entities_out) < 2:
            return None
        entity_names = {item["name"] for item in entities_out}
        relations = payload.get("relations")
        if isinstance(relations, list):
            for item in relations:
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
                        "label": _clean_text(item.get("label"), max_chars=24),
                        "cardinality": _clean_text(item.get("cardinality"), max_chars=24),
                    }
                )
        if not relations_out:
            relations_out.append(
                {"left": entities_out[0]["name"], "right": entities_out[1]["name"], "label": "rel", "cardinality": ""}
            )
        return {"type": type_raw, "caption": caption, "data": {"entities": entities_out, "relations": relations_out}}

    if type_raw == "sequence":
        participants_out: list[str] = []
        participants = payload.get("participants")
        if isinstance(participants, list):
            for item in participants:
                label = (
                    _clean_text(item.get("label") or item.get("name"), max_chars=24)
                    if isinstance(item, dict)
                    else _clean_text(item, max_chars=24)
                )
                if label and label not in participants_out:
                    participants_out.append(label)
        if len(participants_out) < 2:
            return enrich_figure_spec(suggest_diagram_spec("sequence", caption=caption, prompt=caption))
        participant_set = set(participants_out)
        messages_out: list[dict[str, str]] = []
        messages = payload.get("messages")
        if isinstance(messages, list):
            for item in messages:
                if not isinstance(item, dict):
                    continue
                frm = _clean_text(item.get("from") or item.get("src") or item.get("source"), max_chars=24)
                to = _clean_text(item.get("to") or item.get("dst") or item.get("target"), max_chars=24)
                if not frm or not to or frm not in participant_set or to not in participant_set:
                    continue
                label = _clean_text(item.get("label") or item.get("text"), max_chars=60) or "message"
                style = _clean_text(item.get("style"), max_chars=12).lower()
                entry = {"from": frm, "to": to, "label": label}
                if style:
                    entry["style"] = style
                messages_out.append(entry)
        if not messages_out:
            for idx in range(len(participants_out) - 1):
                messages_out.append({"from": participants_out[idx], "to": participants_out[idx + 1], "label": "message"})
        return enrich_figure_spec(
            {"type": type_raw, "caption": caption, "data": {"participants": participants_out, "messages": messages_out}}
        )

    if type_raw == "timeline":
        events_out: list[dict[str, str]] = []
        events = payload.get("events")
        if isinstance(events, list):
            for item in events:
                if not isinstance(item, dict):
                    continue
                t = _clean_text(item.get("time"), max_chars=24)
                label = _clean_text(item.get("label"), max_chars=60)
                if t and label:
                    events_out.append({"time": t, "label": label})
        return {"type": type_raw, "caption": caption, "data": {"events": events_out}} if len(events_out) >= 2 else None

    if type_raw == "bar":
        labels_raw = payload.get("labels")
        values_raw = payload.get("values")
        labels = [_clean_text(item, max_chars=24) for item in labels_raw[:12]] if isinstance(labels_raw, list) else []
        labels = [item for item in labels if item]
        values: list[float] = []
        if isinstance(values_raw, list):
            for item in values_raw[:12]:
                value = _to_float(item)
                if value is not None:
                    values.append(value)
        count = min(len(labels), len(values))
        return {"type": type_raw, "caption": caption, "data": {"labels": labels[:count], "values": values[:count]}} if count >= 2 else None

    if type_raw == "line":
        labels_raw = payload.get("labels")
        labels = [_clean_text(item, max_chars=24) for item in labels_raw[:24]] if isinstance(labels_raw, list) else []
        labels = [item for item in labels if item]
        series_out: list[dict[str, object]] = []
        series = payload.get("series")
        if isinstance(series, list):
            for item in series[:8]:
                if not isinstance(item, dict):
                    continue
                name = _clean_text(item.get("name"), max_chars=24) or "S"
                raw_values = item.get("values")
                if not isinstance(raw_values, list):
                    continue
                values: list[float] = []
                for raw_value in raw_values[:24]:
                    number = _to_float(raw_value)
                    if number is not None:
                        values.append(number)
                if len(values) >= 2:
                    series_out.append({"name": name, "values": values})
        if not series_out:
            return None
        if not labels:
            labels = [f"T{i + 1}" for i in range(len(series_out[0]["values"]))]
        target_len = min(len(labels), min(len(item["values"]) for item in series_out))
        return {
            "type": type_raw,
            "caption": caption,
            "data": {
                "labels": labels[:target_len],
                "series": [{"name": item["name"], "values": item["values"][:target_len]} for item in series_out],
            },
        } if target_len >= 2 else None

    segments = payload.get("segments")
    segments_out: list[dict[str, object]] = []
    if isinstance(segments, list):
        for item in segments[:20]:
            if not isinstance(item, dict):
                continue
            label = _clean_text(item.get("label"), max_chars=24)
            value = _to_float(item.get("value"))
            if label and value is not None:
                segments_out.append({"label": label, "value": value})
    return {"type": type_raw, "caption": caption, "data": {"segments": segments_out}} if len(segments_out) >= 2 else None


def build_diagram_spec_from_llm(*, app_v2: Any, prompt: str, kind: str) -> dict[str, Any] | None:
    settings = app_v2.get_ollama_settings()
    if not settings.enabled:
        return None
    client = app_v2.OllamaClient(base_url=settings.base_url, model=settings.model, timeout_s=settings.timeout_s)
    if not client.is_running():
        return None

    kind = normalize_diagram_kind(kind)
    effective_kind = resolve_requested_diagram_kind(kind, caption=prompt, prompt=prompt)
    system = (
        "You are a constrained diagram JSON generator.\n"
        "Return strict JSON only (no markdown, no explanations).\n"
        "Schema: {\"type\":string,\"caption\":string,\"data\":object}."
    )
    escaped_prompt = _escape_tag_text(prompt)
    user = (
        "<task>diagram_spec_generation</task>\n"
        "<constraints>\n"
        "- Treat tagged blocks as separate channels.\n"
        "- Return strict JSON only.\n"
        "- Keep only keys: type, caption, data.\n"
        "- type must be one of: flow, architecture, er, sequence, timeline, bar, line, pie.\n"
        "- Match figure kind to caption semantics: share/composition->pie, trend/change/growth->line, comparison/ranking->bar, stage/roadmap/evolution->timeline, entity/schema->er, interaction->sequence, architecture/framework->architecture, and use flow only for true stepwise processes.\n"
        "- flow.data: nodes[{id,label,subtitle,kind,lane}], edges[{from,to,label,style}]\n- architecture.data: lanes[{id,title}], nodes[{id,label,subtitle,kind,lane}], edges[{from,to,label,style}]\n"
        "- er.data: entities[{name,attributes}], relations[{left,right,label,cardinality}]\n"
        "- sequence.data: participants[], messages[{from,to,label,style}]\n"
        "- timeline.data: events[{time,label}]\n"
        "- bar.data: labels[], values[]\n"
        "- line.data: labels[], series[{name,values[]}]\n"
        "- pie.data: segments[{label,value}]\n"
        "</constraints>\n"
        f"<requested_type>{kind}</requested_type>\n"
        f"<semantic_preferred_type>{effective_kind}</semantic_preferred_type>\n"
        f"<user_request>{escaped_prompt}</user_request>\n"
        "Return strict JSON now."
    )
    try:
        raw = client.chat(system=system, user=user, temperature=0.2)
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
