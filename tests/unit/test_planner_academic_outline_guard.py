from writing_agent.v2 import graph_runner as graph_runner_module
from writing_agent.v2 import graph_runner_runtime as runtime_module
from writing_agent.v2.prompts import PromptBuilder


def test_default_outline_returns_weekly_only_for_weekly_intent() -> None:
    weekly = graph_runner_module._default_outline_from_instruction("请生成本周项目周报")
    assert weekly == ["本周工作", "问题与风险", "下周计划", "需协助事项"]

    academic = graph_runner_module._default_outline_from_instruction("请生成一篇中文学术论文")
    assert academic == []


def test_fast_plan_sections_do_not_leak_weekly_template_into_academic() -> None:
    sections = runtime_module._fast_plan_sections_for_instruction("写一篇关于多智能体系统的中文学术论文")
    assert "本周工作" not in sections
    assert "下周计划" not in sections
    assert "摘要" in sections
    assert "参考文献" in sections


def test_fast_plan_sections_keep_weekly_for_weekly_intent() -> None:
    sections = runtime_module._fast_plan_sections_for_instruction("请给我一份周报")
    assert sections == ["本周工作", "问题与风险", "下周计划", "需协助事项"]


def test_academic_planner_prompt_uses_academic_few_shot() -> None:
    context = PromptBuilder.build_route_context(
        instruction="请写一篇中文学术论文，主题是图神经网络在交通预测中的应用",
        doc_type="academic",
    )
    system, _ = PromptBuilder.build_planner_prompt(
        title="图神经网络在交通预测中的应用",
        total_chars=8000,
        sections=["摘要", "关键词", "引言", "方法", "实验", "结论", "参考文献"],
        instruction=context.instruction,
        context=context,
    )

    assert "摘要" in system
    assert "关键词" in system
    assert "本周工作" not in system
    assert "This Week Work" not in system
