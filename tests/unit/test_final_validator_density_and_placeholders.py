from writing_agent.v2.final_validator import validate_final_document


_TITLE = "\u667a\u80fd\u5199\u4f5c\u4ee3\u7406\u7814\u7a76"
_SECTIONS = ["\u5f15\u8a00", "\u7ed3\u8bba"]


def test_validate_final_document_fails_on_placeholder_residue() -> None:
    text = (
        "# " + _TITLE + "\n\n"
        "## \u5f15\u8a00\n\n"
        "\u5b9e\u9a8c\u9879\uff1a\u5f85\u8865\u5145\u3002\n\n"
        "## \u7ed3\u8bba\n\n"
        "[1]\uff1b\u533a\u5757\u94fe\u8def\u5f84\u5f85\u8865\u5145\u3002"
    )
    out = validate_final_document(title=_TITLE, text=text, sections=_SECTIONS, problems=[], rag_gate_dropped=[])
    assert out["passed"] is False
    assert out["semantic_passed"] is False
    assert float(out["placeholder_residue_ratio"]) > 0.0
    assert out["placeholder_residue_hits"]


def test_validate_final_document_fails_on_low_information_density() -> None:
    text = (
        "# " + _TITLE + "\n\n"
        "## \u5f15\u8a00\n\n"
        "\u9996\u5148\uff0c\u7814\u7a76\u5206\u6790\u95ee\u9898\u4e0e\u5185\u5bb9\uff1b\u5176\u6b21\uff0c\u7814\u7a76\u5206\u6790\u95ee\u9898\u4e0e\u5185\u5bb9\uff1b\u6700\u540e\uff0c\u7814\u7a76\u5206\u6790\u95ee\u9898\u4e0e\u5185\u5bb9\uff0c\u5e76\u5728\u540e\u7eed\u5de5\u4f5c\u4e2d\u8fdb\u4e00\u6b65\u8bf4\u660e\u3002\n\n"
        "## \u7ed3\u8bba\n\n"
        "\u9996\u5148\uff0c\u7814\u7a76\u5206\u6790\u95ee\u9898\u4e0e\u5185\u5bb9\uff1b\u5176\u6b21\uff0c\u7814\u7a76\u5206\u6790\u95ee\u9898\u4e0e\u5185\u5bb9\uff1b\u6700\u540e\uff0c\u7814\u7a76\u5206\u6790\u95ee\u9898\u4e0e\u5185\u5bb9\uff0c\u5e76\u5bf9\u540e\u7eed\u65b9\u5411\u8fdb\u884c\u8ba8\u8bba\u3002"
    )
    out = validate_final_document(title=_TITLE, text=text, sections=_SECTIONS, problems=[], rag_gate_dropped=[])
    assert out["passed"] is False
    assert out["semantic_passed"] is False
    assert float(out["information_density_fail_ratio"]) > 0.0
    assert out["information_density_hits"]



def test_validate_final_document_fails_on_unexpected_sections_and_order_drift() -> None:
    sections = ["Introduction", "Conclusion"]
    text = (
        "# Title\n\n"
        "## Introduction\n\n"
        "Background content.\n\n"
        "## Related Work\n\n"
        "This is an unexpected drift section.\n\n"
        "## Conclusion\n\n"
        "Conclusion content."
    )
    out = validate_final_document(title=_TITLE, text=text, sections=sections, problems=[], rag_gate_dropped=[])
    assert out["passed"] is False
    assert out["structure_passed"] is False
    assert "Related Work" in list(out.get("unexpected_sections") or [])
    assert bool(out.get("section_order_passed")) is False

def test_validate_final_document_fails_on_empty_required_sections() -> None:
    text = (
        "# Title\n\n"
        "## Introduction\n\n"
        "Intro body.\n\n"
        "## Data Source and Retrieval Strategy\n\n"
        "\n\n"
        "## Conclusion\n\n"
        "Conclusion body."
    )
    out = validate_final_document(
        title="Title",
        text=text,
        sections=["Introduction", "Data Source and Retrieval Strategy", "Conclusion"],
        problems=[],
        rag_gate_dropped=[],
    )
    assert out["passed"] is False
    assert out["structure_passed"] is False
    assert "Data Source and Retrieval Strategy" in list(out.get("empty_sections") or [])
