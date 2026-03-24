from __future__ import annotations

from writing_agent.v2 import graph_runner_runtime as runtime_module


def test_should_synthesize_analysis_when_outline_fixed_and_no_current_text():
    assert runtime_module._should_synthesize_analysis(
        instruction="请写一篇中文学术论文，主题是区块链赋能农村社会化服务。",
        current_text="",
        required_outline=[(2, "摘要"), (2, "引言"), (2, "参考文献")],
        required_h2=None,
    ) is True


def test_synthesize_analysis_keeps_required_sections_and_academic_doc_type():
    analysis = runtime_module._synthesize_analysis_from_requirements(
        instruction="请写一篇中文学术论文，主题是区块链赋能农村社会化服务。",
        required_outline=[(2, "摘要"), (2, "引言"), (2, "参考文献")],
        required_h2=["摘要", "引言", "参考文献"],
    )
    assert str(analysis.get("doc_type") or "") == "academic"
    must_include = analysis.get("must_include") or []
    assert "摘要" in must_include
    assert "引言" in must_include
    assert "参考文献" in must_include
