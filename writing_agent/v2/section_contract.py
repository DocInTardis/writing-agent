"""Section contract engine for target sizing, slot-filling and evidence-driven rebalance."""

from __future__ import annotations

from dataclasses import dataclass
import re

from writing_agent.v2 import section_contract_build_domain as build_domain
from writing_agent.v2 import section_contract_evidence_domain as evidence_domain
from writing_agent.v2 import section_contract_rules_domain as rules_domain
from writing_agent.v2 import section_contract_slots_domain as slots_domain

_ZH_ABSTRACT = "\u6458\u8981"
_ZH_KEYWORDS = "\u5173\u952e\u8bcd"
_ZH_REFERENCES = "\u53c2\u8003\u6587\u732e"
_ZH_KW_PREFIX = "\u5173\u952e\u8bcd\uff1a"
_ZH_SEP = "\uff1b"
_ZH_COLON = "\uff1a"
_ZH_COMMA = "\uff0c"

_ABSTRACT_RE = re.compile(rf"(^|\b)({_ZH_ABSTRACT}|abstract)(\b|$)", re.IGNORECASE)
_KEYWORDS_RE = re.compile(rf"(^|\b)({_ZH_KEYWORDS}|key ?words?)(\b|$)", re.IGNORECASE)
_REFERENCES_RE = re.compile(rf"({_ZH_REFERENCES}|references|bibliography)", re.IGNORECASE)

_BIB_SECTION_RULES: list[tuple[re.Pattern[str], tuple[int, int]]] = [
    (re.compile("(\u6570\u636e\u6765\u6e90|\u68c0\u7d22\u7b56\u7565|data source|search strategy)", re.IGNORECASE), (800, 1300)),
    (re.compile("(\u53d1\u6587\u91cf|\u65f6\u7a7a\u5206\u5e03|publication volume|temporal)", re.IGNORECASE), (900, 1500)),
    (re.compile("(\u5408\u4f5c\u7f51\u7edc|cooperation|collaboration)", re.IGNORECASE), (900, 1500)),
    (re.compile("(\u5173\u952e\u8bcd\u5171\u73b0|\u805a\u7c7b\u5206\u6790|cluster|co-occurrence)", re.IGNORECASE), (1100, 1800)),
    (re.compile("(\u7814\u7a76\u70ed\u70b9|\u7a81\u73b0|burst)", re.IGNORECASE), (1100, 1800)),
    (re.compile("(\u8ba8\u8bba|discussion)", re.IGNORECASE), (900, 1500)),
    (re.compile("(\u7ed3\u8bba|conclusion)", re.IGNORECASE), (600, 1100)),
]

_DEFAULT_DIMENSION_HINTS = [
    "\u4e0e\u540c\u7c7b\u7814\u7a76\u7684\u5bf9\u6bd4\u5dee\u5f02",
    "\u533a\u57df\u5dee\u5f02\u4e0e\u573a\u666f\u8fb9\u754c",
    "\u653f\u7b56\u5f71\u54cd\u4e0e\u6cbb\u7406\u673a\u5236",
    "\u65b9\u6cd5\u9650\u5236\u4e0e\u9002\u7528\u8303\u56f4",
]

_KEYWORDS_DIMENSION_HINTS = [
    "\u672f\u8bed\u5185\u6db5",
    "\u672f\u8bed\u8fb9\u754c",
    "\u672f\u8bed\u5173\u7cfb",
]

_KEYWORD_FALLBACK_TERMS = [
    "\u7814\u7a76\u5bf9\u8c61",
    "\u65b9\u6cd5\u8def\u5f84",
    "\u5b9e\u8bc1\u5206\u6790",
    "\u7ed3\u679c\u89e3\u91ca",
    "\u5e94\u7528\u8fb9\u754c",
]

@dataclass(frozen=True)
class SectionContractSpec:
    section: str
    min_chars: int
    max_chars: int
    min_paras: int
    required_slots: list[str]
    min_keyword_items: int = 0
    max_keyword_items: int = 0
    dimension_hints: list[str] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "section": self.section,
            "min_chars": int(self.min_chars),
            "max_chars": int(self.max_chars),
            "min_paras": int(self.min_paras),
            "required_slots": list(self.required_slots),
            "min_keyword_items": int(self.min_keyword_items),
            "max_keyword_items": int(self.max_keyword_items),
            "dimension_hints": list(self.dimension_hints or []),
        }

_contract_scale = rules_domain._contract_scale
_safe_int = rules_domain._safe_int
_safe_float = rules_domain._safe_float
_section_budget_floor = rules_domain._section_budget_floor

class SectionContract:
    def build_contracts(self, *, paradigm: str, sections: list[str], total_chars: int, base_min_paras: int) -> dict[str, SectionContractSpec]:
        return build_domain.build_contracts(
            paradigm=paradigm,
            sections=sections,
            total_chars=total_chars,
            base_min_paras=base_min_paras,
        )

    @staticmethod
    def _is_keywords_section(section_title: str) -> bool:
        return bool(slots_domain._is_keywords_section(section_title))

    @staticmethod
    def _extract_terms(text: str) -> list[str]:
        return slots_domain._extract_terms(text)

    def fill_slots(self, *, section_title: str, text: str, analysis: dict | None, contract: SectionContractSpec | None) -> str:
        return slots_domain.fill_slots(section_title=section_title, text=text, analysis=analysis, contract=contract)

    def validate_slots(self, *, section_title: str, text: str, contract: SectionContractSpec | None) -> list[str]:
        return slots_domain.validate_slots(section_title=section_title, text=text, contract=contract)

    def estimate_supported_chars(self, *, section_title: str, contract: SectionContractSpec, evidence: dict | None) -> int:
        return evidence_domain.estimate_supported_chars(section_title=section_title, contract=contract, evidence=evidence)

    def rebalance_contracts_by_evidence(self, *, contracts: dict[str, SectionContractSpec], evidence_by_section: dict[str, dict]) -> tuple[dict[str, SectionContractSpec], list[dict[str, object]]]:
        return evidence_domain.rebalance_contracts_by_evidence(contracts=contracts, evidence_by_section=evidence_by_section)

__all__ = [name for name in globals() if not name.startswith("__")]
