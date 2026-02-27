"""Context Governance module.

This module belongs to `writing_agent.v2` in the writing-agent codebase.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class SectionBudget:
    section: str
    token_budget: int


def estimate_token_count(text: str) -> int:
    # practical approximation for mixed CJK/EN prompts
    s = str(text or "").strip()
    if not s:
        return 0
    return max(1, int(math.ceil(len(s) / 2.4)))


def allocate_token_budget(*, sections: list[str], total_budget: int) -> list[SectionBudget]:
    items = [str(s).strip() for s in sections if str(s).strip()]
    if not items:
        return []
    total_budget = max(256, int(total_budget))
    weight_sum = sum(max(1, len(s)) for s in items)
    out: list[SectionBudget] = []
    remaining = total_budget
    for i, sec in enumerate(items):
        if i == len(items) - 1:
            alloc = max(64, remaining)
        else:
            alloc = max(64, int(total_budget * (max(1, len(sec)) / weight_sum)))
            remaining -= alloc
        out.append(SectionBudget(section=sec, token_budget=alloc))
    return out


def compress_context(text: str, *, max_chars: int = 1200, preserve: list[str] | None = None) -> str:
    body = str(text or "").strip()
    if len(body) <= max_chars:
        return body
    keep = [k for k in (preserve or []) if str(k).strip()]
    keep_lines: list[str] = []
    for line in body.splitlines():
        ln = line.strip()
        if any(key in ln for key in keep):
            keep_lines.append(ln)
    prefix = "\n".join(keep_lines)[: int(max_chars * 0.35)]
    tail = body[-max(0, max_chars - len(prefix) - 8) :]
    return (prefix + "\n...\n" + tail).strip()
