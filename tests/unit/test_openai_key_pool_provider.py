from __future__ import annotations

import pytest

from writing_agent.llm.factory import get_default_provider, get_provider_snapshot
from writing_agent.llm.provider import LLMProviderError
from writing_agent.llm.providers.failover_provider import OpenAIKeyPoolProvider


class _FailThenPassProvider:
    def __init__(self, *, exc: Exception | None = None, text: str = "") -> None:
        self._exc = exc
        self._text = text

    def is_running(self) -> bool:
        return True

    def chat(self, *, system, user, temperature=0.2, options=None):
        _ = system, user, temperature, options
        if self._exc is not None:
            raise self._exc
        return self._text

    def chat_stream(self, *, system, user, temperature=0.2, options=None):
        _ = system, user, temperature, options
        if self._exc is not None:
            raise self._exc
        yield self._text

    def embeddings(self, *, prompt, model=None):
        _ = prompt, model
        if self._exc is not None:
            raise self._exc
        return [0.1]


def test_openai_key_pool_provider_uses_next_candidate_on_quota_error() -> None:
    provider = OpenAIKeyPoolProvider(
        providers=(
            _FailThenPassProvider(exc=LLMProviderError("api_insufficient_quota:http_429")),
            _FailThenPassProvider(text="ok-from-second"),
        ),
        provider_labels=("primary", "secondary"),
    )

    assert provider.chat(system="s", user="u") == "ok-from-second"
    assert "".join(provider.chat_stream(system="s", user="u")) == "ok-from-second"
    assert provider.embeddings(prompt="x") == [0.1]


def test_openai_key_pool_provider_stops_on_non_retryable_error() -> None:
    provider = OpenAIKeyPoolProvider(
        providers=(
            _FailThenPassProvider(exc=LLMProviderError("validation_failed:bad_request")),
            _FailThenPassProvider(text="should-not-run"),
        ),
        provider_labels=("primary", "secondary"),
    )

    with pytest.raises(LLMProviderError, match="validation_failed:bad_request"):
        provider.chat(system="s", user="u")


def test_factory_builds_openai_key_pool_when_multiple_candidates_exist(monkeypatch) -> None:
    monkeypatch.setenv("WRITING_AGENT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("WRITING_AGENT_OPENAI_QUOTA_FALLBACK", "0")

    first = _FailThenPassProvider(text="first")
    first.base_url = "https://a.example.com/v1"
    second = _FailThenPassProvider(text="second")
    second.base_url = "https://b.example.com/v1"

    monkeypatch.setattr(
        "writing_agent.llm.factory.openai_providers_from_env",
        lambda **_kwargs: [first, second],
    )

    provider = get_default_provider()

    assert isinstance(provider, OpenAIKeyPoolProvider)
    assert provider.chat(system="s", user="u") == "first"


def test_provider_snapshot_reports_openai_pool_size(monkeypatch, tmp_path) -> None:
    bat_path = tmp_path / "100美刀配置 .bat"
    bat_path.write_text(
        '\n'.join(
            [
                '@echo off',
                'echo base_url = "https://pool.example.com/v1"',
                'echo model = "gpt-5.4"',
                'echo   "OPENAI_API_KEY": "sk-bat-key"',
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("WRITING_AGENT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("WRITING_AGENT_OPENAI_BASE_URL", "https://env.example.com/v1")
    monkeypatch.setenv("WRITING_AGENT_OPENAI_API_KEY", "sk-env-key")
    monkeypatch.setenv("WRITING_AGENT_OPENAI_BAT_CONFIG_PATHS", str(bat_path))

    snapshot = get_provider_snapshot(model="gpt-5.4")

    assert snapshot["provider"] == "openai"
    assert snapshot["api_key_pool_size"] == "2"
    assert snapshot["base_url"] == "https://env.example.com/v1"
