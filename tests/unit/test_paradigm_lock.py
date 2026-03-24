from __future__ import annotations

from writing_agent.v2.paradigm_lock import ParadigmLock


def test_paradigm_classifier_outputs_confidence_and_margin() -> None:
    lock = ParadigmLock()
    decision = lock.classify(
        instruction="请基于CiteSpace完成文献计量可视化分析，包含关键词共现与突现分析。",
        analysis={"doc_type": "academic", "keywords": ["文献计量", "CiteSpace"]},
    )
    assert decision.paradigm == "bibliometric"
    assert 0.0 <= float(decision.confidence) <= 1.0
    assert 0.0 <= float(decision.margin) <= 1.0


def test_paradigm_classifier_supports_user_override() -> None:
    lock = ParadigmLock()
    decision = lock.classify(
        instruction="请写一篇论文",
        analysis={"doc_type": "academic"},
        user_override="engineering",
    )
    assert decision.paradigm == "engineering"
    assert decision.source == "override"
    assert float(decision.confidence) == 1.0
    assert float(decision.margin) == 1.0


def test_paradigm_enforce_sections_physical_isolation_for_bibliometric() -> None:
    lock = ParadigmLock()
    out = lock.enforce_sections(
        sections=["摘要", "引言", "系统总体架构", "关键技术实现", "结论", "参考文献"],
        paradigm="bibliometric",
        allow_engineering=False,
        bibliometric_outline=["摘要", "关键词", "引言", "数据来源与检索策略", "结论", "参考文献"],
    )
    assert out == ["摘要", "关键词", "引言", "数据来源与检索策略", "结论", "参考文献"]


def test_dual_outline_probe_returns_unresolved_when_scores_too_close() -> None:
    lock = ParadigmLock()
    probe = lock.dual_outline_probe(
        instruction="写一篇论文",
        analysis={},
        primary_paradigm="engineering",
        secondary_paradigm="empirical",
        primary_outline=["引言", "方法", "结论"],
        secondary_outline=["引言", "方法", "结论"],
    )
    assert probe["resolved"] is False
    assert str(probe.get("reason") or "") == "probe_score_too_close"


def test_dual_outline_probe_picks_bibliometric_when_markers_present() -> None:
    lock = ParadigmLock()
    probe = lock.dual_outline_probe(
        instruction="CiteSpace bibliometric visualization analysis",
        analysis={"topic": "bibliometric analysis"},
        primary_paradigm="bibliometric",
        secondary_paradigm="engineering",
        primary_outline=[
            "Abstract",
            "Keywords",
            "Data source and search strategy",
            "Keyword co-occurrence and clustering",
            "Conclusion",
            "References",
        ],
        secondary_outline=["Abstract", "System architecture", "Implementation", "Conclusion", "References"],
    )
    assert probe["resolved"] is True
    assert str(probe.get("selected_paradigm") or "") == "bibliometric"
