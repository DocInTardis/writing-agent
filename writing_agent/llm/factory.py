"""Provider factory with incremental Python/Node dual-backend routing."""

from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

from writing_agent.llm.openai_config import resolve_openai_candidates, resolve_openai_primary
from writing_agent.llm.provider import LLMProvider, LLMProviderError
from writing_agent.llm.providers.failover_provider import OpenAIKeyPoolProvider
from writing_agent.llm.providers.ollama_provider import OllamaProvider
from writing_agent.llm.providers.openai_compatible_provider import from_env as openai_from_env
from writing_agent.llm.providers.openai_compatible_provider import providers_from_env as openai_providers_from_env
from writing_agent.llm.providers.openai_compatible_provider import OpenAICompatibleProvider
from writing_agent.llm.settings import get_ollama_settings
from writing_agent.llm.user_config import UserConfigStore, build_openai_compatible_config

# Default TTL for cached provider instances (seconds). When a key rotation
# or config change occurs, the cache expires naturally within this window.
_PROVIDER_CACHE_TTL_S = 300

_PROVIDER_CACHE_LOCK = threading.Lock()
# Values are (provider, created_at) tuples to support TTL expiry.
_PROVIDER_CACHE: dict[tuple, tuple[LLMProvider, float]] = {}


def _provider_cache_enabled() -> bool:
    raw = str(os.environ.get("WRITING_AGENT_PROVIDER_CACHE_ENABLED", "1")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _provider_cache_key(*, provider_name: str, model: str | None, timeout_s: float | None) -> tuple:
    chosen_model = str(model or "").strip()
    chosen_timeout = float(timeout_s) if timeout_s is not None else None
    if provider_name == "openai":
        candidates = tuple(
            (
                cfg.base_url,
                cfg.api_key,
                cfg.model,
                float(cfg.timeout_s),
                cfg.wire_api,
                cfg.source,
            )
            for cfg in resolve_openai_candidates(model=chosen_model or None, timeout_s=chosen_timeout)
        )
        cache = (
            provider_name,
            candidates,
            chosen_model or (candidates[0][2] if candidates else str(os.environ.get("WRITING_AGENT_OPENAI_MODEL", "gpt-4o-mini")).strip()),
            chosen_timeout if chosen_timeout is not None else float(os.environ.get("WRITING_AGENT_OPENAI_TIMEOUT_S", "60")),
        )
        return cache
    if provider_name == "ollama":
        settings = get_ollama_settings()
        return (
            provider_name,
            bool(settings.enabled),
            str(settings.base_url or "").strip(),
            chosen_model or str(settings.model or "").strip(),
            chosen_timeout if chosen_timeout is not None else float(settings.timeout_s),
        )
    return (provider_name, chosen_model, chosen_timeout)


def _provider_cache_ttl() -> float:
    try:
        return max(0.0, float(os.environ.get("WRITING_AGENT_PROVIDER_CACHE_TTL_S", "") or _PROVIDER_CACHE_TTL_S))
    except (ValueError, TypeError):
        return float(_PROVIDER_CACHE_TTL_S)


def _provider_cache_get(key: tuple) -> LLMProvider | None:
    with _PROVIDER_CACHE_LOCK:
        entry = _PROVIDER_CACHE.get(key)
        if entry is None:
            return None
        provider, created_at = entry
        ttl = _provider_cache_ttl()
        if ttl > 0 and (time.time() - created_at) > ttl:
            del _PROVIDER_CACHE[key]
            return None
        return provider


def _provider_cache_put(key: tuple, provider: LLMProvider) -> LLMProvider:
    with _PROVIDER_CACHE_LOCK:
        _PROVIDER_CACHE[key] = (provider, time.time())
    return provider


def get_provider_name() -> str:
    raw = str(os.environ.get("WRITING_AGENT_LLM_PROVIDER", "openai") or "openai").strip().lower()
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
    snapshot: dict[str, str] = {
        "provider": provider,
        "backend": "python",
        "model": str(model or "").strip(),
    }
    if provider == "openai":
        candidates = resolve_openai_candidates(model=model)
        primary = candidates[0] if candidates else resolve_openai_primary(model=model)
        snapshot["base_url"] = str(primary.base_url if primary is not None else os.environ.get("WRITING_AGENT_OPENAI_BASE_URL", "https://api.openai.com/v1")).strip()
        snapshot["api_key_masked"] = mask_secret(primary.api_key if primary is not None else str(os.environ.get("WRITING_AGENT_OPENAI_API_KEY", "")).strip())
        snapshot["api_key_pool_size"] = str(len(candidates))
        sources = [str(item.source or "").strip() for item in candidates if str(item.source or "").strip()]
        if sources:
            snapshot["config_sources"] = "; ".join(sources[:4])
        if primary is not None:
            snapshot["wire_api"] = str(primary.wire_api or "").strip() or "chat_completions"
    elif provider == "ollama":
        settings = get_ollama_settings()
        snapshot["base_url"] = str(settings.base_url or "").strip()
    return snapshot


def _build_user_configured_provider(*, model: str | None = None, timeout_s: float | None = None) -> LLMProvider | None:
    """Build provider from user-managed configuration if available."""
    try:
        active = UserConfigStore().get_active_provider()
        if active is None:
            return None
        if not active.enabled or not active.api_key:
            return None
        cfg = build_openai_compatible_config(active)
        chosen_model = str(model or "").strip() or cfg["model"]
        chosen_timeout = float(timeout_s if timeout_s is not None else cfg["timeout_s"])
        return OpenAICompatibleProvider(
            base_url=cfg["base_url"],
            api_key=cfg["api_key"],
            model=chosen_model,
            timeout_s=chosen_timeout,
        )
    except Exception as exc:
        logger.warning("_build_user_configured_provider failed: %s", exc)
        return None


def _build_openai_provider(*, model: str | None = None, timeout_s: float | None = None) -> LLMProvider:
    openai_candidates = openai_providers_from_env(model=model, timeout_s=timeout_s)
    if not openai_candidates:
        primary_provider = openai_from_env(model=model, timeout_s=timeout_s)
    elif len(openai_candidates) == 1:
        primary_provider = openai_candidates[0]
    else:
        primary_provider = OpenAIKeyPoolProvider(
            providers=tuple(openai_candidates),
            provider_labels=tuple(str(provider.base_url or "").strip() for provider in openai_candidates),
        )
    return primary_provider


def _build_python_provider(*, model: str | None = None, timeout_s: float | None = None) -> LLMProvider:
    provider = get_provider_name()
    if provider == "openai":
        return _build_openai_provider(model=model, timeout_s=timeout_s)
    if provider != "ollama":
        raise LLMProviderError(f"unsupported llm provider: {provider}")
    settings = get_ollama_settings()
    if not settings.enabled:
        raise LLMProviderError("llm provider disabled")
    return OllamaProvider.from_settings(settings, model=model, timeout_s=timeout_s)


def get_default_provider(
    *,
    model: str | None = None,
    timeout_s: float | None = None,
    route_key: str = "",
) -> LLMProvider:
    """Resolve the user-selected or environment-configured provider."""

    _ = route_key
    provider_name = get_provider_name()
    user_provider = _build_user_configured_provider(model=model, timeout_s=timeout_s)
    if user_provider is not None:
        return user_provider

    cache_key = _provider_cache_key(
        provider_name=provider_name,
        model=model,
        timeout_s=timeout_s,
    )
    if _provider_cache_enabled():
        cached = _provider_cache_get(cache_key)
        if cached is not None:
            return cached
    python_provider = _build_python_provider(model=model, timeout_s=timeout_s)
    return _provider_cache_put(cache_key, python_provider) if _provider_cache_enabled() else python_provider
