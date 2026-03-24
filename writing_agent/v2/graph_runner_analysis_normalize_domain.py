"""Analysis requirement normalization helpers split from graph_runner_analysis_requirements_domain.py."""

from __future__ import annotations

import re

from writing_agent.v2.graph_reference_domain import _topic_tokens


def _base():
    from writing_agent.v2 import graph_runner_analysis_requirements_domain as base

    return base


def _resolve_doc_type_for_prompt(instruction: str) -> str:
    return str(_base()._resolve_doc_type_for_prompt(instruction))


def _meta_firewall_scan(text: str) -> bool:
    return bool(_base()._meta_firewall_scan(text))


def _guess_title(instruction: str) -> str:
    return str(_base()._guess_title(instruction))


def _sanitize_section_tokens(tokens: list[str], *, keep_full_titles: bool = False) -> list[str]:
    return list(_base()._sanitize_section_tokens(tokens, keep_full_titles=keep_full_titles))


def _bibliometric_section_spine() -> list[str]:
    return list(_base()._bibliometric_section_spine())


def _is_reference_section(section: str) -> bool:
    return bool(_base()._is_reference_section(section))


def _is_bibliometric_instruction(instruction: str) -> bool:
    return bool(_base()._is_bibliometric_instruction(instruction))


def _user_explicitly_requests_engineering_sections(instruction: str) -> bool:
    return bool(_base()._user_explicitly_requests_engineering_sections(instruction))


def _normalize_reference_query(text: str) -> str:
    return str(_base()._normalize_reference_query(text))


def _process_line(text: str) -> bool:
    return bool(_base()._process_line(text))

_ANALYSIS_REQUIRED_SECTION_ALIASES: list[tuple[str, tuple[str, ...]]] = [
    ("摘要", ("摘要", "abstract")),
    (
        "数据来源与检索策略",
        (
            "数据来源与检索策略",
            "数据来源与检索",
            "数据来源及检索策略",
            "数据来源",
            "检索策略",
            "data source and search strategy",
            "search strategy",
        ),
    ),
    (
        "发文量时空分布",
        (
            "发文量时空分布",
            "发文量分布",
            "时空分布",
            "publication volume distribution",
            "temporal-spatial distribution",
        ),
    ),
    (
        "作者与机构合作网络",
        (
            "作者与机构合作网络",
            "作者合作网络",
            "机构合作网络",
            "author collaboration network",
            "institution collaboration network",
        ),
    ),
    (
        "关键词共现与聚类分析",
        (
            "关键词共现与聚类分析",
            "关键词共现",
            "关键词聚类",
            "co-occurrence",
            "keyword clustering",
        ),
    ),
    (
        "研究热点演化与突现分析",
        (
            "研究热点演化与突现分析",
            "热点演化",
            "突现分析",
            "burst analysis",
            "research hotspot evolution",
        ),
    ),
    ("关键词", ("关键词", "关键字", "key words", "keywords")),
    ("引言", ("引言", "绪论", "研究背景", "背景与意义", "研究意义", "background", "introduction", "overview")),
    ("相关研究", ("相关研究", "文献综述", "研究现状", "国内外研究", "文献回顾", "综述", "related work", "related studies", "literature review")),
    ("研究方法", ("研究方法", "方法", "方法设计", "研究设计", "技术路线", "method", "methodology")),
    ("系统设计与实现", ("系统设计与实现", "系统设计", "设计与实现", "架构设计", "系统实现", "实现方案", "implementation", "architecture")),
    ("实验设计与结果", ("实验设计与结果", "实验与结果", "实验结果", "结果分析", "实证分析", "性能评估", "experiment", "evaluation", "results")),
    ("讨论", ("讨论", "discussion")),
    ("结论", ("结论", "总结", "conclusion")),
    ("参考文献", ("参考文献", "references", "bibliography")),
]


def _dedupe_keep_order(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        token = str(item or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def _extract_required_sections(text: str) -> list[str]:
    src = str(text or "")
    if not src:
        return []
    lower = src.lower()
    hits: list[str] = []
    for canonical, aliases in _ANALYSIS_REQUIRED_SECTION_ALIASES:
        for alias in aliases:
            a = str(alias or "").strip()
            if not a:
                continue
            if any("\u4e00" <= ch <= "\u9fff" for ch in a):
                if a in src:
                    hits.append(canonical)
                    break
            elif a.lower() in lower:
                hits.append(canonical)
                break
    return _dedupe_keep_order(hits)


def _canonicalize_section_name(text: str) -> str:
    src = str(text or "").strip()
    if not src:
        return ""
    lower = src.lower()
    for canonical, aliases in _ANALYSIS_REQUIRED_SECTION_ALIASES:
        for alias in aliases:
            a = str(alias or "").strip()
            if not a:
                continue
            if any("\u4e00" <= ch <= "\u9fff" for ch in a):
                if a in src:
                    return canonical
            elif a.lower() in lower:
                return canonical
    return src


def _looks_like_heading_requirement(text: str) -> bool:
    s = str(text or "").strip()
    if not s:
        return False
    if len(s) > 40:
        return False
    if any(ch in s for ch in ["\n", "\r", "\t"]):
        return False
    # Sentence-like constraints should not be treated as section titles.
    if re.search(r"(必须|不少于|按顺序|字符数|不得|约束|要求|结构包含|章节|段落|输出|格式)", s):
        return False
    punct = sum(1 for ch in s if ch in {"，", "。", "；", "：", ":", "!", "！", "?", "？"})
    if punct > 1:
        return False
    return True


def _normalize_must_include_sections(
    *,
    must_include_raw: list[str],
    constraints_raw: list[str],
    instruction: str,
    doc_type: str,
) -> list[str]:
    # Prefer canonical section names parsed from must_include/constraints/instruction.
    extracted: list[str] = []
    for txt in [*must_include_raw, *constraints_raw, str(instruction or "")]:
        extracted.extend(_extract_required_sections(txt))
    extracted = _dedupe_keep_order(extracted)
    if extracted:
        return extracted

    # Fallback: keep only compact heading-like items from must_include.
    compact: list[str] = []
    for item in must_include_raw:
        s = re.sub(r"^\s*[\d一二三四五六七八九十]+[).、]\s*", "", str(item or "")).strip()
        s = re.sub(r"\s+", " ", s).strip()
        if _looks_like_heading_requirement(s):
            compact.append(s)
    compact = _dedupe_keep_order(compact)
    if compact:
        return compact

    # Last fallback for academic tasks keeps a minimal structural guard.
    doc_type_lower = str(doc_type or "").strip().lower()
    if _resolve_doc_type_for_prompt(instruction) == "academic" or ("学术" in str(doc_type or "")) or (doc_type_lower in {"academic", "paper", "thesis"}):
        return ["引言", "结论", "参考文献"]
    return []


_ANALYSIS_SCHEMA_TOKENS = {
    "topic",
    "title",
    "doc_type",
    "doctype",
    "keyword",
    "keywords",
    "key",
    "points",
    "section_id",
    "section",
    "figure",
    "caption",
    "kind",
    "data",
    "json",
    "analysis",
    "analysis_summary",
    "plan",
    "plan_hint",
    "plan_summary",
    "user_requirement",
}


def _analysis_text_is_meta_noise(text: str) -> bool:
    token = str(text or "").strip()
    if not token:
        return False
    if _process_line(token):
        return True
    if _meta_firewall_scan(token):
        return True
    if re.search(
        r"(?i)(?:^|\n|\r)\s*(?:topic|title|doc_type|doctype|keywords?|key\s*points?|section_id|analysis(?:_summary)?|plan(?:_hint|_summary)?|figure|caption|kind|data|json)\s*[:=]",
        token,
    ):
        return True
    if re.search(r"</?[a-z_][a-z0-9_:-]*>", token, flags=re.IGNORECASE):
        return True
    return False


def _sanitize_analysis_scalar(raw: object) -> str:
    token = str(raw or "").strip()
    if not token:
        return ""
    for pattern in (
        r"(?im)^\s*(?:topic|title|\u4e3b\u9898|\u9898\u76ee)\s*[:\uff1a]\s*(.+)$",
        r"(?im)^\s*['\"]?(?:topic|title|\u4e3b\u9898|\u9898\u76ee)['\"]?\s*:\s*['\"]?(.+?)['\"]?\s*$",
    ):
        match = re.search(pattern, token)
        if match:
            token = str(match.group(1) or "").strip()
            break
    if _analysis_text_is_meta_noise(token):
        lines = []
        for raw_line in re.split(r"[\r\n]+", token):
            line = str(raw_line or "").strip()
            if not line:
                continue
            if _analysis_text_is_meta_noise(line):
                continue
            if re.search(r"(?i)^(?:topic|title|doc_type|doctype|keywords?|key\s*points?|section_id)\s*[:=]", line):
                continue
            lines.append(line)
        token = " ".join(lines).strip()
    token = re.sub(r"\s+", " ", token).strip(" ,;:\uff1a\uff0c\u3002")
    if _analysis_text_is_meta_noise(token):
        return ""
    return token


def _normalize_analysis_doc_type(raw: object, instruction: str) -> str:
    token = _sanitize_analysis_scalar(raw)
    probe = token.lower()
    resolved = _resolve_doc_type_for_prompt(instruction)
    if probe in {"academic", "paper", "thesis", "report", "weekly"}:
        return probe
    if any(key in token for key in ["\u5b66\u672f", "\u8bba\u6587", "\u6bd5\u8bbe"]):
        return "academic"
    if any(key in token for key in ["\u62a5\u544a", "report"]):
        return "report"
    if any(key in token for key in ["\u5468\u62a5", "weekly"]):
        return "weekly"
    return resolved or "academic"


def _normalize_analysis_topic(raw: object, instruction: str) -> str:
    title_hint = _sanitize_analysis_scalar(_guess_title(instruction))
    topic = _sanitize_analysis_scalar(raw)
    normalized_title = _normalize_reference_query(title_hint)
    normalized_topic = _normalize_reference_query(topic)
    title_tokens = set(_topic_tokens(normalized_title or title_hint))
    topic_tokens = set(_topic_tokens(normalized_topic or topic))
    if title_hint:
        if not topic:
            return title_hint
        if not topic_tokens:
            return title_hint
        overlap = float(len(title_tokens & topic_tokens)) / float(max(1, len(title_tokens))) if title_tokens else 1.0
        if overlap < 0.35:
            return title_hint
        if len(topic_tokens) > max(10, len(title_tokens) + 6):
            return title_hint
    if topic:
        return topic
    if title_hint:
        return title_hint
    fallback = _sanitize_analysis_scalar(instruction)
    return fallback or str(instruction or "").strip()


def _normalize_analysis_keywords(raw_keywords: object, *, topic: str, instruction: str) -> list[str]:
    candidates: list[object] = []
    if isinstance(raw_keywords, list):
        candidates.extend(raw_keywords)
    elif isinstance(raw_keywords, str):
        candidates.extend(re.split(r"[,;\uff0c\uff1b/\n\r]+", raw_keywords))

    cleaned: list[str] = []
    for raw in candidates:
        token = _sanitize_analysis_scalar(raw)
        if not token:
            continue
        normalized = _normalize_reference_query(token)
        probe = normalized or token
        parts = [part.lower() for part in re.findall(r"[\u4e00-\u9fff]{2,}|[a-z][a-z0-9_\-]{1,}", probe, flags=re.IGNORECASE)]
        if not parts:
            continue
        if all(part in _ANALYSIS_SCHEMA_TOKENS for part in parts):
            continue
        if any(part in _ANALYSIS_SCHEMA_TOKENS for part in parts) and not any("\u4e00" <= ch <= "\u9fff" for ch in token):
            continue
        if len(parts) > 8:
            continue
        cleaned.append(token if any("\u4e00" <= ch <= "\u9fff" for ch in token) else probe)

    if not cleaned:
        seed = _normalize_reference_query(_guess_title(instruction) or "") or _normalize_reference_query(topic) or _normalize_reference_query(instruction)
        cleaned = _topic_tokens(seed)[:8]
    return _dedupe_keep_order([str(x).strip() for x in cleaned if str(x).strip()])[:8]


def _normalize_analysis_for_generation(data: dict, instruction: str) -> dict:
    base = data if isinstance(data, dict) else {}
    topic = _normalize_analysis_topic(base.get("topic"), instruction)
    doc_type = _normalize_analysis_doc_type(base.get("doc_type"), instruction)
    keywords = _normalize_analysis_keywords(base.get("keywords"), topic=topic, instruction=instruction)
    must_include_raw = base.get("must_include")
    must_include_items = [_sanitize_analysis_scalar(x) for x in must_include_raw] if isinstance(must_include_raw, list) else []
    must_include_items = [x for x in must_include_items if x]
    constraints_raw = base.get("constraints")
    constraints_items = [_sanitize_analysis_scalar(x) for x in constraints_raw] if isinstance(constraints_raw, list) else []
    constraints_items = [x for x in constraints_items if x]
    must_include = _normalize_must_include_sections(
        must_include_raw=must_include_items,
        constraints_raw=constraints_items,
        instruction=instruction,
        doc_type=doc_type,
    )
    confidence_raw = base.get("confidence")
    confidence = confidence_raw if isinstance(confidence_raw, dict) else {}

    def _field_conf(name: str, default: float) -> float:
        try:
            value = float(confidence.get(name, default))
        except Exception:
            value = default
        return max(0.0, min(1.0, value))

    conf_map = {
        "topic": _field_conf("topic", 0.7 if topic else 0.2),
        "doc_type": _field_conf("doc_type", 0.65 if doc_type else 0.2),
        "structure": _field_conf("structure", 0.66 if must_include else 0.58),
        "keywords": _field_conf("keywords", 0.64 if keywords else 0.56),
    }
    conf_score = round(sum(conf_map.values()) / float(len(conf_map)), 4)
    missing: list[str] = []
    if not topic:
        missing.append("topic")
    if not doc_type:
        missing.append("doc_type")

    clarification: list[str] = []
    if conf_map["topic"] < 0.55:
        clarification.append("???????????")
    if conf_map["doc_type"] < 0.55:
        clarification.append("????????????/????/????")
    if conf_map["structure"] < 0.5:
        clarification.append("???????????????????????")
    if conf_map["keywords"] < 0.45:
        clarification.append("???3-5??????????")
    if not clarification and missing:
        clarification.append("????????????????????")

    out = dict(base)
    out["topic"] = topic
    out["doc_type"] = doc_type
    out["keywords"] = keywords
    out["must_include"] = must_include
    out["confidence"] = conf_map
    out["_confidence_score"] = conf_score
    out["_clarification_questions"] = clarification
    out["_schema_missing"] = missing
    out["_schema_valid"] = len(missing) == 0
    return out


__all__ = [name for name in globals() if not name.startswith("__")]
