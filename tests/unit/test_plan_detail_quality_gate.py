from writing_agent.v2 import graph_runner as graph_runner_module
from writing_agent.v2 import graph_runner_runtime as runtime_module


def _base_targets_for(sections: list[str]) -> dict[str, graph_runner_module.SectionTargets]:
    out: dict[str, graph_runner_module.SectionTargets] = {}
    for sec in sections:
        out[sec] = graph_runner_module.SectionTargets(
            weight=1.0,
            min_paras=3,
            min_chars=600,
            max_chars=1800,
            min_tables=0,
            min_figures=0,
        )
    return out


def test_default_plan_map_populates_key_points_and_evidence() -> None:
    sections = ["引言", "研究方法", "实验结果分析", "参考文献"]
    plan_map = graph_runner_module._default_plan_map(
        sections=sections,
        base_targets=_base_targets_for(sections),
        total_chars=8000,
    )
    assert plan_map
    non_ref = [plan_map[s] for s in sections if "参考文献" not in s]
    assert all(len(p.key_points) >= 2 for p in non_ref)
    assert sum(len(p.evidence_queries or []) for p in non_ref) >= 2
    method_plan = plan_map["研究方法"]
    experiment_plan = plan_map["实验结果分析"]
    assert bool(method_plan.figures or method_plan.tables)
    assert bool(experiment_plan.figures or experiment_plan.tables)


def test_validate_plan_detail_rejects_empty_detail() -> None:
    sections = ["引言", "研究方法", "实验结果分析", "参考文献"]
    empty_plan = {
        "引言": graph_runner_module.PlanSection(
            title="引言",
            target_chars=1000,
            min_chars=600,
            max_chars=1400,
            min_tables=0,
            min_figures=0,
            key_points=[],
            figures=[],
            tables=[],
            evidence_queries=[],
        ),
        "研究方法": graph_runner_module.PlanSection(
            title="研究方法",
            target_chars=1600,
            min_chars=800,
            max_chars=2200,
            min_tables=0,
            min_figures=0,
            key_points=[],
            figures=[],
            tables=[],
            evidence_queries=[],
        ),
        "实验结果分析": graph_runner_module.PlanSection(
            title="实验结果分析",
            target_chars=1800,
            min_chars=900,
            max_chars=2400,
            min_tables=0,
            min_figures=0,
            key_points=[],
            figures=[],
            tables=[],
            evidence_queries=[],
        ),
        "参考文献": graph_runner_module.PlanSection(
            title="参考文献",
            target_chars=600,
            min_chars=300,
            max_chars=900,
            min_tables=0,
            min_figures=0,
            key_points=[],
            figures=[],
            tables=[],
            evidence_queries=[],
        ),
    }
    ok, reasons, meta = runtime_module._validate_plan_detail(
        instruction="请生成中文学术论文",
        sections=sections,
        plan_map=empty_plan,
    )
    assert ok is False
    assert any(str(r).startswith("plan_detail_key_points_insufficient") for r in reasons)
    assert "plan_detail_evidence_queries_insufficient" in reasons
    assert any(str(r).startswith("plan_detail_method_or_experiment_missing_media") for r in reasons)
    assert isinstance(meta, dict)

