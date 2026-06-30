from writing_agent.v2.graph_section_draft_guard_domain import _hits_semantic_sampling_guard


def test_semantic_sampling_guard_catches_meta_like_opening_without_regex_failure() -> None:
    text = "本节将说明研究边界、关键变量与验收规则，并补充后续分析所需约束。"

    hits = _hits_semantic_sampling_guard(text=text, section="引言")

    assert hits
    assert "本节将说明研究边界" in hits[0]


def test_semantic_sampling_guard_keeps_reader_facing_section_text() -> None:
    text = (
        "村级服务日志显示，补贴申报窗口会显著推高需求峰值，"
        "而跨部门复核任务主要拖慢的是结案时长而非受理速度。"
    )

    hits = _hits_semantic_sampling_guard(text=text, section="引言")

    assert hits == []
