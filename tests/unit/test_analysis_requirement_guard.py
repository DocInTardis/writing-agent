from writing_agent.v2 import graph_runner as runner


def test_normalize_analysis_extracts_canonical_must_include_sections():
    analysis = {
        "topic": "区块链+农村社会化服务",
        "doc_type": "学术论文初稿",
        "keywords": ["区块链", "农村社会化服务"],
        "must_include": [
            "结构包含并按顺序出现：摘要、关键词、引言、相关研究、研究方法、系统设计与实现、实验设计与结果、讨论、结论、参考文献",
        ],
        "constraints": ["标题必须完全一致，不得改写"],
    }
    out = runner._normalize_analysis_for_generation(analysis, "请写一篇中文学术论文")
    must_include = list(out.get("must_include") or [])
    assert "摘要" in must_include
    assert "关键词" in must_include
    assert "研究方法" in must_include
    assert "结论" in must_include
    assert all("结构包含并按顺序出现" not in x for x in must_include)


def test_analysis_guard_does_not_fail_keyword_title_match_by_default():
    analysis = {
        "doc_type": "学术论文",
        "must_include": ["引言", "结论", "参考文献"],
        "keywords": ["区块链", "农村社会化服务"],
    }
    ok, reasons, meta = runner._analysis_correctness_guard(
        analysis=analysis,
        instruction="请写一篇中文学术论文",
        sections=["引言", "相关研究", "研究方法", "结论", "参考文献"],
        section_title=lambda x: x,
        is_reference_section=lambda x: str(x).strip() == "参考文献",
    )
    assert ok is True
    assert "keyword_domain_mismatch" not in reasons
    assert int(meta.get("keyword_title_match_count") or 0) == 0


def test_analysis_guard_accepts_alias_like_section_titles():
    analysis = {
        "doc_type": "学术论文",
        "must_include": ["摘要", "关键词", "引言", "相关研究", "研究方法", "系统设计与实现", "实验设计与结果", "结论", "参考文献"],
        "keywords": ["区块链"],
    }
    sections = [
        "摘要",
        "关键词",
        "研究背景与引言",
        "相关研究综述",
        "研究方法与数据来源",
        "系统架构设计与实现细节",
        "实验结果与分析",
        "结论与展望",
        "参考文献",
    ]
    ok, reasons, meta = runner._analysis_correctness_guard(
        analysis=analysis,
        instruction="请写一篇中文学术论文",
        sections=sections,
        section_title=lambda x: x,
        is_reference_section=lambda x: "参考文献" in str(x),
    )
    assert ok is True
    assert "must_include_missing" not in reasons
    assert not list(meta.get("must_include_missing") or [])


def test_sanitize_planned_sections_handles_dict_and_dict_like_items():
    sections = [
        {"title": "研究背景"},
        {"name": "文献综述"},
        "{'title': '结果与分析', 'target_chars': 1000}",
        "参考文献",
    ]
    out = runner._sanitize_planned_sections(sections)  # type: ignore[arg-type]
    assert "研究背景" in out
    assert "文献综述" in out
    assert "结果与分析" in out
    assert out[-1] == "参考文献"


def test_merge_required_sections_from_analysis_injects_missing_required_titles():
    analysis = {
        "doc_type": "学术论文",
        "must_include": ["摘要", "关键词", "引言", "相关研究", "研究方法", "结论", "参考文献"],
        "constraints": [],
    }
    sections = ["研究背景", "文献综述", "技术路线", "结论与展望", "参考文献"]
    merged = runner._merge_required_sections_from_analysis(
        sections=sections,
        analysis=analysis,
        instruction="请写一篇中文学术论文",
    )
    canonical = [runner._canonicalize_section_name(runner._section_title(x) or x) for x in merged]
    assert "摘要" in canonical
    assert "关键词" in canonical
    assert "引言" in canonical
    assert "相关研究" in canonical
    assert "研究方法" in canonical
    assert "结论" in canonical
    assert "参考文献" in canonical


def test_merge_required_sections_from_analysis_keeps_academic_canonical_order():
    analysis = {
        "doc_type": "学术论文",
        "must_include": ["参考文献", "结论", "实验设计与结果", "引言", "摘要", "关键词", "研究方法"],
        "constraints": [],
    }
    sections = ["结论", "参考文献", "引言"]
    merged = runner._merge_required_sections_from_analysis(
        sections=sections,
        analysis=analysis,
        instruction="请写一篇中文学术论文，结构要规范",
    )
    titles = [runner._canonicalize_section_name(runner._section_title(x) or x) for x in merged]
    assert titles[0] == "摘要"
    assert titles[1] == "关键词"
    assert titles[-1] == "参考文献"
    assert "引言" in titles
    assert "研究方法" in titles


def test_default_outline_from_instruction_uses_bibliometric_spine_for_citespace_intent():
    instruction = "请写一篇基于CiteSpace的文献计量可视化分析论文，主题为乡村治理数字化"
    outline = runner._default_outline_from_instruction(instruction)
    assert outline == runner._bibliometric_section_spine()


def test_merge_required_sections_from_analysis_prefers_bibliometric_canonical_spine():
    analysis = {
        "doc_type": "学术论文",
        "must_include": ["摘要", "关键词", "引言", "系统设计与实现", "实验设计与结果", "结论", "参考文献"],
        "constraints": [],
    }
    sections = ["引言", "系统设计与实现", "实验设计与结果", "结论", "参考文献"]
    merged = runner._merge_required_sections_from_analysis(
        sections=sections,
        analysis=analysis,
        instruction="请基于CiteSpace完成数字乡村治理的文献计量可视化分析论文",
    )
    titles = [runner._canonicalize_section_name(runner._section_title(x) or x) for x in merged]
    assert titles == runner._bibliometric_section_spine()


def test_analysis_correctness_guard_flags_bibliometric_structure_mismatch():
    analysis = {
        "doc_type": "学术论文",
        "must_include": ["摘要", "关键词", "引言", "结论", "参考文献"],
    }
    sections = ["摘要", "关键词", "引言", "系统设计与实现", "实验设计与结果", "结论", "参考文献"]
    ok, reasons, _meta = runner._analysis_correctness_guard(
        analysis=analysis,
        instruction="请写基于CiteSpace的文献计量分析",
        sections=sections,
        section_title=lambda x: x,
        is_reference_section=lambda x: "参考文献" in str(x),
    )
    assert ok is False
    assert "bibliometric_structure_mismatch" in reasons


def test_analysis_correctness_guard_ignores_drifted_must_include_in_bibliometric_mode():
    analysis = {
        "doc_type": "学术论文",
        "must_include": ["摘要", "关键词", "引言", "相关研究", "研究方法", "结论", "参考文献"],
    }
    sections = runner._bibliometric_section_spine()
    ok, reasons, meta = runner._analysis_correctness_guard(
        analysis=analysis,
        instruction="请写基于CiteSpace的文献计量可视化分析论文",
        sections=sections,
        section_title=lambda x: x,
        is_reference_section=lambda x: "参考文献" in str(x),
    )
    assert ok is True
    assert "must_include_missing" not in reasons
    assert not list(meta.get("must_include_missing") or [])
