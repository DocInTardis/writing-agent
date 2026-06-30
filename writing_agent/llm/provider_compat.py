"""Compatibility helpers for local-test LLM provider fallback."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from writing_agent.llm import OllamaClient, get_default_provider, get_ollama_settings


def provider_or_ollama(
    namespace: Mapping[str, Any] | object | None = None,
    *,
    model: str | None = None,
    timeout_s: float | None = None,
):
    """Return the configured provider, falling back to a module-local Ollama client.

    Older agent tests monkeypatch ``OllamaClient`` and ``get_ollama_settings`` on the
    caller module. The newer provider factory defaults to OpenAI and can fail before
    those monkeypatches are observed, so this shim preserves the old behavior while
    still using the configured provider when it is available.
    """

    try:
        return get_default_provider(model=model, timeout_s=timeout_s)
    except Exception:
        pass

    def _lookup(name: str, default: Any) -> Any:
        if isinstance(namespace, Mapping):
            return namespace.get(name, default)
        if namespace is not None:
            return getattr(namespace, name, default)
        return default

    settings_fn = _lookup("get_ollama_settings", get_ollama_settings)
    client_cls = _lookup("OllamaClient", OllamaClient)
    settings = settings_fn()
    return client_cls(
        base_url=settings.base_url,
        model=(model or settings.model),
        timeout_s=float(timeout_s if timeout_s is not None else settings.timeout_s),
    )


__all__ = ["provider_or_ollama"]
