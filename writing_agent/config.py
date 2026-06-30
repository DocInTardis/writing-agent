"""Unified application configuration.

This module is the single source of truth for environment-variable-backed
configuration.  All new config should be declared here.  Existing callers that
read ``os.environ`` directly are still supported but should migrate over time.

Usage::

    from writing_agent.config import cfg
    timeout = cfg.section_timeout_s

Call ``cfg.validate()`` once at startup to catch missing required values early.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


def _bool_env(name: str, default: bool) -> bool:
    raw = str(os.environ.get(name, "") or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int) -> int:
    try:
        return int(str(os.environ.get(name, "") or "").strip())
    except (ValueError, TypeError):
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(str(os.environ.get(name, "") or "").strip())
    except (ValueError, TypeError):
        return default


def _str_env(name: str, default: str) -> str:
    return str(os.environ.get(name, "") or "").strip() or default


@dataclass
class AppConfig:
    # ---- LLM provider ----
    llm_provider: str = field(default_factory=lambda: _str_env("WRITING_AGENT_LLM_PROVIDER", "openai"))
    llm_backend: str = field(default_factory=lambda: _str_env("WRITING_AGENT_LLM_BACKEND", "python"))
    llm_backend_rollout_percent: int = field(default_factory=lambda: _int_env("WRITING_AGENT_LLM_BACKEND_ROLLOUT_PERCENT", 100))

    openai_base_url: str = field(default_factory=lambda: _str_env("WRITING_AGENT_OPENAI_BASE_URL", "https://api.openai.com/v1"))
    openai_api_key: str = field(default_factory=lambda: _str_env("WRITING_AGENT_OPENAI_API_KEY", ""))
    openai_model: str = field(default_factory=lambda: _str_env("WRITING_AGENT_OPENAI_MODEL", "gpt-4o-mini"))
    openai_timeout_s: float = field(default_factory=lambda: _float_env("WRITING_AGENT_OPENAI_TIMEOUT_S", 60.0))
    openai_quota_fallback: bool = field(default_factory=lambda: _bool_env("WRITING_AGENT_OPENAI_QUOTA_FALLBACK", True))

    # ---- Concurrency ----
    workers: int = field(default_factory=lambda: _int_env("WRITING_AGENT_WORKERS", 12))
    section_timeout_s: float = field(default_factory=lambda: _float_env("WRITING_AGENT_SECTION_TIMEOUT_S", 60.0))
    plan_timeout_s: float = field(default_factory=lambda: _float_env("WRITING_AGENT_PLAN_TIMEOUT_S", 20.0))
    stream_event_timeout_s: float = field(default_factory=lambda: _float_env("WRITING_AGENT_STREAM_EVENT_TIMEOUT_S", 90.0))
    stream_max_s: float = field(default_factory=lambda: _float_env("WRITING_AGENT_STREAM_MAX_S", 180.0))

    # ---- Content generation ----
    hard_max: bool = field(default_factory=lambda: _bool_env("WRITING_AGENT_HARD_MAX", False))
    target_margin: float = field(default_factory=lambda: _float_env("WRITING_AGENT_TARGET_MARGIN", 0.15))
    evidence_enabled: bool = field(default_factory=lambda: _bool_env("WRITING_AGENT_EVIDENCE_ENABLED", True))

    # ---- Storage ----
    store_max_sessions: int = field(default_factory=lambda: _int_env("WRITING_AGENT_STORE_MAX_SESSIONS", 500))
    idempotency_ttl_s: int = field(default_factory=lambda: _int_env("WRITING_AGENT_IDEMPOTENCY_TTL_S", 21600))

    # ---- Provider cache ----
    provider_cache_enabled: bool = field(default_factory=lambda: _bool_env("WRITING_AGENT_PROVIDER_CACHE_ENABLED", True))
    provider_cache_ttl_s: float = field(default_factory=lambda: _float_env("WRITING_AGENT_PROVIDER_CACHE_TTL_S", 300.0))

    def validate(self) -> list[str]:
        """Return a list of validation error strings. Empty means config is valid."""
        errors: list[str] = []
        provider = self.llm_provider.lower()
        if provider in {"openai", "remote", "openai_compatible"}:
            if not self.openai_api_key:
                errors.append(
                    "WRITING_AGENT_OPENAI_API_KEY is not set. "
                    "Set it or switch to WRITING_AGENT_LLM_PROVIDER=ollama."
                )
        if self.workers < 1:
            errors.append("WRITING_AGENT_WORKERS must be >= 1")
        if self.llm_backend_rollout_percent < 0 or self.llm_backend_rollout_percent > 100:
            errors.append("WRITING_AGENT_LLM_BACKEND_ROLLOUT_PERCENT must be 0-100")
        return errors

    def log_summary(self) -> None:
        """Log a concise config summary at INFO level (no secrets)."""
        key = self.openai_api_key
        masked = f"{key[:4]}***{key[-2:]}" if len(key) > 6 else ("***" if key else "<not set>")
        logger.info(
            "Config: provider=%s backend=%s model=%s workers=%d store_max=%d cache_ttl=%.0fs",
            self.llm_provider,
            self.llm_backend,
            self.openai_model,
            self.workers,
            self.store_max_sessions,
            self.provider_cache_ttl_s,
        )
        logger.info("Config: openai_base_url=%s api_key=%s", self.openai_base_url, masked)


# Module-level singleton — read lazily so tests can set env vars before import.
def _make_cfg() -> AppConfig:
    return AppConfig()


cfg: AppConfig = _make_cfg()


def reload() -> AppConfig:
    """Re-read all env vars and replace the module-level singleton. Useful in tests."""
    global cfg
    cfg = _make_cfg()
    return cfg
