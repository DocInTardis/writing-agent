from __future__ import annotations

import json

from writing_agent.v2 import graph_reference_domain
from writing_agent.v2 import graph_runner as graph_runner_module
from writing_agent.v2 import graph_runner_runtime as runtime_module
from writing_agent.v2.prompts import PromptBuilder


def _base_targets_for(sections: list[str]) -> dict[str, graph_runner_module.SectionTargets]:
    return {
        sec: graph_runner_module.SectionTargets(
            weight=1.0,
            min_paras=3,
            min_chars=600,
            max_chars=1800,
            min_tables=0,
            min_figures=0,
        )
        for sec in sections
    }


def test_synthesize_analysis_prefers_clean_title_and_strips_schema_tokens() -> None:
    instruction = (
        "请围绕《区块链赋能农村社会化服务的机制与路径》"
        "生成中文学术论文正文，需要 figure caption kind data json 这些字段说明，"
        "并包含摘要、引言和参考文献。"
    )
    analysis = runtime_module._synthesize_analysis_from_requirements(
        instruction=instruction,
        required_outline=[(2, "摘要"), (2, "引言"), (2, "参考文献")],
        required_h2=["摘要", "引言", "参考文献"],
    )
    assert analysis.get("topic") == "区块链赋能农村社会化服务的机制与路径"
    keywords = [str(x) for x in (analysis.get("keywords") or [])]
    assert keywords
    banned = {"figure", "caption", "kind", "data", "json", "doc_type", "topic"}
    assert banned.isdisjoint(set(keywords))
    must_include = analysis.get("must_include") or []
    assert "摘要" in must_include
    assert "引言" in must_include
    assert "参考文献" in must_include


def test_default_plan_map_uses_soft_visual_suggestions_without_hard_figure_minimum() -> None:
    sections = [
        "引言",
        "系统总体架构",
        "实验结果分析",
        "参考文献",
    ]
    plan_map = graph_runner_module._default_plan_map(
        sections=sections,
        base_targets=_base_targets_for(sections),
        total_chars=7000,
    )
    intro_plan = plan_map["引言"]
    arch_plan = plan_map["系统总体架构"]
    result_plan = plan_map["实验结果分析"]
    assert intro_plan.figures == []
    assert arch_plan.min_figures == 0
    assert any(str(item.get("type") or "") == "architecture" for item in (arch_plan.figures or []))
    assert any(str(item.get("caption") or "") for item in (arch_plan.figures or []))
    assert bool(result_plan.tables)


def test_writer_prompt_adds_soft_visual_preference_only_for_visual_sections() -> None:
    visual_hint = json.dumps(
        {
            "section_title": "系统总体架构",
            "figures": [{"type": "architecture", "caption": "系统总体架构图"}],
        },
        ensure_ascii=False,
    )
    _system, visual_user = PromptBuilder.build_writer_prompt(
        section_title="系统总体架构",
        plan_hint=visual_hint,
        doc_title="Doc",
        analysis_summary="写作架构章节",
        section_id="H2::arch",
    )
    assert "prefer one valid figure block" in visual_user
    assert "omit the figure instead of fabricating" in visual_user

    _system, intro_user = PromptBuilder.build_writer_prompt(
        section_title="引言",
        plan_hint=json.dumps({"section_title": "引言", "key_points": ["研究背景"]}, ensure_ascii=False),
        doc_title="Doc",
        analysis_summary="写作引言章节",
        section_id="H2::intro",
    )
    assert "prefer one valid figure block" not in intro_user



def test_visual_value_score_prefers_architecture_over_intro() -> None:
    arch_score = graph_reference_domain.visual_value_score_for_section("System Architecture", section_type="method")
    intro_score = graph_reference_domain.visual_value_score_for_section("Introduction", section_type="intro")
    assert arch_score >= 0.8
    assert intro_score < arch_score


def test_format_plan_hint_includes_visual_priority_for_visual_sections() -> None:
    plan = graph_runner_module.PlanSection(
        title="System Architecture",
        target_chars=1200,
        min_chars=800,
        max_chars=1600,
        min_tables=0,
        min_figures=0,
        key_points=["module layering", "interface relation"],
        figures=[{"type": "architecture", "caption": "System Architecture Diagram"}],
        tables=[],
        evidence_queries=["system architecture research progress"],
    )
    payload = json.loads(graph_runner_module._format_plan_hint(plan))
    assert float(payload.get("visual_priority") or 0.0) >= 0.8
    assert payload.get("figures")



def test_normalize_analysis_prefers_title_hint_on_meta_polluted_topic() -> None:
    instruction = (
        "请围绕《区块链赋能农村社会化服务的机制与路径》"
        "生成中文学术论文，不要输出 topic/doc_type/figure/caption/kind/data/json 等元指令字段。"
    )
    analysis = {
        "topic": "topic: 区块链赋能农村社会化服务的机制与路径\ndoc_type: academic\nkey points: evidence chain and workflow",
        "doc_type": "doc_type: academic",
        "keywords": [
            "topic",
            "doc_type",
            "json",
            "figure",
            "caption",
            "kind",
            "data",
            "区块链",
            "农村社会化服务",
        ],
        "must_include": [
            "topic: ignored",
            "引言",
            "参考文献",
        ],
        "constraints": ["keywords: ignored"],
    }

    normalized = graph_runner_module._normalize_analysis_for_generation(analysis, instruction)

    assert normalized.get("topic") == "区块链赋能农村社会化服务的机制与路径"
    assert normalized.get("doc_type") == "academic"
    keywords = {str(x) for x in (normalized.get("keywords") or [])}
    assert keywords
    assert {"topic", "doc_type", "json", "figure", "caption", "kind", "data"}.isdisjoint(keywords)
    must_include = list(normalized.get("must_include") or [])
    assert "引言" in must_include
    assert "参考文献" in must_include
