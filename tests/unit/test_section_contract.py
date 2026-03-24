from __future__ import annotations

from writing_agent.v2.section_contract import SectionContract


def test_keywords_contract_has_slot_bounds_and_hints():
    engine = SectionContract()
    contracts = engine.build_contracts(
        paradigm="academic",
        sections=["摘要", "关键词", "结论"],
        total_chars=6000,
        base_min_paras=2,
    )
    spec = contracts["关键词"]
    assert spec.required_slots == ["keywords"]
    assert spec.min_keyword_items == 3
    assert spec.max_keyword_items == 8
    assert len(spec.dimension_hints or []) >= 3


def test_keywords_fill_slots_uses_analysis_and_enforces_range():
    engine = SectionContract()
    contracts = engine.build_contracts(
        paradigm="academic",
        sections=["关键词"],
        total_chars=1200,
        base_min_paras=1,
    )
    spec = contracts["关键词"]
    text = "关键词："
    analysis = {"topic": "区块链驱动的农村服务协同治理", "keywords": ["区块链", "农村社会化服务", "协同治理"]}
    filled = engine.fill_slots(
        section_title="关键词",
        text=text,
        analysis=analysis,
        contract=spec,
    )
    assert "关键词：" in filled
    terms = [t.strip() for t in filled.split("：", 1)[1].split("；") if t.strip()]
    assert 3 <= len(terms) <= 8
    issues = engine.validate_slots(section_title="关键词", text=filled, contract=spec)
    assert issues == []




def test_contract_scale_reduces_non_keyword_sections(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_SECTION_CONTRACT_SCALE", "0.5")
    engine = SectionContract()
    contracts = engine.build_contracts(
        paradigm="bibliometric",
        sections=["Data source and search strategy", "Keywords"],
        total_chars=6000,
        base_min_paras=1,
    )
    data_spec = contracts["Data source and search strategy"]
    kw_spec = contracts["Keywords"]
    assert data_spec.min_chars < 800
    assert data_spec.max_chars < 1300
    assert kw_spec.max_chars == 220



def test_contract_auto_scale_reduces_short_document_sections(monkeypatch):
    monkeypatch.delenv("WRITING_AGENT_SECTION_CONTRACT_SCALE", raising=False)
    engine = SectionContract()
    contracts = engine.build_contracts(
        paradigm="bibliometric",
        sections=["Data source and search strategy", "Keywords"],
        total_chars=1200,
        base_min_paras=1,
    )
    data_spec = contracts["Data source and search strategy"]
    kw_spec = contracts["Keywords"]
    assert data_spec.min_chars < 800
    assert data_spec.max_chars < 1300
    assert kw_spec.max_chars == 220
