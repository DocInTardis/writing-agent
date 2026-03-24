from __future__ import annotations

from types import SimpleNamespace

from writing_agent.v2 import graph_runner_runtime as runtime_module
from writing_agent.v2.graph_runner import GenerateConfig
from writing_agent.v2.section_contract import SectionContractSpec


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


def test_runtime_emits_contracts_and_applies_target_overrides(monkeypatch):
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
        lambda *args, **kwargs: "这是用于测试的段落内容。它包含完整句子并可用于验证运行时约束接线。" * 10,
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
            "keywords": ["区块链", "农村社会化服务", "协同治理"],
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
    monkeypatch.setattr(
        runtime_module,
        "_build_section_contracts",
        lambda **_kwargs: {
            "\u5f15\u8a00": SectionContractSpec(
                section="\u5f15\u8a00",
                min_chars=480,
                max_chars=860,
                min_paras=1,
                required_slots=[],
                dimension_hints=["policy impact"],
            ),
            "\u7ed3\u8bba": SectionContractSpec(
                section="\u7ed3\u8bba",
                min_chars=600,
                max_chars=1100,
                min_paras=2,
                required_slots=[],
                dimension_hints=["risk controls"],
            ),
            "\u53c2\u8003\u6587\u732e": SectionContractSpec(
                section="\u53c2\u8003\u6587\u732e",
                min_chars=0,
                max_chars=0,
                min_paras=1,
                required_slots=[],
                dimension_hints=[],
            ),
        },
    )

    monkeypatch.setenv("WRITING_AGENT_FAST_PLAN", "1")
    monkeypatch.setenv("WRITING_AGENT_FAST_DRAFT", "1")
    monkeypatch.setenv("WRITING_AGENT_STRICT_JSON", "0")
    monkeypatch.setenv("WRITING_AGENT_ENFORCE_REFERENCE_MIN", "0")
    monkeypatch.setenv("WRITING_AGENT_VALIDATE_PLAN", "0")
    monkeypatch.setenv("WRITING_AGENT_ENSURE_MIN_LENGTH", "0")
    monkeypatch.setenv("WRITING_AGENT_ENFORCE_CONTRACT_SLOTS", "1")
    monkeypatch.setenv("WRITING_AGENT_MIN_H2_COUNT", "0")

    events = list(
        runtime_module.run_generate_graph(
            instruction="write a paper",
            current_text="",
            required_h2=["Abstract", "Keywords", "Conclusion"],
            required_outline=[],
            expand_outline=False,
            config=GenerateConfig(workers=1, min_total_chars=0),
        )
    )

    contracts_events = [e for e in events if isinstance(e, dict) and str(e.get("event") or "") == "section_contracts"]
    assert contracts_events
    contracts_payload = contracts_events[-1].get("contracts") or {}
    assert "\u5f15\u8a00" in contracts_payload
    assert int((contracts_payload["\u5f15\u8a00"] or {}).get("min_chars") or 0) == 480

    target_events = [e for e in events if isinstance(e, dict) and str(e.get("event") or "") == "targets"]
    assert target_events
    targets_payload = target_events[-1].get("targets") or {}
    assert int((targets_payload["\u5f15\u8a00"] or {}).get("min_chars") or -1) == 480
    assert int((targets_payload["\u5f15\u8a00"] or {}).get("max_chars") or -1) == 860
