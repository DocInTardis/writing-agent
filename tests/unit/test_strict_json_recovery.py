from types import SimpleNamespace

from writing_agent.v2 import graph_runner_runtime as runtime_module
from writing_agent.v2.graph_runner import GenerateConfig


def _patch_common(monkeypatch):
    class _DummyClient:
        def __init__(self, *args, **kwargs):
            _ = args, kwargs

        def is_running(self) -> bool:
            return True

    monkeypatch.setattr(
        runtime_module,
        "get_ollama_settings",
        lambda: SimpleNamespace(enabled=True, base_url="http://test", model="m", timeout_s=3.0),
    )
    monkeypatch.setattr(runtime_module, "OllamaClient", _DummyClient)
    monkeypatch.setattr(runtime_module, "_ollama_installed_models", lambda: [])
    monkeypatch.setattr(runtime_module, "_is_evidence_enabled", lambda: False)
    monkeypatch.setenv("WRITING_AGENT_STRICT_JSON", "1")
    monkeypatch.setenv("WRITING_AGENT_FAST_DRAFT", "1")
    monkeypatch.setenv("WRITING_AGENT_FAST_PLAN", "1")
    monkeypatch.setenv("WRITING_AGENT_DRAFT_MAX_MODELS", "2")
    monkeypatch.setenv("WRITING_AGENT_MIN_H2_COUNT", "1")
    monkeypatch.setenv("WRITING_AGENT_ENFORCE_FINAL_VALIDATION", "0")
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
            "_confidence_score": 0.95,
            "_schema_valid": True,
            "_needs_clarification": False,
        },
    )
    monkeypatch.setattr(runtime_module, "_analysis_correctness_guard", lambda **_kwargs: (True, [], {}))


def test_strict_json_recovers_missing_sections_before_final(monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(runtime_module, "_fast_fill_section", lambda *args, **kwargs: "")
    monkeypatch.setattr(runtime_module, "_generate_section_stream", lambda **_kwargs: "修复后的段落内容。" * 30)

    events = list(
        runtime_module.run_generate_graph(
            instruction="请写一篇中文学术论文",
            current_text="",
            required_h2=["背景", "方法", "实验"],
            required_outline=[],
            expand_outline=False,
            config=GenerateConfig(workers=1, min_total_chars=1200),
        )
    )
    recovery_events = [ev for ev in events if isinstance(ev, dict) and str(ev.get("event") or "") == "strict_json_recovery"]
    assert recovery_events
    assert any(int(ev.get("attempt") or 0) == 1 for ev in recovery_events)
    final = [ev for ev in events if isinstance(ev, dict) and str(ev.get("event") or "") == "final"][-1]
    assert str(final.get("runtime_status") or "") == "success"
    assert not str(final.get("failure_reason") or "").startswith("strict_json_missing_sections:")
    assert str(final.get("text") or "").strip()


def test_strict_json_returns_structured_failure_after_recovery_exhausted(monkeypatch):
    _patch_common(monkeypatch)
    monkeypatch.setattr(runtime_module, "_fast_fill_section", lambda *args, **kwargs: "")
    monkeypatch.setattr(runtime_module, "_generate_section_stream", lambda **_kwargs: "")

    events = list(
        runtime_module.run_generate_graph(
            instruction="请写一篇中文学术论文",
            current_text="",
            required_h2=["背景", "方法", "实验"],
            required_outline=[],
            expand_outline=False,
            config=GenerateConfig(workers=1, min_total_chars=1200),
        )
    )
    recovery_events = [ev for ev in events if isinstance(ev, dict) and str(ev.get("event") or "") == "strict_json_recovery"]
    assert any(int(ev.get("attempt") or 0) == 1 for ev in recovery_events)
    assert any(int(ev.get("attempt") or 0) == 2 for ev in recovery_events)
    final = [ev for ev in events if isinstance(ev, dict) and str(ev.get("event") or "") == "final"][-1]
    assert str(final.get("status") or "") == "failed"
    reason = str(final.get("failure_reason") or "")
    assert reason.startswith("strict_json_missing_sections:")
    snapshot = final.get("quality_snapshot") if isinstance(final.get("quality_snapshot"), dict) else {}
    assert str(snapshot.get("reason") or "").startswith("strict_json_missing_sections")
    assert isinstance(snapshot.get("missing_sections"), list)
