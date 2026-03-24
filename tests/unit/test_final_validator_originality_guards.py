from __future__ import annotations

from writing_agent.v2.final_validator import validate_final_document


def test_validate_final_document_fails_when_source_overlap_exceeds_threshold(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_MAX_SOURCE_OVERLAP_RATIO", "0.10")
    text = (
        "# Research Workflow\n\n"
        "## Introduction\n\n"
        "This study develops a research workflow for rural service governance. "
        "The platform integrates blockchain records, service requests, audit trails, and cross-agency review for transparent execution.\n\n"
        "## Conclusion\n\n"
        "The workflow improves transparency and traceability for rural service governance."
    )
    out = validate_final_document(
        title="Research Workflow",
        text=text,
        sections=["Introduction", "Conclusion"],
        problems=[],
        rag_gate_dropped=[],
        source_rows=[
            {
                "summary": "The platform integrates blockchain records, service requests, audit trails, and cross-agency review for transparent execution."
            }
        ],
    )
    assert out["passed"] is False
    assert out["semantic_passed"] is False
    assert float(out["source_overlap_ratio"]) > float(out["max_source_overlap_ratio"])
    assert out["source_overlap_hits"]


def test_validate_final_document_fails_when_formulaic_opening_ratio_exceeds_threshold(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_MAX_FORMULAIC_OPENING_RATIO", "0.20")
    monkeypatch.setenv("WRITING_AGENT_MAX_LOW_INFORMATION_RATIO", "1.0")
    text = (
        "# Research Workflow\n\n"
        "## Introduction\n\n"
        "This study maps service demand across villages using archived request logs and annual statistics. "
        "This study compares response latency across counties using audited workflow timestamps and completion records. "
        "This study examines actor coordination through task routing data, signed confirmations, and error traces.\n\n"
        "## Conclusion\n\n"
        "This study evaluates governance transparency with traceability indicators, dispute logs, and review outcomes. "
        "This study summarizes the final evidence boundary with explicit variables, observed tradeoffs, and implementation limits."
    )
    out = validate_final_document(
        title="Research Workflow",
        text=text,
        sections=["Introduction", "Conclusion"],
        problems=[],
        rag_gate_dropped=[],
        source_rows=[],
    )
    assert out["passed"] is False
    assert out["semantic_passed"] is False
    assert float(out["formulaic_opening_ratio"]) > float(out["max_formulaic_opening_ratio"])
    assert out["formulaic_opening_hits"]
