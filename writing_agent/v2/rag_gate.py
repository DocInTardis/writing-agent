"""Theme consistency and entity-alignment gate for RAG sources."""

from __future__ import annotations

import re


_STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "using",
    "based",
    "study",
    "research",
    "analysis",
}

_CRITICAL_ENTITY_ALIAS: dict[str, list[str]] = {
    "blockchain": ["区块链", "blockchain", "distributed ledger", "分布式账本"],
    "citespace": ["citespace", "cite space", "知识图谱", "文献计量"],
    "rural_service": [
        "农村社会化服务",
        "农业社会化服务",
        "农村服务",
        "agricultural socialized service",
        "agricultural service",
        "rural service",
        "socialized service",
    ],
    "writing_agent": [
        "智能写作",
        "智能写作代理",
        "写作代理",
        "学术写作",
        "academic writing",
        "scientific writing",
        "student writing",
        "writing agent",
        "writing assistant",
        "agentic writing",
        "scholarly writing",
        "ai-assisted writing",
        "scholarcopilot",
        "copilot",
    ],
    "academic_research": [
        "高校科研",
        "科研场景",
        "科研工作流",
        "academic research",
        "university research",
        "higher education",
        "research workflow",
        "scholarly workflow",
    ],
}

_TOPIC_TERMS = [
    "区块链",
    "分布式账本",
    "农村",
    "农业",
    "社会化服务",
    "服务",
    "协同",
    "治理",
    "文献计量",
    "可视化",
    "知识图谱",
    "智能写作",
    "写作代理",
    "学术写作",
    "高校科研",
    "科研工作流",
]


_REFERENCE_METHOD_PATTERNS = (
    r"\bcitespace\b",
    r"\bcite\s*space\b",
    r"\bbibliometric\b",
    r"\bscientometric\b",
    r"knowledge mapping",
    r"visual(?:ization)? analysis",
)

_REFERENCE_NOISE_PATTERNS = (
    r"\bsupplemental information\b",
    r"\bsupporting information\b",
    r"\braw data\b",
    r"\bappendix\b",
    r"\btraceback\b",
    r"\bfigure\s*\d",
    r"\btable\s*\d",
    r"\bsettings\b",
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower()).strip()


def _split_keywords(text: str) -> set[str]:
    src = _normalize(text)
    if not src:
        return set()
    words = re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9][a-z0-9\-]{1,}", src)
    out: set[str] = set()
    for token in words:
        t = token.strip().lower()
        if not t or t in _STOP_WORDS:
            continue
        out.add(t)
    return out


def _extract_entities(title: str) -> list[str]:
    src = _normalize(title)
    entities: list[str] = []
    for canonical, aliases in _CRITICAL_ENTITY_ALIAS.items():
        if any(alias.lower() in src for alias in aliases):
            entities.append(canonical)
    return entities


def _matched_entities(title: str, source_text: str) -> list[str]:
    required_entities = _extract_entities(title)
    src = _normalize(source_text)
    if not required_entities or not src:
        return []
    matched: list[str] = []
    for canonical in required_entities:
        aliases = _CRITICAL_ENTITY_ALIAS.get(canonical) or []
        if any(alias.lower() in src for alias in aliases):
            matched.append(canonical)
    return matched


def theme_consistency_score(*, title: str, source_text: str) -> float:
    title_terms = _title_terms(title)
    if not title_terms:
        return 0.0
    source_norm = _normalize(source_text)
    if not source_norm:
        return 0.0
    overlap = sum(1 for t in title_terms if t in source_norm)
    return float(overlap) / float(len(title_terms))


def _looks_like_method_reference(source_text: str) -> bool:
    src = _normalize(source_text)
    if not src:
        return False
    return any(re.search(pattern, src, flags=re.IGNORECASE) for pattern in _REFERENCE_METHOD_PATTERNS)


def _looks_like_reference_noise(title: str, source_text: str) -> bool:
    title_norm = _normalize(title)
    src = _normalize(source_text)
    if title_norm in {"citespace", "cite space"}:
        return True
    if len(title_norm) < 8 and not re.search(r"[\u4e00-\u9fff]", title_norm):
        return True
    return any(re.search(pattern, src, flags=re.IGNORECASE) for pattern in _REFERENCE_NOISE_PATTERNS)


def entity_aligned(*, title: str, source_text: str, mode: str = "strict") -> bool:
    required_entities = _extract_entities(title)
    if not required_entities:
        return True
    matched = _matched_entities(title, source_text)
    if mode == "reference":
        if not matched:
            return False
        topic_matches = [item for item in matched if item != "citespace"]
        if topic_matches:
            return True
        return _looks_like_method_reference(source_text)
    return len(matched) == len(required_entities)


def _title_terms(title: str) -> set[str]:
    src = _normalize(title)
    terms: set[str] = set()
    if not src:
        return terms
    matched_entities = _extract_entities(title)
    for canonical in matched_entities:
        for alias in (_CRITICAL_ENTITY_ALIAS.get(canonical) or []):
            token = alias.lower().strip()
            if token:
                terms.add(token)
    for aliases in _CRITICAL_ENTITY_ALIAS.values():
        for alias in aliases:
            token = alias.lower()
            if token and token in src:
                terms.add(token)
    for token in _TOPIC_TERMS:
        low = token.lower()
        if low and low in src:
            terms.add(low)
    for token in re.findall(r"[a-z0-9][a-z0-9\-]{1,}", src):
        if token in _STOP_WORDS:
            continue
        terms.add(token)
    if terms:
        return terms
    return _split_keywords(title)


def filter_sources(
    *,
    title: str,
    sources: list[dict],
    min_theme_score: float = 0.25,
    mode: str = "strict",
) -> dict[str, object]:
    kept: list[dict] = []
    dropped: list[dict] = []
    for item in sources or []:
        row = item if isinstance(item, dict) else {}
        row_title = str(row.get("title") or "").strip()
        source_text = " ".join(
            [
                row_title,
                str(row.get("summary") or ""),
                str(row.get("snippet") or ""),
                str(row.get("url") or ""),
                str(row.get("source") or ""),
            ]
        ).strip()
        score = theme_consistency_score(title=title, source_text=source_text)
        matched = _matched_entities(title, source_text)
        aligned = entity_aligned(title=title, source_text=source_text, mode=mode)
        threshold = float(min_theme_score)
        if mode == "reference":
            if _looks_like_reference_noise(row_title, source_text):
                dropped.append(
                    {
                        "title": row_title,
                        "url": str(row.get("url") or ""),
                        "theme_score": float(score),
                        "entity_aligned": bool(aligned),
                        "reason": "rag_reference_noise",
                    }
                )
                continue
            topical_matches = [item for item in matched if item != "citespace"]
            if topical_matches or matched:
                threshold = max(0.04, min(threshold, 0.04))
        if score >= float(threshold) and aligned:
            kept.append(row)
            continue
        dropped.append(
            {
                "title": row_title,
                "url": str(row.get("url") or ""),
                "theme_score": float(score),
                "entity_aligned": bool(aligned),
                "reason": "rag_entity_mismatch" if not aligned else "rag_theme_mismatch",
            }
        )
    return {"kept": kept, "dropped": dropped}


_GENERIC_SECTION_TERMS = {
    "摘要",
    "关键词",
    "引言",
    "绪论",
    "讨论",
    "结论",
    "参考文献",
    "abstract",
    "keywords",
    "introduction",
    "discussion",
    "conclusion",
    "references",
}


def _section_terms(section_title: str) -> set[str]:
    out = _split_keywords(section_title)
    return {token for token in out if token not in _GENERIC_SECTION_TERMS}



def section_theme_consistency_score(*, document_title: str, section_title: str, source_text: str) -> dict[str, float]:
    document_score = theme_consistency_score(title=document_title, source_text=source_text)
    section_terms = _section_terms(section_title)
    if not section_terms:
        return {"document_score": float(document_score), "section_score": 1.0}
    source_norm = _normalize(source_text)
    if not source_norm:
        return {"document_score": float(document_score), "section_score": 0.0}
    overlap = sum(1 for token in section_terms if token in source_norm)
    return {
        "document_score": float(document_score),
        "section_score": float(overlap) / float(len(section_terms)),
    }



def filter_sources_for_section(
    *,
    document_title: str,
    section_title: str,
    sources: list[dict],
    min_theme_score: float = 0.25,
    min_section_score: float = 0.35,
    mode: str = "strict",
) -> dict[str, object]:
    kept: list[dict] = []
    dropped: list[dict] = []
    for item in sources or []:
        row = item if isinstance(item, dict) else {}
        row_title = str(row.get("title") or "").strip()
        source_text = " ".join(
            [
                row_title,
                str(row.get("summary") or ""),
                str(row.get("snippet") or ""),
                str(row.get("url") or ""),
                str(row.get("source") or ""),
            ]
        ).strip()
        score_row = section_theme_consistency_score(
            document_title=document_title,
            section_title=section_title,
            source_text=source_text,
        )
        document_score = float(score_row.get("document_score") or 0.0)
        section_score = float(score_row.get("section_score") or 0.0)
        aligned = entity_aligned(title=document_title, source_text=source_text, mode=mode)
        section_terms = _section_terms(section_title)
        if document_score >= float(min_theme_score) and aligned and (not section_terms or section_score >= float(min_section_score)):
            kept.append(row)
            continue
        reason = "rag_entity_mismatch" if not aligned else "rag_section_theme_mismatch"
        if document_score < float(min_theme_score):
            reason = "rag_theme_mismatch"
        dropped.append(
            {
                "title": row_title,
                "url": str(row.get("url") or ""),
                "document_theme_score": float(document_score),
                "section_theme_score": float(section_score),
                "entity_aligned": bool(aligned),
                "section": str(section_title or ""),
                "reason": reason,
            }
        )
    return {"kept": kept, "dropped": dropped}
