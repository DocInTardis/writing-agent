"""Compatibility entry point for the configured model provider."""

from __future__ import annotations

from writing_agent.llm import get_default_provider


def provider_or_ollama(
    namespace: object | None = None,
    *,
    model: str | None = None,
    timeout_s: float | None = None,
):
    """Return only the configured provider; provider failures stay explicit."""

    _ = namespace
    return get_default_provider(model=model, timeout_s=timeout_s)


__all__ = ["provider_or_ollama"]
