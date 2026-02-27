"""Provider factory with incremental Python/Node dual-backend routing."""

from __future__ import annotations

import hashlib
import os

from writing_agent.llm.provider import LLMProvider, LLMProviderError
from writing_agent.llm.providers import OllamaProvider, node_gateway_from_env, openai_from_env
from writing_agent.llm.settings import get_ollama_settings


def _build_python_provider(*, model: str | None = None, timeout_s: float | None = None) -> LLMProvider:
    provider = str(os.environ.get("WRITING_AGENT_LLM_PROVIDER", "ollama") or "ollama").strip().lower()
    if provider in {"openai", "remote"}:
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

    python_provider = _build_python_provider(model=model, timeout_s=timeout_s)
    if not _should_use_node_backend(route_key=route_key):
        return python_provider

    try:
        return node_gateway_from_env(
            model=model,
            timeout_s=timeout_s,
            fallback_provider=python_provider if _bool_env("WRITING_AGENT_NODE_GATEWAY_AUTO_FALLBACK", True) else None,
        )
    except Exception:
        if _bool_env("WRITING_AGENT_NODE_GATEWAY_AUTO_FALLBACK", True):
            return python_provider
        raise
