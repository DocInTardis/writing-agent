"""Section continuation segmentation config and split helpers."""

from __future__ import annotations

import os

def _continue_segment_enabled() -> bool:
    raw = str(os.environ.get("WRITING_AGENT_SECTION_CONTINUE_SEGMENT_ENABLED", "1")).strip().lower()
    return raw in {"1", "true", "yes", "on"}

def _continue_segment_threshold_chars() -> int:
    raw = str(os.environ.get("WRITING_AGENT_SECTION_CONTINUE_SEGMENT_THRESHOLD_CHARS", "420")).strip()
    try:
        value = int(raw)
    except Exception:
        value = 420
    return max(160, value)

def _continue_segment_target_chars() -> int:
    raw = str(os.environ.get("WRITING_AGENT_SECTION_CONTINUE_SEGMENT_TARGET_CHARS", "280")).strip()
    try:
        value = int(raw)
    except Exception:
        value = 280
    return max(140, value)

def _continue_segment_max_segments() -> int:
    raw = str(os.environ.get("WRITING_AGENT_SECTION_CONTINUE_SEGMENT_MAX", "3")).strip()
    try:
        value = int(raw)
    except Exception:
        value = 3
    return max(2, min(5, value))

def _split_integer_budget(total: int, parts: int) -> list[int]:
    count = max(1, int(parts or 1))
    value = max(0, int(total or 0))
    base = value // count
    rem = value % count
    return [base + (1 if idx < rem else 0) for idx in range(count)]

def _split_list_evenly(items: list[str], parts: int) -> list[list[str]]:
    values = [str(x).strip() for x in (items or []) if str(x).strip()]
    count = max(1, int(parts or 1))
    if not values:
        return [[] for _ in range(count)]
    base = len(values) // count
    rem = len(values) % count
    out: list[list[str]] = []
    cursor = 0
    for idx in range(count):
        size = base + (1 if idx < rem else 0)
        if size <= 0:
            out.append([])
            continue
        out.append(values[cursor:cursor + size])
        cursor += size
    return out

__all__ = [name for name in globals() if not name.startswith("__")]
