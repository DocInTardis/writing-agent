from __future__ import annotations

from writing_agent.v2.graph_reference_domain import ReferenceAgent


def test_reference_agent_detects_natural_language_contamination() -> None:
    agent = ReferenceAgent(
        extract_year_fn=lambda _x: "2024",
        format_authors_fn=lambda names: ", ".join(names) if names else "Anonymous",
    )
    issues = agent.validate([
        "[1] 张三. 区块链治理研究[J]. 2024.",
        "[2] 本研究围绕区块链展开说明并给出如下建议。",
    ])
    assert any(str(item).startswith("natural_language_contamination:") for item in issues)
