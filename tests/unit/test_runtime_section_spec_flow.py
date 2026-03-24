from __future__ import annotations

from types import SimpleNamespace

from writing_agent.v2 import graph_runner_runtime as runtime_module
from writing_agent.v2.graph_runner import GenerateConfig


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


def test_runtime_emits_section_specs_and_struct_plan_section_ids(monkeypatch):
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
    monkeypatch.setattr(
        runtime_module,
        "_fast_fill_section",
        lambda *args, **kwargs: "这是用于测试的段落内容。它包含完整句子并可用于验证 section_id 传递。"
        * 8,
    )
    monkeypatch.setattr(runtime_module, "_analysis_correctness_guard", lambda **_kwargs: (True, [], {}))
    monkeypatch.setattr(
        runtime_module,
        "_analyze_instruction",
        lambda **_kwargs: {
            "topic": "区块链农村服务",
            "doc_type": "academic",
            "audience": "researcher",
            "style": "formal",
            "keywords": ["区块链", "农村服务"],
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
            "paradigm": "engineering",
            "runner_up": "bibliometric",
            "confidence": 0.93,
            "margin": 0.42,
            "reasons": ["test"],
            "score_map": {"engineering": 2.2, "bibliometric": 0.7},
            "source": "classifier",
            "low_confidence": False,
        },
    )

    monkeypatch.setenv("WRITING_AGENT_FAST_PLAN", "1")
    monkeypatch.setenv("WRITING_AGENT_FAST_DRAFT", "1")
    monkeypatch.setenv("WRITING_AGENT_STRICT_JSON", "0")
    monkeypatch.setenv("WRITING_AGENT_ENFORCE_REFERENCE_MIN", "0")
    monkeypatch.setenv("WRITING_AGENT_VALIDATE_PLAN", "0")
    monkeypatch.setenv("WRITING_AGENT_ENSURE_MIN_LENGTH", "0")
    monkeypatch.setenv("WRITING_AGENT_ENFORCE_CONTRACT_SLOTS", "0")
    monkeypatch.setenv("WRITING_AGENT_ENFORCE_META_FIREWALL", "0")
    monkeypatch.setenv("WRITING_AGENT_ENFORCE_FINAL_VALIDATION", "0")
    monkeypatch.setenv("WRITING_AGENT_MIN_H2_COUNT", "0")

    events = list(
        runtime_module.run_generate_graph(
            instruction="write a paper",
            current_text="",
            required_h2=["引言", "结论", "参考文献"],
            required_outline=[],
            expand_outline=False,
            config=GenerateConfig(workers=1, min_total_chars=0),
        )
    )

    section_specs_events = [
        e for e in events if isinstance(e, dict) and str(e.get("event") or "") == "section_specs"
    ]
    assert section_specs_events
    spec_items = list(section_specs_events[-1].get("items") or [])
    assert spec_items
    assert str(spec_items[0].get("id") or "").startswith("sec_")
    assert str(spec_items[0].get("token") or "").startswith("H")

    struct_plan_events = [e for e in events if isinstance(e, dict) and str(e.get("event") or "") == "struct_plan"]
    assert struct_plan_events
    plan_sections = list((struct_plan_events[-1].get("plan") or {}).get("sections") or [])
    assert plan_sections
    assert all(str(row.get("section_id") or "").startswith("sec_") for row in plan_sections)

    section_start_events = [
        e
        for e in events
        if isinstance(e, dict)
        and str(e.get("event") or "") == "section"
        and str(e.get("phase") or "") == "start"
    ]
    assert section_start_events
    assert all(str(e.get("section_id") or "").startswith("sec_") for e in section_start_events)
