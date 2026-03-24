from __future__ import annotations

from writing_agent.v2 import graph_runner_runtime as runtime



def test_starvation_failure_decision_triggers_when_ratio_exceeds_threshold(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_RAG_DATA_STARVATION_FAIL_RATIO", "0.5")
    out = runtime._starvation_failure_decision(
        sections=["Abstract", "Introduction", "Method", "Conclusion", "References"],
        data_starvation_rows=[
            {"title": "Introduction"},
            {"title": "Method"},
        ],
        evidence_enabled=True,
    )
    assert out["section_count"] == 3
    assert out["starved_count"] == 2
    assert float(out["ratio"]) == 0.6667
    assert out["triggered"] is True



def test_starvation_failure_decision_ignores_summary_and_reference_sections(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_RAG_DATA_STARVATION_FAIL_RATIO", "0.5")
    out = runtime._starvation_failure_decision(
        sections=["Abstract", "Introduction", "Method", "Conclusion", "References"],
        data_starvation_rows=[
            {"title": "Abstract"},
            {"title": "References"},
            {"title": "Introduction"},
        ],
        evidence_enabled=True,
    )
    assert out["section_count"] == 3
    assert out["starved_count"] == 1
    assert float(out["ratio"]) == 0.3333
    assert out["triggered"] is False

def test_starvation_failure_decision_uses_tighter_default_threshold(monkeypatch):
    monkeypatch.delenv("WRITING_AGENT_RAG_DATA_STARVATION_FAIL_RATIO", raising=False)
    out = runtime._starvation_failure_decision(
        sections=["Abstract", "Introduction", "Method", "Results", "Conclusion", "References"],
        data_starvation_rows=[{"title": "Introduction"}],
        evidence_enabled=True,
    )
    assert out["section_count"] == 4
    assert out["starved_count"] == 1
    assert float(out["threshold"]) == 0.25
    assert float(out["ratio"]) == 0.25
    assert out["triggered"] is True

