from __future__ import annotations

from writing_agent.v2 import graph_runner_runtime as runtime_module
from writing_agent.v2.graph_runner import GenerateConfig


def test_run_generate_graph_provider_misconfigured_returns_failed(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_LLM_PROVIDER", "openai")
    monkeypatch.delenv("WRITING_AGENT_OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("WRITING_AGENT_OPENAI_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("WRITING_AGENT_OPENAI_MODEL", "gpt-4o-mini")

    events = list(
        runtime_module.run_generate_graph(
            instruction="请写一份报告",
            current_text="",
            required_h2=[],
            required_outline=[],
            expand_outline=False,
            config=GenerateConfig(workers=1),
        )
    )
    final = [ev for ev in events if isinstance(ev, dict) and ev.get("event") == "final"][-1]
    assert final.get("status") == "failed"
    assert final.get("failure_reason") == "api_provider_misconfigured"


def test_run_generate_graph_provider_auth_failed_returns_failed(monkeypatch):
    class _AuthFailedProvider:
        def is_running(self) -> bool:
            return True

        def chat(self, *, system: str, user: str, temperature: float = 0.2, options=None) -> str:
            _ = system, user, temperature, options
            raise RuntimeError("401 Unauthorized")

        def chat_stream(self, *, system: str, user: str, temperature: float = 0.2, options=None):
            _ = system, user, temperature, options
            yield ""

        def embeddings(self, *, prompt: str, model: str | None = None):
            _ = prompt, model
            return []

    monkeypatch.setenv("WRITING_AGENT_LLM_PROVIDER", "openai")
    monkeypatch.setenv("WRITING_AGENT_OPENAI_API_KEY", "sk-test-key")
    monkeypatch.setattr(runtime_module, "get_default_provider", lambda **_kwargs: _AuthFailedProvider())

    events = list(
        runtime_module.run_generate_graph(
            instruction="请写一份报告",
            current_text="",
            required_h2=[],
            required_outline=[],
            expand_outline=False,
            config=GenerateConfig(workers=1),
        )
    )
    final = [ev for ev in events if isinstance(ev, dict) and ev.get("event") == "final"][-1]
    assert final.get("status") == "failed"
    assert final.get("failure_reason") == "api_auth_failed"


def test_provider_preflight_openai_compat_allows_missing_is_running_when_chat_preflight_disabled(monkeypatch):
    class _GatewayProvider:
        def is_running(self) -> bool:
            return False

        def chat(self, *, system: str, user: str, temperature: float = 0.2, options=None) -> str:
            _ = system, user, temperature, options
            return "OK"

    monkeypatch.setenv("WRITING_AGENT_PROVIDER_PREFLIGHT_CHAT", "0")
    ok, reason = runtime_module._provider_preflight(
        provider=_GatewayProvider(),
        model="gpt-5.4",
        provider_name="openai",
    )
    assert ok is True
    assert reason == ""


def test_provider_default_per_model_concurrency_is_provider_aware(monkeypatch):
    monkeypatch.delenv("WRITING_AGENT_PER_MODEL_CONCURRENCY", raising=False)
    assert runtime_module._provider_default_per_model_concurrency("openai") == 4
    assert runtime_module._provider_default_per_model_concurrency("ollama") == 1

    monkeypatch.setenv("WRITING_AGENT_PER_MODEL_CONCURRENCY", "3")
    assert runtime_module._provider_default_per_model_concurrency("openai") == 3



def test_provider_default_evidence_workers_respects_override_and_section_cap(monkeypatch):
    monkeypatch.delenv("WRITING_AGENT_EVIDENCE_WORKERS", raising=False)
    assert runtime_module._provider_default_evidence_workers("openai", sections_count=2) == 2
    assert runtime_module._provider_default_evidence_workers("openai", sections_count=10) == 6
    assert runtime_module._provider_default_evidence_workers("ollama", sections_count=10) == 3

    monkeypatch.setenv("WRITING_AGENT_EVIDENCE_WORKERS", "5")
    assert runtime_module._provider_default_evidence_workers("openai", sections_count=3) == 3
