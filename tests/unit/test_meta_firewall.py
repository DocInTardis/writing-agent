from __future__ import annotations

from writing_agent.v2.meta_firewall import MetaFirewall


def test_meta_firewall_scan_and_strip_detects_meta_instruction_residue():
    fw = MetaFirewall()
    draft = (
        "摘要应覆盖研究目标、范围边界、关键约束与可量化产出。\n\n"
        "本研究围绕农村社会化服务场景展开，并通过案例对比验证可行性。"
    )
    result = fw.scan(draft)
    assert result.has_meta is True
    assert result.fragments
    cleaned = fw.strip(draft)
    assert "摘要应覆盖研究目标" not in cleaned
    assert "本研究围绕农村社会化服务场景展开" in cleaned


def test_meta_firewall_build_rewrite_prompt_contains_feedback_fragments():
    fw = MetaFirewall()
    system, user = fw.build_rewrite_prompt(
        section_title="摘要",
        draft="摘要应覆盖研究目标。",
        hit_fragments=["摘要应覆盖研究目标。", "本节将说明方法路径。"],
    )
    assert "REWRITE_WITHOUT_META" in system
    assert "<meta_hits>" in user
    assert "本节将说明方法路径" in user
    assert "本段补充了" in user
    assert "[1]；区块链" in user


def test_meta_firewall_scan_detects_self_evaluative_topup_meta():
    fw = MetaFirewall()
    draft = (
        "本研究围绕农村社会化服务场景展开，并通过案例对比验证可行性。\n\n"
        "此外，围绕“论证路径与证据支撑”，进一步补充了样本边界与变量控制方法。"
    )
    result = fw.scan(draft)
    assert result.has_meta is True
    cleaned = fw.strip(draft)
    assert "本研究围绕农村社会化服务场景展开" in cleaned
    assert "进一步补充了样本边界与变量控制方法" not in cleaned


def test_meta_firewall_scan_detects_bracket_semicolon_meta_residue():
    fw = MetaFirewall()
    draft = "[1]；区块链赋能农村社会化服务的路径需要进一步说明。"
    result = fw.scan(draft)
    assert result.has_meta is True
    assert result.fragments

def test_meta_firewall_scan_detects_section_catalog_style_meta_residue():
    fw = MetaFirewall()
    draft = (
        "\u5f15\u8a00\u4ea4\u4ee3\u7814\u7a76\u6216\u9879\u76ee\u80cc\u666f\u3001\u95ee\u9898\u8d77\u70b9\u4e0e\u62a5\u544a\u8303\u56f4\uff0c\u5e2e\u52a9\u8bfb\u8005\u7406\u89e3\u4e3a\u4ec0\u4e48\u8981\u505a\u3002\n\n"
        "\u5f15\u8a00\u7ed9\u51fa\u65b9\u6cd5\u6d41\u7a0b\u4e0e\u5173\u952e\u53c2\u6570\u8bbe\u7f6e\uff0c\u5c55\u793a\u7814\u7a76\u8def\u5f84\u7684\u53ef\u590d\u73b0\u6027\u3002"
    )
    result = fw.scan(draft)
    assert result.has_meta is True
    assert any("\u5e2e\u52a9\u8bfb\u8005\u7406\u89e3\u4e3a\u4ec0\u4e48\u8981\u505a" in frag or "\u7814\u7a76\u8def\u5f84\u7684\u53ef\u590d\u73b0\u6027" in frag for frag in result.fragments)

