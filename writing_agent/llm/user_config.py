"""User-managed LLM configuration with multi-provider API key support.

This module belongs to `writing_agent.llm` in the writing-agent codebase.
"""

from __future__ import annotations

import json
import logging
import os
import base64
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _protect_secret(secret: str) -> str:
    """Protect a secret with the current Windows user's DPAPI credentials."""
    value = str(secret or "")
    if not value or os.name != "nt" or value.startswith("dpapi:"):
        return value
    try:
        import ctypes
        from ctypes import wintypes

        class _Blob(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

        raw = value.encode("utf-8")
        buffer = ctypes.create_string_buffer(raw)
        source = _Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
        protected = _Blob()
        if not ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(source), ctypes.c_wchar_p("Writing Agent API key"), None, None, None, 1, ctypes.byref(protected)
        ):
            return value
        try:
            payload = ctypes.string_at(protected.pbData, protected.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(protected.pbData)
        return "dpapi:" + base64.b64encode(payload).decode("ascii")
    except Exception as exc:
        logger.warning("DPAPI protection unavailable; key was not rewritten: %s", exc)
        return value


def _unprotect_secret(secret: str) -> str:
    value = str(secret or "")
    if not value.startswith("dpapi:"):
        return value
    if os.name != "nt":
        return ""
    try:
        import ctypes
        from ctypes import wintypes

        class _Blob(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

        raw = base64.b64decode(value[6:].encode("ascii"), validate=True)
        buffer = ctypes.create_string_buffer(raw)
        source = _Blob(len(raw), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
        plain = _Blob()
        if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(source), None, None, None, None, 1, ctypes.byref(plain)
        ):
            return ""
        try:
            return ctypes.string_at(plain.pbData, plain.cbData).decode("utf-8")
        finally:
            ctypes.windll.kernel32.LocalFree(plain.pbData)
    except Exception as exc:
        logger.warning("DPAPI key could not be read: %s", exc)
        return ""

# Keep only stable connection presets. Other compatible services use `custom`.
PROVIDER_PRESETS: dict[str, dict[str, Any]] = {
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models": [],
        "default_model": "",
    },
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "models": ["deepseek-v4-flash", "deepseek-v4-pro"],
        "default_model": "deepseek-v4-flash",
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
            api_key=_unprotect_secret(str(data.get("api_key", ""))),
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
        data_root = Path(str(os.environ.get("WRITING_AGENT_DATA_DIR", "")).strip() or ".data")
        self._config_path = data_root / "user_llm_configs.json"
        self._cached_config: UserLLMConfig | None = None
        self._cached_at: float = 0.0

    def _persist(self, config: UserLLMConfig) -> None:
        with self._file_lock:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            payload = config.to_dict(mask_keys=False)
            for provider in payload.get("providers", []):
                if isinstance(provider, dict):
                    provider["api_key"] = _protect_secret(str(provider.get("api_key", "")))
            self._config_path.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
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
