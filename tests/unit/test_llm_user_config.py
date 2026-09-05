"""Tests for user-managed LLM configuration."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from writing_agent.llm.user_config import (
    PROVIDER_PRESETS,
    UserConfigStore,
    UserLLMConfig,
    UserProviderConfig,
    build_openai_compatible_config,
    get_provider_presets,
    _mask_key,
)


class TestProviderPresets:
    def test_all_presets_have_required_fields(self):
        presets = get_provider_presets()
        assert len(presets) == 3
        for key, preset in presets.items():
            assert "name" in preset
            assert "base_url" in preset
            assert "models" in preset
            assert "default_model" in preset

    def test_popular_providers_present(self):
        presets = get_provider_presets()
        for key in ["openai", "deepseek", "custom"]:
            assert key in presets


class TestUserProviderConfig:
    def test_to_dict_masks_key(self):
        cfg = UserProviderConfig(provider_id="openai", api_key="sk-1234567890abcdef")
        d = cfg.to_dict(mask_key=True)
        assert d["api_key"] == "sk-1...cdef"
        assert "provider_id" in d

    def test_to_dict_shows_key(self):
        cfg = UserProviderConfig(provider_id="openai", api_key="sk-secret")
        d = cfg.to_dict(mask_key=False)
        assert d["api_key"] == "sk-secret"

    def test_from_dict_roundtrip(self):
        original = UserProviderConfig(
            provider_id="deepseek",
            api_key="sk-test",
            base_url="https://api.deepseek.com/v1",
            model="deepseek-chat",
            timeout_s=60.0,
            enabled=True,
            label="My DeepSeek",
        )
        data = original.to_dict(mask_key=False)
        restored = UserProviderConfig.from_dict(data)
        assert restored.provider_id == original.provider_id
        assert restored.api_key == original.api_key
        assert restored.model == original.model


class TestUserLLMConfig:
    def test_get_active_provider(self):
        p1 = UserProviderConfig(provider_id="openai", api_key="sk-1", enabled=True)
        p2 = UserProviderConfig(provider_id="deepseek", api_key="sk-2", enabled=False)
        config = UserLLMConfig(active_provider_id="openai", providers=[p1, p2])
        active = config.get_active_provider()
        assert active is not None
        assert active.provider_id == "openai"

    def test_get_active_fallback_to_first_enabled(self):
        p1 = UserProviderConfig(provider_id="openai", api_key="sk-1", enabled=False)
        p2 = UserProviderConfig(provider_id="deepseek", api_key="sk-2", enabled=True)
        config = UserLLMConfig(active_provider_id="openai", providers=[p1, p2])
        active = config.get_active_provider()
        assert active is not None
        assert active.provider_id == "deepseek"

    def test_get_active_none_when_all_disabled(self):
        p1 = UserProviderConfig(provider_id="openai", api_key="sk-1", enabled=False)
        config = UserLLMConfig(active_provider_id="openai", providers=[p1])
        assert config.get_active_provider() is None


class TestBuildOpenAICompatibleConfig:
    def test_uses_preset_defaults(self):
        provider = UserProviderConfig(provider_id="deepseek", api_key="sk-test")
        cfg = build_openai_compatible_config(provider)
        assert cfg["base_url"] == "https://api.deepseek.com"
        assert cfg["model"] == "deepseek-v4-flash"
        assert cfg["api_key"] == "sk-test"

    def test_uses_user_overrides(self):
        provider = UserProviderConfig(
            provider_id="custom",
            api_key="sk-test",
            base_url="https://my-proxy.com/v1",
            model="gpt-4o",
            timeout_s=90.0,
        )
        cfg = build_openai_compatible_config(provider)
        assert cfg["base_url"] == "https://my-proxy.com/v1"
        assert cfg["model"] == "gpt-4o"
        assert cfg["timeout_s"] == 90.0


class TestUserConfigStore:
    def test_singleton(self):
        s1 = UserConfigStore()
        s2 = UserConfigStore()
        assert s1 is s2

    def test_load_empty_when_no_file(self, tmp_path):
        store = UserConfigStore()
        store._config_path = tmp_path / "test_config.json"
        store._cached_config = None
        config = store.load()
        assert config.active_provider_id == ""
        assert config.providers == []

    def test_add_and_retrieve_provider(self, tmp_path):
        store = UserConfigStore()
        store._config_path = tmp_path / "test_config.json"
        store._cached_config = None

        cfg = UserProviderConfig(provider_id="openai", api_key="sk-test", model="gpt-4o")
        store.add_or_update_provider(cfg)

        loaded = store.load()
        assert len(loaded.providers) == 1
        assert loaded.providers[0].provider_id == "openai"
        assert loaded.providers[0].api_key == "sk-test"
        assert loaded.active_provider_id == "openai"
        if os.name == "nt":
            assert "sk-test" not in store._config_path.read_text(encoding="utf-8")

    def test_update_overwrites_all_fields(self, tmp_path):
        store = UserConfigStore()
        store._config_path = tmp_path / "test_config.json"
        store._cached_config = None

        store.add_or_update_provider(
            UserProviderConfig(provider_id="openai", api_key="sk-secret", model="gpt-4o")
        )
        # Update with empty key overwrites it
        store.add_or_update_provider(
            UserProviderConfig(provider_id="openai", api_key="", model="gpt-4o-mini")
        )
        loaded = store.load()
        assert loaded.providers[0].api_key == ""
        assert loaded.providers[0].model == "gpt-4o-mini"

    def test_remove_provider(self, tmp_path):
        store = UserConfigStore()
        store._config_path = tmp_path / "test_config.json"
        store._cached_config = None

        store.add_or_update_provider(
            UserProviderConfig(provider_id="openai", api_key="sk-1", enabled=True)
        )
        store.add_or_update_provider(
            UserProviderConfig(provider_id="deepseek", api_key="sk-2", enabled=True)
        )
        store.remove_provider("openai")
        loaded = store.load()
        assert len(loaded.providers) == 1
        assert loaded.providers[0].provider_id == "deepseek"

    def test_set_active_provider(self, tmp_path):
        store = UserConfigStore()
        store._config_path = tmp_path / "test_config.json"
        store._cached_config = None

        store.add_or_update_provider(
            UserProviderConfig(provider_id="openai", api_key="sk-1", enabled=True)
        )
        store.set_active_provider("openai")
        assert store.load().active_provider_id == "openai"


class TestMaskKey:
    def test_masks_long_key(self):
        assert _mask_key("sk-1234567890abcdef", prefix=4, suffix=4) == "sk-1...cdef"

    def test_masks_short_key(self):
        assert _mask_key("abc", prefix=4, suffix=4) == "***"

    def test_empty_key(self):
        assert _mask_key("") == ""
