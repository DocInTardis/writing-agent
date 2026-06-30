"""Provider factory with incremental Python/Node dual-backend routing."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
import threading
import time

logger = logging.getLogger(__name__)

from writing_agent.llm.openai_config import resolve_openai_candidates, resolve_openai_primary
from writing_agent.llm.provider import LLMProvider, LLMProviderError
from writing_agent.llm.providers.failover_provider import OpenAIKeyPoolProvider, OpenAIQuotaFallbackProvider
from writing_agent.llm.providers.node_ai_gateway_provider import from_env as node_gateway_from_env
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


def _bool_env(name: str, default: bool) -> bool:
    raw = str(os.environ.get(name, "")).strip().lower()
    if not raw:
        return bool(default)
    return raw in {"1", "true", "yes", "on"}


def _openai_quota_fallback_enabled() -> bool:
    return _bool_env("WRITING_AGENT_OPENAI_QUOTA_FALLBACK", True)


def _provider_cache_key(*, provider_name: str, backend_name: str, model: str | None, timeout_s: float | None) -> tuple:
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
            backend_name,
            candidates,
            chosen_model or (candidates[0][2] if candidates else str(os.environ.get("WRITING_AGENT_OPENAI_MODEL", "gpt-4o-mini")).strip()),
            chosen_timeout if chosen_timeout is not None else float(os.environ.get("WRITING_AGENT_OPENAI_TIMEOUT_S", "60")),
            _openai_quota_fallback_enabled(),
        )
        if _openai_quota_fallback_enabled():
            settings = get_ollama_settings()
            cache += (
                bool(settings.enabled),
                str(settings.base_url or "").strip(),
                str(settings.model or "").strip(),
                float(settings.timeout_s),
            )
        return cache
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
    backend = str(os.environ.get("WRITING_AGENT_LLM_BACKEND", "python") or "python").strip().lower() or "python"
    snapshot: dict[str, str] = {
        "provider": provider,
        "backend": backend,
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
        if _openai_quota_fallback_enabled():
            settings = get_ollama_settings()
            if settings.enabled:
                snapshot["fallback_provider"] = "ollama"
                snapshot["fallback_model"] = str(settings.model or "").strip()
    elif provider == "ollama":
        settings = get_ollama_settings()
        snapshot["base_url"] = str(settings.base_url or "").strip()
    return snapshot


def _build_user_configured_provider(*, model: str | None = None, timeout_s: float | None = None) -> LLMProvider | None:
    """Build provider from user-managed configuration if available."""
    try:
        from writing_agent.llm.user_config import UserLLMConfig
        config_path = Path(".data/user_llm_configs.json")
        if not config_path.exists():
            return None
        data = json.loads(config_path.read_text(encoding="utf-8"))
        config = UserLLMConfig.from_dict(data)
        active = config.get_active_provider()
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
    if not _openai_quota_fallback_enabled():
        return primary_provider
    settings = get_ollama_settings()
    if not settings.enabled:
        return primary_provider
    fallback_provider = OllamaProvider.from_settings(settings)
    return OpenAIQuotaFallbackProvider(
        primary_provider=primary_provider,
        fallback_provider=fallback_provider,
    )


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

    Priority:
    1. User-configured provider (if set and valid)
    2. Environment-based provider (legacy)
    3. Node gateway (if enabled)

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

    # 1. Try user-configured provider first (not cached; config may change anytime)
    user_provider = _build_user_configured_provider(model=model, timeout_s=timeout_s)
    if user_provider is not None:
        if not use_node_backend:
            return user_provider
        try:
            provider = node_gateway_from_env(
                model=model,
                timeout_s=timeout_s,
                fallback_provider=user_provider if _bool_env("WRITING_AGENT_NODE_GATEWAY_AUTO_FALLBACK", True) else None,
            )
            return provider
        except Exception as exc:
            if _bool_env("WRITING_AGENT_NODE_GATEWAY_AUTO_FALLBACK", True):
                logger.warning(
                    "Node gateway provider init failed, falling back to user-configured provider: %s",
                    exc,
                    exc_info=True,
                )
                return user_provider
            raise

    # 2. Fallback to environment-based provider
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
    except Exception as exc:
        if _bool_env("WRITING_AGENT_NODE_GATEWAY_AUTO_FALLBACK", True):
            logger.warning(
                "Node gateway provider init failed, falling back to Python provider: %s",
                exc,
                exc_info=True,
            )
            return _provider_cache_put(cache_key, python_provider) if _provider_cache_enabled() else python_provider
        raise
