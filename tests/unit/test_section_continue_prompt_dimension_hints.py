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
    assert "<originality_guidance>" in user
    assert "政策影响" in user
    assert "regional heterogeneity" in user
    assert "add NEW information" in user
    assert "Extend the draft by opening a new analytical angle" in user


def test_build_continue_prompt_adds_section_specific_originality_guidance():
    _, method_user = draft_domain._build_continue_prompt(
        title="测试标题",
        section="研究方法",
        parent_section="",
        instruction="写一篇论文",
        analysis_summary="主题是区块链在农村社会化服务中的应用",
        evidence_summary="包含样本边界和变量定义",
        allowed_urls=[],
        plan_hint='{"target_chars":900}',
        dimension_hints=[],
        txt="已有一段正文。",
        section_id="H2::研究方法",
        min_paras=3,
        missing_chars=420,
    )
    assert "For method sections, extend with operational details such as sample boundary, variable definition, workflow step, or parameter choice." in method_user

    _, result_user = draft_domain._build_continue_prompt(
        title="测试标题",
        section="结果与分析",
        parent_section="",
        instruction="写一篇论文",
        analysis_summary="主题是区块链在农村社会化服务中的应用",
        evidence_summary="包含比较结果和异常现象",
        allowed_urls=[],
        plan_hint='{"target_chars":900}',
        dimension_hints=[],
        txt="已有一段正文。",
        section_id="H2::结果与分析",
        min_paras=3,
        missing_chars=420,
    )
    assert "For results or discussion sections, extend with a new comparison, mechanism, anomaly, or boundary condition rather than a generic summary." in result_user
