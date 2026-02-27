from writing_agent.v2.doc_format import parse_report_text


def _find_h2(blocks, title):
    for idx, b in enumerate(blocks):
        if b.type == "heading" and (b.level or 0) == 2 and (b.text or "").strip() == title:
            return idx
    return -1


def _find_heading(blocks, level, title):
    for idx, b in enumerate(blocks):
        if b.type == "heading" and (b.level or 0) == level and (b.text or "").strip() == title:
            return idx
    return -1


def test_heading_glue_split_basic():
    text = "# 标题\n\n## 背景本周完成了模型接入与联调，当前进度稳定。\n"
    blocks = parse_report_text(text).blocks
    idx = _find_h2(blocks, "背景")
    assert idx >= 0
    assert blocks[idx + 1].type == "paragraph"
    assert blocks[idx + 1].text.startswith("本周完成了模型接入与联调")


def test_heading_glue_split_colon():
    text = "# 标题\n\n## 背景：本周完成了模型接入与联调。\n"
    blocks = parse_report_text(text).blocks
    idx = _find_h2(blocks, "背景")
    assert idx >= 0
    assert blocks[idx + 1].type == "paragraph"
    assert blocks[idx + 1].text.startswith("本周完成了模型接入与联调")


def test_heading_glue_no_split_for_title():
    text = "# 标题\n\n## 系统设计与实现\n下一行是正文。\n"
    blocks = parse_report_text(text).blocks
    idx = _find_h2(blocks, "系统设计与实现")
    assert idx >= 0
    # Should not inject a paragraph from the same line.
    assert blocks[idx + 1].type == "paragraph"
    assert blocks[idx + 1].text.startswith("下一行是正文")


def test_numbered_heading_glue_split_with_model_subject():
    text = (
        "# T\n\n"
        "3.1 \u63d0\u5347\u8bca\u65ad\u51c6\u786e\u6027\u6a21\u578b\u901a\u8fc7\u6df1\u5ea6\u5b66\u4e60\u7b97\u6cd5"
        "\u5bf9\u5927\u91cf\u533b\u5b66\u5f71\u50cf\u6570\u636e\u8fdb\u884c\u8bad\u7ec3\u3002\n"
    )
    blocks = parse_report_text(text).blocks
    idx = _find_heading(blocks, 3, "\u63d0\u5347\u8bca\u65ad\u51c6\u786e\u6027")
    assert idx >= 0
    assert blocks[idx + 1].type == "paragraph"
    assert (blocks[idx + 1].text or "").startswith("\u6a21\u578b\u901a\u8fc7")


def test_cn_numbered_heading_glue_split():
    text = (
        "# T\n\n"
        "\u56db\u3001\u9762\u4e34\u7684\u6311\u6218\u53ca\u89e3\u51b3\u7b56\u7565"
        "\u5c3d\u7ba1\u6280\u672f\u5728\u533b\u5b66\u5f71\u50cf\u8bca\u65ad\u4e2d\u5c55\u73b0\u51fa\u5de8\u5927\u6f5c\u529b\u3002\n"
    )
    blocks = parse_report_text(text).blocks
    idx = _find_h2(blocks, "\u9762\u4e34\u7684\u6311\u6218\u53ca\u89e3\u51b3\u7b56\u7565")
    assert idx >= 0
    assert blocks[idx + 1].type == "paragraph"
    assert (blocks[idx + 1].text or "").startswith("\u5c3d\u7ba1")


def test_cn_numbered_heading_no_false_split():
    text = (
        "# T\n\n"
        "\u4e09\u3001\u6280\u672f\u5728\u533b\u7597\u5f71\u50cf\u4e2d\u7684\u5e94\u7528\u4f18\u52bf\n\n"
        "\u4e0b\u4e00\u884c\u662f\u6b63\u6587\u3002\n"
    )
    blocks = parse_report_text(text).blocks
    idx = _find_h2(blocks, "\u6280\u672f\u5728\u533b\u7597\u5f71\u50cf\u4e2d\u7684\u5e94\u7528\u4f18\u52bf")
    assert idx >= 0
    assert blocks[idx + 1].type == "paragraph"
    assert (blocks[idx + 1].text or "").startswith("\u4e0b\u4e00\u884c\u662f\u6b63\u6587")


def test_heading_glue_split_repeated_subject_before_marker():
    text = (
        "# T\n\n"
        "2.1 "
        "\u8ba1\u7b97\u673a\u89c6\u89c9\u4e0e\u56fe\u50cf\u5904\u7406"
        "\u8ba1\u7b97\u673a\u89c6\u89c9\u4f5c\u4e3a"
        "\u4eba\u5de5\u667a\u80fd\u7684\u91cd\u8981\u5206\u652f\uff0c"
        "\u5728\u81ea\u52a8\u9a7e\u9a76\u4e2d\u53d1\u6325\u5173\u952e\u4f5c\u7528\u3002\n"
    )
    blocks = parse_report_text(text).blocks
    idx = _find_heading(blocks, 3, "\u8ba1\u7b97\u673a\u89c6\u89c9\u4e0e\u56fe\u50cf\u5904\u7406")
    assert idx >= 0
    assert blocks[idx + 1].type == "paragraph"
    assert (blocks[idx + 1].text or "").startswith(
        "\u8ba1\u7b97\u673a\u89c6\u89c9\u4f5c\u4e3a\u4eba\u5de5\u667a\u80fd\u7684\u91cd\u8981\u5206\u652f"
    )


def test_heading_glue_marker_does_not_split_nominal_heading():
    text = (
        "# T\n\n"
        "3. "
        "\u6280\u672f\u5728\u533b\u7597\u5f71\u50cf\u4e2d\u7684\u5e94\u7528\u4f18\u52bf\n\n"
        "\u4e0b\u4e00\u884c\u662f\u6b63\u6587\u3002\n"
    )
    blocks = parse_report_text(text).blocks
    idx = _find_h2(blocks, "\u6280\u672f\u5728\u533b\u7597\u5f71\u50cf\u4e2d\u7684\u5e94\u7528\u4f18\u52bf")
    assert idx >= 0
    assert blocks[idx + 1].type == "paragraph"
    assert (blocks[idx + 1].text or "").startswith("\u4e0b\u4e00\u884c\u662f\u6b63\u6587")


def test_numbered_list_item_with_colon_stays_in_paragraph():
    text = (
        "# T\n\n"
        "## Method\n"
        "1. **Internal Sources**: include technical docs and logs.\n"
        "2. **External Sources**: include interviews and reports.\n"
    )
    blocks = parse_report_text(text).blocks
    headings = {(b.level, (b.text or "").strip()) for b in blocks if b.type == "heading"}
    paragraphs = [(b.text or "") for b in blocks if b.type == "paragraph"]
    assert (2, "**Internal Sources**") not in headings
    assert (2, "**External Sources**") not in headings
    assert any("Internal Sources" in p for p in paragraphs)
    assert any("External Sources" in p for p in paragraphs)
