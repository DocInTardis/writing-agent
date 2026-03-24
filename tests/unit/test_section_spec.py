from __future__ import annotations

from writing_agent.v2.section_spec import build_section_specs, token_to_id_map


def test_build_section_specs_assigns_parent_and_kind() -> None:
    specs = build_section_specs(
        [
            "H2::引言",
            "H3::研究背景",
            "H2::方法设计",
            "H2::参考文献",
        ]
    )
    assert [s.id for s in specs] == ["sec_001", "sec_002", "sec_003", "sec_004"]
    assert specs[0].parent_id == ""
    assert specs[1].parent_id == "sec_001"
    assert specs[2].parent_id == ""
    assert specs[3].kind == "reference"


def test_token_to_id_map_uses_normalized_tokens() -> None:
    specs = build_section_specs(["引言", "H3::子章节"])
    mapping = token_to_id_map(specs)
    assert mapping["H2::引言"] == "sec_001"
    assert mapping["H3::子章节"] == "sec_002"

