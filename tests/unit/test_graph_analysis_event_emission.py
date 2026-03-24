from types import SimpleNamespace

from writing_agent.v2 import graph_runner_runtime as runtime_module
from writing_agent.v2.graph_runner import GenerateConfig


def test_run_generate_graph_emits_structured_analysis_event(monkeypatch):
    class _DummyProvider:
        def chat(self, *, system: str, user: str, temperature: float = 0.2, options=None) -> str:
            _ = system, user, temperature, options
            return "OK"

        def is_running(self) -> bool:
            return True

        def chat_stream(self, *, system: str, user: str, temperature: float = 0.2, options=None):
            _ = system, user, temperature, options
            yield "OK"

        def embeddings(self, *, prompt: str, model: str | None = None):
            _ = prompt, model
            return [0.0]

    monkeypatch.setattr(
        runtime_module,
        "get_ollama_settings",
        lambda: SimpleNamespace(enabled=True, base_url="http://test", model="m", timeout_s=3.0),
    )
    monkeypatch.setattr(runtime_module, "get_default_provider", lambda **_kwargs: _DummyProvider())
    monkeypatch.setattr(runtime_module, "get_provider_name", lambda: "ollama")
    monkeypatch.setattr(runtime_module, "get_provider_snapshot", lambda **_kwargs: {"provider": "ollama"})
    monkeypatch.setattr(runtime_module, "_ollama_installed_models", lambda: [])
    monkeypatch.setattr(
        runtime_module,
        "_analyze_instruction",
        lambda **_kwargs: {
            "topic": "多智能体写作",
            "doc_type": "academic",
            "audience": "researcher",
            "style": "formal",
            "keywords": ["多智能体", "质量门禁"],
            "must_include": ["摘要", "关键词"],
            "constraints": ["中文"],
            "_confidence_score": 0.3,
            "_schema_valid": True,
            "_needs_clarification": True,
            "_clarification_questions": ["请明确具体研究对象。"],
        },
    )

    events = list(
        runtime_module.run_generate_graph(
            instruction="请写一篇中文学术论文",
            current_text="",
            required_h2=[],
            required_outline=[],
            expand_outline=False,
            config=GenerateConfig(workers=1, min_total_chars=1200),
        )
    )
    analysis_events = [ev for ev in events if isinstance(ev, dict) and str(ev.get("event") or "") == "analysis"]
    assert len(analysis_events) == 1
    analysis = analysis_events[0]
    assert analysis.get("topic") == "多智能体写作"
    assert analysis.get("doc_type") == "academic"
    assert analysis.get("needs_clarification") is True
    final_events = [ev for ev in events if isinstance(ev, dict) and str(ev.get("event") or "") == "final"]
    assert final_events
    assert final_events[-1].get("status") == "interrupted"
