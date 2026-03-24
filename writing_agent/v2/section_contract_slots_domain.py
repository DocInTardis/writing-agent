"""Section contract slot-filling helpers."""

from __future__ import annotations

import re


def _base():
    from writing_agent.v2 import section_contract as base

    return base


def _is_keywords_section(section_title: str) -> bool:
    return bool(_base()._KEYWORDS_RE.search(str(section_title or "")))


def _extract_terms(text: str) -> list[str]:
    base = _base()
    raw = str(text or "").strip()
    if not raw:
        return []
    normalized = re.sub(f"(?i)^{base._ZH_KEYWORDS}\\s*[:{base._ZH_COLON}]\\s*", "", raw).strip()
    normalized = normalized.replace("\n", base._ZH_SEP)
    chunks = re.split(f"[\\s,{base._ZH_COMMA};{base._ZH_SEP}]+", normalized)
    out: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        token = str(chunk or "").strip().strip(base._ZH_SEP)
        if not token or re.fullmatch(r"[\W_]+", token):
            continue
        key = token.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(token)
    return out


def fill_slots(*, section_title: str, text: str, analysis: dict | None, contract: object | None) -> str:
    base = _base()
    if not _is_keywords_section(section_title):
        return text
    spec = contract if isinstance(contract, base.SectionContractSpec) else None
    min_items = int(spec.min_keyword_items if spec else 3)
    max_items = int(spec.max_keyword_items if spec else 8)
    terms = _extract_terms(text)
    seen = {term.casefold() for term in terms}

    analysis_obj = analysis if isinstance(analysis, dict) else {}
    candidate_terms: list[str] = []
    for item in (analysis_obj.get("keywords") or []):
        token = str(item or "").strip()
        if token:
            candidate_terms.append(token)
    topic = str(analysis_obj.get("topic") or "").strip()
    if topic:
        candidate_terms.extend(_extract_terms(topic))

    for token in candidate_terms:
        if len(terms) >= max_items:
            break
        key = token.casefold()
        if key in seen:
            continue
        seen.add(key)
        terms.append(token)

    while len(terms) < min_items:
        for fallback in base._KEYWORD_FALLBACK_TERMS:
            key = fallback.casefold()
            if key in seen:
                continue
            seen.add(key)
            terms.append(fallback)
            if len(terms) >= min_items:
                break
        else:
            break

    terms = terms[:max_items]
    if not terms:
        return text
    return base._ZH_KW_PREFIX + base._ZH_SEP.join(terms)


def validate_slots(*, section_title: str, text: str, contract: object | None) -> list[str]:
    base = _base()
    if not _is_keywords_section(section_title):
        return []
    spec = contract if isinstance(contract, base.SectionContractSpec) else None
    min_items = int(spec.min_keyword_items if spec else 3)
    max_items = int(spec.max_keyword_items if spec else 8)
    terms = _extract_terms(text)
    required_slots = list(spec.required_slots if spec else ["keywords"])
    issues: list[str] = []
    if "keywords" in required_slots and not terms:
        issues.append("keyword_slot_missing")
        return issues
    if len(terms) < min_items:
        issues.append("keyword_slot_insufficient")
    if len(terms) > max_items:
        issues.append("keyword_slot_overflow")
    return issues


__all__ = [name for name in globals() if not name.startswith('__')]
