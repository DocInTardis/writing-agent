from writing_agent.capabilities.generation_quality import check_generation_quality, looks_like_prompt_echo


def test_check_generation_quality_detects_short_duplicate_and_heading_issues() -> None:
    text = "same\nsame"
    issues = check_generation_quality(text, target_chars=200)

    assert any("过短" in issue for issue in issues)
    assert any("重复内容" in issue for issue in issues)
    assert any("缺少标题结构" in issue for issue in issues)


def test_looks_like_prompt_echo_detects_prompt_scaffold() -> None:
    text = "You are a writing assistant. Output Markdown only. <original_document>foo</original_document>"
    assert looks_like_prompt_echo(text, "write report") is True


def test_looks_like_prompt_echo_allows_normal_markdown() -> None:
    text = "# 标题\n\n## 方法\n\n这是正常正文内容，不包含提示词脚手架。"
    assert looks_like_prompt_echo(text, "write report") is False
