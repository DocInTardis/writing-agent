"""Shared contracts for workflow assembly and business capabilities."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

GraphStatePatch = dict[str, Any]
GraphHandler = Callable[[GraphStatePatch], GraphStatePatch]


@dataclass(frozen=True)
class GenerateWorkflowRequest:
    instruction: str
    current_text: str
    required_h2: list[str]
    required_outline: list[tuple[int, str]] | list[str] | None
    expand_outline: bool
    config: Any
    compose_mode: str
    resume_sections: list[str] | None
    format_only: bool
    plan_confirm: dict[str, Any] | None


@dataclass(frozen=True)
class GenerateWorkflowDeps:
    run_generate_graph: Callable[..., Iterable[dict[str, Any]]]
    light_self_check: Callable[..., list[str]]
    target_total_chars: Callable[[Any], int]
    is_evidence_enabled: Callable[[], bool]


__all__ = [name for name in globals() if not name.startswith("__")]
