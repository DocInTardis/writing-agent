"""Length Target Domain module.

This module belongs to `writing_agent.web.domains` in the writing-agent codebase.
"""

from __future__ import annotations

import re


def estimate_chars_per_page(formatting: dict, prefs: dict) -> int:
    font_size = float(formatting.get("font_size_pt") or 12)
    line_spacing = float(formatting.get("line_spacing") or 1.5)
    margins = float(prefs.get("page_margins_cm") or 2.5)
    size = str(prefs.get("page_size") or "A4").upper()
    if size == "A5":
        width, height = 14.8, 21.0
    elif size == "LETTER":
        width, height = 21.59, 27.94
    else:
        width, height = 21.0, 29.7
    page_width = width - 2 * margins
    page_height = height - 2 * margins
    line_height_pt = line_spacing if line_spacing >= 4 else font_size * line_spacing
    line_height_cm = line_height_pt * 0.0352778
    lines_per_page = max(1, int(page_height / max(0.35, line_height_cm)))
    base_chars_per_line = 38
    chars_per_line = max(10, int(base_chars_per_line * (12 / max(8, font_size))))
    return max(120, int(lines_per_page * chars_per_line))


def resolve_target_chars(formatting: dict, prefs: dict) -> int:
    if not isinstance(prefs, dict):
        return 0

    def _safe_int(val) -> int:
        try:
            return int(float(val))
        except Exception:
            return 0

    target_chars = _safe_int(prefs.get("target_char_count") or 0)
    if target_chars > 0:
        return target_chars
    mode = str(prefs.get("target_length_mode") or "").strip().lower()
    if mode == "chars":
        return _safe_int(prefs.get("target_word_count") or prefs.get("target_length_value") or 0)
    if mode == "pages":
        pages = _safe_int(prefs.get("target_page_count") or prefs.get("target_length_value") or 0)
        if pages > 0:
            return int(pages * estimate_chars_per_page(formatting or {}, prefs))
    return 0


def extract_target_chars_from_instruction(instruction: str) -> int:
    src = (instruction or "").strip()
    if not src:
        return 0
    m = re.search(r"(\d{1,2}(?:\.\d)?)\s*万\s*字", src)
    if m:
        try:
            val = int(float(m.group(1)) * 10000)
        except Exception:
            val = 0
        if 100 <= val <= 200000:
            return val
    m = re.search(r"(\d{1,3})\s*千\s*字", src)
    if m:
        try:
            val = int(float(m.group(1)) * 1000)
        except Exception:
            val = 0
        if 100 <= val <= 200000:
            return val
    patterns = [
        (r"(?:字数|字符数)\s*[:：]?\s*(\d{2,6})", 1),
        (r"(\d{2,6})\s*(?:字|字符)", 1),
        (r"(\d{1,3})\s*(?:k|K)\s*(?:字|字符)?", 1000),
    ]
    for pat, multi in patterns:
        m = re.search(pat, src)
        if not m:
            continue
        try:
            val = int(float(m.group(1)) * multi)
        except Exception:
            val = 0
        if 100 <= val <= 200000:
            return val
    return 0
