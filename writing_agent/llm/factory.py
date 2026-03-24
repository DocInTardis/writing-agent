"""Provider factory with incremental Python/Node dual-backend routing."""

from __future__ import annotations

import hashlib
import os
import threading

from writing_agent.llm.provider import LLMProvider, LLMProviderError
from writing_agent.llm.providers import OllamaProvider, node_gateway_from_env, openai_from_env
from writing_agent.llm.settings import get_ollama_settings


_PROVIDER_CACHE_LOCK = threading.Lock()
_PROVIDER_CACHE: dict[tuple, LLMProvider] = {}


def _provider_cache_enabled() -> bool:
    raw = str(os.environ.get("WRITING_AGENT_PROVIDER_CACHE_ENABLED", "1")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _provider_cache_key(*, provider_name: str, backend_name: str, model: str | None, timeout_s: float | None) -> tuple:
    chosen_model = str(model or "").strip()
    chosen_timeout = float(timeout_s) if timeout_s is not None else None
    if provider_name == "openai":
        return (
            provider_name,
            backend_name,
            str(os.environ.get("WRITING_AGENT_OPENAI_BASE_URL", "https://api.openai.com/v1")).strip(),
            str(os.environ.get("WRITING_AGENT_OPENAI_API_KEY", "")).strip(),
            chosen_model or str(os.environ.get("WRITING_AGENT_OPENAI_MODEL", "gpt-4o-mini")).strip(),
            chosen_timeout if chosen_timeout is not None else float(os.environ.get("WRITING_AGENT_OPENAI_TIMEOUT_S", "60")),
        )
    if provider_name == "ollama":
        settings = get_ollama_settings()
        return (
            provider_name,
            backend_name,
            bool(settings.enabled),
            str(settings.base_url or "").strip(),
            chosen_model or str(settings.model or "").strip(),
            chosen_timeout if chosen_timeout is not None else float(settings.timeout_s),
            str(os.environ.get("WRITING_AGENT_NODE_GATEWAY_URL", "")).strip() if backend_name == "node" else "",
            str(os.environ.get("WRITING_AGENT_NODE_GATEWAY_AUTO_FALLBACK", "1")).strip(),
        )
    return (provider_name, backend_name, chosen_model, chosen_timeout)


def _provider_cache_get(key: tuple) -> LLMProvider | None:
    with _PROVIDER_CACHE_LOCK:
        return _PROVIDER_CACHE.get(key)


def _provider_cache_put(key: tuple, provider: LLMProvider) -> LLMProvider:
    with _PROVIDER_CACHE_LOCK:
        _PROVIDER_CACHE[key] = provider
    return provider


def get_provider_name() -> str:
    raw = str(os.environ.get("WRITING_AGENT_LLM_PROVIDER", "ollama") or "ollama").strip().lower()
    if raw in {"openai", "remote", "openai_compatible"}:
        return "openai"
    if raw == "ollama":
        return "ollama"
    return raw


def mask_secret(value: str, *, show_prefix: int = 4, show_suffix: int = 2) -> str:
    secret = str(value or "")
    if not secret:
        return ""
    if len(secret) <= max(1, show_prefix + show_suffix):
        return "*" * len(secret)
    return f"{secret[:show_prefix]}***{secret[-show_suffix:]}"


def get_provider_snapshot(*, model: str | None = None) -> dict[str, str]:
    provider = get_provider_name()
    backend = str(os.environ.get("WRITING_AGENT_LLM_BACKEND", "python") or "python").strip().lower() or "python"
    snapshot: dict[str, str] = {
        "provider": provider,
        "backend": backend,
        "model": str(model or "").strip(),
    }
    if provider == "openai":
        snapshot["base_url"] = str(os.environ.get("WRITING_AGENT_OPENAI_BASE_URL", "https://api.openai.com/v1")).strip()
        snapshot["api_key_masked"] = mask_secret(str(os.environ.get("WRITING_AGENT_OPENAI_API_KEY", "")).strip())
    elif provider == "ollama":
        settings = get_ollama_settings()
        snapshot["base_url"] = str(settings.base_url or "").strip()
    return snapshot


def _build_python_provider(*, model: str | None = None, timeout_s: float | None = None) -> LLMProvider:
    provider = get_provider_name()
    if provider == "openai":
        return openai_from_env(model=model, timeout_s=timeout_s)
    if provider != "ollama":
        raise LLMProviderError(f"unsupported llm provider: {provider}")
    settings = get_ollama_settings()
    if not settings.enabled:
        raise LLMProviderError("llm provider disabled")
    return OllamaProvider.from_settings(settings, model=model, timeout_s=timeout_s)


def _bool_env(name: str, default: bool) -> bool:
    raw = str(os.environ.get(name, "")).strip().lower()
    if not raw:
        return bool(default)
    return raw in {"1", "true", "yes", "on"}


def _rollout_bucket(route_key: str) -> int:
    digest = hashlib.sha1(route_key.encode("utf-8", errors="ignore")).hexdigest()
    return int(digest[:8], 16) % 100


def _should_use_node_backend(route_key: str = "") -> bool:
    backend = str(os.environ.get("WRITING_AGENT_LLM_BACKEND", "python")).strip().lower()
    if backend != "node":
        return False
    raw_percent = str(os.environ.get("WRITING_AGENT_LLM_BACKEND_ROLLOUT_PERCENT", "100")).strip()
    try:
        percent = int(raw_percent)
    except Exception:
        percent = 100
    percent = max(0, min(100, percent))
    if percent <= 0:
        return False
    if percent >= 100:
        return True
    key = str(route_key or os.environ.get("WRITING_AGENT_LLM_ROUTE_KEY", "default")).strip() or "default"
    return _rollout_bucket(key) < percent


def get_default_provider(
    *,
    model: str | None = None,
    timeout_s: float | None = None,
    route_key: str = "",
) -> LLMProvider:
    """
    Resolve default provider using incremental dual-backend routing.

    Backend decision:
    - `WRITING_AGENT_LLM_BACKEND=python` -> python native provider
    - `WRITING_AGENT_LLM_BACKEND=node` -> node gateway provider (with rollout support)
    """

    provider_name = get_provider_name()
    use_node_backend = _should_use_node_backend(route_key=route_key)
    backend_name = "node" if use_node_backend else "python"
    cache_key = _provider_cache_key(
        provider_name=provider_name,
        backend_name=backend_name,
        model=model,
        timeout_s=timeout_s,
    )
    if _provider_cache_enabled():
        cached = _provider_cache_get(cache_key)
        if cached is not None:
            return cached

    python_provider = _build_python_provider(model=model, timeout_s=timeout_s)
    if not use_node_backend:
        return _provider_cache_put(cache_key, python_provider) if _provider_cache_enabled() else python_provider

    try:
        provider = node_gateway_from_env(
            model=model,
            timeout_s=timeout_s,
            fallback_provider=python_provider if _bool_env("WRITING_AGENT_NODE_GATEWAY_AUTO_FALLBACK", True) else None,
        )
        return _provider_cache_put(cache_key, provider) if _provider_cache_enabled() else provider
    except Exception:
        if _bool_env("WRITING_AGENT_NODE_GATEWAY_AUTO_FALLBACK", True):
            return _provider_cache_put(cache_key, python_provider) if _provider_cache_enabled() else python_provider
        raise
