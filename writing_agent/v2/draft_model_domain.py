"""Draft Model Domain module.

This module belongs to `writing_agent.v2` in the writing-agent codebase.
"""

from __future__ import annotations

import re


def model_size_hint(name: str, sizes: dict[str, float]) -> float:
    if not name:
        return 0.0
    if name in sizes:
        return float(sizes.get(name, 0.0))
    match = re.search(r"(?P<num>\d+(?:\.\d+)?)\s*b\b", name.lower())
    if match:
        try:
            return float(match.group("num"))
        except Exception:
            return 0.0
    return 0.0


def pick_largest(models: list[str], sizes: dict[str, float]) -> str:
    if not models:
        return ""
    return max(models, key=lambda model: (model_size_hint(model, sizes), model))


def pick_smallest(models: list[str], sizes: dict[str, float]) -> str:
    if not models:
        return ""
    return min(models, key=lambda model: (model_size_hint(model, sizes), model))


def pick_draft_models(
    *,
    worker_models: list[str],
    agg_model: str,
    fallback: str,
    env_main: str,
    env_support: str,
    installed: set[str],
    sizes: dict[str, float],
    is_embedding_model: callable,
) -> tuple[str, str]:
    def is_ok(model_name: str) -> bool:
        if not model_name:
            return False
        if is_embedding_model(model_name):
            return False
        return (not installed) or (model_name in installed)

    main = env_main if is_ok(env_main) else ""
    support = env_support if is_ok(env_support) else ""

    candidates = [model_name for model_name in worker_models if is_ok(model_name)]
    if agg_model:
        filtered = [model_name for model_name in candidates if model_name != agg_model]
        candidates = filtered or candidates

    if not main:
        for model_name in candidates:
            if "3b" in model_name.lower():
                main = model_name
                break
        if not main:
            main = pick_largest(candidates, sizes) or (fallback if is_ok(fallback) else (candidates[0] if candidates else fallback))

    if not support:
        for model_name in candidates:
            if model_name != main and ("1.5b" in model_name.lower() or "0.5b" in model_name.lower()):
                support = model_name
                break
        if not support:
            support = pick_smallest([model_name for model_name in candidates if model_name != main], sizes)

    if support == main:
        support = ""
    return main, support
