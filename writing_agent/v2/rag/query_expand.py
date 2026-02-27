"""Query Expand module.

This module belongs to `writing_agent.v2.rag` in the writing-agent codebase.
"""

from __future__ import annotations


def expand_queries(query: str, *, max_queries: int = 4) -> list[str]:
    base = str(query or "").strip()
    if not base:
        return []
    variants = [base]
    parts = [x.strip() for x in base.replace("，", ",").split(",") if x.strip()]
    if len(parts) >= 2:
        variants.append(" ".join(parts[:2]))
        variants.append(" ".join(parts[-2:]))
    variants.append(f"{base} implementation")
    out: list[str] = []
    seen: set[str] = set()
    for item in variants:
        key = item.lower().strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= max(1, int(max_queries)):
            break
    return out
