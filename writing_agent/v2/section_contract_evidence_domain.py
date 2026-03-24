"""Section contract evidence rebalance helpers."""

from __future__ import annotations

from dataclasses import replace

from writing_agent.v2 import section_contract_rules_domain as rules_domain


def _base():
    from writing_agent.v2 import section_contract as base

    return base


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
    fact_gain_count = rules_domain._safe_int(payload.get("fact_gain_count"), 0)
    fact_density_score = max(0.0, rules_domain._safe_float(payload.get("fact_density_score"), 0.0))
    source_count = len([row for row in (payload.get("sources") or []) if isinstance(row, dict)])
    if source_count <= 0:
        source_count = rules_domain._safe_int(starvation.get("source_count"), 0)
    context_chars = len(str(payload.get("summary") or payload.get("context") or "").strip())
    alignment_score = rules_domain._safe_float(starvation.get("alignment_score"), 1.0)
    stub_mode = bool(starvation.get("stub_mode")) or bool(starvation.get("is_starved"))

    base_floor = rules_domain._section_budget_floor(title)
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
        floor = rules_domain._section_budget_floor(title)
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
                "fact_gain_count": rules_domain._safe_int((evidence or {}).get("fact_gain_count"), 0),
                "source_count": len([row for row in ((evidence or {}).get("sources") or []) if isinstance(row, dict)]) or rules_domain._safe_int(starvation.get("source_count"), 0),
                "fact_density_score": rules_domain._safe_float((evidence or {}).get("fact_density_score"), 0.0),
                "stub_mode": bool(starvation.get("stub_mode")),
            }
        )
    for section_key, spec in (contracts or {}).items():
        if section_key not in out and isinstance(spec, base.SectionContractSpec):
            out[section_key] = spec
    return out, rows


__all__ = [name for name in globals() if not name.startswith('__')]
