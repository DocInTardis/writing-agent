from __future__ import annotations

import re

from writing_agent.v2 import graph_runner_runtime as runtime


def test_normalize_final_output_maps_expected_sections_to_h2():
    raw = (
        "# 区块链研究文稿\n\n"
        "## 摘要\n\n"
        "这是摘要内容。\n\n"
        "## 引言\n\n"
        "这是引言内容。\n\n"
        "## 参考文献\n\n"
        "[1] 示例文献。"
    )
    out = runtime._normalize_final_output(
        raw,
        expected_sections=["摘要", "引言", "参考文献"],
    )
    assert out.splitlines()[0].startswith("# ")
    h2_lines = re.findall(r"(?m)^##\s+.+$", out)
    assert len(h2_lines) >= 3
    assert any("摘要" in line for line in h2_lines)
    assert any("引言" in line for line in h2_lines)
    assert any("参考文献" in line for line in h2_lines)



def test_normalize_final_output_prunes_unsupported_claim_paragraphs() -> None:
    raw = (
        "# 标题\n\n"
        "## 引言\n\n"
        "研究背景围绕高校科研写作展开。\n\n"
        "## 实验结果与分析\n\n"
        "结果显示，引用匹配准确率达到96.8%，平均生成时延控制在7.4 s/千字。\n\n"
        "## 参考文献\n\n"
        "[1] Example Ref. 2024."
    )
    out = runtime._normalize_final_output(
        raw,
        expected_sections=["引言", "实验结果与分析", "参考文献"],
    )
    assert "96.8%" not in out
    assert "7.4 s/千字" not in out
    assert "研究背景围绕高校科研写作展开" in out
    assert "[1] Example Ref. 2024." in out



def test_normalize_final_output_prunes_only_unsupported_sentence_from_mixed_paragraph() -> None:
    raw = (
        "# 标题\n\n"
        "## 关键技术实现\n\n"
        "系统采用了提纲代理与校核代理的分层协作架构。在线回归测试显示，虚构引文比例由 7.8% 降至 1.9%。\n\n"
        "## 结论\n\n"
        "结论段落。"
    )
    out = runtime._normalize_final_output(
        raw,
        expected_sections=["关键技术实现", "结论"],
    )
    assert "分层协作架构" in out
    assert "7.8%" not in out
    assert "1.9%" not in out



def test_normalize_final_output_prunes_unexpected_sections_in_fixed_outline_mode() -> None:
    raw = (
        "# Title\n\n"
        "## Introduction\n\n"
        "Intro body.\n\n"
        "## Related Work\n\n"
        "This drift section should be removed.\n\n"
        "## Conclusion\n\n"
        "Conclusion body."
    )
    out = runtime._normalize_final_output(
        raw,
        expected_sections=["Introduction", "Conclusion"],
    )
    assert "## Related Work" not in out
    assert "This drift section should be removed." not in out
    assert "## Introduction" in out
    assert "## Conclusion" in out
