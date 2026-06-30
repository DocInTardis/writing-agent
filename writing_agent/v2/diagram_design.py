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
    "state_diagram": "state",
    "uml_state": "state",
    "class_diagram": "class",
    "uml_class": "class",
    "gantt_chart": "gantt",
    "mind_map": "mindmap",
    "quadrant_chart": "quadrant",
    "matrix_2x2": "quadrant",
    "radar_chart": "radar",
    "scatter_plot": "scatter",
    "heatmap_chart": "heatmap",
    "funnel_chart": "funnel",
    "sankey_chart": "sankey",
    "swot_chart": "swot",
    "architecture_diagram": "architecture",
    "arch": "architecture",
}
_GENERIC_CAPTION_RE = re.compile(
    r"^(?:figure(?:_?\d+)?|fig(?:ure)?\s*\d*|chart\s*\d*|diagram\s*\d*|image\s*\d*|graphic\s*\d*|图\s*\d+|图表\s*\d+)$",
    re.IGNORECASE,
)
_ARCHITECTURE_HINT_RE = re.compile(r"(架构|体系|框架|模块|平台|系统|architecture|framework|component)", re.IGNORECASE)
_SEQUENCE_HINT_RE = re.compile(r"(时序|交互|调用链|sequence|lifeline|message)", re.IGNORECASE)
_STATE_HINT_RE = re.compile(r"(状态|状态机|state|lifecycle|transition|审批状态)", re.IGNORECASE)
_CLASS_HINT_RE = re.compile(r"(类图|类关系|class\b|uml|对象模型|领域模型|interface|inheritance)", re.IGNORECASE)
_GANTT_HINT_RE = re.compile(r"(gantt|甘特|排期|计划表|schedule|milestone\s+plan|实施计划)", re.IGNORECASE)
_MINDMAP_HINT_RE = re.compile(r"(思维导图|脑图|mind\s*map|主题发散|知识结构)", re.IGNORECASE)
_QUADRANT_HINT_RE = re.compile(r"(四象限|2x2|2×2|矩阵图|priority matrix|quadrant)", re.IGNORECASE)
_RADAR_HINT_RE = re.compile(r"(雷达图|radar|spider chart|能力画像|多维评估)", re.IGNORECASE)
_SCATTER_HINT_RE = re.compile(r"(散点图|scatter|相关性|样本分布|outlier|cluster)", re.IGNORECASE)
_HEATMAP_HINT_RE = re.compile(r"(热力图|heatmap|热点矩阵|强度分布)", re.IGNORECASE)
_FUNNEL_HINT_RE = re.compile(r"(漏斗图|funnel|转化漏斗|收敛过程|筛选流程)", re.IGNORECASE)
_SANKEY_HINT_RE = re.compile(r"(桑基图|sankey|流向图|流量分配|路径分流)", re.IGNORECASE)
_SWOT_HINT_RE = re.compile(r"(swot|优势|劣势|机会|威胁|战略分析)", re.IGNORECASE)
_FLOW_HINT_RE = re.compile(r"(流程|机制|路径|方法|workflow|process|pipeline|procedure)", re.IGNORECASE)
_RETURN_LABEL_RE = re.compile(r"(\u8fd4\u56de|\u54cd\u5e94|\u7ed3\u679c|ack|response|result)", re.IGNORECASE)
_ER_HINT_RE = re.compile(r"(\u5b9e\u4f53|\u5173\u7cfb|\u6570\u636e\u6a21\u578b|\u6570\u636e\u5e93\u8bbe\u8ba1|schema|entity|relation|er\b|table\b|\u5b57\u6bb5|\u4e3b\u952e|\u5916\u952e)", re.IGNORECASE)
_BAR_HINT_RE = re.compile(r"(\u5bf9\u6bd4|\u6bd4\u8f83|\u5206\u5e03|\u6392\u884c|\u6392\u540d|\u67f1\u72b6|bar\b|compare|comparison|distribution|ranking)", re.IGNORECASE)
_LINE_HINT_RE = re.compile(r"(\u8d8b\u52bf|\u53d8\u5316|\u6ce2\u52a8|\u589e\u957f|\u6298\u7ebf|\bline\b|trend|change|growth|series)", re.IGNORECASE)
_PIE_HINT_RE = re.compile(r"(\u5360\u6bd4|\u6784\u6210|\u6bd4\u4f8b|\u4efd\u989d|\u7ed3\u6784\u5206\u5e03|pie\b|share|composition|proportion|ratio)", re.IGNORECASE)
_TIMELINE_HINT_RE = re.compile(r"(\u65f6\u95f4\u7ebf|\u6f14\u5316|\u5386\u7a0b|\u9636\u6bb5|timeline|roadmap|evolution|history|milestone)", re.IGNORECASE)
_GENERIC_TYPE_WORDS_RE = re.compile(r"(\u56fe|\u56fe\u8868|figure|diagram|chart|\u6d41\u7a0b|\u67b6\u6784|\u65f6\u5e8f|state|class|gantt|mindmap|quadrant|radar|scatter|heatmap|funnel|sankey|swot|timeline|trend|share|comparison|entity|relation)", re.IGNORECASE)

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
    if _MINDMAP_HINT_RE.search(raw):
        return "mindmap"
    if _QUADRANT_HINT_RE.search(raw):
        return "quadrant"
    if _RADAR_HINT_RE.search(raw):
        return "radar"
    if _SCATTER_HINT_RE.search(raw):
        return "scatter"
    if _HEATMAP_HINT_RE.search(raw):
        return "heatmap"
    if _FUNNEL_HINT_RE.search(raw):
        return "funnel"
    if _SANKEY_HINT_RE.search(raw):
        return "sankey"
    if _SWOT_HINT_RE.search(raw):
        return "swot"
    if _CLASS_HINT_RE.search(raw):
        return "class"
    if _STATE_HINT_RE.search(raw):
        return "state"
    if _PIE_HINT_RE.search(raw):
        return "pie"
    if _GANTT_HINT_RE.search(raw):
        return "gantt"
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
_normalize_state_data = spec_domain._normalize_state_data
_normalize_class_data = spec_domain._normalize_class_data
_normalize_gantt_data = spec_domain._normalize_gantt_data
_normalize_mindmap_data = spec_domain._normalize_mindmap_data
_normalize_quadrant_data = spec_domain._normalize_quadrant_data
_normalize_radar_data = spec_domain._normalize_radar_data
_normalize_scatter_data = spec_domain._normalize_scatter_data
_normalize_heatmap_data = spec_domain._normalize_heatmap_data
_normalize_funnel_data = spec_domain._normalize_funnel_data
_normalize_sankey_data = spec_domain._normalize_sankey_data
_normalize_swot_data = spec_domain._normalize_swot_data
_extract_numeric_pairs = spec_domain._extract_numeric_pairs
_extract_numbers = spec_domain._extract_numbers
_extract_timeline_events = spec_domain._extract_timeline_events
_suggest_flow_spec = spec_domain._suggest_flow_spec
_suggest_architecture_spec = spec_domain._suggest_architecture_spec
_suggest_sequence_spec = spec_domain._suggest_sequence_spec
_suggest_state_spec = spec_domain._suggest_state_spec
_suggest_class_spec = spec_domain._suggest_class_spec
_suggest_gantt_spec = spec_domain._suggest_gantt_spec
_suggest_mindmap_spec = spec_domain._suggest_mindmap_spec
_suggest_quadrant_spec = spec_domain._suggest_quadrant_spec
_suggest_radar_spec = spec_domain._suggest_radar_spec
_suggest_scatter_spec = spec_domain._suggest_scatter_spec
_suggest_heatmap_spec = spec_domain._suggest_heatmap_spec
_suggest_funnel_spec = spec_domain._suggest_funnel_spec
_suggest_sankey_spec = spec_domain._suggest_sankey_spec
_suggest_swot_spec = spec_domain._suggest_swot_spec
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
    if normalized == "state":
        return _suggest_state_spec(caption=caption, prompt=prompt, section_title=section_title)
    if normalized == "class":
        return _suggest_class_spec(caption=caption, prompt=prompt, section_title=section_title)
    if normalized == "gantt":
        return _suggest_gantt_spec(caption=caption, prompt=prompt, section_title=section_title)
    if normalized == "mindmap":
        return _suggest_mindmap_spec(caption=caption, prompt=prompt, section_title=section_title)
    if normalized == "quadrant":
        return _suggest_quadrant_spec(caption=caption, prompt=prompt, section_title=section_title)
    if normalized == "radar":
        return _suggest_radar_spec(caption=caption, prompt=prompt, section_title=section_title)
    if normalized == "scatter":
        return _suggest_scatter_spec(caption=caption, prompt=prompt, section_title=section_title)
    if normalized == "heatmap":
        return _suggest_heatmap_spec(caption=caption, prompt=prompt, section_title=section_title)
    if normalized == "funnel":
        return _suggest_funnel_spec(caption=caption, prompt=prompt, section_title=section_title)
    if normalized == "sankey":
        return _suggest_sankey_spec(caption=caption, prompt=prompt, section_title=section_title)
    if normalized == "swot":
        return _suggest_swot_spec(caption=caption, prompt=prompt, section_title=section_title)
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
    elif kind == "flow" and inferred_kind in {"bar", "line", "pie", "timeline", "gantt", "mindmap", "quadrant", "radar", "scatter", "heatmap", "funnel", "sankey", "swot", "er", "state", "class"}:
        if not _normalize_flowish_data(data, kind="flow").get("nodes"):
            kind = inferred_kind

    if kind in {"flow", "architecture"}:
        normalized = _normalize_flowish_data(data, kind=kind)
        if len(normalized.get("nodes") or []) < 2 and has_semantic_signal(semantic_seed):
            return suggest_diagram_spec(kind or inferred_kind or "flow", caption=caption, prompt=context_text or caption, section_title=section_title)
        payload["type"] = kind
        payload["caption"] = caption or (section_title if section_title else ("系统架构图" if kind == "architecture" else "流程图"))
        payload["data"] = normalized
        return payload
    if kind == "sequence":
        normalized = _normalize_sequence_data(data)
        if len(normalized.get("participants") or []) < 2 and has_semantic_signal(semantic_seed):
            return suggest_diagram_spec("sequence", caption=caption, prompt=context_text or caption, section_title=section_title)
        payload["type"] = kind
        payload["caption"] = caption or (section_title if section_title else "时序图")
        payload["data"] = normalized
        return payload
    if kind == "state":
        normalized = _normalize_state_data(data)
        if len(normalized.get("states") or []) < 2 and has_semantic_signal(semantic_seed):
            return suggest_diagram_spec("state", caption=caption, prompt=context_text or caption, section_title=section_title)
        payload["type"] = kind
        payload["caption"] = caption or (section_title if section_title else "状态图")
        payload["data"] = normalized
        return payload
    if kind == "class":
        normalized = _normalize_class_data(data)
        if len(normalized.get("classes") or []) < 2 and has_semantic_signal(semantic_seed):
            return suggest_diagram_spec("class", caption=caption, prompt=context_text or caption, section_title=section_title)
        payload["type"] = kind
        payload["caption"] = caption or (section_title if section_title else "类图")
        payload["data"] = normalized
        return payload
    if kind == "gantt":
        normalized = _normalize_gantt_data(data)
        if len(normalized.get("tasks") or []) < 2 and has_semantic_signal(semantic_seed):
            return suggest_diagram_spec("gantt", caption=caption, prompt=context_text or caption, section_title=section_title)
        payload["type"] = kind
        payload["caption"] = caption or (section_title if section_title else "甘特图")
        payload["data"] = normalized
        return payload
    if kind == "mindmap":
        normalized = _normalize_mindmap_data(data)
        if len(normalized.get("branches") or []) < 2 and has_semantic_signal(semantic_seed):
            return suggest_diagram_spec("mindmap", caption=caption, prompt=context_text or caption, section_title=section_title)
        payload["type"] = kind
        payload["caption"] = caption or (section_title if section_title else "思维导图")
        payload["data"] = normalized
        return payload
    if kind == "quadrant":
        normalized = _normalize_quadrant_data(data)
        if len(normalized.get("items") or []) < 2 and has_semantic_signal(semantic_seed):
            return suggest_diagram_spec("quadrant", caption=caption, prompt=context_text or caption, section_title=section_title)
        payload["type"] = kind
        payload["caption"] = caption or (section_title if section_title else "四象限图")
        payload["data"] = normalized
        return payload
    if kind == "radar":
        normalized = _normalize_radar_data(data)
        if len(normalized.get("axes") or []) < 3 and has_semantic_signal(semantic_seed):
            return suggest_diagram_spec("radar", caption=caption, prompt=context_text or caption, section_title=section_title)
        payload["type"] = kind
        payload["caption"] = caption or (section_title if section_title else "雷达图")
        payload["data"] = normalized
        return payload
    if kind == "scatter":
        normalized = _normalize_scatter_data(data)
        if len(normalized.get("points") or []) < 2 and has_semantic_signal(semantic_seed):
            return suggest_diagram_spec("scatter", caption=caption, prompt=context_text or caption, section_title=section_title)
        payload["type"] = kind
        payload["caption"] = caption or (section_title if section_title else "散点图")
        payload["data"] = normalized
        return payload
    if kind == "heatmap":
        normalized = _normalize_heatmap_data(data)
        if len(normalized.get("rows") or []) < 2 and has_semantic_signal(semantic_seed):
            return suggest_diagram_spec("heatmap", caption=caption, prompt=context_text or caption, section_title=section_title)
        payload["type"] = kind
        payload["caption"] = caption or (section_title if section_title else "热力图")
        payload["data"] = normalized
        return payload
    if kind == "funnel":
        normalized = _normalize_funnel_data(data)
        if len(normalized.get("stages") or []) < 2 and has_semantic_signal(semantic_seed):
            return suggest_diagram_spec("funnel", caption=caption, prompt=context_text or caption, section_title=section_title)
        payload["type"] = kind
        payload["caption"] = caption or (section_title if section_title else "漏斗图")
        payload["data"] = normalized
        return payload
    if kind == "sankey":
        normalized = _normalize_sankey_data(data)
        if len(normalized.get("nodes") or []) < 2 and has_semantic_signal(semantic_seed):
            return suggest_diagram_spec("sankey", caption=caption, prompt=context_text or caption, section_title=section_title)
        payload["type"] = kind
        payload["caption"] = caption or (section_title if section_title else "桑基图")
        payload["data"] = normalized
        return payload
    if kind == "swot":
        normalized = _normalize_swot_data(data)
        if not any(normalized.get(key) for key in ("strengths", "weaknesses", "opportunities", "threats")) and has_semantic_signal(semantic_seed):
            return suggest_diagram_spec("swot", caption=caption, prompt=context_text or caption, section_title=section_title)
        payload["type"] = kind
        payload["caption"] = caption or (section_title if section_title else "SWOT图")
        payload["data"] = normalized
        return payload
    if kind == "er":
        normalized = _normalize_er_data(data)
        if len(normalized.get("entities") or []) < 2 and has_semantic_signal(semantic_seed):
            return suggest_diagram_spec("er", caption=caption, prompt=context_text or caption, section_title=section_title)
        payload["type"] = kind
        payload["caption"] = caption or (section_title if section_title else "实体关系图")
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
        payload["caption"] = caption or (section_title if section_title else "柱状图")
        payload["data"] = {"labels": labels[: len(values)], "values": values[: len(labels)]}
        return payload
    if kind == "line":
        labels = [_clean_text(item, max_chars=20) for item in (data.get("labels") if isinstance(data.get("labels"), list) else [])[:16]]
        series = data.get("series") if isinstance(data.get("series"), list) else []
        if (not labels or not series) and has_semantic_signal(semantic_seed):
            return suggest_diagram_spec("line", caption=caption, prompt=context_text or caption, section_title=section_title)
        payload["type"] = kind
        payload["caption"] = caption or (section_title if section_title else "趋势分析图")
        payload["data"] = data
        return payload
    if kind == "pie":
        segments = data.get("segments") if isinstance(data.get("segments"), list) else []
        if len(segments) < 2 and has_semantic_signal(semantic_seed):
            return suggest_diagram_spec("pie", caption=caption, prompt=context_text or caption, section_title=section_title)
        payload["type"] = kind
        payload["caption"] = caption or (section_title if section_title else "占比分析图")
        payload["data"] = data
        return payload
    if kind == "timeline":
        events = data.get("events") if isinstance(data.get("events"), list) else []
        if len(events) < 2 and has_semantic_signal(semantic_seed):
            return suggest_diagram_spec("timeline", caption=caption, prompt=context_text or caption, section_title=section_title)
        payload["type"] = kind
        payload["caption"] = caption or (section_title if section_title else "时间线")
        payload["data"] = data
        return payload
    if has_semantic_signal(semantic_seed):
        return suggest_diagram_spec(inferred_kind or "flow", caption=caption, prompt=context_text or caption, section_title=section_title)
    return payload


from writing_agent.v2 import diagram_design_render_domain as render_domain  # noqa: E402

_normalize_er_data = render_domain._normalize_er_data
render_flow_or_architecture_svg = render_domain.render_flow_or_architecture_svg
render_professional_sequence_svg = render_domain.render_professional_sequence_svg
render_professional_state_svg = render_domain.render_professional_state_svg
render_professional_class_svg = render_domain.render_professional_class_svg
render_professional_gantt_svg = render_domain.render_professional_gantt_svg
render_professional_mindmap_svg = render_domain.render_professional_mindmap_svg
render_professional_quadrant_svg = render_domain.render_professional_quadrant_svg
render_professional_radar_svg = render_domain.render_professional_radar_svg
render_professional_scatter_svg = render_domain.render_professional_scatter_svg
render_professional_heatmap_svg = render_domain.render_professional_heatmap_svg
render_professional_funnel_svg = render_domain.render_professional_funnel_svg
render_professional_sankey_svg = render_domain.render_professional_sankey_svg
render_professional_swot_svg = render_domain.render_professional_swot_svg
render_professional_er_svg = render_domain.render_professional_er_svg
render_professional_bar_svg = render_domain.render_professional_bar_svg
render_professional_line_svg = render_domain.render_professional_line_svg
render_professional_pie_svg = render_domain.render_professional_pie_svg
render_professional_timeline_svg = render_domain.render_professional_timeline_svg
