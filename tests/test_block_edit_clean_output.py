from writing_agent.web.block_edit import _clean_ai_rewrite_text


def test_clean_ai_rewrite_text_extracts_rewrite_section():
    raw = "原文：这是原文。\n改写后的文本：这是改写。"
    cleaned = _clean_ai_rewrite_text(raw, "这是原文。")
    assert cleaned == "这是改写。"


def test_clean_ai_rewrite_text_removes_original_paragraph():
    raw = "这是原文。\n\n这是改写后的新内容。"
    cleaned = _clean_ai_rewrite_text(raw, "这是原文。")
    assert cleaned == "这是改写后的新内容。"


def test_clean_ai_rewrite_text_keeps_plain_result():
    raw = "这是一条直接返回的改写结果。"
    cleaned = _clean_ai_rewrite_text(raw, "这是原文。")
    assert cleaned == "这是一条直接返回的改写结果。"


def test_clean_ai_rewrite_text_handles_markdown_list_labels():
    raw = "- 原文：这是原文。\n- 改写后的文本：这是改写后的新段落。"
    cleaned = _clean_ai_rewrite_text(raw, "这是原文。")
    assert cleaned == "这是改写后的新段落。"


def test_clean_ai_rewrite_text_drops_original_block_in_fenced_output():
    raw = "```markdown\n原文：这是原文。\n\n改写后：这是优化后的段落，语义保持一致。\n```"
    cleaned = _clean_ai_rewrite_text(raw, "这是原文。")
    assert cleaned == "这是优化后的段落，语义保持一致。"
