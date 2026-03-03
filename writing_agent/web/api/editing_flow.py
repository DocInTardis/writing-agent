"""Editing Flow module.

This module belongs to `writing_agent.web.api` in the writing-agent codebase.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from writing_agent.web.domains import context_policy_domain

router = APIRouter()


def _app_v2():
    from writing_agent.web import app_v2

    return app_v2


def _clamp_int(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def _normalize_inline_context_policy(raw: object) -> dict[str, object]:
    return context_policy_domain.normalize_inline_context_policy(raw)


def _trim_inline_context(
    *,
    selected_text: str,
    before_text: str,
    after_text: str,
    policy: dict[str, object],
) -> tuple[str, str, dict[str, object]]:
    selected_len = len(str(selected_text or ""))
    base = int(policy.get("window_formula_base") or 220)
    coef = float(policy.get("window_formula_coef") or 0.8)
    extra = int(policy.get("short_selection_extra_chars") or 180)
    win_min = int(policy.get("window_min_chars") or 240)
    win_max = max(win_min, int(policy.get("window_max_chars") or 1200))
    short_threshold = int(policy.get("short_selection_threshold_chars") or 60)

    short_boost = extra if selected_len < short_threshold else 0
    side = _clamp_int(int(base + coef * max(1, selected_len) + short_boost), win_min, win_max)

    before_raw = str(before_text or "")
    after_raw = str(after_text or "")
    before_trim = before_raw[-side:] if len(before_raw) > side else before_raw
    after_trim = after_raw[:side] if len(after_raw) > side else after_raw
    trimmed_for_window = (before_trim != before_raw) or (after_trim != after_raw)

    total_cap = int(policy.get("context_total_max_chars") or 2400)
    if len(before_trim) + len(after_trim) > total_cap:
        half = max(120, total_cap // 2)
        before_trim = before_trim[-half:] if len(before_trim) > half else before_trim
        after_trim = after_trim[:half] if len(after_trim) > half else after_trim
        trimmed_for_window = True

    meta = {
        "policy_version": str(policy.get("version") or "dynamic_v1"),
        "left_window_chars": int(len(before_trim)),
        "right_window_chars": int(len(after_trim)),
        "trimmed_for_budget": bool(trimmed_for_window),
    }
    return before_trim, after_trim, meta


async def doc_ir_ops(doc_id: str, request: Request) -> dict:
    app_v2 = _app_v2()
    session = app_v2.store.get(doc_id)
    if session is None:
        raise app_v2.HTTPException(status_code=404, detail="document not found")

    data = await request.json()
    ops_raw = data.get("ops") or []
    ops: list[app_v2.DocIROperation] = []
    for item in ops_raw:
        if not isinstance(item, dict):
            continue
        try:
            ops.append(app_v2.DocIROperation.parse_obj(item))
        except Exception:
            continue

    if not ops:
        raise app_v2.HTTPException(status_code=400, detail="ops required")

    doc_ir = app_v2.doc_ir_from_dict(session.doc_ir or {})
    doc_ir = app_v2.doc_ir_apply_ops(doc_ir, ops)
    session.doc_ir = app_v2.doc_ir_to_dict(doc_ir)
    session.doc_text = app_v2.doc_ir_to_text(doc_ir)
    app_v2.store.put(session)
    return {"ok": 1, "doc_ir": session.doc_ir, "text": session.doc_text}


async def doc_ir_diff(doc_id: str, request: Request) -> dict:
    app_v2 = _app_v2()
    session = app_v2.store.get(doc_id)
    if session is None:
        raise app_v2.HTTPException(status_code=404, detail="document not found")

    data = await request.json()
    other = data.get("doc_ir")
    if not isinstance(other, dict):
        raise app_v2.HTTPException(status_code=400, detail="doc_ir must be object")

    cur = app_v2.doc_ir_from_dict(session.doc_ir or {})
    nxt = app_v2.doc_ir_from_dict(other)
    diff = app_v2.doc_ir_diff(cur, nxt)
    return {"ok": 1, "diff": diff}


async def render_figure(request: Request) -> dict:
    app_v2 = _app_v2()
    data = await request.json()
    spec = data.get("spec") if isinstance(data, dict) else {}
    if not isinstance(spec, dict):
        raise app_v2.HTTPException(status_code=400, detail="spec must be object")

    svg, caption = app_v2.render_figure_svg(spec)
    safe_svg = app_v2.sanitize_html(svg)
    return {"svg": safe_svg, "caption": caption}


def _extract_json_payload(raw: str):
    app_v2 = _app_v2()
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
    m = app_v2.re.search(r"\{[\s\S]*\}", raw)
    if not m:
        return None
    try:
        data = app_v2.json.loads(m.group(0))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


_ALLOWED_DIAGRAM_TYPES = {"flow", "er", "sequence", "timeline", "bar", "line", "pie"}


def _normalize_diagram_kind(kind: str) -> str:
    value = str(kind or "flow").strip().lower()
    if value == "flowchart":
        value = "flow"
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


def _normalize_diagram_spec_payload(spec: object, *, kind: str) -> dict | None:
    if not isinstance(spec, dict):
        return None
    type_raw = str(spec.get("type") or kind or "flow").strip().lower()
    if type_raw == "flowchart":
        type_raw = "flow"
    if type_raw not in _ALLOWED_DIAGRAM_TYPES:
        return None

    payload = spec.get("data")
    if not isinstance(payload, dict):
        return None

    caption = _clean_text(spec.get("caption") or kind or "diagram", max_chars=60) or "diagram"

    if type_raw == "flow":
        nodes_out: list[dict[str, str]] = []
        edges_out: list[dict[str, str]] = []
        nodes = payload.get("nodes")
        if isinstance(nodes, list):
            seen_ids: set[str] = set()
            for item in nodes:
                if not isinstance(item, dict):
                    continue
                node_id = _clean_text(item.get("id") or item.get("name"), max_chars=24)
                node_text = _clean_text(item.get("text") or node_id, max_chars=48)
                if not node_id or not node_text or node_id in seen_ids:
                    continue
                seen_ids.add(node_id)
                nodes_out.append({"id": node_id, "text": node_text})
                if len(nodes_out) >= 24:
                    break
        if len(nodes_out) < 2:
            return None

        node_ids = {item["id"] for item in nodes_out}
        edges = payload.get("edges")
        if isinstance(edges, list):
            for item in edges:
                if not isinstance(item, dict):
                    continue
                src = _clean_text(item.get("src"), max_chars=24)
                dst = _clean_text(item.get("dst"), max_chars=24)
                if not src or not dst or src not in node_ids or dst not in node_ids:
                    continue
                label = _clean_text(item.get("label"), max_chars=48)
                edges_out.append({"src": src, "dst": dst, "label": label})
                if len(edges_out) >= 40:
                    break
        if not edges_out:
            for idx in range(len(nodes_out) - 1):
                edges_out.append(
                    {
                        "src": nodes_out[idx]["id"],
                        "dst": nodes_out[idx + 1]["id"],
                        "label": "",
                    }
                )
        return {"type": type_raw, "caption": caption, "data": {"nodes": nodes_out, "edges": edges_out}}

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
                attrs: list[str] = []
                if isinstance(attrs_raw, list):
                    for attr in attrs_raw:
                        txt = _clean_text(attr, max_chars=24)
                        if txt:
                            attrs.append(txt)
                        if len(attrs) >= 10:
                            break
                entities_out.append({"name": name, "attributes": attrs or ["attr"]})
                if len(entities_out) >= 20:
                    break
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
                if len(relations_out) >= 24:
                    break
        if not relations_out:
            relations_out.append(
                {
                    "left": entities_out[0]["name"],
                    "right": entities_out[1]["name"],
                    "label": "rel",
                    "cardinality": "",
                }
            )
        return {"type": type_raw, "caption": caption, "data": {"entities": entities_out, "relations": relations_out}}

    if type_raw == "sequence":
        participants_out: list[str] = []
        participants = payload.get("participants")
        if isinstance(participants, list):
            seen: set[str] = set()
            for item in participants:
                name = _clean_text(item, max_chars=24)
                if not name or name in seen:
                    continue
                seen.add(name)
                participants_out.append(name)
                if len(participants_out) >= 10:
                    break
        if len(participants_out) < 2:
            return None

        participant_set = set(participants_out)
        messages_out: list[dict[str, str]] = []
        messages = payload.get("messages")
        if isinstance(messages, list):
            for item in messages:
                if not isinstance(item, dict):
                    continue
                frm = _clean_text(item.get("from"), max_chars=24)
                to = _clean_text(item.get("to"), max_chars=24)
                if not frm or not to or frm not in participant_set or to not in participant_set:
                    continue
                text = _clean_text(item.get("text"), max_chars=60) or "message"
                messages_out.append({"from": frm, "to": to, "text": text})
                if len(messages_out) >= 32:
                    break
        if not messages_out:
            for idx in range(len(participants_out) - 1):
                messages_out.append(
                    {
                        "from": participants_out[idx],
                        "to": participants_out[idx + 1],
                        "text": "message",
                    }
                )
        return {
            "type": type_raw,
            "caption": caption,
            "data": {"participants": participants_out, "messages": messages_out},
        }

    if type_raw == "timeline":
        events_out: list[dict[str, str]] = []
        events = payload.get("events")
        if isinstance(events, list):
            for item in events:
                if not isinstance(item, dict):
                    continue
                t = _clean_text(item.get("time"), max_chars=24)
                label = _clean_text(item.get("label"), max_chars=60)
                if not t or not label:
                    continue
                events_out.append({"time": t, "label": label})
                if len(events_out) >= 16:
                    break
        if len(events_out) < 2:
            return None
        return {"type": type_raw, "caption": caption, "data": {"events": events_out}}

    if type_raw == "bar":
        labels_raw = payload.get("labels")
        values_raw = payload.get("values")
        labels: list[str] = []
        values: list[float] = []
        if isinstance(labels_raw, list):
            labels = [_clean_text(item, max_chars=24) for item in labels_raw]
            labels = [item for item in labels if item][:12]
        if isinstance(values_raw, list):
            for item in values_raw[:12]:
                value = _to_float(item)
                if value is None:
                    continue
                values.append(value)
        count = min(len(labels), len(values))
        if count < 2:
            return None
        return {"type": type_raw, "caption": caption, "data": {"labels": labels[:count], "values": values[:count]}}

    if type_raw == "line":
        labels_raw = payload.get("labels")
        labels: list[str] = []
        if isinstance(labels_raw, list):
            labels = [_clean_text(item, max_chars=24) for item in labels_raw]
            labels = [item for item in labels if item][:24]

        series_out: list[dict[str, object]] = []
        series = payload.get("series")
        if isinstance(series, list):
            for item in series:
                if not isinstance(item, dict):
                    continue
                name = _clean_text(item.get("name"), max_chars=24) or "S"
                raw_values = item.get("values")
                if not isinstance(raw_values, list):
                    continue
                values: list[float] = []
                for raw_value in raw_values[:24]:
                    number = _to_float(raw_value)
                    if number is None:
                        continue
                    values.append(number)
                if len(values) < 2:
                    continue
                series_out.append({"name": name, "values": values})
                if len(series_out) >= 8:
                    break
        if not series_out:
            return None
        if not labels:
            labels = [f"T{i + 1}" for i in range(len(series_out[0]["values"]))]
        target_len = min(len(labels), min(len(item["values"]) for item in series_out))
        if target_len < 2:
            return None
        labels = labels[:target_len]
        normalized_series = [
            {"name": item["name"], "values": item["values"][:target_len]}
            for item in series_out
        ]
        return {"type": type_raw, "caption": caption, "data": {"labels": labels, "series": normalized_series}}

    segments = payload.get("segments")
    segments_out: list[dict[str, object]] = []
    if isinstance(segments, list):
        for item in segments:
            if not isinstance(item, dict):
                continue
            label = _clean_text(item.get("label"), max_chars=24)
            value = _to_float(item.get("value"))
            if not label or value is None:
                continue
            segments_out.append({"label": label, "value": value})
            if len(segments_out) >= 20:
                break
    if len(segments_out) < 2:
        return None
    return {"type": type_raw, "caption": caption, "data": {"segments": segments_out}}


def _diagram_spec_from_llm(prompt: str, kind: str) -> dict | None:
    app_v2 = _app_v2()
    settings = app_v2.get_ollama_settings()
    if not settings.enabled:
        return None
    client = app_v2.OllamaClient(base_url=settings.base_url, model=settings.model, timeout_s=settings.timeout_s)
    if not client.is_running():
        return None

    kind = _normalize_diagram_kind(kind)
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
        "- type must be one of: flow, er, sequence, timeline, bar, line, pie.\n"
        "- flow.data: nodes[{id,text}], edges[{src,dst,label}]\n"
        "- er.data: entities[{name,attributes}], relations[{left,right,label,cardinality}]\n"
        "- sequence.data: participants[], messages[{from,to,text}]\n"
        "- timeline.data: events[{time,label}]\n"
        "- bar.data: labels[], values[]\n"
        "- line.data: labels[], series[{name,values[]}]\n"
        "- pie.data: segments[{label,value}]\n"
        "</constraints>\n"
        f"<requested_type>{kind}</requested_type>\n"
        f"<user_request>{escaped_prompt}</user_request>\n"
        "Return strict JSON now."
    )
    try:
        raw = client.chat(system=system, user=user, temperature=0.2)
    except Exception:
        return None
    data = _extract_json_payload(raw)
    return _normalize_diagram_spec_payload(data, kind=kind)


def _diagram_spec_fallback(prompt: str, kind: str) -> dict:
    app_v2 = _app_v2()
    kind = (kind or "flow").strip().lower()
    raw_prompt = str(prompt or "")
    norm_prompt = raw_prompt.translate(str.maketrans({"：": ":", "，": ",", "；": ";", "。": ".", "、": ","}))
    caption = raw_prompt.strip()[:20] or "diagram"
    sep_pattern = r"[,.;\n]+"

    def _parts(text: str) -> list[str]:
        toks = [p.strip() for p in app_v2.re.split(r"\s*(?:->|=>|>|:|/|\\|\||,|;|\n)+\s*", text or "") if p.strip()]
        if toks:
            return toks
        return [p.strip() for p in app_v2.re.split(sep_pattern, text or "") if p.strip()]

    def _num_pairs(text: str) -> list[tuple[str, float]]:
        out: list[tuple[str, float]] = []
        for name, value in app_v2.re.findall(r"([A-Za-z0-9_\u4e00-\u9fff]{1,16})\s*[:=]\s*(-?\d+(?:\.\d+)?)", text or ""):
            try:
                out.append((name, float(value)))
            except Exception:
                continue
        return out

    if kind in {"flow", "flowchart"}:
        pairs = app_v2.re.findall(r"([A-Za-z0-9_\u4e00-\u9fff]{1,16})\s*(?:->|=>|>)\s*([A-Za-z0-9_\u4e00-\u9fff]{1,16})", norm_prompt)
        nodes = []
        edges = []
        seen = set()
        for src, dst in pairs:
            if src not in seen:
                nodes.append({"id": src, "text": src})
                seen.add(src)
            if dst not in seen:
                nodes.append({"id": dst, "text": dst})
                seen.add(dst)
            edges.append({"src": src, "dst": dst, "label": ""})
        if not nodes:
            parts = _parts(norm_prompt)
            if len(parts) < 2:
                parts = ["Start", "Process", "End"]
            nodes = [{"id": f"n{i+1}", "text": p[:16]} for i, p in enumerate(parts[:8])]
            edges = [{"src": f"n{i+1}", "dst": f"n{i+2}", "label": ""} for i in range(len(nodes) - 1)]
        return {"type": "flow", "caption": caption or "flow", "data": {"nodes": nodes, "edges": edges}}

    if kind == "er":
        entities = []
        relations = []
        for line in norm_prompt.splitlines():
            if ":" not in line:
                continue
            left, right = line.split(":", 1)
            name = left.strip()
            attrs = [a.strip() for a in app_v2.re.split(r"[,;/]", right) if a.strip()]
            if name:
                entities.append({"name": name[:16], "attributes": attrs[:8] or ["attr"]})
        if len(entities) < 2:
            entities = [
                {"name": "EntityA", "attributes": ["field1", "field2"]},
                {"name": "EntityB", "attributes": ["field1", "field2"]},
            ]
        relations.append({"left": entities[0]["name"], "right": entities[1]["name"], "label": "rel", "cardinality": ""})
        return {"type": "er", "caption": caption or "er", "data": {"entities": entities, "relations": relations}}

    if kind == "sequence":
        parts = _parts(norm_prompt)
        actors = parts[:4] or ["Client", "Server", "DB"]
        messages = [{"from": actors[i], "to": actors[i + 1], "text": "message"} for i in range(len(actors) - 1)]
        if not messages:
            messages = [
                {"from": "Client", "to": "Server", "text": "request"},
                {"from": "Server", "to": "DB", "text": "query"},
                {"from": "DB", "to": "Server", "text": "result"},
            ]
        return {"type": "sequence", "caption": caption or "sequence", "data": {"participants": actors, "messages": messages}}

    if kind == "timeline":
        parts = _parts(norm_prompt)
        events = [{"time": f"T{i+1}", "label": p[:24]} for i, p in enumerate(parts[:10])]
        if len(events) < 2:
            events = [{"time": "T1", "label": "phase 1"}, {"time": "T2", "label": "phase 2"}, {"time": "T3", "label": "phase 3"}]
        return {"type": "timeline", "caption": caption or "timeline", "data": {"events": events}}

    if kind == "bar":
        pairs = _num_pairs(norm_prompt)
        if pairs:
            labels = [p[0] for p in pairs[:12]]
            values = [p[1] for p in pairs[:12]]
        else:
            nums = [float(x) for x in app_v2.re.findall(r"-?\d+(?:\.\d+)?", norm_prompt)[:12]]
            values = nums or [12, 18, 9, 22]
            labels = [f"C{i+1}" for i in range(len(values))]
        return {"type": "bar", "caption": caption or "bar", "data": {"labels": labels, "values": values}}

    if kind == "line":
        pairs = _num_pairs(norm_prompt)
        if pairs:
            labels = [p[0] for p in pairs[:20]]
            values = [p[1] for p in pairs[:20]]
        else:
            nums = [float(x) for x in app_v2.re.findall(r"-?\d+(?:\.\d+)?", norm_prompt)[:20]]
            values = nums or [5, 9, 12, 10, 16]
            labels = [f"T{i+1}" for i in range(len(values))]
        series = [{"name": "S1", "values": values}]
        return {"type": "line", "caption": caption or "line", "data": {"labels": labels, "series": series}}

    if kind == "pie":
        pairs = _num_pairs(norm_prompt)
        if pairs:
            segments = [{"label": p[0][:12], "value": p[1]} for p in pairs[:12]]
        else:
            nums = [float(x) for x in app_v2.re.findall(r"-?\d+(?:\.\d+)?", norm_prompt)[:8]]
            if nums:
                segments = [{"label": f"S{i+1}", "value": v} for i, v in enumerate(nums)]
            else:
                segments = [{"label": "A", "value": 40}, {"label": "B", "value": 35}, {"label": "C", "value": 25}]
        return {"type": "pie", "caption": caption or "pie", "data": {"segments": segments}}

    return {"type": "flow", "caption": caption or "flow", "data": {"nodes": [], "edges": []}}


def _diagram_spec_from_prompt(prompt: str, kind: str) -> dict:
    prompt = str(prompt or "").strip()
    kind = _normalize_diagram_kind(kind)
    spec = _diagram_spec_from_llm(prompt, kind)
    if not spec:
        return _diagram_spec_fallback(prompt, kind)
    normalized = _normalize_diagram_spec_payload(spec, kind=kind)
    return normalized if normalized else _diagram_spec_fallback(prompt, kind)


async def diagram_generate(doc_id: str, request: Request) -> dict:
    app_v2 = _app_v2()
    session = app_v2.store.get(doc_id)
    if session is None:
        raise app_v2.HTTPException(status_code=404, detail="document not found")

    data = await request.json()
    prompt = str(data.get("prompt") or "").strip()
    kind = str(data.get("kind") or "flow").strip().lower()
    if not prompt:
        raise app_v2.HTTPException(status_code=400, detail="prompt required")

    spec = _diagram_spec_from_prompt(prompt, kind)
    return {"ok": 1, "spec": spec}


async def inline_ai(doc_id: str, request: Request) -> dict:
    from writing_agent.v2.inline_ai import InlineAIEngine, InlineContext, InlineOperation, ToneStyle

    app_v2 = _app_v2()
    session = app_v2.store.get(doc_id)
    if session is None:
        raise app_v2.HTTPException(status_code=404, detail="document not found")

    data = await request.json()
    operation = data.get("operation")
    selected_text = str(data.get("selected_text", "") or "")
    before_text_raw = str(data.get("before_text", "") or "")
    after_text_raw = str(data.get("after_text", "") or "")
    context_policy = _normalize_inline_context_policy(data.get("context_policy"))
    before_text, after_text, context_meta = _trim_inline_context(
        selected_text=selected_text,
        before_text=before_text_raw,
        after_text=after_text_raw,
        policy=context_policy,
    )

    try:
        op = InlineOperation(operation)
    except ValueError:
        raise app_v2.HTTPException(status_code=400, detail=f"invalid operation: {operation}")

    context = InlineContext(
        selected_text=selected_text,
        before_text=before_text,
        after_text=after_text,
        document_title=data.get("document_title", ""),
        section_title=data.get("section_title"),
        document_type=data.get("document_type"),
        pretrimmed=True,
    )
    engine = InlineAIEngine()

    kwargs = {}
    if op == InlineOperation.CONTINUE:
        kwargs["target_words"] = data.get("target_words", 200)
    elif op == InlineOperation.IMPROVE:
        kwargs["focus"] = data.get("focus", "general")
    elif op == InlineOperation.SUMMARIZE:
        kwargs["max_sentences"] = data.get("max_sentences", 3)
    elif op == InlineOperation.EXPAND:
        kwargs["expansion_ratio"] = data.get("expansion_ratio", 2.0)
    elif op == InlineOperation.CHANGE_TONE:
        tone_str = data.get("target_tone", "professional")
        try:
            kwargs["target_tone"] = ToneStyle(tone_str)
        except ValueError:
            kwargs["target_tone"] = ToneStyle.PROFESSIONAL
    elif op == InlineOperation.ASK_AI:
        kwargs["question"] = data.get("question", "")
    elif op == InlineOperation.EXPLAIN:
        kwargs["detail_level"] = data.get("detail_level", "medium")
    elif op == InlineOperation.TRANSLATE:
        kwargs["target_language"] = data.get("target_language", "en")

    result = await engine.execute_operation(op, context, **kwargs)
    if not result.success:
        raise app_v2.HTTPException(status_code=500, detail=result.error or "operation failed")
    return {
        "ok": 1,
        "generated_text": result.generated_text,
        "operation": result.operation.value,
        "context_meta": context_meta,
    }


async def inline_ai_stream(doc_id: str, request: Request) -> StreamingResponse:
    from writing_agent.v2.inline_ai import InlineAIEngine, InlineContext, InlineOperation, ToneStyle

    app_v2 = _app_v2()
    session = app_v2.store.get(doc_id)
    if session is None:
        raise app_v2.HTTPException(status_code=404, detail="document not found")

    data = await request.json()
    operation = data.get("operation")
    selected_text = str(data.get("selected_text", "") or "")
    before_text_raw = str(data.get("before_text", "") or "")
    after_text_raw = str(data.get("after_text", "") or "")
    context_policy = _normalize_inline_context_policy(data.get("context_policy"))
    before_text, after_text, context_meta = _trim_inline_context(
        selected_text=selected_text,
        before_text=before_text_raw,
        after_text=after_text_raw,
        policy=context_policy,
    )

    try:
        op = InlineOperation(operation)
    except ValueError:
        raise app_v2.HTTPException(status_code=400, detail=f"invalid operation: {operation}")

    context = InlineContext(
        selected_text=selected_text,
        before_text=before_text,
        after_text=after_text,
        document_title=data.get("document_title", ""),
        section_title=data.get("section_title"),
        document_type=data.get("document_type"),
        pretrimmed=True,
    )

    kwargs = {}
    if op == InlineOperation.CONTINUE:
        kwargs["target_words"] = data.get("target_words", 200)
    elif op == InlineOperation.IMPROVE:
        kwargs["focus"] = data.get("focus", "general")
    elif op == InlineOperation.SUMMARIZE:
        kwargs["max_sentences"] = data.get("max_sentences", 3)
    elif op == InlineOperation.EXPAND:
        kwargs["expansion_ratio"] = data.get("expansion_ratio", 2.0)
    elif op == InlineOperation.CHANGE_TONE:
        tone_str = data.get("target_tone", "professional")
        try:
            kwargs["target_tone"] = ToneStyle(tone_str)
        except ValueError:
            kwargs["target_tone"] = ToneStyle.PROFESSIONAL
    elif op == InlineOperation.ASK_AI:
        kwargs["question"] = data.get("question", "")
    elif op == InlineOperation.EXPLAIN:
        kwargs["detail_level"] = data.get("detail_level", "medium")
    elif op == InlineOperation.TRANSLATE:
        kwargs["target_language"] = data.get("target_language", "en")

    engine = InlineAIEngine()

    def emit(event: str, payload: dict) -> str:
        return f"event: {event}\ndata: {app_v2.json.dumps(payload, ensure_ascii=False)}\n\n"

    async def event_generator():
        yield emit("context_meta", context_meta)
        try:
            async for event in engine.execute_operation_stream(op, context, **kwargs):
                yield emit(event.get("type", "message"), event)
        except Exception as e:
            app_v2.logger.error(f"Streaming inline AI failed: {e}", exc_info=True)
            yield emit("error", {"error": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


def _extract_block_text_from_ir(doc_ir_obj, block_id: str) -> str:
    app_v2 = _app_v2()
    try:
        idx = app_v2.doc_ir_build_index(doc_ir_obj)
        block = idx.block_by_id.get(block_id)
        if block is None:
            return ""
        return str(app_v2.doc_ir_render_block_text(block) or "").strip()
    except Exception:
        return ""


async def block_edit(doc_id: str, request: Request) -> dict:
    app_v2 = _app_v2()
    session = app_v2.store.get(doc_id)
    if session is None:
        raise app_v2.HTTPException(status_code=404, detail="document not found")

    data = await request.json()
    if not isinstance(data, dict):
        raise app_v2.HTTPException(status_code=400, detail="body must be object")
    block_id = str(data.get("block_id") or "").strip()
    instruction = str(data.get("instruction") or "").strip()
    if not block_id or not instruction:
        raise app_v2.HTTPException(status_code=400, detail="block_id and instruction required")

    incoming_ir = data.get("doc_ir")
    if isinstance(incoming_ir, dict) and incoming_ir.get("sections") is not None:
        doc_ir = app_v2.doc_ir_from_dict(incoming_ir)
    else:
        doc_ir = app_v2.doc_ir_from_dict(session.doc_ir or {})

    try:
        base_text = app_v2.doc_ir_to_text(doc_ir)
    except Exception:
        base_text = ""
    if base_text.strip():
        session.doc_text = base_text
        session.doc_ir = app_v2.doc_ir_to_dict(doc_ir)
        app_v2._auto_commit_version(session, "auto: before update")

    try:
        updated_ir, meta = await app_v2.apply_block_edit(doc_ir, block_id, instruction)
    except Exception as exc:
        raise app_v2.HTTPException(status_code=500, detail=str(exc))

    session.doc_ir = app_v2.doc_ir_to_dict(updated_ir)
    session.doc_text = app_v2.doc_ir_to_text(updated_ir)
    app_v2._auto_commit_version(session, "auto: after update")
    app_v2.store.put(session)
    return {"ok": 1, "doc_ir": session.doc_ir, "text": session.doc_text, "meta": meta}


async def block_edit_preview(doc_id: str, request: Request) -> dict:
    app_v2 = _app_v2()
    session = app_v2.store.get(doc_id)
    if session is None:
        raise app_v2.HTTPException(status_code=404, detail="document not found")

    data = await request.json()
    if not isinstance(data, dict):
        raise app_v2.HTTPException(status_code=400, detail="body must be object")
    block_id = str(data.get("block_id") or "").strip()
    instruction = str(data.get("instruction") or "").strip()
    if not block_id or not instruction:
        raise app_v2.HTTPException(status_code=400, detail="block_id and instruction required")

    incoming_ir = data.get("doc_ir")
    if isinstance(incoming_ir, dict) and incoming_ir.get("sections") is not None:
        base_ir = app_v2.doc_ir_from_dict(incoming_ir)
    else:
        base_ir = app_v2.doc_ir_from_dict(session.doc_ir or {})

    before_text = _extract_block_text_from_ir(base_ir, block_id)
    if not before_text:
        raise app_v2.HTTPException(status_code=404, detail="block not found")

    variants_raw = data.get("variants")
    variants: list[dict] = []
    if isinstance(variants_raw, list):
        for item in variants_raw:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or item.get("name") or "").strip()
            ins = str(item.get("instruction") or "").strip()
            if ins:
                variants.append({"label": label or f"Variant {len(variants) + 1}", "instruction": ins})
            if len(variants) >= 2:
                break

    if not variants:
        variants = [
            {"label": "Variant A", "instruction": instruction},
            {"label": "Variant B", "instruction": instruction + " Keep structure and maintain concise style."},
        ]

    candidates: list[dict] = []
    for item in variants:
        cand_label = str(item.get("label") or "Variant").strip() or "Variant"
        cand_ins = str(item.get("instruction") or "").strip()
        if not cand_ins:
            continue
        try:
            working_ir = app_v2.doc_ir_from_dict(app_v2.doc_ir_to_dict(base_ir))
            updated_ir, meta = await app_v2.apply_block_edit(working_ir, block_id, cand_ins)
            cand_after = _extract_block_text_from_ir(updated_ir, block_id)
            candidates.append(
                {
                    "label": cand_label,
                    "instruction": cand_ins,
                    "doc_ir": app_v2.doc_ir_to_dict(updated_ir),
                    "text": app_v2.doc_ir_to_text(updated_ir),
                    "selected_before": before_text,
                    "selected_after": cand_after,
                    "diff": app_v2.doc_ir_diff(base_ir, updated_ir),
                    "meta": meta,
                }
            )
        except Exception as exc:
            candidates.append({"label": cand_label, "instruction": cand_ins, "error": str(exc), "selected_before": before_text})
    return {"ok": 1, "before": before_text, "candidates": candidates}


class EditingService:
    async def doc_ir_ops(self, doc_id: str, request: Request) -> dict:
        return await doc_ir_ops(doc_id, request)

    async def doc_ir_diff(self, doc_id: str, request: Request) -> dict:
        return await doc_ir_diff(doc_id, request)

    async def render_figure(self, request: Request) -> dict:
        return await render_figure(request)

    async def diagram_generate(self, doc_id: str, request: Request) -> dict:
        return await diagram_generate(doc_id, request)

    async def inline_ai(self, doc_id: str, request: Request) -> dict:
        return await inline_ai(doc_id, request)

    async def inline_ai_stream(self, doc_id: str, request: Request) -> StreamingResponse:
        return await inline_ai_stream(doc_id, request)

    async def block_edit(self, doc_id: str, request: Request) -> dict:
        return await block_edit(doc_id, request)

    async def block_edit_preview(self, doc_id: str, request: Request) -> dict:
        return await block_edit_preview(doc_id, request)


service = EditingService()


@router.post("/api/doc/{doc_id}/doc_ir/ops")
async def doc_ir_ops_flow(doc_id: str, request: Request) -> dict:
    return await service.doc_ir_ops(doc_id, request)


@router.post("/api/doc/{doc_id}/doc_ir/diff")
async def doc_ir_diff_flow(doc_id: str, request: Request) -> dict:
    return await service.doc_ir_diff(doc_id, request)


@router.post("/api/figure/render")
async def render_figure_flow(request: Request) -> dict:
    return await service.render_figure(request)


@router.post("/api/doc/{doc_id}/diagram/generate")
async def diagram_generate_flow(doc_id: str, request: Request) -> dict:
    return await service.diagram_generate(doc_id, request)


@router.post("/api/doc/{doc_id}/inline-ai")
async def inline_ai_flow(doc_id: str, request: Request) -> dict:
    return await service.inline_ai(doc_id, request)


@router.post("/api/doc/{doc_id}/inline-ai/stream")
async def inline_ai_stream_flow(doc_id: str, request: Request) -> StreamingResponse:
    return await service.inline_ai_stream(doc_id, request)


@router.post("/api/doc/{doc_id}/block-edit")
async def block_edit_flow(doc_id: str, request: Request) -> dict:
    return await service.block_edit(doc_id, request)


@router.post("/api/doc/{doc_id}/block-edit/preview")
async def block_edit_preview_flow(doc_id: str, request: Request) -> dict:
    return await service.block_edit_preview(doc_id, request)
