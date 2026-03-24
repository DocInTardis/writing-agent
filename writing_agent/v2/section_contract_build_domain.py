"""Section contract construction helpers."""

from __future__ import annotations

from writing_agent.v2 import section_contract_rules_domain as rules_domain


def _base():
    from writing_agent.v2 import section_contract as base

    return base


def build_contracts(*, paradigm: str, sections: list[str], total_chars: int, base_min_paras: int) -> dict[str, object]:
    out: dict[str, object] = {}
    base = _base()
    paradigm_key = str(paradigm or "").strip().lower()
    section_count = max(1, len([section for section in sections if str(section).strip()]))
    fallback_share = max(220, int(float(total_chars or 0) / float(section_count))) if total_chars > 0 else 600
    scale = rules_domain._contract_scale(total_chars=total_chars, section_count=section_count)

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


__all__ = [name for name in globals() if not name.startswith('__')]
