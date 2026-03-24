from __future__ import annotations

from writing_agent.v2 import graph_reference_domain as reference_domain
from writing_agent.v2 import graph_runner_post_domain as post_domain
from writing_agent.v2 import graph_section_draft_domain as section_domain
from writing_agent.v2 import graph_text_sanitize_domain as sanitize_domain


def test_is_engineering_instruction_does_not_misclassify_academic_prompt() -> None:
    academic = "请生成一篇学术论文，包含摘要、关键词、引言和参考文献。"
    assert post_domain._is_engineering_instruction(academic) is False

    engineering = "请输出系统架构设计文档与API文档，包含部署手册。"
    assert post_domain._is_engineering_instruction(engineering) is True


def test_ensure_media_markers_only_sanitizes_existing_media() -> None:
    raw = '\u6b63\u6587\u6bb5\u843d\u3002\n\n[[FIGURE:{"caption":"\u65e0\u6548\u56fe"}]]'
    out = section_domain.ensure_media_markers(
        raw,
        section_title="\u7814\u7a76\u65b9\u6cd5",
        min_tables=1,
        min_figures=1,
        is_reference_section=lambda _x: False,
    )
    assert "\u6b63\u6587\u6bb5\u843d" in out
    assert "[[FIGURE:" not in out
    assert "[[TABLE:" not in out


def test_postprocess_section_does_not_add_generic_filler_when_short() -> None:
    out = section_domain.postprocess_section(
        "\u5f15\u8a00",
        "\u4fdd\u7559\u8fd9\u4e00\u6bb5\u3002",
        min_paras=3,
        min_chars=800,
        max_chars=0,
        min_tables=1,
        min_figures=1,
        section_title=lambda x: str(x),
        is_reference_section=lambda _x: False,
        format_references=lambda x: x,
        strip_reference_like_lines=lambda x: x,
        strip_inline_headings=lambda x, _s: x,
        generic_fill_paragraph=lambda _s, _i: "\u6a21\u677f\u6bb5\u843d",
        sanitize_output_text=lambda x: sanitize_domain.sanitize_output_text(
            x,
            meta_phrases=[],
            has_cjk=lambda s: any("\u4e00" <= ch <= "\u9fff" for ch in str(s)),
            is_mostly_ascii_line=lambda _s: False,
            banned_phrases=[],
        ),
        ensure_media_markers=lambda txt, _sec, _t, _f: txt,
    )
    assert "\u4fdd\u7559\u8fd9\u4e00\u6bb5" in out
    assert "\u6a21\u677f\u6bb5\u843d" not in out
    assert "[[TABLE:" not in out
    assert "[[FIGURE:" not in out

def test_postprocess_section_drops_prompt_residue_paragraphs() -> None:
    raw = (
        "topic: 区块链+农村社会化服务\n\n"
        "应给出可测量的验收规则，并说明假设前提与适用限制。\n\n"
        "本节需明确研究范围、约束条件与可检验的阶段性产出。\n\n"
        "该研究围绕农村服务流程中的信息不对称问题展开，核心目标是提升服务透明度与协同效率。"
    )
    out = section_domain.postprocess_section(
        "引言",
        raw,
        min_paras=1,
        min_chars=0,
        max_chars=0,
        min_tables=0,
        min_figures=0,
        section_title=lambda x: str(x),
        is_reference_section=lambda _x: False,
        format_references=lambda x: x,
        strip_reference_like_lines=lambda x: x,
        strip_inline_headings=lambda x, _s: x,
        generic_fill_paragraph=lambda _s, _i: "",
        sanitize_output_text=lambda x: sanitize_domain.sanitize_output_text(
            x,
            meta_phrases=[],
            has_cjk=lambda s: any("\u4e00" <= ch <= "\u9fff" for ch in str(s)),
            is_mostly_ascii_line=lambda _s: False,
            banned_phrases=[],
        ),
        ensure_media_markers=lambda txt, _sec, _t, _f: txt,
    )
    assert "topic:" not in out
    assert "应给出可测量的验收规则" not in out
    assert "本节需明确研究范围" not in out
    assert "信息不对称问题展开" in out


def test_reference_filter_prefers_topic_matched_sources() -> None:
    rows = [
        {
            "title": "Blockchain-enabled rural public service governance: evidence from village pilots",
            "url": "https://example.org/a",
            "source": "journal",
        },
        {
            "title": "EditEval: Evaluating AI text editing systems",
            "url": "https://example.org/b",
            "source": "conference",
        },
        {
            "title": "Promptware Engineering: Software Engineering for LLM Prompt Development",
            "url": "https://example.org/c",
            "source": "arxiv",
        },
    ]
    filtered = reference_domain.filter_sources_by_topic(rows, query="区块链 农村社会化服务", min_score=1)
    assert len(filtered) == 1
    assert "Blockchain-enabled rural public service governance" in filtered[0]["title"]


def test_reference_filter_returns_empty_when_no_topic_match() -> None:
    rows = [
        {
            "title": "Promptware Engineering: Software Engineering for LLM Prompt Development",
            "url": "https://example.org/a",
            "source": "arxiv",
        },
        {
            "title": "EditEval: Evaluating AI text editing systems",
            "url": "https://example.org/b",
            "source": "conference",
        },
    ]
    filtered = reference_domain.filter_sources_by_topic(rows, query="区块链 农村社会化服务", min_score=1)
    assert filtered == []


def test_sanitize_output_text_drops_instructional_residue_lines() -> None:
    raw = (
        "摘要应覆盖研究目标、范围边界、关键约束与可量化产出，并给出核验方式。\n"
        "在引言中，建议统一术语口径、边界定义与量化指标，支撑后续章节分析。\n"
        "需突出实施策略、边界场景与风险缓释机制，保证方案具备工程可操作性。\n"
        "附录：相关文献列表感谢中国知网提供的数据支持。\n"
        "Based on the available sources provided, none appear to be directly related.\n"
        "本研究围绕农村社会化服务中的协同效率问题展开，提出可复核的分析路径。"
    )
    out = sanitize_domain.sanitize_output_text(
        raw,
        meta_phrases=[],
        has_cjk=lambda s: any("\u4e00" <= ch <= "\u9fff" for ch in str(s)),
        is_mostly_ascii_line=lambda _s: False,
        banned_phrases=[],
    )
    assert "摘要应覆盖研究目标" not in out
    assert "建议统一术语口径" not in out
    assert "需突出实施策略" not in out
    assert "附录：相关文献列表" not in out
    assert "Based on the available sources provided" not in out
    assert "本研究围绕农村社会化服务中的协同效率问题展开" in out


def test_sanitize_output_text_drops_self_evaluative_topup_lines() -> None:
    raw = (
        "本研究围绕农村社会化服务中的协同效率问题展开，并给出可复核的指标体系。\n"
        "此外，围绕“论证路径与证据支撑”，进一步补充了样本边界与变量控制方法。\n"
        "同时围绕本节的关键问题，补充方法路径、输入输出与关键参数设置。"
    )
    out = sanitize_domain.sanitize_output_text(
        raw,
        meta_phrases=[],
        has_cjk=lambda s: any("\u4e00" <= ch <= "\u9fff" for ch in str(s)),
        is_mostly_ascii_line=lambda _s: False,
        banned_phrases=[],
    )
    assert "本研究围绕农村社会化服务中的协同效率问题展开" in out
    assert "进一步补充了样本边界与变量控制方法" not in out
    assert "补充方法路径、输入输出与关键参数设置" not in out


def test_sanitize_output_text_drops_template_padding_lines() -> None:
    raw = (
        "引言先界定研究目标与对象，再说明核心问题的形成机制，为后续分析建立统一语义基线。\n"
        "引言给出方法路径、输入输出与关键参数设置，并解释各环节对研究结论的具体贡献。\n"
        "引言基于数据来源、评价指标与结果解释构建证据链，避免空泛表述并提升可核查性。\n"
        "这是一段真实分析结论，指出不同区域样本在治理协同效率上存在显著差异。"
    )
    out = sanitize_domain.sanitize_output_text(
        raw,
        meta_phrases=[],
        has_cjk=lambda s: any("\u4e00" <= ch <= "\u9fff" for ch in str(s)),
        is_mostly_ascii_line=lambda _s: False,
        banned_phrases=[],
    )
    assert "先界定研究目标与对象" not in out
    assert "给出方法路径、输入输出与关键参数设置" not in out
    assert "基于数据来源、评价指标与结果解释构建证据链" not in out
    assert "不同区域样本在治理协同效率上存在显著差异" in out


def test_sanitize_output_text_limits_duplicate_prose_lines() -> None:
    raw = (
        "该平台通过链上确权与多方协同机制提升农村社会化服务透明度。\n"
        "该平台通过链上确权与多方协同机制提升农村社会化服务透明度。\n"
        "该平台通过链上确权与多方协同机制提升农村社会化服务透明度。\n"
        "实验部分进一步给出了可复核的评价指标与对照设置。"
    )
    out = sanitize_domain.sanitize_output_text(
        raw,
        meta_phrases=[],
        has_cjk=lambda s: any("\u4e00" <= ch <= "\u9fff" for ch in str(s)),
        is_mostly_ascii_line=lambda _s: False,
        banned_phrases=[],
    )
    assert out.count("该平台通过链上确权与多方协同机制提升农村社会化服务透明度。") == 1
    assert "实验部分进一步给出了可复核的评价指标与对照设置。" in out


def test_sanitize_output_text_dedupes_repeated_sentences_in_one_line() -> None:
    raw = "该研究构建协同治理框架并验证其可行性。该研究构建协同治理框架并验证其可行性。该研究构建协同治理框架并验证其可行性。"
    out = sanitize_domain.sanitize_output_text(
        raw,
        meta_phrases=[],
        has_cjk=lambda s: any("\u4e00" <= ch <= "\u9fff" for ch in str(s)),
        is_mostly_ascii_line=lambda _s: False,
        banned_phrases=[],
    )
    assert out.count("该研究构建协同治理框架并验证其可行性。") == 1


def test_sanitize_output_text_normalizes_generic_media_markers() -> None:
    raw = (
        '[[TABLE:{"caption":"核心指标对比表","columns":["指标","基线","本研究"],'
        '"rows":[["准确率","--","--"],["召回率","--","--"],["F1","--","--"]]}]]\n'
        '[[FIGURE:{"type":"flow","caption":"方法流程图","data":{"nodes":["输入","处理","输出"],'
        '"edges":[["输入","处理"],["处理","输出"]]}}]]'
    )
    out = sanitize_domain.sanitize_output_text(
        raw,
        meta_phrases=[],
        has_cjk=lambda s: any("\u4e00" <= ch <= "\u9fff" for ch in str(s)),
        is_mostly_ascii_line=lambda _s: False,
        banned_phrases=[],
    )
    assert "方法流程图" not in out
    assert "流程示意图" in out
    assert "--" not in out
    assert "评价维度" in out


def test_light_self_check_flags_repetition_and_reference_title() -> None:
    text = (
        "# 参考文献\n\n"
        "## 引言\n\n"
        "研究结论说明了系统改造方向。\n\n"
        "研究结论说明了系统改造方向。\n\n"
        "研究结论说明了系统改造方向。"
    )
    problems = post_domain._light_self_check(
        text=text,
        sections=["引言", "参考文献"],
        target_chars=0,
        evidence_enabled=False,
        reference_sources=[],
        reference_query="区块链 农村社会化服务",
    )
    assert "title_is_reference" in problems
    assert any(str(p).startswith("paragraph_repetition:") for p in problems)


def test_light_self_check_flags_reference_text_topic_mismatch(monkeypatch) -> None:
    monkeypatch.setenv("WRITING_AGENT_REFERENCE_TEXT_MIN_ROWS", "4")
    text = (
        "# 区块链+农村社会化服务\n\n"
        "## 引言\n\n"
        "本文讨论区块链在农村社会化服务中的应用场景。\n\n"
        "## 参考文献\n\n"
        "[1] Promptware Engineering: Software Engineering for LLM Prompt Development.\n\n"
        "[2] EditEval: Evaluating AI text editing systems.\n\n"
        "[3] Foundations of GenIR.\n\n"
        "[4] Towards AI-assisted Academic Writing."
    )
    problems = post_domain._light_self_check(
        text=text,
        sections=["引言", "参考文献"],
        target_chars=0,
        evidence_enabled=True,
        reference_sources=[],
        reference_query="区块链 农村社会化服务",
    )
    assert any(str(p).startswith("reference_text_topic_mismatch:") for p in problems)


def test_sanitize_output_text_drops_structured_key_value_residue() -> None:
    raw = (
        '"section_id":"H2::引言","block_id":"1","type":"paragraph","text":"这是保留内容。"\n'
        '"section_id":"H2::引言","block_id":"2","type":"table","caption":"这条应删除"\n'
        "这是正常段落。"
    )
    out = sanitize_domain.sanitize_output_text(
        raw,
        meta_phrases=[],
        has_cjk=lambda s: any("\u4e00" <= ch <= "\u9fff" for ch in str(s)),
        is_mostly_ascii_line=lambda _s: False,
        banned_phrases=[],
    )
    assert "section_id" not in out
    assert "block_id" not in out
    assert "这是正常段落" in out



def test_ensure_media_markers_drops_invalid_caption_only_figures_without_backfill() -> None:
    raw = 'Valid paragraph.\n\n[[FIGURE:{"caption":"Figure 5-1 system architecture"}]]'
    out = section_domain.ensure_media_markers(
        raw,
        section_title="\u7cfb\u7edf\u67b6\u6784",
        min_tables=0,
        min_figures=1,
        is_reference_section=lambda _x: False,
    )
    assert "Valid paragraph." in out
    assert "[[FIGURE:" not in out

def test_sanitize_output_text_drops_invalid_caption_only_figure_marker() -> None:
    raw = 'Valid paragraph one.\n\n[[FIGURE:{"caption":"Figure 5-1 system architecture"}]]\n\nValid paragraph two.'
    out = sanitize_domain.sanitize_output_text(
        raw,
        meta_phrases=[],
        has_cjk=lambda s: any("\u4e00" <= ch <= "\u9fff" for ch in str(s)),
        is_mostly_ascii_line=lambda _s: False,
        banned_phrases=[],
    )
    assert '[[FIGURE:' not in out
    assert 'Valid paragraph one.' in out
    assert 'Valid paragraph two.' in out



def test_postprocess_section_drops_unsupported_claim_paragraphs() -> None:
    raw = (
        "研究背景围绕学术写作自动化展开。\n\n"
        "结果显示，系统在综述与论文场景下引用匹配准确率达到96.8%，平均生成时延控制在7.4 s/千字，人工二次修改工作量下降41.3%。\n\n"
        "本文进一步梳理了学术写作系统的结构设计要点。"
    )
    out = section_domain.postprocess_section(
        "实验结果与讨论",
        raw,
        min_paras=1,
        min_chars=0,
        max_chars=0,
        min_tables=0,
        min_figures=0,
        section_title=lambda x: str(x),
        is_reference_section=lambda _x: False,
        format_references=lambda x: x,
        strip_reference_like_lines=lambda x: x,
        strip_inline_headings=lambda x, _s: x,
        generic_fill_paragraph=lambda _s, _i: "",
        sanitize_output_text=lambda x: sanitize_domain.sanitize_output_text(
            x,
            meta_phrases=[],
            has_cjk=lambda s: any("一" <= ch <= "鿿" for ch in str(s)),
            is_mostly_ascii_line=lambda _s: False,
            banned_phrases=[],
        ),
        ensure_media_markers=lambda txt, _sec, _t, _f: txt,
    )
    assert "96.8%" not in out
    assert "7.4 s/千字" not in out
    assert "41.3%" not in out
    assert "研究背景围绕学术写作自动化展开" in out
    assert "结构设计要点" in out



def test_light_self_check_ignores_repeated_structured_marker_fragments() -> None:
    text = (
        "# 标题\n\n"
        "## 系统总体架构\n\n"
        '[[TABLE:{"columns":["A","B"],"rows":[["x","y"]],"caption":"关键指标对比"}]]\n\n'
        ', "caption": "关键指标对比"}]]\n\n'
        ', "caption": "关键指标对比"}]]\n\n'
        ', "caption": "关键指标对比"}]]\n\n'
        "## 结论\n\n"
        "结论段落。"
    )
    problems = post_domain._light_self_check(
        text=text,
        sections=["系统总体架构", "结论"],
        target_chars=0,
        evidence_enabled=False,
        reference_sources=[],
        reference_query="",
    )
    assert not any(str(item).startswith("paragraph_repetition") for item in problems)


def test_sanitize_output_text_preserves_cjk_heading_body_boundaries() -> None:
    raw = (
        "# test\n\n"
        "## \u6458\u8981\n\n"
        "\u533a\u5757\u94fe\u6280\u672f\u7528\u4e8e\u63d0\u5347\u519c\u6751\u793e\u4f1a\u5316\u670d\u52a1\u7684\u6570\u636e\u53ef\u4fe1\u6027\u3002\n\n"
        "## \u5173\u952e\u8bcd\n\n"
        "\u5173\u952e\u8bcd\uff1a\u533a\u5757\u94fe\uff1b\u519c\u6751\u793e\u4f1a\u5316\u670d\u52a1\uff1bCiteSpace\n\n"
        "## \u5f15\u8a00\n\n"
        "\u6570\u5b57\u7ecf\u6d4e\u80cc\u666f\u4e0b\uff0c\u519c\u6751\u670d\u52a1\u7ec4\u7ec7\u6b63\u5728\u5feb\u901f\u91cd\u6784\u3002"
    )
    out = sanitize_domain.sanitize_output_text(
        raw,
        meta_phrases=[],
        has_cjk=lambda s: any("\u4e00" <= ch <= "\u9fff" for ch in str(s)),
        is_mostly_ascii_line=lambda _s: False,
        banned_phrases=[],
    )
    assert "## \u6458\u8981\n\n\u533a\u5757\u94fe\u6280\u672f" in out
    assert "## \u5173\u952e\u8bcd\n\n\u5173\u952e\u8bcd\uff1a" in out
    assert "## \u5f15\u8a00\n\n\u6570\u5b57\u7ecf\u6d4e\u80cc\u666f" in out
