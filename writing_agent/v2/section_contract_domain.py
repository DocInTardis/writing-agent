"""Section contract helpers: construction, evidence rebalance, rules, and slots."""

from __future__ import annotations

import os
import re
from dataclasses import replace

# -- Low-level rules and numeric helpers --


def _base():
    from writing_agent.v2 import section_contract as base

    return base


def _contract_scale(*, total_chars: int, section_count: int) -> float:
    raw = str(os.environ.get("WRITING_AGENT_SECTION_CONTRACT_SCALE", "")).strip()
    if raw:
        try:
            value = float(raw)
        except Exception:
            value = 1.0
        return max(0.3, min(1.0, value))

    total = max(0, int(total_chars or 0))
    count = max(1, int(section_count or 1))
    avg_share = float(total) / float(count) if total > 0 else 0.0
    if avg_share <= 0 or avg_share >= 900.0:
        return 1.0
    return max(0.55, min(1.0, avg_share / 900.0))


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value or 0)
    except Exception:
        return int(default)


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return float(default)


def _section_budget_floor(title: str) -> int:
    section = str(title or "").strip()
    base = _base()
    if base._ABSTRACT_RE.search(section):
        return 260
    if base._KEYWORDS_RE.search(section) or base._REFERENCES_RE.search(section):
        return 0
    if re.search("(\u7ed3\u8bba|conclusion|discussion|\u8ba8\u8bba)", section, re.IGNORECASE):
        return 220
    if re.search("(\u5f15\u8a00|\u7eea\u8bba|introduction)", section, re.IGNORECASE):
        return 260
    return 180


# -- Construction helpers --


def build_contracts(*, paradigm: str, sections: list[str], total_chars: int, base_min_paras: int) -> dict[str, object]:
    out: dict[str, object] = {}
    base = _base()
    paradigm_key = str(paradigm or "").strip().lower()
    section_count = max(1, len([section for section in sections if str(section).strip()]))
    fallback_share = max(220, int(float(total_chars or 0) / float(section_count))) if total_chars > 0 else 600
    scale = _contract_scale(total_chars=total_chars, section_count=section_count)

    for sec in sections:
        title = str(sec or "").strip()
        if not title:
            continue
        min_chars = max(220, int(fallback_share * 0.7))
        max_chars = max(min_chars + 260, int(fallback_share * 1.35))
        min_paras = max(1, int(base_min_paras or 1))
        required_slots: list[str] = []
        min_keyword_items = 0
        max_keyword_items = 0
        dimension_hints = list(base._DEFAULT_DIMENSION_HINTS)

        if base._ABSTRACT_RE.search(title):
            min_chars, max_chars, min_paras = 300, 520, 1
        elif base._KEYWORDS_RE.search(title):
            min_chars, max_chars, min_paras = 0, 220, 1
            required_slots = ["keywords"]
            min_keyword_items = 3
            max_keyword_items = 8
            dimension_hints = list(base._KEYWORDS_DIMENSION_HINTS)
        elif base._REFERENCES_RE.search(title):
            min_chars, max_chars, min_paras = 0, 0, 1
        elif paradigm_key == "bibliometric":
            for pattern, (rule_min, rule_max) in base._BIB_SECTION_RULES:
                if pattern.search(title):
                    min_chars, max_chars = rule_min, rule_max
                    break

        if scale < 1.0 and (not base._KEYWORDS_RE.search(title)) and (not base._REFERENCES_RE.search(title)):
            min_chars = max(180, int(round(float(min_chars) * scale)))
            max_chars = max(min_chars + 160, int(round(float(max_chars) * scale)))

        out[sec] = base.SectionContractSpec(
            section=title,
            min_chars=min_chars,
            max_chars=max_chars,
            min_paras=min_paras,
            required_slots=required_slots,
            min_keyword_items=min_keyword_items,
            max_keyword_items=max_keyword_items,
            dimension_hints=dimension_hints,
        )
    return out


# -- Evidence rebalance helpers --


def estimate_supported_chars(*, section_title: str, contract: object, evidence: dict | None) -> int:
    base = _base()
    if not isinstance(contract, base.SectionContractSpec):
        return 0
    title = str(section_title or contract.section or "").strip()
    if not title:
        return max(0, int(contract.max_chars or contract.min_chars or 0))
    if base._KEYWORDS_RE.search(title) or base._REFERENCES_RE.search(title):
        return max(0, int(contract.max_chars or 0))
    if base._ABSTRACT_RE.search(title):
        return max(260, min(int(contract.max_chars or 520), 520))

    payload = evidence if isinstance(evidence, dict) else {}
    starvation = payload.get("data_starvation") if isinstance(payload.get("data_starvation"), dict) else {}
    fact_gain_count = _safe_int(payload.get("fact_gain_count"), 0)
    fact_density_score = max(0.0, _safe_float(payload.get("fact_density_score"), 0.0))
    source_count = len([row for row in (payload.get("sources") or []) if isinstance(row, dict)])
    if source_count <= 0:
        source_count = _safe_int(starvation.get("source_count"), 0)
    context_chars = len(str(payload.get("summary") or payload.get("context") or "").strip())
    alignment_score = _safe_float(starvation.get("alignment_score"), 1.0)
    stub_mode = bool(starvation.get("stub_mode")) or bool(starvation.get("is_starved"))

    base_floor = _section_budget_floor(title)
    fact_budget = int(round(float(fact_gain_count) * (180.0 + min(1.0, fact_density_score) * 120.0)))
    source_budget = int(round(float(source_count) * 160.0))
    context_budget = min(900, int(round(float(context_chars) * 0.12)))
    raw_supported = base_floor + fact_budget + source_budget + context_budget
    if source_count <= 0 and fact_gain_count <= 0 and context_chars <= 0:
        raw_supported = base_floor
    if stub_mode:
        raw_supported = max(base_floor, int(round(float(raw_supported) * 0.7)))
    if alignment_score > 0.0:
        alignment_factor = max(0.65, min(1.0, 0.7 + alignment_score * 0.3))
        raw_supported = int(round(float(raw_supported) * alignment_factor))

    hard_cap = int(contract.max_chars or 0)
    if hard_cap > 0:
        raw_supported = min(hard_cap, raw_supported)
    return max(base_floor, raw_supported)


def rebalance_contracts_by_evidence(*, contracts: dict[str, object], evidence_by_section: dict[str, dict]) -> tuple[dict[str, object], list[dict[str, object]]]:
    base = _base()
    out: dict[str, object] = {}
    rows: list[dict[str, object]] = []
    for section_key, spec in (contracts or {}).items():
        if not isinstance(spec, base.SectionContractSpec):
            continue
        title = str(spec.section or section_key or "").strip()
        evidence = evidence_by_section.get(section_key) if isinstance(evidence_by_section, dict) else None
        supported_chars = estimate_supported_chars(section_title=title, contract=spec, evidence=evidence)
        if supported_chars <= 0 or base._KEYWORDS_RE.search(title) or base._REFERENCES_RE.search(title):
            out[section_key] = spec
            continue
        floor = _section_budget_floor(title)
        new_min = min(int(spec.min_chars), max(floor, int(round(float(supported_chars) * 0.72))))
        new_max = max(new_min + 80, min(int(spec.max_chars or supported_chars), supported_chars))
        if int(spec.max_chars or 0) > 0:
            new_max = min(new_max, int(spec.max_chars))
        if new_max < new_min:
            new_max = new_min
        if new_min == int(spec.min_chars) and new_max == int(spec.max_chars):
            out[section_key] = spec
            continue
        adjusted = replace(spec, min_chars=int(new_min), max_chars=int(new_max))
        out[section_key] = adjusted
        starvation = evidence.get("data_starvation") if isinstance(evidence, dict) and isinstance(evidence.get("data_starvation"), dict) else {}
        rows.append(
            {
                "section": str(section_key),
                "title": title,
                "old_min_chars": int(spec.min_chars),
                "old_max_chars": int(spec.max_chars),
                "new_min_chars": int(adjusted.min_chars),
                "new_max_chars": int(adjusted.max_chars),
                "supported_chars": int(supported_chars),
                "fact_gain_count": _safe_int((evidence or {}).get("fact_gain_count"), 0),
                "source_count": len([row for row in ((evidence or {}).get("sources") or []) if isinstance(row, dict)]) or _safe_int(starvation.get("source_count"), 0),
                "fact_density_score": _safe_float((evidence or {}).get("fact_density_score"), 0.0),
                "stub_mode": bool(starvation.get("stub_mode")),
            }
        )
    for section_key, spec in (contracts or {}).items():
        if section_key not in out and isinstance(spec, base.SectionContractSpec):
            out[section_key] = spec
    return out, rows


# -- Slot-filling helpers --


def _is_keywords_section(section_title: str) -> bool:
    return bool(_base()._KEYWORDS_RE.search(str(section_title or "")))


def _extract_terms(text: str) -> list[str]:
    base = _base()
    raw = str(text or "").strip()
    if not raw:
        return []
    normalized = re.sub(rf"(?i)^{base._ZH_KEYWORDS}\s*[:{base._ZH_COLON}]\s*", "", raw).strip()
    normalized = normalized.replace("\n", base._ZH_SEP)
    chunks = re.split(rf"[\s,{base._ZH_COMMA};{base._ZH_SEP}]+", normalized)
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
