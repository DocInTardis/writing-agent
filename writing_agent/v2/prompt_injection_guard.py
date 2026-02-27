"""Prompt Injection Guard module.

This module belongs to `writing_agent.v2` in the writing-agent codebase.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InjectionScanResult:
    blocked: bool
    reason: str


BLOCK_PATTERNS = (
    "ignore previous instructions",
    "system prompt",
    "developer message",
    "reveal hidden prompt",
    "bypass safety",
)


def scan_prompt_injection(text: str) -> InjectionScanResult:
    raw = str(text or "").lower()
    for pat in BLOCK_PATTERNS:
        if pat in raw:
            return InjectionScanResult(blocked=True, reason=f"matched:{pat}")
    return InjectionScanResult(blocked=False, reason="ok")


def sanitize_external_quote(text: str) -> str:
    value = str(text or "").strip()
    # remove suspicious instruction-like directives from citations/snippets
    for token in ("ignore previous", "you must", "system:", "developer:"):
        value = value.replace(token, "")
        value = value.replace(token.title(), "")
    return value.strip()
