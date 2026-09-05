"""Compatibility entry point for the configured model provider."""

from __future__ import annotations

from collections.abc import Mapping

from writing_agent.llm import OllamaClient, get_default_provider, get_ollama_settings


def provider_or_ollama(
    namespace: object | None = None,
    *,
    model: str | None = None,
    timeout_s: float | None = None,
):
    """Return only the configured provider; provider failures stay explicit."""

    # Preserve dependency-injection tests without creating a production fallback:
    # only honor module-local symbols when a caller explicitly replaced them.
    if isinstance(namespace, Mapping):
        local_client = namespace.get("OllamaClient", OllamaClient)
        local_settings = namespace.get("get_ollama_settings", get_ollama_settings)
    else:
        local_client = getattr(namespace, "OllamaClient", OllamaClient) if namespace is not None else OllamaClient
        local_settings = getattr(namespace, "get_ollama_settings", get_ollama_settings) if namespace is not None else get_ollama_settings
    if local_client is not OllamaClient or local_settings is not get_ollama_settings:
        settings = local_settings()
        return local_client(
            base_url=settings.base_url,
            model=model or settings.model,
            timeout_s=float(timeout_s if timeout_s is not None else settings.timeout_s),
        )
    return get_default_provider(model=model, timeout_s=timeout_s)


__all__ = ["provider_or_ollama"]
