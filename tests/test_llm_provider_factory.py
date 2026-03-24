from __future__ import annotations

from types import SimpleNamespace

import pytest

from writing_agent.llm.factory import get_default_provider, get_provider_name, get_provider_snapshot, mask_secret
from writing_agent.llm.provider import LLMProviderError
from writing_agent.llm.providers import NodeAIGatewayProvider, OllamaProvider, OpenAICompatibleProvider


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


def test_get_default_provider_supports_node_backend(monkeypatch) -> None:
    monkeypatch.setenv("WRITING_AGENT_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("WRITING_AGENT_LLM_BACKEND", "node")
    monkeypatch.setenv("WRITING_AGENT_NODE_GATEWAY_URL", "http://127.0.0.1:8787")
    monkeypatch.setenv("WRITING_AGENT_LLM_BACKEND_ROLLOUT_PERCENT", "100")
    monkeypatch.setattr(
        "writing_agent.llm.factory.get_ollama_settings",
        lambda: SimpleNamespace(enabled=True, base_url="http://127.0.0.1:11434", model="qwen2.5:1.5b", timeout_s=12.0),
    )
    provider = get_default_provider()
    assert isinstance(provider, NodeAIGatewayProvider)


def test_get_default_provider_rollout_zero_uses_python(monkeypatch) -> None:
    monkeypatch.setenv("WRITING_AGENT_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("WRITING_AGENT_LLM_BACKEND", "node")
    monkeypatch.setenv("WRITING_AGENT_NODE_GATEWAY_URL", "http://127.0.0.1:8787")
    monkeypatch.setenv("WRITING_AGENT_LLM_BACKEND_ROLLOUT_PERCENT", "0")
    monkeypatch.setattr(
        "writing_agent.llm.factory.get_ollama_settings",
        lambda: SimpleNamespace(enabled=True, base_url="http://127.0.0.1:11434", model="qwen2.5:1.5b", timeout_s=12.0),
    )
    provider = get_default_provider()
    assert isinstance(provider, OllamaProvider)


def test_get_default_provider_node_without_url_falls_back_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("WRITING_AGENT_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("WRITING_AGENT_LLM_BACKEND", "node")
    monkeypatch.delenv("WRITING_AGENT_NODE_GATEWAY_URL", raising=False)
    monkeypatch.setenv("WRITING_AGENT_NODE_GATEWAY_AUTO_FALLBACK", "1")
    monkeypatch.setattr(
        "writing_agent.llm.factory.get_ollama_settings",
        lambda: SimpleNamespace(enabled=True, base_url="http://127.0.0.1:11434", model="qwen2.5:1.5b", timeout_s=12.0),
    )
    provider = get_default_provider()
    assert isinstance(provider, OllamaProvider)


def test_get_default_provider_supports_openai_compatible(monkeypatch) -> None:
    monkeypatch.setenv("WRITING_AGENT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("WRITING_AGENT_OPENAI_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("WRITING_AGENT_OPENAI_API_KEY", "sk-test-openai-123456")
    monkeypatch.setenv("WRITING_AGENT_OPENAI_MODEL", "gpt-4o-mini")

    provider = get_default_provider()
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.base_url == "https://api.example.com/v1"
    assert provider.model == "gpt-4o-mini"


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
