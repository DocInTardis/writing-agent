from writing_agent.v2.section_contract import SectionContract


def test_rebalance_contracts_by_evidence_shrinks_sparse_section_budget() -> None:
    engine = SectionContract()
    contracts = engine.build_contracts(
        paradigm="engineering",
        sections=["\u5f15\u8a00", "\u7ed3\u8bba", "\u5173\u952e\u8bcd"],
        total_chars=9000,
        base_min_paras=3,
    )
    original_intro = contracts["\u5f15\u8a00"]
    rebalanced, rows = engine.rebalance_contracts_by_evidence(
        contracts=contracts,
        evidence_by_section={
            "\u5f15\u8a00": {
                "sources": [{"title": "only-one-source"}],
                "facts": [{"claim": "x", "source": "only-one-source"}],
                "fact_gain_count": 1,
                "fact_density_score": 0.2,
                "data_starvation": {"stub_mode": True, "source_count": 1, "alignment_score": 0.4},
            }
        },
    )
    assert rebalanced["\u5f15\u8a00"].max_chars < original_intro.max_chars
    assert rebalanced["\u5f15\u8a00"].min_chars <= original_intro.min_chars
    assert any(str(row.get("section") or "") == "\u5f15\u8a00" for row in rows)


def test_rebalance_contracts_by_evidence_keeps_keywords_unchanged() -> None:
    engine = SectionContract()
    contracts = engine.build_contracts(
        paradigm="engineering",
        sections=["\u5173\u952e\u8bcd"],
        total_chars=4000,
        base_min_paras=1,
    )
    rebalanced, rows = engine.rebalance_contracts_by_evidence(
        contracts=contracts,
        evidence_by_section={
            "\u5173\u952e\u8bcd": {
                "sources": [],
                "facts": [],
                "fact_gain_count": 0,
                "fact_density_score": 0.0,
                "data_starvation": {"stub_mode": True, "source_count": 0, "alignment_score": 0.0},
            }
        },
    )
    assert rebalanced["\u5173\u952e\u8bcd"] == contracts["\u5173\u952e\u8bcd"]
    assert rows == []
