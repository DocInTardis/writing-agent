from __future__ import annotations

import re

import writing_agent.web.app_v2 as app_v2


def test_enforce_required_sections_and_disclaimer():
    instruction = (
        "必须包含以下一级章节：目标与范围、预算与资源、附录检查清单。"
        "并且必须提供对外沟通免责声明。"
    )
    text = "# 标题\n\n## 目标与范围\n内容A\n"

    out = app_v2._enforce_instruction_requirements(text, instruction)

    assert "## 目标与范围" in out
    assert "## 预算与资源" in out
    assert "## 附录检查清单" in out
    assert "## 免责声明" in out


def test_enforce_term_mapping_and_weekly_plan_counts():
    instruction = (
        "第三部分“执行版清单”需输出按周分解的任务表（至少12周），每周包含负责人、输入、输出、验收标准。"
        "必须提供“术语映射表”（中文术语-英文术语-业务定义）不少于15项。"
    )
    text = (
        "# 项目\n\n"
        "## 执行版清单\n\n"
        "第1至2周\n"
        "- 负责人：A\n"
        "- 输入：x\n"
        "- 输出：y\n"
        "- 验收标准：z\n\n"
        "## 术语映射表\n"
        "| 中文术语 | 英文术语 | 业务定义 |\n"
        "| :-- | :-- | :-- |\n"
        "| 术语1 | Term-1 | 定义1 |\n"
    )

    out = app_v2._enforce_instruction_requirements(text, instruction)

    week_entries = re.findall(r"第\s*(\d+)\s*周", out)
    assert len(set(int(x) for x in week_entries)) >= 12

    rows = re.findall(r"(?m)^\|\s*[^|\n]+\s*\|\s*[^|\n]+\s*\|\s*[^|\n]+\s*\|", out)
    # one header row + >=15 data rows
    assert len(rows) >= 16


def test_enforce_risk_and_slo_and_checklist_minimums():
    instruction = (
        "在“监控告警与SLO”中给出至少8条可量化指标，包含阈值、采样周期、触发动作。"
        "在“风险台账”中给出至少10项风险，包含概率、影响、缓解策略、预警信号。"
        "在“附录检查清单”里给出可执行打勾项，至少20条。"
    )
    text = "# 标题\n\n## 监控告警与SLO\n现有一条。\n\n## 风险台账\n现有一条。\n"

    out = app_v2._enforce_instruction_requirements(text, instruction)

    slo_items = re.findall(r"(?m)^-\s*指标\d+：", out)
    assert len(slo_items) >= 8

    risk_ids = set(re.findall(r"\bR(\d+)\b", out))
    assert len(risk_ids) >= 10

    checklist_items = re.findall(r"(?m)^-\s*\[\s\]\s*检查项\d+：", out)
    assert len(checklist_items) >= 20
