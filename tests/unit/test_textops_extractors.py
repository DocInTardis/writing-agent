from __future__ import annotations

import pytest

import writing_agent.web.app_v2 as app_v2


def test_extract_template_with_model_returns_structured_payload() -> None:
    text = """# 模板标题

## 引言
说明

## 方法设计
说明

## 实验结果
说明
"""
    out = app_v2._extract_template_with_model(
        base_url="http://test",
        model="demo",
        filename="template.md",
        text=text,
    )
    assert isinstance(out, dict)
    assert str(out.get("name") or "").strip()
    outline = out.get("outline")
    assert isinstance(outline, list)
    assert len(outline) >= 2
    required_h2 = out.get("required_h2")
    assert isinstance(required_h2, list)
    assert "引言" in required_h2


def test_extract_prefs_with_model_returns_non_empty_payload() -> None:
    prompt = "题目：多智能体写作系统质量闭环研究，目标字数8000字，写成毕业论文。"
    out = app_v2._extract_prefs_with_model(
        base_url="http://test",
        model="demo",
        text=prompt,
        timeout_s=8.0,
    )
    assert isinstance(out, dict)
    assert isinstance(out.get("generation_prefs"), dict)
    assert int((out.get("generation_prefs") or {}).get("target_char_count") or 0) >= 8000
    assert str(out.get("title") or "").strip()


def test_extract_prefs_with_model_rejects_empty_input() -> None:
    with pytest.raises(ValueError):
        app_v2._extract_prefs_with_model(
            base_url="http://test",
            model="demo",
            text="",
            timeout_s=8.0,
        )
