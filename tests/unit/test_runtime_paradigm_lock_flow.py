from __future__ import annotations

from types import SimpleNamespace

from writing_agent.v2 import graph_runner_runtime as runtime_module
from writing_agent.v2.graph_runner import GenerateConfig


def _patch_common(monkeypatch) -> None:
    class _DummyProvider:
        def is_running(self) -> bool:
            return True

        def chat(self, *, system: str, user: str, temperature: float = 0.2, options=None) -> str:
            _ = system, user, temperature, options
            return "OK"

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
    monkeypatch.setattr(runtime_module, "_is_evidence_enabled", lambda: False)
    monkeypatch.setattr(runtime_module, "_fast_fill_section", lambda *args, **kwargs: "测试段落内容。" * 30)
    monkeypatch.setattr(runtime_module, "_analysis_correctness_guard", lambda **_kwargs: (True, [], {}))
    monkeypatch.setenv("WRITING_AGENT_FAST_PLAN", "1")
    monkeypatch.setenv("WRITING_AGENT_FAST_DRAFT", "1")
    monkeypatch.setenv("WRITING_AGENT_STRICT_JSON", "0")
    monkeypatch.setenv("WRITING_AGENT_ENFORCE_REFERENCE_MIN", "0")


def test_runtime_low_confidence_probe_unresolved_fails(monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(
        runtime_module,
        "_analyze_instruction",
        lambda **_kwargs: {
            "topic": "测试主题",
            "doc_type": "academic",
            "audience": "researcher",
            "style": "formal",
            "keywords": ["测试"],
            "must_include": [],
            "constraints": [],
            "_confidence_score": 0.9,
            "_schema_valid": True,
            "_needs_clarification": False,
        },
    )
    monkeypatch.setattr(
        runtime_module,
        "_classify_paradigm",
        lambda **_kwargs: {
            "paradigm": "engineering",
            "runner_up": "bibliometric",
            "confidence": 0.51,
            "margin": 0.05,
            "reasons": ["ambiguous_markers"],
            "score_map": {"engineering": 0.51, "bibliometric": 0.46},
            "source": "classifier",
            "low_confidence": True,
        },
    )
    monkeypatch.setattr(
        runtime_module,
        "_dual_outline_probe",
        lambda **_kwargs: {
            "resolved": False,
            "selected_paradigm": "",
            "selected_outline": [],
            "margin": 0.01,
            "scores": {"engineering": 0.24, "bibliometric": 0.23},
            "reason": "probe_score_too_close",
        },
    )

    events = list(
        runtime_module.run_generate_graph(
            instruction="请写一篇论文",
            current_text="",
            required_h2=[],
            required_outline=[],
            expand_outline=False,
            config=GenerateConfig(workers=1),
        )
    )
    probe = [ev for ev in events if isinstance(ev, dict) and str(ev.get("event") or "") == "dual_outline_probe"]
    assert probe
    final = [ev for ev in events if isinstance(ev, dict) and str(ev.get("event") or "") == "final"][-1]
    assert str(final.get("status") or "") == "failed"
    assert str(final.get("failure_reason") or "") == "paradigm_low_confidence_unresolved"


def test_runtime_enforces_bibliometric_spine_when_paradigm_locked(monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(
        runtime_module,
        "_analyze_instruction",
        lambda **_kwargs: {
            "topic": "文献计量分析",
            "doc_type": "academic",
            "audience": "researcher",
            "style": "formal",
            "keywords": ["文献计量", "CiteSpace"],
            "must_include": [],
            "constraints": [],
            "_confidence_score": 0.95,
            "_schema_valid": True,
            "_needs_clarification": False,
        },
    )
    monkeypatch.setattr(
        runtime_module,
        "_classify_paradigm",
        lambda **_kwargs: {
            "paradigm": "bibliometric",
            "runner_up": "engineering",
            "confidence": 0.94,
            "margin": 0.41,
            "reasons": ["bibliometric_markers"],
            "score_map": {"bibliometric": 2.6, "engineering": 0.8, "empirical": 0.2},
            "source": "classifier",
            "low_confidence": False,
        },
    )

    events = list(
        runtime_module.run_generate_graph(
            instruction="请基于CiteSpace写作",
            current_text="",
            required_h2=["系统总体架构", "关键技术实现"],
            required_outline=[],
            expand_outline=False,
            config=GenerateConfig(workers=1),
        )
    )
    plan = [ev for ev in events if isinstance(ev, dict) and str(ev.get("event") or "") == "plan"][-1]
    plan_titles = [
        runtime_module._canonicalize_section_name(runtime_module._section_title(s) or s)
        for s in (plan.get("sections") or [])
    ]
    expected_titles = [runtime_module._canonicalize_section_name(x) for x in runtime_module._bibliometric_section_spine()]
    assert plan_titles == expected_titles
