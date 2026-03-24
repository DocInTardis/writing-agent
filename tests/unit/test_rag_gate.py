from __future__ import annotations

from writing_agent.v2 import rag_gate


def test_theme_consistency_score_positive_on_overlap():
    score = rag_gate.theme_consistency_score(
        title="blockchain rural socialized service collaboration governance",
        source_text="This study discusses blockchain and rural service governance pathways.",
    )
    assert score > 0.2


def test_filter_sources_drops_entity_mismatch_for_blockchain_title():
    result = rag_gate.filter_sources(
        title="blockchain rural socialized service collaboration governance",
        sources=[
            {
                "title": "green finance and rural industrial upgrading",
                "summary": "Focuses on industrial policy and finance without distributed ledger technology.",
                "url": "https://example.com/a",
            },
            {
                "title": "blockchain-driven rural service collaboration governance",
                "summary": "A rural service collaboration model based on distributed ledger.",
                "url": "https://example.com/b",
            },
        ],
        min_theme_score=0.1,
    )
    kept = result.get("kept") or []
    dropped = result.get("dropped") or []
    assert len(kept) == 1
    assert len(dropped) == 1
    assert str(dropped[0].get("reason") or "") == "rag_entity_mismatch"


def test_reference_mode_keeps_topical_and_method_sources_but_drops_noise():
    title = "“区块链+农村社会化服务”研究现状与研究热点分析——基于CiteSpace的可视化分析"
    result = rag_gate.filter_sources(
        title=title,
        sources=[
            {
                "title": "Blockchain for decentralised rural development and governance",
                "summary": "This article studies blockchain-enabled governance for rural development services.",
                "url": "https://example.com/topic",
            },
            {
                "title": "Hot Spots and Trends of Credit Research Based on Blockchain Technology-A CiteSpace Visual Analysis",
                "summary": "A bibliometric and visualization study using CiteSpace.",
                "url": "https://example.com/mixed",
            },
            {
                "title": "Knowledge Mapping of Rural Elderly Health Research - A CiteSpace Bibliometric Analysis",
                "summary": "Bibliometric method paper using CiteSpace for rural studies.",
                "url": "https://example.com/method",
            },
            {
                "title": "Supplemental Information 1: Raw data analyzed by CiteSpace",
                "summary": "Raw data and settings.",
                "url": "https://example.com/noise",
            },
        ],
        min_theme_score=0.25,
        mode="reference",
    )
    kept_titles = {str(row.get("title") or "") for row in (result.get("kept") or [])}
    dropped = result.get("dropped") or []
    assert "Blockchain for decentralised rural development and governance" in kept_titles
    assert "Hot Spots and Trends of Credit Research Based on Blockchain Technology-A CiteSpace Visual Analysis" in kept_titles
    assert "Knowledge Mapping of Rural Elderly Health Research - A CiteSpace Bibliometric Analysis" in kept_titles
    noise_rows = [row for row in dropped if str(row.get("title") or "").startswith("Supplemental Information 1")]
    assert noise_rows
    assert str(noise_rows[0].get("reason") or "") == "rag_reference_noise"



def test_reference_mode_keeps_ai_writing_sources_for_cn_title():
    title = "\u9762\u5411\u9ad8\u6821\u79d1\u7814\u573a\u666f\u7684\u667a\u80fd\u5199\u4f5c\u4ee3\u7406\u7cfb\u7edf\u8bbe\u8ba1\u4e0e\u5b9e\u73b0"
    result = rag_gate.filter_sources(
        title=title,
        sources=[
            {
                "title": "ScholarCopilot: Training Large Language Models for Academic Writing with Accurate Citations",
                "summary": "An academic writing assistant for research workflows and accurate citations.",
                "url": "https://example.com/a",
            },
            {
                "title": "Human-LLM Coevolution: Evidence from Academic Writing",
                "summary": "Studies AI-assisted academic writing and research writing collaboration.",
                "url": "https://example.com/b",
            },
            {
                "title": "Green finance and regional industrial upgrading",
                "summary": "Unrelated finance topic without writing-agent or academic workflow alignment.",
                "url": "https://example.com/c",
            },
        ],
        min_theme_score=0.1,
        mode="reference",
    )
    kept_titles = {str(row.get("title") or "") for row in (result.get("kept") or [])}
    dropped_titles = {str(row.get("title") or "") for row in (result.get("dropped") or [])}
    assert "ScholarCopilot: Training Large Language Models for Academic Writing with Accurate Citations" in kept_titles
    assert "Human-LLM Coevolution: Evidence from Academic Writing" in kept_titles
    # Student/scientific-writing titles should also align with the Chinese writing-agent title.
    assert rag_gate.entity_aligned(title=title, source_text="Reward Modeling for Scientific Writing Evaluation", mode="reference") is True
    assert rag_gate.entity_aligned(title=title, source_text="Human-AI Collaboration in Student Writing", mode="reference") is True
    assert "Green finance and regional industrial upgrading" in dropped_titles
