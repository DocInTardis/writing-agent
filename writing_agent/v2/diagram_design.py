"""Professional diagram design helpers for academic paper figures."""

from __future__ import annotations

import copy
import re
from typing import Any

from writing_agent.v2 import diagram_design_spec_domain as spec_domain

_FONT_STACK = "Microsoft YaHei, PingFang SC, Hiragino Sans GB, Noto Sans CJK SC, SimHei, SimSun, Arial Unicode MS, Segoe UI, Arial, sans-serif"
_KIND_ALIASES = {
    "flowchart": "flow",
    "sequence_diagram": "sequence",
    "architecture_diagram": "architecture",
    "arch": "architecture",
}
_GENERIC_CAPTION_RE = re.compile(
    r"^(?:figure(?:_?\d+)?|fig(?:ure)?\s*\d*|chart\s*\d*|diagram\s*\d*|image\s*\d*|graphic\s*\d*|图\s*\d+|图表\s*\d+)$",
    re.IGNORECASE,
)
_ARCHITECTURE_HINT_RE = re.compile(r"(架构|体系|框架|模块|平台|系统|architecture|framework|component)", re.IGNORECASE)
_SEQUENCE_HINT_RE = re.compile(r"(时序|交互|调用链|sequence|lifeline|message)", re.IGNORECASE)
_FLOW_HINT_RE = re.compile(r"(流程|机制|路径|方法|workflow|process|pipeline|procedure)", re.IGNORECASE)
_RETURN_LABEL_RE = re.compile(r"(\u8fd4\u56de|\u54cd\u5e94|\u7ed3\u679c|ack|response|result)", re.IGNORECASE)
_ER_HINT_RE = re.compile(r"(\u5b9e\u4f53|\u5173\u7cfb|\u6570\u636e\u6a21\u578b|\u6570\u636e\u5e93\u8bbe\u8ba1|schema|entity|relation|er\b|table\b|\u5b57\u6bb5|\u4e3b\u952e|\u5916\u952e)", re.IGNORECASE)
_BAR_HINT_RE = re.compile(r"(\u5bf9\u6bd4|\u6bd4\u8f83|\u5206\u5e03|\u6392\u884c|\u6392\u540d|\u67f1\u72b6|bar\b|compare|comparison|distribution|ranking)", re.IGNORECASE)
_LINE_HINT_RE = re.compile(r"(\u8d8b\u52bf|\u53d8\u5316|\u6ce2\u52a8|\u589e\u957f|\u6298\u7ebf|\bline\b|trend|change|growth|series)", re.IGNORECASE)
_PIE_HINT_RE = re.compile(r"(\u5360\u6bd4|\u6784\u6210|\u6bd4\u4f8b|\u4efd\u989d|\u7ed3\u6784\u5206\u5e03|pie\b|share|composition|proportion|ratio)", re.IGNORECASE)
_TIMELINE_HINT_RE = re.compile(r"(\u65f6\u95f4\u7ebf|\u6f14\u5316|\u5386\u7a0b|\u9636\u6bb5|timeline|roadmap|evolution|history|milestone)", re.IGNORECASE)
_GENERIC_TYPE_WORDS_RE = re.compile(r"(\u56fe|\u56fe\u8868|figure|diagram|chart|\u6d41\u7a0b|\u67b6\u6784|\u65f6\u5e8f|timeline|trend|share|comparison|entity|relation)", re.IGNORECASE)

_LANE_PROFILES: list[dict[str, Any]] = [
    {"id": "access", "title": "接入层", "keywords": ["接入", "门户", "用户", "client", "gateway", "入口", "api", "认证"]},
    {"id": "orchestration", "title": "编排层", "keywords": ["编排", "调度", "planner", "workflow", "agent", "orchestr", "任务", "控制"]},
    {"id": "capability", "title": "能力层", "keywords": ["服务", "生成", "检索", "模型", "校核", "能力", "engine", "service", "rag", "validator"]},
    {"id": "data", "title": "数据层", "keywords": ["数据", "数据库", "知识库", "cache", "index", "存储", "仓库", "向量", "日志", "repository"]},
    {"id": "governance", "title": "治理层", "keywords": ["治理", "审计", "安全", "权限", "合规", "脱敏", "监控", "policy", "audit"]},
]

_NODE_KIND_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("actor", re.compile(r"(用户|门户|终端|client|browser|gateway|入口|api)", re.IGNORECASE)),
    ("data", re.compile(r"(数据|数据库|知识库|cache|store|storage|index|vector|文档库|日志|repository)", re.IGNORECASE)),
    ("control", re.compile(r"(治理|审计|合规|权限|策略|认证|security|policy|audit)", re.IGNORECASE)),
    ("decision", re.compile(r"(判断|校验|审核|验证|路由|gate|check|review|质检)", re.IGNORECASE)),
    ("service", re.compile(r"(服务|引擎|模型|生成|检索|编排|调度|agent|service|engine|planner|orchestr)", re.IGNORECASE)),
]

_KIND_BADGE = {
    "actor": "入口",
    "service": "能力",
    "process": "流程",
    "data": "数据",
    "control": "治理",
    "decision": "校核",
}

_KIND_STYLE = {
    "actor": {"fill": "#ECF4EA", "stroke": "#5B8A61", "accent": "#5B8A61"},
    "service": {"fill": "#EAF2FB", "stroke": "#2D5F8B", "accent": "#2D5F8B"},
    "process": {"fill": "#EEF3F8", "stroke": "#4E6A85", "accent": "#4E6A85"},
    "data": {"fill": "#F9EFE6", "stroke": "#A66A3F", "accent": "#A66A3F"},
    "control": {"fill": "#F0F0EB", "stroke": "#5A6B5D", "accent": "#5A6B5D"},
    "decision": {"fill": "#FBF2D8", "stroke": "#A97A12", "accent": "#A97A12"},
}

_LANE_BG = ["#F7F9FC", "#F2F5F8", "#F8FAFC", "#F3F7FB", "#F7F6F2"]


def normalize_diagram_kind(kind: str | None) -> str:
    raw = str(kind or "").strip().lower()
    return _KIND_ALIASES.get(raw, raw)


def _clean_text(value: object, *, max_chars: int = 48) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if len(text) > max_chars:
        text = text[:max_chars].rstrip()
    return text


def _slug_id(text: str, fallback: str) -> str:
    value = re.sub(r"[^0-9A-Za-z_\-\u4E00-\u9FFF]+", "_", text.strip())
    value = re.sub(r"_+", "_", value).strip("_")
    return value or fallback


def _is_generic_caption(text: str) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return True
    if _GENERIC_CAPTION_RE.match(raw):
        return True
    normalized = re.sub(r"[\s_:\-：]+", "", raw)
    return normalized in {"流程图", "示意图", "方法流程图", "关键流程图", "系统图", "架构图"}


def has_semantic_signal(text: str) -> bool:
    raw = _clean_text(text, max_chars=120)
    if not raw or _is_generic_caption(raw):
        return False
    alpha = re.findall(r"[A-Za-z]{3,}", raw)
    cjk = re.findall(r"[\u4E00-\u9FFF]", raw)
    digits_only = bool(re.fullmatch(r"[\d\s\-_.]+", raw))
    return not digits_only and (len(alpha) >= 2 or len(cjk) >= 4)


def extract_semantic_tokens(text: str) -> list[str]:
    raw = _clean_text(text, max_chars=160)
    if not raw:
        return []
    normalized = _GENERIC_TYPE_WORDS_RE.sub(" ", raw)
    cjk_tokens = [tok for tok in re.findall(r"[一-鿿]{2,}", normalized) if len(tok) >= 2]
    alpha_tokens = [tok.casefold() for tok in re.findall(r"[A-Za-z]{4,}", normalized)]
    tokens: list[str] = []
    for token in cjk_tokens + alpha_tokens:
        if token not in tokens:
            tokens.append(token)
    return tokens[:12]


def resolve_requested_diagram_kind(requested_kind: str | None, *, caption: str = "", prompt: str = "", section_title: str = "", context_text: str = "") -> str:
    normalized = normalize_diagram_kind(requested_kind)
    semantic_seed = " ".join(part for part in [caption, section_title, prompt, context_text] if str(part or "").strip())
    preferred = infer_preferred_diagram_kind(semantic_seed)
    if preferred and normalized in {"", "flow"}:
        return preferred
    return normalized or preferred or "flow"


def infer_preferred_diagram_kind(text: str) -> str:
    raw = _clean_text(text, max_chars=180)
    if not raw:
        return ""
    if _ER_HINT_RE.search(raw):
        return "er"
    if _PIE_HINT_RE.search(raw):
        return "pie"
    if _TIMELINE_HINT_RE.search(raw):
        return "timeline"
    if _LINE_HINT_RE.search(raw):
        return "line"
    if _BAR_HINT_RE.search(raw):
        return "bar"
    if _ARCHITECTURE_HINT_RE.search(raw):
        return "architecture"
    if _SEQUENCE_HINT_RE.search(raw):
        return "sequence"
    if _FLOW_HINT_RE.search(raw):
        return "flow"
    return ""


def infer_node_kind(label: str, *, explicit: str = "") -> str:
    raw = normalize_diagram_kind(explicit)
    if raw in _KIND_STYLE:
        return raw
    text = str(label or "")
    for kind, pattern in _NODE_KIND_RULES:
        if pattern.search(text):
            return kind
    return "process"


def _lane_title(lane_id: str) -> str:
    for item in _LANE_PROFILES:
        if item["id"] == lane_id:
            return str(item["title"])
    return str(lane_id or "核心层")


def infer_lane_id(label: str, *, explicit: str = "") -> str:
    raw = _clean_text(explicit, max_chars=24)
    if raw:
        for item in _LANE_PROFILES:
            if raw == item["id"] or raw == item["title"]:
                return str(item["id"])
        return raw
    text = str(label or "")
    for item in _LANE_PROFILES:
        for keyword in item["keywords"]:
            if keyword and keyword.lower() in text.lower():
                return str(item["id"])
    return "capability"


_tokenize_parts = spec_domain._tokenize_parts
_phase_lanes = spec_domain._phase_lanes
_normalize_lanes = spec_domain._normalize_lanes
_normalize_flowish_data = spec_domain._normalize_flowish_data
_normalize_sequence_data = spec_domain._normalize_sequence_data
_extract_numeric_pairs = spec_domain._extract_numeric_pairs
_extract_numbers = spec_domain._extract_numbers
_extract_timeline_events = spec_domain._extract_timeline_events
_suggest_flow_spec = spec_domain._suggest_flow_spec
_suggest_architecture_spec = spec_domain._suggest_architecture_spec
_suggest_sequence_spec = spec_domain._suggest_sequence_spec
_suggest_er_spec = spec_domain._suggest_er_spec
_suggest_bar_spec = spec_domain._suggest_bar_spec
_suggest_line_spec = spec_domain._suggest_line_spec
_suggest_pie_spec = spec_domain._suggest_pie_spec
_suggest_timeline_spec = spec_domain._suggest_timeline_spec


def suggest_diagram_spec(kind: str, *, caption: str = "", prompt: str = "", section_title: str = "") -> dict[str, Any]:
    normalized = resolve_requested_diagram_kind(kind, caption=caption, prompt=prompt, section_title=section_title)
    if normalized == "architecture":
        return _suggest_architecture_spec(caption=caption, prompt=prompt, section_title=section_title)
    if normalized == "sequence":
        return _suggest_sequence_spec(caption=caption, prompt=prompt, section_title=section_title)
    if normalized == "er":
        return _suggest_er_spec(caption=caption, prompt=prompt, section_title=section_title)
    if normalized == "bar":
        return _suggest_bar_spec(caption=caption, prompt=prompt, section_title=section_title)
    if normalized == "line":
        return _suggest_line_spec(caption=caption, prompt=prompt, section_title=section_title)
    if normalized == "pie":
        return _suggest_pie_spec(caption=caption, prompt=prompt, section_title=section_title)
    if normalized == "timeline":
        return _suggest_timeline_spec(caption=caption, prompt=prompt, section_title=section_title)
    return _suggest_flow_spec(caption=caption, prompt=prompt, section_title=section_title)


def enrich_figure_spec(spec: dict[str, Any] | None, *, section_title: str = "", context_text: str = "") -> dict[str, Any]:
    payload = copy.deepcopy(spec or {})
    kind = normalize_diagram_kind(str(payload.get("type") or payload.get("kind") or "").strip())
    caption = _clean_text(payload.get("caption") or section_title or "", max_chars=60)
    semantic_seed = " ".join(part for part in [caption, section_title, context_text] if part)
    inferred_kind = infer_preferred_diagram_kind(semantic_seed)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}

    if not kind:
        kind = inferred_kind
    elif kind == "flow" and inferred_kind in {"bar", "line", "pie", "timeline", "er"}:
        if not _normalize_flowish_data(data, kind="flow").get("nodes"):
            kind = inferred_kind

    if kind in {"flow", "architecture"}:
        normalized = _normalize_flowish_data(data, kind=kind)
        if len(normalized.get("nodes") or []) < 2 and has_semantic_signal(semantic_seed):
            return suggest_diagram_spec(kind or inferred_kind or "flow", caption=caption, prompt=context_text or caption, section_title=section_title)
        payload["type"] = kind
        payload["caption"] = caption or (section_title if section_title else ("System Architecture" if kind == "architecture" else "Process Diagram"))
        payload["data"] = normalized
        return payload
    if kind == "sequence":
        normalized = _normalize_sequence_data(data)
        if len(normalized.get("participants") or []) < 2 and has_semantic_signal(semantic_seed):
            return suggest_diagram_spec("sequence", caption=caption, prompt=context_text or caption, section_title=section_title)
        payload["type"] = kind
        payload["caption"] = caption or (section_title if section_title else "Sequence Diagram")
        payload["data"] = normalized
        return payload
    if kind == "er":
        normalized = _normalize_er_data(data)
        if len(normalized.get("entities") or []) < 2 and has_semantic_signal(semantic_seed):
            return suggest_diagram_spec("er", caption=caption, prompt=context_text or caption, section_title=section_title)
        payload["type"] = kind
        payload["caption"] = caption or (section_title if section_title else "Entity Relationship Graph")
        payload["data"] = normalized
        return payload
    if kind == "bar":
        labels = [_clean_text(item, max_chars=20) for item in (data.get("labels") if isinstance(data.get("labels"), list) else [])[:10]]
        labels = [item for item in labels if item]
        values: list[float] = []
        for item in (data.get("values") if isinstance(data.get("values"), list) else [])[:10]:
            try:
                values.append(float(item))
            except Exception:
                continue
        if min(len(labels), len(values)) < 2 and has_semantic_signal(semantic_seed):
            return suggest_diagram_spec("bar", caption=caption, prompt=context_text or caption, section_title=section_title)
        payload["type"] = kind
        payload["caption"] = caption or (section_title if section_title else "Comparison Metrics")
        payload["data"] = {"labels": labels[: len(values)], "values": values[: len(labels)]}
        return payload
    if kind == "line":
        labels = [_clean_text(item, max_chars=20) for item in (data.get("labels") if isinstance(data.get("labels"), list) else [])[:16]]
        series = data.get("series") if isinstance(data.get("series"), list) else []
        if (not labels or not series) and has_semantic_signal(semantic_seed):
            return suggest_diagram_spec("line", caption=caption, prompt=context_text or caption, section_title=section_title)
        payload["type"] = kind
        payload["caption"] = caption or (section_title if section_title else "Trend Analysis")
        payload["data"] = data
        return payload
    if kind == "pie":
        segments = data.get("segments") if isinstance(data.get("segments"), list) else []
        if len(segments) < 2 and has_semantic_signal(semantic_seed):
            return suggest_diagram_spec("pie", caption=caption, prompt=context_text or caption, section_title=section_title)
        payload["type"] = kind
        payload["caption"] = caption or (section_title if section_title else "Composition Share")
        payload["data"] = data
        return payload
    if kind == "timeline":
        events = data.get("events") if isinstance(data.get("events"), list) else []
        if len(events) < 2 and has_semantic_signal(semantic_seed):
            return suggest_diagram_spec("timeline", caption=caption, prompt=context_text or caption, section_title=section_title)
        payload["type"] = kind
        payload["caption"] = caption or (section_title if section_title else "Research Timeline")
        payload["data"] = data
        return payload
    if has_semantic_signal(semantic_seed):
        return suggest_diagram_spec(inferred_kind or "flow", caption=caption, prompt=context_text or caption, section_title=section_title)
    return payload


from writing_agent.v2 import diagram_design_render_domain as render_domain  # noqa: E402

_normalize_er_data = render_domain._normalize_er_data
render_flow_or_architecture_svg = render_domain.render_flow_or_architecture_svg
render_professional_sequence_svg = render_domain.render_professional_sequence_svg
render_professional_er_svg = render_domain.render_professional_er_svg
render_professional_bar_svg = render_domain.render_professional_bar_svg
render_professional_line_svg = render_domain.render_professional_line_svg
render_professional_pie_svg = render_domain.render_professional_pie_svg
render_professional_timeline_svg = render_domain.render_professional_timeline_svg
