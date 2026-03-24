"""Semantic sampling guard helpers extracted from graph_section_draft_domain."""

from __future__ import annotations

import re

from writing_agent.v2.meta_firewall import MetaFirewall


_META_FIREWALL = MetaFirewall()


def _hits_semantic_sampling_guard(*, text: str, section: str) -> list[str]:
    sample = str(text or "").strip()
    if not sample:
        return []
    hits = list(_META_FIREWALL.scan(sample).fragments[:4])
    if hits:
        return hits
    patterns = [
        r"^(?:??|??|??|??|??).{0,20}(?:??|??|??|??|??)",
        r"(?:??|??).{0,30}(?:??|??|??).{0,30}(?:??|??|??|??|??)",
    ]
    for pattern in patterns:
        if re.search(pattern, sample, flags=re.IGNORECASE):
            return [sample[:120]]
    section_name = str(section or "").strip()
    if section_name and sample.startswith(section_name) and ("?" in sample[:16] or "?" in sample[:16]):
        return [sample[:120]]
    return []


__all__ = [name for name in globals() if not name.startswith("__")]
