"""Section contract low-level rules and numeric helpers."""

from __future__ import annotations

import os
import re


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


__all__ = [name for name in globals() if not name.startswith('__')]
