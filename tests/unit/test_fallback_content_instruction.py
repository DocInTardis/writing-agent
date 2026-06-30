from __future__ import annotations

from writing_agent.web.domains.fallback_content_domain import augment_instruction


def test_augment_instruction_keeps_formatting_as_export_only_constraints() -> None:
    prompt = augment_instruction(
        "请生成一篇围绕实验室安全治理的文章。",
        formatting={
            "font_size_name": "小四",
            "font_size_pt": 12,
            "line_spacing": 28,
            "heading1_font_name_east_asia": "黑体",
            "heading1_size_pt": 22,
            "heading2_font_name_east_asia": "黑体",
            "heading2_size_pt": 16,
        },
        generation_prefs={"purpose": "学术论文", "target_char_count": 3000},
    )
    assert "排版会在导出阶段自动应用" in prompt
    assert "不要把字体、字号、行距、目录、页眉页脚等设置写入正文" in prompt
    assert "不要把排版参数、样式名称或模板标签当作标题" in prompt
    assert "黑体" not in prompt
    assert "22pt" not in prompt
    assert "一级标题" not in prompt
