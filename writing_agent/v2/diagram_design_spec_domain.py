"""Diagram spec construction and normalization helpers."""

from __future__ import annotations

import re
from typing import Any


def _base():
    from writing_agent.v2 import diagram_design as base
    return base


def _clean_text(value: object, *, max_chars: int = 48) -> str:
    return _base()._clean_text(value, max_chars=max_chars)


def _slug_id(text: str, fallback: str) -> str:
    return _base()._slug_id(text, fallback)


def infer_node_kind(label: str, *, explicit: str = "") -> str:
    return _base().infer_node_kind(label, explicit=explicit)


def infer_lane_id(label: str, *, explicit: str = "") -> str:
    return _base().infer_lane_id(label, explicit=explicit)


def _lane_title(lane_id: str) -> str:
    return _base()._lane_title(lane_id)


def _lane_profiles() -> list[dict[str, Any]]:
    return list(_base()._LANE_PROFILES)


def _tokenize_parts(text: str) -> list[str]:
    raw = str(text or "")
    parts = [
        p.strip()
        for p in re.split(r"\s*(?:->|=>|→|>|/|\\|\||,|;|；|，|\n|\r)+\s*", raw)
        if p and p.strip()
    ]
    deduped: list[str] = []
    seen: set[str] = set()
    for part in parts:
        cleaned = _clean_text(part, max_chars=28)
        if len(cleaned) < 2:
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        deduped.append(cleaned)
    return deduped[:12]


def _phase_lanes(count: int) -> list[str]:
    if count <= 4:
        return ["输入准备", "核心处理", "结果输出"]
    return ["任务输入", "分析处理", "结果校核"]

def _normalize_lanes(payload: dict[str, Any], nodes: list[dict[str, Any]], *, kind: str) -> list[dict[str, str]]:
    lanes_in = payload.get("lanes") if isinstance(payload, dict) else None
    lanes_out: list[dict[str, str]] = []
    seen: set[str] = set()
    if isinstance(lanes_in, list):
        for idx, lane in enumerate(lanes_in):
            if isinstance(lane, dict):
                lane_id = _slug_id(_clean_text(lane.get("id") or lane.get("title") or f"lane_{idx+1}", max_chars=24), f"lane_{idx+1}")
                title = _clean_text(lane.get("title") or lane_id, max_chars=24)
            else:
                title = _clean_text(lane, max_chars=24)
                lane_id = _slug_id(title, f"lane_{idx+1}")
            if not lane_id or lane_id in seen:
                continue
            seen.add(lane_id)
            lanes_out.append({"id": lane_id, "title": title or _lane_title(lane_id)})
    for node in nodes:
        lane_id = _clean_text(node.get("lane"), max_chars=24)
        if not lane_id:
            continue
        lane_slug = _slug_id(lane_id, lane_id)
        if lane_slug in seen:
            continue
        seen.add(lane_slug)
        lanes_out.append({"id": lane_slug, "title": _lane_title(lane_id) if lane_id in {p['id'] for p in _lane_profiles()} else lane_id})
    if not lanes_out and kind == "architecture":
        desired: list[str] = []
        for node in nodes:
            lane_id = infer_lane_id(str(node.get("label") or ""), explicit=str(node.get("lane") or ""))
            node["lane"] = lane_id
            if lane_id not in desired:
                desired.append(lane_id)
        if not desired:
            desired = ["access", "orchestration", "capability", "data"]
        for lane_id in desired:
            lanes_out.append({"id": lane_id, "title": _lane_title(lane_id)})
    if not lanes_out and kind == "flow" and len(nodes) >= 5:
        titles = _phase_lanes(len(nodes))
        cut1 = max(1, round(len(nodes) / 3))
        cut2 = max(cut1 + 1, round(len(nodes) * 2 / 3))
        for idx, node in enumerate(nodes):
            if idx < cut1:
                node["lane"] = titles[0]
            elif idx < cut2:
                node["lane"] = titles[1]
            else:
                node["lane"] = titles[2]
        lanes_out = [{"id": title, "title": title} for title in titles]
    return lanes_out


def _normalize_flowish_data(payload: dict[str, Any], *, kind: str) -> dict[str, Any]:
    nodes_out: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for idx, item in enumerate(payload.get("nodes") if isinstance(payload.get("nodes"), list) else []):
        if isinstance(item, dict):
            label = _clean_text(item.get("label") or item.get("text") or item.get("name") or item.get("title") or "", max_chars=30)
            node_id = _slug_id(_clean_text(item.get("id") or label or f"n{idx+1}", max_chars=24), f"n{idx+1}")
            subtitle = _clean_text(item.get("subtitle") or item.get("desc") or item.get("note") or "", max_chars=34)
            lane = _clean_text(item.get("lane") or item.get("group") or item.get("layer") or item.get("domain") or "", max_chars=24)
            node_kind = infer_node_kind(label, explicit=_clean_text(item.get("kind") or item.get("role") or item.get("category") or "", max_chars=16))
        else:
            label = _clean_text(item, max_chars=30)
            node_id = f"n{idx+1}"
            subtitle = ""
            lane = ""
            node_kind = infer_node_kind(label)
        if not label or node_id in seen_ids:
            continue
        seen_ids.add(node_id)
        nodes_out.append({"id": node_id, "label": label, "subtitle": subtitle, "lane": lane, "kind": node_kind})
    edges_out: list[dict[str, str]] = []
    node_ids = {node["id"] for node in nodes_out}
    for item in payload.get("edges") if isinstance(payload.get("edges"), list) else []:
        if isinstance(item, dict):
            src = _slug_id(_clean_text(item.get("src") or item.get("from") or item.get("source") or "", max_chars=24), "")
            dst = _slug_id(_clean_text(item.get("dst") or item.get("to") or item.get("target") or "", max_chars=24), "")
            label = _clean_text(item.get("label") or item.get("text") or "", max_chars=28)
            style = _clean_text(item.get("style") or "", max_chars=12).lower()
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            src = _slug_id(_clean_text(item[0], max_chars=24), "")
            dst = _slug_id(_clean_text(item[1], max_chars=24), "")
            label = _clean_text(item[2] if len(item) >= 3 else "", max_chars=28)
            style = ""
        else:
            continue
        if not src or not dst or src not in node_ids or dst not in node_ids:
            continue
        edges_out.append({"from": src, "to": dst, "label": label, "style": style or "solid"})
    if not edges_out and len(nodes_out) >= 2:
        for idx in range(len(nodes_out) - 1):
            edges_out.append({"from": nodes_out[idx]["id"], "to": nodes_out[idx + 1]["id"], "label": "", "style": "solid"})
    lanes_out = _normalize_lanes(payload, nodes_out, kind=kind)
    if lanes_out:
        lane_map = {lane["id"]: lane for lane in lanes_out}
        for node in nodes_out:
            lane_id = _clean_text(node.get("lane"), max_chars=24)
            if lane_id in lane_map:
                node["lane"] = lane_id
            elif lane_id:
                slug = _slug_id(lane_id, lane_id)
                node["lane"] = slug
                if slug not in lane_map:
                    lane_map[slug] = {"id": slug, "title": lane_id}
                    lanes_out.append(lane_map[slug])
    return {"nodes": nodes_out, "edges": edges_out, **({"lanes": lanes_out} if lanes_out else {})}


def _normalize_sequence_data(payload: dict[str, Any]) -> dict[str, Any]:
    participants_out: list[str] = []
    seen: set[str] = set()
    for item in payload.get("participants") if isinstance(payload.get("participants"), list) else []:
        if isinstance(item, dict):
            label = _clean_text(item.get("label") or item.get("name") or item.get("id") or "", max_chars=20)
        else:
            label = _clean_text(item, max_chars=20)
        if not label or label in seen:
            continue
        seen.add(label)
        participants_out.append(label)
    messages_out: list[dict[str, str]] = []
    participant_set = set(participants_out)
    for item in payload.get("messages") if isinstance(payload.get("messages"), list) else []:
        if not isinstance(item, dict):
            continue
        frm = _clean_text(item.get("from") or item.get("src") or item.get("source") or "", max_chars=20)
        to = _clean_text(item.get("to") or item.get("dst") or item.get("target") or "", max_chars=20)
        label = _clean_text(item.get("label") or item.get("text") or "", max_chars=36)
        style = _clean_text(item.get("style") or item.get("line") or "", max_chars=12).lower()
        if not frm or not to or (participant_set and (frm not in participant_set or to not in participant_set)):
            continue
        if not style and _base()._RETURN_LABEL_RE.search(label):
            style = "dashed"
        messages_out.append({"from": frm, "to": to, "label": label or "message", "style": style or "solid"})
    if not messages_out and len(participants_out) >= 2:
        defaults = ["提交任务", "编排请求", "返回证据", "输出草稿", "返回结果"]
        for idx in range(len(participants_out) - 1):
            messages_out.append(
                {
                    "from": participants_out[idx],
                    "to": participants_out[idx + 1],
                    "label": defaults[min(idx, len(defaults) - 1)],
                    "style": "solid",
                }
            )
    return {"participants": participants_out, "messages": messages_out}


def _suggest_flow_spec(*, caption: str, prompt: str, section_title: str) -> dict[str, Any]:
    source = " ".join(part for part in [prompt, caption, section_title] if part)
    steps = _tokenize_parts(source)
    if len(steps) < 4:
        if re.search(r"(论文|写作|研究|学术|文献)", source, re.IGNORECASE):
            steps = ["选题界定", "证据检索", "结构规划", "章节起草", "质量校核", "导出归档"]
        elif re.search(r"(系统|平台|服务|架构)", source, re.IGNORECASE):
            steps = ["需求输入", "任务编排", "能力调用", "结果校核", "文档输出"]
        else:
            steps = ["问题识别", "输入收集", "核心处理", "结果验证", "交付输出"]
    lanes = _phase_lanes(len(steps))
    nodes: list[dict[str, Any]] = []
    for idx, label in enumerate(steps[:8]):
        lane = lanes[0] if idx < max(1, round(len(steps) / 3)) else (lanes[1] if idx < max(2, round(len(steps) * 2 / 3)) else lanes[2])
        nodes.append({"id": f"n{idx+1}", "label": label, "subtitle": "", "lane": lane, "kind": infer_node_kind(label)})
    edges = [{"from": nodes[idx]["id"], "to": nodes[idx + 1]["id"], "label": "", "style": "solid"} for idx in range(len(nodes) - 1)]
    return {"type": "flow", "caption": caption or section_title or "核心流程图", "data": {"lanes": [{"id": lane, "title": lane} for lane in lanes], "nodes": nodes, "edges": edges}}


def _extract_numeric_pairs(text: str) -> list[tuple[str, float]]:
    pairs: list[tuple[str, float]] = []
    for name, value in re.findall(r"([A-Za-z0-9_一-鿿][A-Za-z0-9_\-一-鿿\s]{0,24})\s*[:=]\s*(-?\d+(?:\.\d+)?)", text or ""):
        clean_name = _clean_text(name, max_chars=22)
        if not clean_name:
            continue
        try:
            pairs.append((clean_name, float(value)))
        except Exception:
            continue
    return pairs[:12]


def _extract_numbers(text: str, *, limit: int = 12) -> list[float]:
    values: list[float] = []
    for token in re.findall(r"-?\d+(?:\.\d+)?", text or "")[:limit]:
        try:
            values.append(float(token))
        except Exception:
            continue
    return values


def _extract_timeline_events(text: str) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    patterns = [
        r"((?:19|20)\d{2}(?:[./-]\d{1,2})?)\s*[:：-]\s*([^,;\n]{2,36})",
        r"(\u9636\u6bb5\d+|Step\s*\d+|Phase\s*\d+)\s*[:：-]\s*([^,;\n]{2,36})",
    ]
    for pattern in patterns:
        for tm, label in re.findall(pattern, text or "", flags=re.IGNORECASE):
            events.append({"time": _clean_text(tm, max_chars=16), "label": _clean_text(label, max_chars=30)})
    if events:
        deduped: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for event in events:
            key = (event["time"], event["label"])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(event)
        return deduped[:8]
    tokens = _tokenize_parts(text)
    if len(tokens) >= 3:
        return [{"time": f"Stage {idx+1}", "label": token} for idx, token in enumerate(tokens[:6])]
    return []


def _suggest_architecture_spec(*, caption: str, prompt: str, section_title: str) -> dict[str, Any]:
    tokens = _tokenize_parts(prompt)
    if len(tokens) >= 5:
        nodes = []
        for idx, token in enumerate(tokens[:12]):
            lane = infer_lane_id(token)
            nodes.append({"id": f"n{idx+1}", "label": token, "subtitle": "", "lane": lane, "kind": infer_node_kind(token)})
        lanes = _normalize_lanes({}, nodes, kind="architecture")
    else:
        nodes = [
            {"id": "u1", "label": "用户门户", "subtitle": "课题提交/状态查看", "lane": "access", "kind": "actor"},
            {"id": "u2", "label": "统一认证", "subtitle": "身份与权限控制", "lane": "access", "kind": "control"},
            {"id": "o1", "label": "任务编排中心", "subtitle": "章节拆解/依赖调度", "lane": "orchestration", "kind": "service"},
            {"id": "o2", "label": "提示策略库", "subtitle": "范式锁/写作合同", "lane": "orchestration", "kind": "control"},
            {"id": "c1", "label": "检索与证据服务", "subtitle": "RAG/事实包生成", "lane": "capability", "kind": "service"},
            {"id": "c2", "label": "模型适配网关", "subtitle": "多模型路由与限流", "lane": "capability", "kind": "service"},
            {"id": "c3", "label": "校核与重写器", "subtitle": "元指令拦截/一致性校验", "lane": "capability", "kind": "decision"},
            {"id": "d1", "label": "科研知识库", "subtitle": "文献元数据/摘要索引", "lane": "data", "kind": "data"},
            {"id": "d2", "label": "向量索引与缓存", "subtitle": "召回缓存/临时事实包", "lane": "data", "kind": "data"},
            {"id": "g1", "label": "日志审计", "subtitle": "链路事件/失败原因", "lane": "governance", "kind": "control"},
        ]
        lanes = [{"id": item["id"], "title": item["title"]} for item in _lane_profiles() if item["id"] in {"access", "orchestration", "capability", "data", "governance"}]
    edges = [
        {"from": "u1", "to": "u2", "label": "用户请求", "style": "solid"},
        {"from": "u2", "to": "o1", "label": "任务入列", "style": "solid"},
        {"from": "o1", "to": "o2", "label": "策略装配", "style": "solid"},
        {"from": "o1", "to": "c1", "label": "证据计划", "style": "solid"},
        {"from": "o1", "to": "c2", "label": "生成调用", "style": "solid"},
        {"from": "c1", "to": "d1", "label": "语义检索", "style": "solid"},
        {"from": "c1", "to": "d2", "label": "向量召回", "style": "solid"},
        {"from": "c2", "to": "c3", "label": "草稿输出", "style": "solid"},
        {"from": "c3", "to": "g1", "label": "审计记录", "style": "dashed"},
    ] if len(tokens) < 5 else [{"from": nodes[idx]["id"], "to": nodes[idx + 1]["id"], "label": "", "style": "solid"} for idx in range(len(nodes) - 1)]
    return {"type": "architecture", "caption": caption or section_title or "系统总体架构", "data": {"lanes": lanes, "nodes": nodes, "edges": edges}}


def _suggest_sequence_spec(*, caption: str, prompt: str, section_title: str) -> dict[str, Any]:
    participants = _tokenize_parts(prompt)
    if len(participants) < 3:
        participants = ["relates", "API??", "?????", "????", "????", "????", "????"]
    participants = participants[:8]
    default_labels = ["????", "?????", "????", "????", "????", "????", "????"]
    messages = []
    for idx in range(len(participants) - 1):
        messages.append(
            {
                "from": participants[idx],
                "to": participants[idx + 1],
                "label": default_labels[min(idx, len(default_labels) - 1)],
                "style": "solid",
            }
        )
    if len(participants) >= 3:
        messages.append({"from": participants[-1], "to": participants[0], "label": "????", "style": "dashed"})
    return {"type": "sequence", "caption": caption or section_title or "??????", "data": {"participants": participants, "messages": messages}}


def _suggest_er_spec(*, caption: str, prompt: str, section_title: str) -> dict[str, Any]:
    tokens = [token for token in _tokenize_parts(prompt or caption or section_title) if len(token) >= 2]
    if len(tokens) < 3:
        tokens = ["User", "Project", "Document"]
    entities = []
    for idx, token in enumerate(tokens[:5]):
        attrs = ["id", f"{_slug_id(token, f'e{idx+1}').lower()}_name", "status"]
        entities.append({"name": token, "attributes": attrs})
    relations = []
    for idx in range(len(entities) - 1):
        relations.append({"left": entities[idx]["name"], "right": entities[idx + 1]["name"], "label": "relates", "cardinality": "1:N"})
    return {"type": "er", "caption": caption or section_title or "Entity Relationship Graph", "data": {"entities": entities, "relations": relations}}


def _suggest_bar_spec(*, caption: str, prompt: str, section_title: str) -> dict[str, Any]:
    pairs = _extract_numeric_pairs(prompt)
    if pairs:
        labels = [name for name, _ in pairs[:8]]
        values = [value for _, value in pairs[:8]]
    else:
        labels = _tokenize_parts(prompt or caption or section_title)[:5]
        if len(labels) < 3:
            labels = ["Metric A", "Metric B", "Metric C", "Metric D"]
        values = [18 + idx * 6 for idx in range(len(labels))]
    return {"type": "bar", "caption": caption or section_title or "Comparison Metrics", "data": {"labels": labels, "values": values}}


def _suggest_line_spec(*, caption: str, prompt: str, section_title: str) -> dict[str, Any]:
    pairs = _extract_numeric_pairs(prompt)
    if pairs:
        labels = [name for name, _ in pairs[:8]]
        values = [value for _, value in pairs[:8]]
    else:
        labels = [f"T{idx+1}" for idx in range(5)]
        values = [12, 18, 22, 27, 31]
    return {
        "type": "line",
        "caption": caption or section_title or "Trend Analysis",
        "data": {"labels": labels, "series": [{"name": "Series A", "values": values}]},
    }


def _suggest_pie_spec(*, caption: str, prompt: str, section_title: str) -> dict[str, Any]:
    pairs = _extract_numeric_pairs(prompt)
    segments: list[dict[str, float | str]] = []
    if pairs:
        for name, value in pairs[:6]:
            segments.append({"label": name, "value": max(0.0, value)})
    else:
        labels = _tokenize_parts(prompt or caption or section_title)[:4]
        if len(labels) < 3:
            labels = ["Dimension A", "Dimension B", "Dimension C", "Dimension D"]
        weights = [35, 28, 22, 15][: len(labels)]
        segments = [{"label": label, "value": weights[idx]} for idx, label in enumerate(labels)]
    return {"type": "pie", "caption": caption or section_title or "Composition Share", "data": {"segments": segments}}


def _suggest_timeline_spec(*, caption: str, prompt: str, section_title: str) -> dict[str, Any]:
    events = _extract_timeline_events(prompt or caption or section_title)
    if not events:
        events = [
            {"time": "Stage 1", "label": "Problem Scoping"},
            {"time": "Stage 2", "label": "Evidence Collection"},
            {"time": "Stage 3", "label": "Analysis and Discussion"},
            {"time": "Stage 4", "label": "Conclusion and Delivery"},
        ]
    return {"type": "timeline", "caption": caption or section_title or "Research Timeline", "data": {"events": events}}



__all__ = [name for name in globals() if not name.startswith("__")]
