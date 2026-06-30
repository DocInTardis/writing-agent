"""User-managed LLM configuration with multi-provider API key support.

This module belongs to `writing_agent.llm` in the writing-agent codebase.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Built-in provider presets for popular LLM services.
# All use OpenAI-compatible API format (base_url + api_key + model).
PROVIDER_PRESETS: dict[str, dict[str, Any]] = {
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
        "default_model": "gpt-4o-mini",
    },
    "anthropic": {
        "name": "Anthropic",
        "base_url": "https://api.anthropic.com/v1",
        "models": ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229", "claude-3-haiku-20240307"],
        "default_model": "claude-3-5-sonnet-20241022",
        "requires_adapter": True,
    },
    "google": {
        "name": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "models": ["gemini-2.0-flash-exp", "gemini-1.5-pro", "gemini-1.5-flash"],
        "default_model": "gemini-1.5-pro",
    },
    "azure_openai": {
        "name": "Azure OpenAI",
        "base_url": "",
        "models": ["gpt-4o", "gpt-4", "gpt-35-turbo"],
        "default_model": "gpt-4o",
        "api_version": "2024-06-01",
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "default_model": "deepseek-chat",
    },
    "moonshot": {
        "name": "Moonshot (Kimi)",
        "base_url": "https://api.moonshot.cn/v1",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        "default_model": "moonshot-v1-8k",
    },
    "qwen": {
        "name": "通义千问 (Qwen)",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-max", "qwen-plus", "qwen-turbo", "qwen-coder-plus"],
        "default_model": "qwen-plus",
    },
    "zhipu": {
        "name": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-4-plus", "glm-4", "glm-4-air", "glm-4-flash"],
        "default_model": "glm-4-air",
    },
    "doubao": {
        "name": "豆包 / 火山引擎",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "models": ["doubao-pro-128k", "doubao-lite-128k"],
        "default_model": "doubao-pro-128k",
    },
    "baichuan": {
        "name": "百川智能",
        "base_url": "https://api.baichuan-ai.com/v1",
        "models": ["Baichuan4", "Baichuan3-Turbo", "Baichuan3-Turbo-128k"],
        "default_model": "Baichuan3-Turbo",
    },
    "siliconflow": {
        "name": "SiliconFlow",
        "base_url": "https://api.siliconflow.cn/v1",
        "models": ["Qwen/Qwen2.5-72B-Instruct", "deepseek-ai/DeepSeek-V3", "THUDM/glm-4-9b-chat"],
        "default_model": "Qwen/Qwen2.5-72B-Instruct",
    },
    "openrouter": {
        "name": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "models": ["openai/gpt-4o", "anthropic/claude-3.5-sonnet", "google/gemini-pro-1.5"],
        "default_model": "openai/gpt-4o",
    },
    "custom": {
        "name": "自定义 (OpenAI-compatible)",
        "base_url": "",
        "models": [],
        "default_model": "",
    },
}


@dataclass
class UserProviderConfig:
    provider_id: str
    api_key: str
    base_url: str = ""
    model: str = ""
    timeout_s: float = 120.0
    enabled: bool = True
    label: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self, *, mask_key: bool = True) -> dict[str, Any]:
        data = asdict(self)
        if mask_key:
            data["api_key"] = _mask_key(self.api_key)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserProviderConfig:
        return cls(
            provider_id=str(data.get("provider_id", "")),
            api_key=str(data.get("api_key", "")),
            base_url=str(data.get("base_url", "")),
            model=str(data.get("model", "")),
            timeout_s=float(data.get("timeout_s", 120.0)),
            enabled=bool(data.get("enabled", True)),
            label=str(data.get("label", "")),
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
        )


@dataclass
class UserLLMConfig:
    active_provider_id: str = ""
    providers: list[UserProviderConfig] = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self, *, mask_keys: bool = True) -> dict[str, Any]:
        return {
            "active_provider_id": self.active_provider_id,
            "providers": [p.to_dict(mask_key=mask_keys) for p in self.providers],
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> UserLLMConfig:
        return cls(
            active_provider_id=str(data.get("active_provider_id", "")),
            providers=[UserProviderConfig.from_dict(p) for p in data.get("providers", []) if isinstance(p, dict)],
            updated_at=float(data.get("updated_at", time.time())),
        )

    def get_active_provider(self) -> UserProviderConfig | None:
        for p in self.providers:
            if p.provider_id == self.active_provider_id and p.enabled:
                return p
        # Fallback to first enabled provider
        for p in self.providers:
            if p.enabled:
                return p
        return None


class UserConfigStore:
    """Thread-safe file-based store for user LLM configurations."""

    _instance: UserConfigStore | None = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls) -> UserConfigStore:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self) -> None:
        self._file_lock = threading.Lock()
        self._config_path = Path(".data/user_llm_configs.json")
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        self._cached_config: UserLLMConfig | None = None
        self._cached_at: float = 0.0

    def _persist(self, config: UserLLMConfig) -> None:
        with self._file_lock:
            self._config_path.write_text(
                json.dumps(config.to_dict(mask_keys=False), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._cached_config = config
            self._cached_at = time.time()

    def load(self) -> UserLLMConfig:
        with self._file_lock:
            if self._cached_config is not None and (time.time() - self._cached_at) < 5.0 and self._config_path.exists():
                return self._cached_config
            if not self._config_path.exists():
                empty = UserLLMConfig()
                self._cached_config = empty
                self._cached_at = time.time()
                return empty
            try:
                data = json.loads(self._config_path.read_text(encoding="utf-8"))
                config = UserLLMConfig.from_dict(data)
                self._cached_config = config
                self._cached_at = time.time()
                return config
            except Exception as exc:
                logger.warning("UserConfigStore.load failed: %s", exc)
                empty = UserLLMConfig()
                self._cached_config = empty
                self._cached_at = time.time()
                return empty

    def save(self, config: UserLLMConfig) -> None:
        config.updated_at = time.time()
        self._persist(config)

    def get_active_provider(self) -> UserProviderConfig | None:
        return self.load().get_active_provider()

    def set_active_provider(self, provider_id: str) -> None:
        config = self.load()
        config.active_provider_id = provider_id
        self.save(config)

    def add_or_update_provider(self, provider_config: UserProviderConfig) -> None:
        config = self.load()
        found = False
        for i, p in enumerate(config.providers):
            if p.provider_id == provider_config.provider_id:
                config.providers[i] = provider_config
                found = True
                break
        if not found:
            config.providers.append(provider_config)
        if not config.active_provider_id:
            config.active_provider_id = provider_config.provider_id
        self.save(config)

    def remove_provider(self, provider_id: str) -> None:
        config = self.load()
        config.providers = [p for p in config.providers if p.provider_id != provider_id]
        if config.active_provider_id == provider_id:
            config.active_provider_id = next((p.provider_id for p in config.providers if p.enabled), "")
        self.save(config)

    def list_providers(self) -> list[dict[str, Any]]:
        return self.load().to_dict(mask_keys=True)["providers"]


def _mask_key(key: str, *, prefix: int = 4, suffix: int = 4) -> str:
    secret = str(key or "")
    if not secret:
        return ""
    if len(secret) <= prefix + suffix + 3:
        return "*" * len(secret)
    return f"{secret[:prefix]}...{secret[-suffix:]}"


def get_provider_presets() -> dict[str, dict[str, Any]]:
    return dict(PROVIDER_PRESETS)


def build_openai_compatible_config(provider: UserProviderConfig) -> dict[str, Any]:
    """Build OpenAI-compatible provider kwargs from user config."""
    preset = PROVIDER_PRESETS.get(provider.provider_id, {})
    base_url = provider.base_url.strip() or preset.get("base_url", "")
    model = provider.model.strip() or preset.get("default_model", "")
    return {
        "base_url": base_url.rstrip("/"),
        "api_key": provider.api_key,
        "model": model,
        "timeout_s": provider.timeout_s,
    }
