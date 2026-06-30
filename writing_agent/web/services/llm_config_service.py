"""LLM Config Service module.

This module belongs to `writing_agent.web.services` in the writing-agent codebase.
"""

from __future__ import annotations

import logging
from typing import Any

from writing_agent.llm.provider import LLMProviderError
from writing_agent.llm.providers.openai_compatible_provider import OpenAICompatibleProvider
from writing_agent.llm.user_config import (
    PROVIDER_PRESETS,
    UserConfigStore,
    UserLLMConfig,
    UserProviderConfig,
    build_openai_compatible_config,
    get_provider_presets,
)

logger = logging.getLogger(__name__)


class LLMConfigService:
    def __init__(self) -> None:
        self._store = UserConfigStore()

    def list_presets(self) -> dict[str, dict[str, Any]]:
        return get_provider_presets()

    def get_config(self) -> dict[str, Any]:
        config = self._store.load()
        return config.to_dict(mask_keys=True)

    def set_active_provider(self, provider_id: str) -> dict[str, Any]:
        self._store.set_active_provider(provider_id)
        return self.get_config()

    def add_or_update_provider(self, data: dict[str, Any]) -> dict[str, Any]:
        provider_id = str(data.get("provider_id", "")).strip()
        if not provider_id:
            raise ValueError("provider_id is required")

        preset = PROVIDER_PRESETS.get(provider_id, {})
        api_key = str(data.get("api_key", "")).strip()
        base_url = str(data.get("base_url", "") or preset.get("base_url", "")).strip()
        model = str(data.get("model", "") or preset.get("default_model", "")).strip()
        timeout_s = float(data.get("timeout_s", 120.0))
        label = str(data.get("label", "") or preset.get("name", provider_id)).strip()
        enabled = bool(data.get("enabled", True))

        # Preserve existing key if empty string sent and provider already exists
        if not api_key:
            existing = self._store.load()
            for p in existing.providers:
                if p.provider_id == provider_id:
                    api_key = p.api_key
                    break

        cfg = UserProviderConfig(
            provider_id=provider_id,
            api_key=api_key,
            base_url=base_url,
            model=model,
            timeout_s=timeout_s,
            enabled=enabled,
            label=label,
        )
        self._store.add_or_update_provider(cfg)
        return self.get_config()

    def remove_provider(self, provider_id: str) -> dict[str, Any]:
        self._store.remove_provider(provider_id)
        return self.get_config()

    def test_provider(self, data: dict[str, Any]) -> dict[str, Any]:
        """Test a provider configuration with a lightweight chat call."""
        provider_id = str(data.get("provider_id", "")).strip()
        api_key = str(data.get("api_key", "")).strip()
        base_url = str(data.get("base_url", "")).strip()
        model = str(data.get("model", "")).strip()
        timeout_s = float(data.get("timeout_s", 60.0))

        preset = PROVIDER_PRESETS.get(provider_id, {})
        if not base_url:
            base_url = preset.get("base_url", "")
        if not model:
            model = preset.get("default_model", "")

        if not api_key:
            return {"ok": False, "error": "API key is required"}
        if not base_url:
            return {"ok": False, "error": "Base URL is required"}
        if not model:
            return {"ok": False, "error": "Model is required"}

        try:
            provider = OpenAICompatibleProvider(
                base_url=base_url.rstrip("/"),
                api_key=api_key,
                model=model,
                timeout_s=timeout_s,
            )
            # Lightweight test: just check if the provider is reachable
            if not provider.is_running():
                return {"ok": False, "error": "Provider endpoint is not reachable"}
            # Try a minimal chat to validate the key
            result = provider.chat(
                system=(
                    "<task>provider_healthcheck</task>\n"
                    "<constraints>\n"
                    "- Reply briefly.\n"
                    "- Do not include sensitive configuration values.\n"
                    "</constraints>"
                ),
                user="<user_message>Hi</user_message>",
                temperature=0.2,
            )
            return {
                "ok": True,
                "reachable": True,
                "response_preview": str(result or "")[:200],
            }
        except LLMProviderError as exc:
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            logger.warning("test_provider failed: %s", exc, exc_info=True)
            return {"ok": False, "error": f"Connection failed: {exc}"}
