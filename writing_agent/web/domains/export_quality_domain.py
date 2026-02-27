"""Export Quality Domain module.

This module belongs to `writing_agent.web.domains` in the writing-agent codebase.
"""

from __future__ import annotations

import re
from typing import Callable


def coerce_optional_bool(value: object) -> bool | None:
    raw = str(value or "").strip().lower()
    if not raw:
        return None
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return None


def compact_list_spacing_for_export(text: str) -> str:
    lines = (text or "").splitlines()

    def is_list_line(line: str) -> bool:
        t = (line or "").strip()
        if not t:
            return False
        if re.match(r"^\d+[.\uFF0E\u3001\)]\s+", t):
            return True
        if re.match(r"^[一二三四五六七八九十两]+[.\u3001\)]\s+", t):
            return True
        if re.match(r"^[\u2022\u00B7]\s+", t):
            return True
        return False

    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip():
            out.append(line)
            i += 1
            continue
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        prev = ""
        for k in range(len(out) - 1, -1, -1):
            if out[k].strip():
                prev = out[k]
                break
        next_line = lines[j] if j < len(lines) else ""
        if prev and next_line and is_list_line(prev) and is_list_line(next_line):
            i = j
            continue
        out.append("")
        i = j
    return "\n".join(out)


def clean_export_text(
    text: str,
    *,
    json_converter: Callable[[str], str | None] | None = None,
) -> str:
    s = (text or "").replace("\r", "")
    converted = json_converter(s) if callable(json_converter) else None
    if converted:
        s = converted
    # Normalize heading markers: "##标题" -> "## 标题"
    s = re.sub(r"(?m)^(#{1,6})([^#\s])", r"\1 \2", s)
    # Strip XML-illegal control characters to avoid DOCX corruption.
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)
    s = s.replace("\uFFFE", "").replace("\uFFFF", "")
    lines = s.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        raw = lines[i]
        t = raw.strip()
        if not t:
            out.append("")
            i += 1
            continue
        if t in {"#", "##", "###"}:
            if i + 1 < len(lines):
                nxt = lines[i + 1].strip()
                if nxt:
                    out.append(f"{t} {nxt}")
                    i += 2
                    continue
            i += 1
            continue
        out.append(raw)
        i += 1
    s = "\n".join(out)
    s = compact_list_spacing_for_export(s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()
