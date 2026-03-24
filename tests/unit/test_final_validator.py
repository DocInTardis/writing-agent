from __future__ import annotations

from writing_agent.v2.final_validator import validate_final_document


def test_validate_final_document_passes_when_all_gates_true():
    text = "# 标题\n\n## 引言\n\n内容A。\n\n## 结论\n\n内容B。"
    out = validate_final_document(
        title="测试",
        text=text,
        sections=["引言", "结论"],
        problems=[],
        rag_gate_dropped=[],
    )
    assert out["passed"] is True
    assert out["structure_passed"] is True
    assert out["semantic_passed"] is True
    assert out["meta_residue_zero"] is True
    assert out["entity_aligned"] is True


def test_validate_final_document_fails_on_entity_mismatch():
    text = "# 标题\n\n## 引言\n\n内容A。\n\n## 结论\n\n内容B。"
    out = validate_final_document(
        title="区块链研究",
        text=text,
        sections=["引言", "结论"],
        problems=[],
        rag_gate_dropped=[{"reason": "rag_entity_mismatch"}],
    )
    assert out["passed"] is False
    assert out["entity_aligned"] is False


def test_validate_final_document_fails_when_repeat_sentence_ratio_exceeds_threshold(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_MAX_REPEAT_SENTENCE_RATIO", "0.10")
    repeated = "研究方法包含数据采集与指标构建。"
    text = "# 标题\n\n## 引言\n\n" + "\n\n".join([repeated] * 12) + "\n\n## 结论\n\n" + "\n\n".join([repeated] * 8)
    out = validate_final_document(
        title="测试",
        text=text,
        sections=["引言", "结论"],
        problems=[],
        rag_gate_dropped=[],
    )
    assert out["passed"] is False
    assert out["semantic_passed"] is False
    assert float(out["repeat_sentence_ratio"]) > 0.10


def test_validate_final_document_fails_when_instruction_mirroring_exceeds_threshold(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_MAX_INSTRUCTION_MIRROR_RATIO", "0.05")
    text = (
        "# 标题\n\n## 引言\n\n"
        "引言聚焦交代研究背景，帮助读者理解为什么要做。\n\n"
        "## 结论\n\n"
        "结论聚焦总结主要发现，建议补充可复核性说明。"
    )
    out = validate_final_document(
        title="测试",
        text=text,
        sections=["引言", "结论"],
        problems=[],
        rag_gate_dropped=[],
    )
    assert out["passed"] is False
    assert out["semantic_passed"] is False
    assert float(out["instruction_mirroring_ratio"]) > 0.05


def test_validate_final_document_uses_repeat_threshold_default_005(monkeypatch):
    monkeypatch.delenv("WRITING_AGENT_MAX_REPEAT_SENTENCE_RATIO", raising=False)
    text = "# 标题\n\n## 引言\n\n内容A。\n\n## 结论\n\n内容B。"
    out = validate_final_document(
        title="测试",
        text=text,
        sections=["引言", "结论"],
        problems=[],
        rag_gate_dropped=[],
    )
    assert float(out["max_repeat_sentence_ratio"]) == 0.05


def test_validate_final_document_fails_when_template_padding_ratio_exceeds_threshold(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_MAX_TEMPLATE_PADDING_RATIO", "0.03")
    text = (
        "# 标题\n\n## 引言\n\n"
        "引言先界定研究目标与对象，再说明核心问题的形成机制。\n\n"
        "引言给出方法路径、输入输出与关键参数设置，并解释各环节对研究结论的具体贡献。\n\n"
        "## 结论\n\n"
        "结论基于数据来源、评价指标与结果解释构建证据链，避免空泛表述并提升可核查性。"
    )
    out = validate_final_document(
        title="测试",
        text=text,
        sections=["引言", "结论"],
        problems=[],
        rag_gate_dropped=[],
    )
    assert out["passed"] is False
    assert out["semantic_passed"] is False
    assert float(out["template_padding_ratio"]) > float(out["max_template_padding_ratio"])


def test_validate_final_document_fails_when_low_information_ratio_exceeds_threshold(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_MAX_LOW_INFORMATION_RATIO", "0.10")
    text = (
        "# 标题\n\n## 引言\n\n"
        "综上所述，我们可以看到该研究具有重要意义。\n\n"
        "本研究旨在通过路径优化来达到提升治理能力的目标。\n\n"
        "## 结论\n\n"
        "由于现实条件复杂的原因，因此后续研究仍需继续推进。"
    )
    out = validate_final_document(
        title="测试",
        text=text,
        sections=["引言", "结论"],
        problems=[],
        rag_gate_dropped=[],
    )
    assert out["passed"] is False
    assert out["semantic_passed"] is False
    assert float(out["low_information_ratio"]) > float(out["max_low_information_ratio"])
    assert out["low_information_hits"]


def test_validate_final_document_fails_when_title_body_alignment_too_low(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_TITLE_BODY_ALIGN_MIN_SCORE", "0.4")
    text = "# 标题\n\n## 引言\n\n本文讨论绿色金融与区域创新。\n\n## 结论\n\n结论同样围绕绿色金融展开。"
    out = validate_final_document(
        title="区块链农村治理",
        text=text,
        sections=["引言", "结论"],
        problems=[],
        rag_gate_dropped=[],
    )
    assert out["passed"] is False
    assert float(out["title_body_alignment_score"]) < float(out["min_title_body_alignment_score"])

def test_validate_final_document_fails_when_section_catalog_style_text_leaks_into_body():
    text = (
        "# \u6807\u9898\n\n## \u5f15\u8a00\n\n"
        "\u5f15\u8a00\u4ea4\u4ee3\u7814\u7a76\u6216\u9879\u76ee\u80cc\u666f\u3001\u95ee\u9898\u8d77\u70b9\u4e0e\u62a5\u544a\u8303\u56f4\uff0c\u5e2e\u52a9\u8bfb\u8005\u7406\u89e3\u4e3a\u4ec0\u4e48\u8981\u505a\u3002\n\n"
        "\u5f15\u8a00\u7ed9\u51fa\u65b9\u6cd5\u6d41\u7a0b\u4e0e\u5173\u952e\u53c2\u6570\u8bbe\u7f6e\uff0c\u5c55\u793a\u7814\u7a76\u8def\u5f84\u7684\u53ef\u590d\u73b0\u6027\u3002\n\n"
        "## \u7ed3\u8bba\n\n"
        "\u7ed3\u8bba\u5bf9\u4e3b\u8981\u7ed3\u679c\u8fdb\u884c\u91cf\u5316\u89e3\u91ca\uff0c\u5e76\u8bf4\u660e\u53ef\u80fd\u7684\u8bef\u5dee\u6765\u6e90\u3002"
    )
    out = validate_final_document(
        title="\u6d4b\u8bd5",
        text=text,
        sections=["\u5f15\u8a00", "\u7ed3\u8bba"],
        problems=[],
        rag_gate_dropped=[],
    )
    assert out["passed"] is False
    assert out["semantic_passed"] is False
    assert out["meta_hits"]



def test_validate_final_document_passes_when_figure_gate_accepts_strong_figure():
    text = (
        "# ??\n\n## ??\n\n"
        "??????????????\n\n"
        '[[FIGURE:{"type":"bar","caption":"??????","data":{"labels":["?","?","?"],"values":[1,2,3]}}]]\n\n'
        "## ??\n\n"
        "??????????????"
    )
    out = validate_final_document(
        title="\u6807\u9898",
        text=text,
        sections=["??", "??"],
        problems=[],
        rag_gate_dropped=[],
    )
    assert out["passed"] is True
    assert out["figure_gate_passed"] is True
    assert int(out["figure_count"]) == 1
    assert float(out["figure_score_avg"]) >= float(out["min_figure_avg_score"])



def test_validate_final_document_fails_when_figure_gate_detects_low_quality_figure():
    text = (
        "# ??\n\n## ??\n\n"
        "??????????????\n\n"
        '[[FIGURE:{"type":"unknown","caption":"? 1","data":{}}]]\n\n'
        "## ??\n\n"
        "??????????????"
    )
    out = validate_final_document(
        title="\u6807\u9898",
        text=text,
        sections=["??", "??"],
        problems=[],
        rag_gate_dropped=[],
    )
    assert out["passed"] is False
    assert out["figure_gate_passed"] is False
    assert int(out["figure_drop_count"]) >= 1
    assert out["weak_figure_items"]



def test_validate_final_document_fails_when_reference_count_below_min(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_ENFORCE_REFERENCE_MIN", "1")
    monkeypatch.setenv("WRITING_AGENT_MIN_REFERENCE_ITEMS", "8")
    text = (
        "# \u6807\u9898\n\n## \u5f15\u8a00\n\n\u5185\u5bb9\u3002\n\n## \u53c2\u8003\u6587\u732e\n\n"
        "[1] A. Ref. 2024.\n"
        "[2] B. Ref. 2024.\n"
        "[3] C. Ref. 2024.\n"
        "[4] D. Ref. 2024.\n"
        "[5] E. Ref. 2024.\n"
        "[6] F. Ref. 2024.\n"
        "[7] G. Ref. 2024."
    )
    out = validate_final_document(
        title="\u6807\u9898",
        text=text,
        sections=["\u5f15\u8a00", "\u53c2\u8003\u6587\u732e"],
        problems=[],
        rag_gate_dropped=[],
    )
    assert out["passed"] is False
    assert out["reference_gate_enabled"] is True
    assert out["reference_gate_passed"] is False
    assert int(out["reference_count"]) == 7
    assert int(out["min_reference_items"]) == 8


def test_validate_final_document_passes_when_reference_count_meets_min(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_ENFORCE_REFERENCE_MIN", "1")
    monkeypatch.setenv("WRITING_AGENT_MIN_REFERENCE_ITEMS", "8")
    text = (
        "# \u6807\u9898\n\n## \u5f15\u8a00\n\n\u5185\u5bb9\u3002\n\n## \u53c2\u8003\u6587\u732e\n\n"
        "[1] A. Ref. 2024.\n"
        "[2] B. Ref. 2024.\n"
        "[3] C. Ref. 2024.\n"
        "[4] D. Ref. 2024.\n"
        "[5] E. Ref. 2024.\n"
        "[6] F. Ref. 2024.\n"
        "[7] G. Ref. 2024.\n"
        "[8] H. Ref. 2024."
    )
    out = validate_final_document(
        title="\u6807\u9898",
        text=text,
        sections=["\u5f15\u8a00", "\u53c2\u8003\u6587\u732e"],
        problems=[],
        rag_gate_dropped=[],
    )
    assert out["reference_gate_enabled"] is True
    assert out["reference_gate_passed"] is True
    assert out["reference_quality_passed"] is True
    assert out["reference_sequence_passed"] is True
    assert int(out["reference_count"]) == 8
    assert int(out["weak_reference_count"]) == 0
    assert int(out["duplicate_reference_count"]) == 0
    assert out["passed"] is True



def test_validate_final_document_fails_on_reference_quality_issues(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_ENFORCE_REFERENCE_MIN", "1")
    monkeypatch.setenv("WRITING_AGENT_MIN_REFERENCE_ITEMS", "3")
    monkeypatch.setenv("WRITING_AGENT_REFERENCE_MAX_WEAK_RATIO", "0.0")
    text = (
        "# Title\n\n## Introduction\n\nBody.\n\n## References\n\n"
        "[1] A. Ref. 2024.\n"
        "[3] A. Ref. 2024.\n"
        "[4] TODO"
    )
    out = validate_final_document(
        title="Title",
        text=text,
        sections=["Introduction", "References"],
        problems=[],
        rag_gate_dropped=[],
    )
    assert out["passed"] is False
    assert out["reference_gate_passed"] is False
    assert out["reference_quality_passed"] is False
    assert out["reference_sequence_passed"] is False
    assert "reference_sequence_broken" in list(out.get("reference_quality_issues") or [])
    assert "reference_duplicates_detected" in list(out.get("reference_quality_issues") or [])
    assert int(out["duplicate_reference_count"]) >= 1
    assert int(out["weak_reference_count"]) >= 1
    assert out["duplicate_reference_items"]
    assert out["weak_reference_items"]


def test_validate_final_document_fails_on_reference_section_contamination(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_ENFORCE_REFERENCE_MIN", "1")
    monkeypatch.setenv("WRITING_AGENT_MIN_REFERENCE_ITEMS", "2")
    text = (
        "# Title\n\n## Introduction\n\nBody.\n\n## References\n\n"
        "[1] A. Ref. 2024.\n"
        "Unexpected explanatory note in reference section.\n"
        "[2] B. Ref. 2024."
    )
    out = validate_final_document(
        title="Title",
        text=text,
        sections=["Introduction", "References"],
        problems=[],
        rag_gate_dropped=[],
    )
    assert out["passed"] is False
    assert out["reference_gate_passed"] is False
    assert out["reference_quality_passed"] is False
    assert int(out["unformatted_reference_count"]) == 1
    assert "reference_unformatted_lines_detected" in list(out.get("reference_quality_issues") or [])
    assert out["unformatted_reference_items"]


def test_validate_final_document_ignores_rejected_entity_mismatch_once_reference_gate_passes(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_ENFORCE_REFERENCE_MIN", "1")
    monkeypatch.setenv("WRITING_AGENT_MIN_REFERENCE_ITEMS", "2")
    text = (
        "# 标题\n\n## 引言\n\n正文。\n\n## 参考文献\n\n"
        "[1] A. Ref. 2024.\n"
        "[2] B. Ref. 2024."
    )
    out = validate_final_document(
        title="标题",
        text=text,
        sections=["引言", "参考文献"],
        problems=[],
        rag_gate_dropped=[{"title": "noise", "reason": "rag_entity_mismatch"}],
    )
    assert out["reference_gate_passed"] is True
    assert out["entity_aligned"] is True
    assert out["passed"] is True



def test_validate_final_document_fails_on_unsupported_numeric_claim_without_citation(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_MAX_UNSUPPORTED_CLAIM_RATIO", "0.2")
    monkeypatch.setenv("WRITING_AGENT_MAX_UNSUPPORTED_NUMERIC_CLAIMS", "0")
    text = (
        "# \u6807\u9898\n\n## \u5f15\u8a00\n\n"
        "\u5b9e\u9a8c\u7ed3\u679c\u8868\u660e\u7cfb\u7edf\u6548\u7387\u63d0\u9ad8\u4e8630%\u3002\n\n"
        "## \u7ed3\u8bba\n\n"
        "\u7ed3\u8bba\u6bb5\u843d\u3002"
    )
    out = validate_final_document(
        title="\u6d4b\u8bd5",
        text=text,
        sections=["\u5f15\u8a00", "\u7ed3\u8bba"],
        problems=[],
        rag_gate_dropped=[],
    )
    assert out["passed"] is False
    assert out["semantic_passed"] is False
    assert int(out["unsupported_numeric_claim_count"]) == 1
    assert out["unsupported_claim_hits"]


def test_validate_final_document_allows_supported_numeric_claim_with_citation(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_MAX_UNSUPPORTED_CLAIM_RATIO", "0.2")
    monkeypatch.setenv("WRITING_AGENT_MAX_UNSUPPORTED_NUMERIC_CLAIMS", "0")
    text = (
        "# \u6807\u9898\n\n## \u5f15\u8a00\n\n"
        "\u5b9e\u9a8c\u7ed3\u679c\u8868\u660e\u7cfb\u7edf\u6548\u7387\u63d0\u9ad8\u4e8630%[1]\u3002\n\n"
        "## \u7ed3\u8bba\n\n"
        "\u7ed3\u8bba\u6bb5\u843d\u3002\n\n"
        "## \u53c2\u8003\u6587\u732e\n\n"
        "[1] A. Ref. 2024."
    )
    out = validate_final_document(
        title="\u6d4b\u8bd5",
        text=text,
        sections=["\u5f15\u8a00", "\u7ed3\u8bba", "\u53c2\u8003\u6587\u732e"],
        problems=[],
        rag_gate_dropped=[],
    )
    assert int(out["unsupported_numeric_claim_count"]) == 0
    assert float(out["unsupported_claim_ratio"]) == 0.0



def test_validate_final_document_does_not_treat_table_marker_as_unsupported_numeric_claim() -> None:
    text = (
        "# 标题\n\n## 引言\n\n"
        "本研究围绕文献检索策略展开分析。\n\n"
        '[[TABLE:{"caption":"文献数据来源与检索策略概况","columns":["维度","具体内容"],"rows":[["数据库","CNKI"],["文献类型","期刊论文、学位论文"],["时间范围","2015-2025"]]}]]\n\n'
        "## 结论\n\n"
        "结论部分总结了数据来源与检索范围。"
    )
    out = validate_final_document(
        title="标题",
        text=text,
        sections=["引言", "结论"],
        problems=[],
        rag_gate_dropped=[],
    )
    assert float(out["unsupported_claim_ratio"]) == 0.0
    assert int(out["unsupported_numeric_claim_count"]) == 0



def test_validate_final_document_ignores_configuration_range_sentence() -> None:
    text = (
        "# 标题\n\n## 引言\n\n"
        "为降低检索噪声，入库流程包含去重与分段。\n\n"
        "## 关键技术实现\n\n"
        "为降低检索噪声，分段粒度控制在 400 至 800 汉字区间，便于兼顾召回率与上下文完整性。\n\n"
        "## 结论\n\n"
        "系统实现保持了稳定的工程结构。"
    )
    out = validate_final_document(
        title="标题",
        text=text,
        sections=["引言", "关键技术实现", "结论"],
        problems=[],
        rag_gate_dropped=[],
    )
    assert float(out["unsupported_claim_ratio"]) == 0.0
    assert int(out["unsupported_numeric_claim_count"]) == 0
