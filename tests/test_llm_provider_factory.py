from __future__ import annotations

from types import SimpleNamespace

import pytest

from writing_agent.llm.factory import get_default_provider
from writing_agent.llm.provider import LLMProviderError
from writing_agent.llm.providers import NodeAIGatewayProvider, OllamaProvider


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
