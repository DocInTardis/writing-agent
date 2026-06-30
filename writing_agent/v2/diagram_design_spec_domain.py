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
        messages_out.append({"from": frm, "to": to, "label": label or "消息", "style": style or "solid"})
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
        return [{"time": f"阶段{idx+1}", "label": token} for idx, token in enumerate(tokens[:6])]
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
        participants = ["用户", "网关", "编排服务", "生成服务", "校核服务", "文档服务", "存储"]
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
        messages.append({"from": participants[-1], "to": participants[0], "label": "返回结果", "style": "dashed"})
    return {"type": "sequence", "caption": caption or section_title or "时序图", "data": {"participants": participants, "messages": messages}}


def _suggest_er_spec(*, caption: str, prompt: str, section_title: str) -> dict[str, Any]:
    tokens = [token for token in _tokenize_parts(prompt or caption or section_title) if len(token) >= 2]
    if len(tokens) < 3:
        tokens = ["用户", "项目", "文档"]
    entities = []
    for idx, token in enumerate(tokens[:5]):
        attrs = ["id", f"{_slug_id(token, f'e{idx+1}').lower()}_name", "status"]
        entities.append({"name": token, "attributes": attrs})
    relations = []
    for idx in range(len(entities) - 1):
        relations.append({"left": entities[idx]["name"], "right": entities[idx + 1]["name"], "label": "关联", "cardinality": "1:N"})
    return {"type": "er", "caption": caption or section_title or "实体关系图", "data": {"entities": entities, "relations": relations}}


def _suggest_bar_spec(*, caption: str, prompt: str, section_title: str) -> dict[str, Any]:
    pairs = _extract_numeric_pairs(prompt)
    if pairs:
        labels = [name for name, _ in pairs[:8]]
        values = [value for _, value in pairs[:8]]
    else:
        labels = _tokenize_parts(prompt or caption or section_title)[:5]
        if len(labels) < 3:
            labels = ["指标A", "指标B", "指标C", "指标D"]
        values = [18 + idx * 6 for idx in range(len(labels))]
    return {"type": "bar", "caption": caption or section_title or "柱状图", "data": {"labels": labels, "values": values}}


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
        "caption": caption or section_title or "趋势分析图",
        "data": {"labels": labels, "series": [{"name": "序列A", "values": values}]},
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
            labels = ["维度A", "维度B", "维度C", "维度D"]
        weights = [35, 28, 22, 15][: len(labels)]
        segments = [{"label": label, "value": weights[idx]} for idx, label in enumerate(labels)]
    return {"type": "pie", "caption": caption or section_title or "占比分析图", "data": {"segments": segments}}


def _suggest_timeline_spec(*, caption: str, prompt: str, section_title: str) -> dict[str, Any]:
    events = _extract_timeline_events(prompt or caption or section_title)
    if not events:
        events = [
            {"time": "阶段1", "label": "问题界定"},
            {"time": "阶段2", "label": "证据收集"},
            {"time": "阶段3", "label": "分析论证"},
            {"time": "阶段4", "label": "结论交付"},
        ]
    return {"type": "timeline", "caption": caption or section_title or "时间线", "data": {"events": events}}


def _normalize_state_data(payload: dict[str, Any]) -> dict[str, Any]:
    states_out: list[dict[str, str]] = []
    seen: set[str] = set()
    for idx, item in enumerate(payload.get("states") if isinstance(payload.get("states"), list) else []):
        if isinstance(item, dict):
            label = _clean_text(item.get("label") or item.get("name") or item.get("id") or f"State {idx+1}", max_chars=28)
            state_id = _slug_id(_clean_text(item.get("id") or label, max_chars=24), f"s{idx+1}")
            state_kind = _clean_text(item.get("kind"), max_chars=12).lower()
        else:
            label = _clean_text(item, max_chars=28)
            state_id = _slug_id(label, f"s{idx+1}")
            state_kind = ""
        if not label or state_id in seen:
            continue
        seen.add(state_id)
        node: dict[str, str] = {"id": state_id, "label": label}
        if state_kind:
            node["kind"] = state_kind
        states_out.append(node)
    transitions_out: list[dict[str, str]] = []
    state_ids = {str(item["id"]) for item in states_out}
    for item in payload.get("transitions") if isinstance(payload.get("transitions"), list) else []:
        if not isinstance(item, dict):
            continue
        src = _slug_id(_clean_text(item.get("from") or item.get("src"), max_chars=24), "")
        dst = _slug_id(_clean_text(item.get("to") or item.get("dst"), max_chars=24), "")
        label = _clean_text(item.get("label"), max_chars=24)
        if src in state_ids and dst in state_ids:
            edge = {"from": src, "to": dst}
            if label:
                edge["label"] = label
            transitions_out.append(edge)
    if not transitions_out and len(states_out) >= 2:
        transitions_out = [{"from": states_out[idx]["id"], "to": states_out[idx + 1]["id"]} for idx in range(len(states_out) - 1)]
    return {"states": states_out[:12], "transitions": transitions_out[:24]}


def _normalize_class_data(payload: dict[str, Any]) -> dict[str, Any]:
    classes_out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in payload.get("classes") if isinstance(payload.get("classes"), list) else []:
        if not isinstance(item, dict):
            continue
        name = _clean_text(item.get("name") or item.get("title"), max_chars=28)
        if not name or name in seen:
            continue
        seen.add(name)
        attrs = [_clean_text(attr, max_chars=26) for attr in (item.get("attributes") if isinstance(item.get("attributes"), list) else [])[:8]]
        methods = [_clean_text(method, max_chars=26) for method in (item.get("methods") if isinstance(item.get("methods"), list) else [])[:8]]
        classes_out.append({
            "name": name,
            "attributes": [attr for attr in attrs if attr],
            "methods": [method for method in methods if method],
        })
    class_names = {str(item["name"]) for item in classes_out}
    relations_out: list[dict[str, str]] = []
    for item in payload.get("relations") if isinstance(payload.get("relations"), list) else []:
        if not isinstance(item, dict):
            continue
        src = _clean_text(item.get("from") or item.get("left"), max_chars=28)
        dst = _clean_text(item.get("to") or item.get("right"), max_chars=28)
        label = _clean_text(item.get("label"), max_chars=24)
        kind = _clean_text(item.get("kind") or item.get("type"), max_chars=16).lower()
        if src in class_names and dst in class_names:
            relation = {"from": src, "to": dst}
            if label:
                relation["label"] = label
            if kind:
                relation["kind"] = kind
            relations_out.append(relation)
    return {"classes": classes_out[:8], "relations": relations_out[:16]}


def _normalize_gantt_data(payload: dict[str, Any]) -> dict[str, Any]:
    tasks_out: list[dict[str, str]] = []
    for idx, item in enumerate(payload.get("tasks") if isinstance(payload.get("tasks"), list) else []):
        if not isinstance(item, dict):
            continue
        task = _clean_text(item.get("task") or item.get("name") or item.get("label") or f"Task {idx+1}", max_chars=30)
        start = _clean_text(item.get("start") or item.get("begin"), max_chars=16)
        end = _clean_text(item.get("end") or item.get("finish"), max_chars=16)
        owner = _clean_text(item.get("owner"), max_chars=18)
        status = _clean_text(item.get("status"), max_chars=14)
        if not task:
            continue
        row = {"task": task, "start": start or f"P{idx+1}", "end": end or f"P{idx+2}"}
        if owner:
            row["owner"] = owner
        if status:
            row["status"] = status
        tasks_out.append(row)
    return {"tasks": tasks_out[:12]}


def _suggest_state_spec(*, caption: str, prompt: str, section_title: str) -> dict[str, Any]:
    tokens = [token for token in _tokenize_parts(prompt or caption or section_title) if len(token) >= 2]
    if len(tokens) < 3:
        tokens = ["草稿", "审核中", "已通过", "已发布"]
    states = []
    for idx, token in enumerate(tokens[:6]):
        state = {"id": _slug_id(token, f"s{idx+1}"), "label": token}
        if idx == 0:
            state["kind"] = "start"
        elif idx == min(len(tokens[:6]) - 1, 5):
            state["kind"] = "end"
        states.append(state)
    transitions = []
    for idx in range(len(states) - 1):
        transitions.append({"from": states[idx]["id"], "to": states[idx + 1]["id"], "label": "提交" if idx == 0 else "流转"})
    return {"type": "state", "caption": caption or section_title or "状态图", "data": {"states": states, "transitions": transitions}}


def _suggest_class_spec(*, caption: str, prompt: str, section_title: str) -> dict[str, Any]:
    tokens = [token for token in _tokenize_parts(prompt or caption or section_title) if len(token) >= 2]
    if len(tokens) < 3:
        tokens = ["项目", "文档", "引用"]
    classes = []
    for idx, token in enumerate(tokens[:4]):
        classes.append(
            {
                "name": token,
                "attributes": ["id", f"{_slug_id(token, f'c{idx+1}').lower()}Name", "status"],
                "methods": ["create()", "update()"],
            }
        )
    relations = []
    for idx in range(len(classes) - 1):
        relations.append({"from": classes[idx]["name"], "to": classes[idx + 1]["name"], "label": "关联", "kind": "association"})
    return {"type": "class", "caption": caption or section_title or "类图", "data": {"classes": classes, "relations": relations}}


def _suggest_gantt_spec(*, caption: str, prompt: str, section_title: str) -> dict[str, Any]:
    events = _extract_timeline_events(prompt or caption or section_title)
    tasks: list[dict[str, str]] = []
    if events:
        for idx, item in enumerate(events[:6]):
            tasks.append(
                {
                    "task": _clean_text(item.get("label"), max_chars=28),
                    "start": _clean_text(item.get("time"), max_chars=16) or f"P{idx+1}",
                    "end": f"P{idx+2}",
                    "status": "planned" if idx < 2 else "active",
                }
            )
    if len(tasks) < 3:
        tasks = [
            {"task": "问题界定", "start": "第1月", "end": "第2月", "status": "已完成"},
            {"task": "证据收集", "start": "第2月", "end": "第3月", "status": "进行中"},
            {"task": "系统实现", "start": "第3月", "end": "第4月", "status": "进行中"},
            {"task": "评估与交付", "start": "第4月", "end": "第5月", "status": "计划中"},
        ]
    return {"type": "gantt", "caption": caption or section_title or "甘特图", "data": {"tasks": tasks}}


def _normalize_mindmap_data(payload: dict[str, Any]) -> dict[str, Any]:
    center = _clean_text(payload.get("center") or payload.get("root") or payload.get("topic"), max_chars=28)
    branches_out: list[dict[str, Any]] = []
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
    return {"center": center, "branches": branches_out[:8]}


def _normalize_quadrant_data(payload: dict[str, Any]) -> dict[str, Any]:
    x_axis = _clean_text(payload.get("x_axis") or payload.get("xLabel"), max_chars=18) or "影响力"
    y_axis = _clean_text(payload.get("y_axis") or payload.get("yLabel"), max_chars=18) or "可行性"
    items_out: list[dict[str, Any]] = []
    for item in payload.get("items") if isinstance(payload.get("items"), list) else []:
        if not isinstance(item, dict):
            continue
        label = _clean_text(item.get("label") or item.get("name"), max_chars=20)
        if not label:
            continue
        try:
            x = float(item.get("x", 0.5))
            y = float(item.get("y", 0.5))
        except Exception:
            x = 0.5
            y = 0.5
        items_out.append({"label": label, "x": max(0.0, min(1.0, x)), "y": max(0.0, min(1.0, y)), "quadrant": _clean_text(item.get("quadrant"), max_chars=18)})
    return {"x_axis": x_axis, "y_axis": y_axis, "items": items_out[:12]}


def _normalize_radar_data(payload: dict[str, Any]) -> dict[str, Any]:
    axes = [_clean_text(item, max_chars=18) for item in (payload.get("axes") if isinstance(payload.get("axes"), list) else [])[:8]]
    axes = [item for item in axes if item]
    series_out: list[dict[str, Any]] = []
    for item in payload.get("series") if isinstance(payload.get("series"), list) else []:
        if not isinstance(item, dict):
            continue
        name = _clean_text(item.get("name") or item.get("label") or "序列", max_chars=18)
        values: list[float] = []
        for value in (item.get("values") if isinstance(item.get("values"), list) else [])[: len(axes) or 8]:
            try:
                values.append(max(0.0, min(100.0, float(value))))
            except Exception:
                continue
        if name and values:
            series_out.append({"name": name, "values": values})
    return {"axes": axes, "series": series_out[:3]}


def _normalize_scatter_data(payload: dict[str, Any]) -> dict[str, Any]:
    x_label = _clean_text(payload.get("x_label") or payload.get("xLabel"), max_chars=18) or "X"
    y_label = _clean_text(payload.get("y_label") or payload.get("yLabel"), max_chars=18) or "Y"
    points_out: list[dict[str, Any]] = []
    for item in payload.get("points") if isinstance(payload.get("points"), list) else []:
        if not isinstance(item, dict):
            continue
        label = _clean_text(item.get("label") or item.get("name"), max_chars=18)
        try:
            x = float(item.get("x"))
            y = float(item.get("y"))
        except Exception:
            continue
        points_out.append({"label": label, "x": x, "y": y, "group": _clean_text(item.get("group"), max_chars=16)})
    return {"x_label": x_label, "y_label": y_label, "points": points_out[:24]}


def _suggest_mindmap_spec(*, caption: str, prompt: str, section_title: str) -> dict[str, Any]:
    tokens = [token for token in _tokenize_parts(prompt or caption or section_title) if len(token) >= 2]
    center = caption or section_title or (tokens[0] if tokens else "研究主题")
    branches = []
    seed = tokens[1:] if len(tokens) > 1 else []
    if not seed:
        seed = ["背景", "方法", "实验", "结论"]
    for token in seed[:6]:
        branches.append({"label": token, "children": [f"{token} A", f"{token} B"] if len(token) <= 10 else []})
    return {"type": "mindmap", "caption": caption or section_title or "思维导图", "data": {"center": center[:28], "branches": branches}}


def _suggest_quadrant_spec(*, caption: str, prompt: str, section_title: str) -> dict[str, Any]:
    tokens = [token for token in _tokenize_parts(prompt or caption or section_title) if len(token) >= 2]
    if len(tokens) < 4:
        tokens = ["核心事项", "快速收益", "研究风险", "待办事项"]
    coords = [(0.75, 0.75), (0.25, 0.75), (0.75, 0.25), (0.25, 0.25)]
    items = [{"label": token, "x": coords[idx][0], "y": coords[idx][1]} for idx, token in enumerate(tokens[:6])]
    return {"type": "quadrant", "caption": caption or section_title or "四象限图", "data": {"x_axis": "影响力", "y_axis": "可行性", "items": items}}


def _suggest_radar_spec(*, caption: str, prompt: str, section_title: str) -> dict[str, Any]:
    axes = [token for token in _tokenize_parts(prompt or caption or section_title) if len(token) >= 2][:6]
    if len(axes) < 4:
        axes = ["质量", "覆盖度", "效率", "鲁棒性", "成本"]
    values = [82, 74, 88, 79, 69][: len(axes)]
    return {"type": "radar", "caption": caption or section_title or "雷达图", "data": {"axes": axes, "series": [{"name": "方案甲", "values": values}]}}


def _suggest_scatter_spec(*, caption: str, prompt: str, section_title: str) -> dict[str, Any]:
    points = [
        {"label": "样本A", "x": 18, "y": 72, "group": "基线"},
        {"label": "样本B", "x": 35, "y": 68, "group": "基线"},
        {"label": "样本C", "x": 58, "y": 86, "group": "优化"},
        {"label": "样本D", "x": 74, "y": 92, "group": "优化"},
    ]
    return {"type": "scatter", "caption": caption or section_title or "散点图", "data": {"x_label": "成本", "y_label": "性能", "points": points}}


def _normalize_heatmap_data(payload: dict[str, Any]) -> dict[str, Any]:
    rows = [_clean_text(item, max_chars=16) for item in (payload.get("rows") if isinstance(payload.get("rows"), list) else [])[:8]]
    cols = [_clean_text(item, max_chars=16) for item in (payload.get("cols") if isinstance(payload.get("cols"), list) else [])[:8]]
    rows = [item for item in rows if item]
    cols = [item for item in cols if item]
    values_in = payload.get("values") if isinstance(payload.get("values"), list) else []
    values_out: list[list[float]] = []
    for row in values_in[: len(rows) or 8]:
        if not isinstance(row, list):
            continue
        row_out: list[float] = []
        for value in row[: len(cols) or 8]:
            try:
                row_out.append(max(0.0, min(100.0, float(value))))
            except Exception:
                row_out.append(0.0)
        if row_out:
            values_out.append(row_out)
    return {"rows": rows, "cols": cols, "values": values_out}


def _normalize_funnel_data(payload: dict[str, Any]) -> dict[str, Any]:
    stages_out: list[dict[str, float | str]] = []
    for item in payload.get("stages") if isinstance(payload.get("stages"), list) else []:
        if not isinstance(item, dict):
            continue
        label = _clean_text(item.get("label") or item.get("name"), max_chars=20)
        try:
            value = float(item.get("value"))
        except Exception:
            continue
        if label:
            stages_out.append({"label": label, "value": max(0.0, value)})
    return {"stages": stages_out[:8]}


def _normalize_sankey_data(payload: dict[str, Any]) -> dict[str, Any]:
    nodes = [_clean_text(item, max_chars=18) for item in (payload.get("nodes") if isinstance(payload.get("nodes"), list) else [])[:10]]
    nodes = [item for item in nodes if item]
    links_out: list[dict[str, float | str]] = []
    for item in payload.get("links") if isinstance(payload.get("links"), list) else []:
        if not isinstance(item, dict):
            continue
        source = _clean_text(item.get("source") or item.get("from"), max_chars=18)
        target = _clean_text(item.get("target") or item.get("to"), max_chars=18)
        try:
            value = float(item.get("value"))
        except Exception:
            continue
        if source and target:
            links_out.append({"source": source, "target": target, "value": max(0.0, value)})
    return {"nodes": nodes, "links": links_out[:16]}


def _normalize_swot_data(payload: dict[str, Any]) -> dict[str, Any]:
    def _list(name: str) -> list[str]:
        raw = payload.get(name) if isinstance(payload.get(name), list) else []
        out = [_clean_text(item, max_chars=24) for item in raw[:6]]
        return [item for item in out if item]

    return {
        "strengths": _list("strengths"),
        "weaknesses": _list("weaknesses"),
        "opportunities": _list("opportunities"),
        "threats": _list("threats"),
    }


def _suggest_heatmap_spec(*, caption: str, prompt: str, section_title: str) -> dict[str, Any]:
    rows = ["引言", "方法", "实验", "结论"]
    cols = ["相关性", "密度", "风险", "优先级"]
    values = [[68, 54, 22, 35], [72, 66, 28, 58], [85, 78, 36, 74], [60, 44, 20, 46]]
    return {"type": "heatmap", "caption": caption or section_title or "热力图", "data": {"rows": rows, "cols": cols, "values": values}}


def _suggest_funnel_spec(*, caption: str, prompt: str, section_title: str) -> dict[str, Any]:
    stages = [
        {"label": "原始候选", "value": 120},
        {"label": "筛选后", "value": 86},
        {"label": "验证通过", "value": 54},
        {"label": "最终采用", "value": 28},
    ]
    return {"type": "funnel", "caption": caption or section_title or "漏斗图", "data": {"stages": stages}}


def _suggest_sankey_spec(*, caption: str, prompt: str, section_title: str) -> dict[str, Any]:
    nodes = ["需求输入", "检索增强", "内容生成", "人工校核", "最终交付"]
    links = [
        {"source": "需求输入", "target": "检索增强", "value": 100},
        {"source": "需求输入", "target": "内容生成", "value": 80},
        {"source": "检索增强", "target": "人工校核", "value": 60},
        {"source": "内容生成", "target": "人工校核", "value": 75},
        {"source": "人工校核", "target": "最终交付", "value": 58},
    ]
    return {"type": "sankey", "caption": caption or section_title or "桑基图", "data": {"nodes": nodes, "links": links}}


def _suggest_swot_spec(*, caption: str, prompt: str, section_title: str) -> dict[str, Any]:
    data = {
        "strengths": ["生成效率高", "知识检索增强", "可扩展图表体系"],
        "weaknesses": ["长文本校核成本高", "图表语义仍需提示"],
        "opportunities": ["论文写作场景增长", "多模态能力融合"],
        "threats": ["模型波动", "数据合规要求提高"],
    }
    return {"type": "swot", "caption": caption or section_title or "SWOT图", "data": data}



__all__ = [name for name in globals() if not name.startswith("__")]
