from __future__ import annotations

from writing_agent.v2 import graph_section_draft_domain as draft_domain


def test_build_continue_prompt_contains_dimension_hints_and_non_redundant_expand_rule():
    _, user = draft_domain._build_continue_prompt(
        title="测试标题",
        section="讨论",
        parent_section="",
        instruction="写一篇论文",
        analysis_summary="主题是区块链在农村社会化服务中的应用",
        evidence_summary="",
        allowed_urls=[],
        plan_hint='{"target_chars":900}',
        dimension_hints=["政策影响", "区域差异", "风险控制"],
        txt="已有一段正文。",
        section_id="H2::讨论",
        min_paras=3,
        missing_chars=420,
    )
    assert "<dimension_hints>" in user
    assert "政策影响" in user
    assert "regional heterogeneity" in user
    assert "add NEW information" in user

