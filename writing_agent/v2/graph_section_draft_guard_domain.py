"""Semantic sampling guard helpers extracted from graph_section_draft_domain."""

from __future__ import annotations

import re

from writing_agent.v2.meta_firewall import MetaFirewall


_META_FIREWALL = MetaFirewall()
_SEMANTIC_META_PATTERNS = [
    re.compile(r"^(?:本段旨在|本节将|本章将|应当涵盖|需要说明|请在本节)", re.IGNORECASE),
    re.compile(r"(?:本节|本段).{0,16}(?:应|需|建议|请).{0,24}(?:验收|可复核|可复现|边界|约束)", re.IGNORECASE),
    re.compile(r"(?:围绕|针对).{0,24}(?:应说明|需交代|补充).{0,36}(?:验收标准|可复核|可复现|边界|约束)", re.IGNORECASE),
]
_SECTION_NARRATION_HINTS = ("本节", "本章", "本段", "该部分")
_SECTION_NARRATION_ACTIONS = ("说明", "阐述", "展开", "补充", "交代", "聚焦")


def _hits_semantic_sampling_guard(*, text: str, section: str) -> list[str]:
    sample = str(text or "").strip()
    if not sample:
        return []
    hits = list(_META_FIREWALL.scan(sample).fragments[:4])
    if hits:
        return hits
    for pattern in _SEMANTIC_META_PATTERNS:
        if pattern.search(sample):
            return [sample[:120]]
    section_name = str(section or "").strip()
    if section_name and sample.startswith(section_name) and any(mark in sample[:16] for mark in (":", "：", "-", "1.", "一、")):
        return [sample[:120]]
    if any(hint in sample[:24] for hint in _SECTION_NARRATION_HINTS) and any(action in sample[:40] for action in _SECTION_NARRATION_ACTIONS):
        return [sample[:120]]
    return []


__all__ = [name for name in globals() if not name.startswith("__")]
