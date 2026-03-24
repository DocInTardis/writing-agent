from __future__ import annotations

from writing_agent.v2.document_assembly import assemble_by_id_map, find_missing_sections
from writing_agent.v2.section_spec import build_section_specs


def test_assemble_by_id_map_preserves_section_order_and_levels() -> None:
    specs = build_section_specs(["H2::引言", "H3::研究背景", "H2::结论"])
    text, assembly_map = assemble_by_id_map(
        title="测试标题",
        section_specs=specs,
        content_by_id={
            "sec_001": "引言内容。",
            "sec_002": "背景内容。",
            "sec_003": "结论内容。",
        },
    )
    assert "## 引言" in text
    assert "### 研究背景" in text
    assert text.index("## 引言") < text.index("### 研究背景") < text.index("## 结论")
    assert len(assembly_map.slots) == 3


def test_find_missing_sections_returns_structured_rows() -> None:
    specs = build_section_specs(["H2::引言", "H2::参考文献"])
    rows = find_missing_sections(
        section_specs=specs,
        content_by_id={"sec_001": ""},
        stage="aggregate",
    )
    assert len(rows) == 1
    assert rows[0].section_id == "sec_001"
    assert rows[0].reason == "section_content_missing"
