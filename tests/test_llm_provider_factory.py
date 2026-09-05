from __future__ import annotations

from types import SimpleNamespace

import pytest

from writing_agent.llm.factory import get_default_provider, get_provider_name, get_provider_snapshot, mask_secret
from writing_agent.llm.provider import LLMProviderError
from writing_agent.llm.providers import OllamaProvider, OpenAICompatibleProvider


def test_get_provider_name_defaults_to_openai(monkeypatch) -> None:
    monkeypatch.delenv("WRITING_AGENT_LLM_PROVIDER", raising=False)
    assert get_provider_name() == "openai"


def test_openai_path_never_inspects_ollama(monkeypatch):
    from writing_agent.llm import factory

    primary = SimpleNamespace(model="chosen-model")
    monkeypatch.setattr(factory, "openai_providers_from_env", lambda **_: [primary])

    def unexpected_ollama():
        raise AssertionError("default API path must not inspect or initialize Ollama")

    monkeypatch.setattr(factory, "get_ollama_settings", unexpected_ollama)
    assert factory._build_openai_provider() is primary


def test_user_model_selection_takes_precedence_over_environment_cache(monkeypatch):
    from writing_agent.llm import factory

    monkeypatch.setenv("WRITING_AGENT_PROVIDER_CACHE_ENABLED", "1")
    current = [SimpleNamespace(model="first-user-model")]
    monkeypatch.setattr(factory, "_build_user_configured_provider", lambda **_: current[0])

    def unexpected_environment_resolution(**_):
        raise AssertionError("user selection must not be shadowed by an environment cache")

    monkeypatch.setattr(factory, "_provider_cache_key", unexpected_environment_resolution)
    assert get_default_provider() is current[0]
    current[0] = SimpleNamespace(model="second-user-model")
    assert get_default_provider() is current[0]


def test_get_default_provider_returns_ollama_provider(monkeypatch) -> None:
    monkeypatch.setenv("WRITING_AGENT_LLM_PROVIDER", "ollama")
    monkeypatch.setattr(
        "writing_agent.llm.factory.get_ollama_settings",
        lambda: SimpleNamespace(enabled=True, base_url="http://127.0.0.1:11434", model="qwen2.5:1.5b", timeout_s=12.0),
    )
    provider = get_default_provider()
    assert isinstance(provider, OllamaProvider)
    assert provider.client.model == "qwen2.5:1.5b"


def test_get_default_provider_rejects_unsupported_provider(monkeypatch) -> None:
    monkeypatch.setenv("WRITING_AGENT_LLM_PROVIDER", "unsupported-x")
    with pytest.raises(LLMProviderError):
        get_default_provider()


def test_get_default_provider_rejects_disabled_settings(monkeypatch) -> None:
    monkeypatch.setenv("WRITING_AGENT_LLM_PROVIDER", "ollama")
    monkeypatch.setattr(
        "writing_agent.llm.factory.get_ollama_settings",
        lambda: SimpleNamespace(enabled=False, base_url="", model="", timeout_s=1.0),
    )
    with pytest.raises(LLMProviderError):
        get_default_provider()


def test_get_default_provider_supports_openai_compatible(monkeypatch) -> None:
    monkeypatch.setenv("WRITING_AGENT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("WRITING_AGENT_OPENAI_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("WRITING_AGENT_OPENAI_API_KEY", "sk-test-openai-123456")
    monkeypatch.setenv("WRITING_AGENT_OPENAI_MODEL", "gpt-4o-mini")

    provider = get_default_provider()
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.base_url == "https://api.example.com/v1"
    assert provider.model == "gpt-4o-mini"
    assert provider.wire_api == "chat_completions"


def test_provider_name_alias_openai_compatible(monkeypatch) -> None:
    monkeypatch.setenv("WRITING_AGENT_LLM_PROVIDER", "openai_compatible")
    assert get_provider_name() == "openai"


def test_provider_snapshot_masks_api_key(monkeypatch) -> None:
    monkeypatch.setenv("WRITING_AGENT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("WRITING_AGENT_OPENAI_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("WRITING_AGENT_OPENAI_API_KEY", "sk-super-secret-abcdefg")
    snap = get_provider_snapshot(model="gpt-5.4")
    assert snap["provider"] == "openai"
    assert snap["base_url"] == "https://api.example.com/v1"
    assert snap["api_key_masked"].startswith("sk-s")
    assert "secret" not in snap["api_key_masked"]
    assert snap["model"] == "gpt-5.4"
    assert snap["wire_api"] == "chat_completions"


def test_mask_secret_handles_short_values() -> None:
    assert mask_secret("") == ""
    assert mask_secret("abc") == "***"


def test_get_default_provider_reuses_cached_instance(monkeypatch) -> None:
    monkeypatch.setenv("WRITING_AGENT_PROVIDER_CACHE_ENABLED", "1")
    monkeypatch.setenv("WRITING_AGENT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("WRITING_AGENT_OPENAI_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("WRITING_AGENT_OPENAI_API_KEY", "sk-cache-test-123456")
    monkeypatch.setenv("WRITING_AGENT_OPENAI_MODEL", "gpt-5.4")

    first = get_default_provider()
    second = get_default_provider()
    assert first is second
