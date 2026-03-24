"""Context expansion helpers extracted from graph_runner_post_domain."""

from __future__ import annotations

import re


def _base():
    from writing_agent.v2 import graph_runner_post_domain as base
    return base


def _plan_point_paragraph(section: str, plan, idx: int) -> str:
    if not plan or not getattr(plan, "key_points", None):
        return ""
    base = _base()
    sec = (base._section_title(section) or section).strip() or "??"
    points = [p for p in (plan.key_points or []) if p]
    if not points:
        return ""
    point = points[(idx - 1) % len(points)]
    templates = [
        f"{sec}??{point}???????????????????????????????????",
        f"{sec}??????????????????????????????????",
        f"{sec}????????????????????????????????????",
        f"{sec}??????????????????????????????????????",
    ]
    return templates[(idx - 1) % len(templates)]


def _expand_with_context(
    section: str,
    text: str,
    ctx: str,
    min_chars: int,
    min_paras: int,
    plan=None,
) -> str:
    base_mod = _base()
    base = (text or '').strip()
    if not ctx or min_chars <= 0:
        return base
    chunks = [p.strip() for p in re.split(r'\n\s*\n+', ctx) if p.strip()]
    added = 0
    emitted_norm: set[str] = set()
    for para in re.split(r"\n\s*\n+", base):
        token = re.sub(r"\s+", " ", para or "").strip()
        if token:
            emitted_norm.add(token)
    for chunk in chunks:
        cleaned = base_mod._strip_rag_meta_lines(chunk)
        if len(cleaned) < 40:
            continue
        if cleaned in base:
            continue
        if re.match(r'^#{1,3}\s+', cleaned):
            continue
        if len(set(cleaned)) <= 12:
            continue
        norm = re.sub(r"\s+", " ", cleaned).strip()
        if not norm or norm in emitted_norm:
            continue
        emitted_norm.add(norm)
        base = (base + '\n\n' + cleaned) if base else cleaned
        added += 1
        if base_mod._section_body_len(base) >= min_chars and added >= max(0, min_paras - 1):
            break
    max_add = max(min_paras, min(4, max(2, int(min_chars / 320) or 2)))
    while base_mod._section_body_len(base) < min_chars and added < max_add:
        extra = _plan_point_paragraph(section, plan, added + 1)
        if not extra:
            break
        base = (base + '\n\n' + extra) if base else extra
        added += 1
    return base


__all__ = [name for name in globals() if not name.startswith("__")]
