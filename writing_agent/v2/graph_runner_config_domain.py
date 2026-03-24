"""Graph runner configuration helpers and section sizing heuristics."""

from __future__ import annotations

import json
import os

from writing_agent.v2 import graph_runner_post_domain as post_domain


def _target_total_chars(config) -> int:
    if getattr(config, "max_total_chars", 0) and config.max_total_chars > 0:
        return max(int(getattr(config, "min_total_chars", 0) or 0), int(config.max_total_chars))
    if getattr(config, "min_total_chars", 0) and config.min_total_chars > 0:
        return int(config.min_total_chars)
    return 1800


def _load_section_weights() -> dict[str, float]:
    raw = str(os.environ.get("WRITING_AGENT_SECTION_WEIGHTS", "")).strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    out: dict[str, float] = {}
    for key, value in payload.items():
        title = str(key or "").strip()
        if not title:
            continue
        try:
            out[title] = max(0.2, float(value))
        except Exception:
            continue
    return out


def _guess_section_weight(section: str) -> float:
    title = str(section or "").strip()
    lowered = title.lower()
    if not title:
        return 1.0
    if post_domain._is_reference_section(title):
        return 0.4
    if lowered in {"???", "???", "keywords"}:
        return 0.35
    if any(token in title for token in ["??", "??", "??", "??", "??"]) or any(token in lowered for token in ["abstract", "introduction", "background", "overview"]):
        return 0.8
    if any(token in title for token in ["??", "??", "??", "??", "??", "??", "??", "??"]) or any(token in lowered for token in ["method", "design", "implementation", "architecture", "experiment", "analysis", "results", "system"]):
        return 1.2
    if any(token in title for token in ["??", "??", "??"]) or any(token in lowered for token in ["conclusion", "summary", "future"]):
        return 0.8
    return 1.0


def _max_chars_for_section(section: str) -> int:
    _ = section
    return 0


def _compute_section_targets(*, sections: list[str], base_min_paras: int, total_chars: int):
    from writing_agent.v2.graph_runner_runtime import _compute_section_targets as _impl

    return _impl(sections=sections, base_min_paras=base_min_paras, total_chars=total_chars)


__all__ = [name for name in globals() if not name.startswith("__")]
