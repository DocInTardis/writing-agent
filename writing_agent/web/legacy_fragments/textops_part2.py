"""Legacy text operation helpers: reference extraction."""

from __future__ import annotations

import os
import re


def _reference_section(text: str) -> str:
    src = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    match = re.search(r"(?mi)^\s{0,3}#{0,6}\s*(参考文献|References|Bibliography)\s*$", src)
    if not match:
        return src
    return src[match.end() :].strip()


def _extract_reference_items_from_text(text: str) -> list[str]:
    body = _reference_section(text)
    if not body.strip():
        return []
    conservative = str(os.environ.get("WRITING_AGENT_REFERENCE_CONSERVATIVE_REPAIR", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if conservative:
        bracketed = [line for line in lines if re.match(r"^\s*(?:\[\d+\]|\d+[.)])\s+", line)]
        if len(bracketed) <= 1:
            return [line for line in lines if line]

    items: list[str] = []
    current: list[str] = []
    for line in lines:
        starts_item = bool(re.match(r"^\s*(?:\[\d+\]|\d+[.)])\s+", line))
        if starts_item and current:
            items.append(" ".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        items.append(" ".join(current).strip())
    return [item for item in items if item]


def bind(ns: dict[str, object]) -> None:
    globals().update(ns or {})


def install(g: dict) -> None:
    g["_extract_reference_items_from_text"] = _extract_reference_items_from_text


__all__ = [name for name in globals() if not name.startswith("__")]
