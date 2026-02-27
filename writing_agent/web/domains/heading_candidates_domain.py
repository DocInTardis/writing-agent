"""Heading Candidates Domain module.

This module belongs to `writing_agent.web.domains` in the writing-agent codebase.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable


def _dedup_keep_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        title = str(raw or "").strip()
        if not title or title in seen:
            continue
        seen.add(title)
        out.append(title)
    return out


def collect_heading_candidates(session: Any, fast_report_sections: list[str]) -> list[str]:
    titles: list[str] = []
    for item in (getattr(session, "template_required_h2", None) or []):
        t = str(item or "").strip()
        if t:
            titles.append(t)
    for item in (getattr(session, "template_outline", None) or []):
        try:
            _, title = item
        except Exception:
            continue
        t = str(title or "").strip()
        if t:
            titles.append(t)
    titles.extend([str(x or "").strip() for x in (fast_report_sections or []) if str(x or "").strip()])
    return _dedup_keep_order(titles)


def extract_heading_candidates_from_text(
    text: str,
    *,
    parse_report_text: Callable[[str], Any],
) -> list[str]:
    if not text:
        return []
    try:
        parsed = parse_report_text(text)
    except Exception:
        return []
    titles: list[str] = []
    for block in (getattr(parsed, "blocks", None) or []):
        if getattr(block, "type", "") != "heading":
            continue
        t = str(getattr(block, "text", "") or "").strip()
        if t:
            titles.append(t)
    return _dedup_keep_order(titles)


def heading_candidates_for_revision(
    session: Any,
    base_text: str,
    *,
    fast_report_sections: list[str],
    parse_report_text: Callable[[str], Any],
) -> list[str]:
    base_titles = collect_heading_candidates(session, fast_report_sections)
    text_titles = extract_heading_candidates_from_text(base_text, parse_report_text=parse_report_text)
    return _dedup_keep_order([*base_titles, *text_titles])
