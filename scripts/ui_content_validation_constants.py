"""Ui Content Validation Constants command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

from typing import Dict, List


TERM_ALIASES: Dict[str, List[str]] = {
    "background": ["背景"],
    "current state": ["现状", "当前情况"],
    "recommendations": ["建议", "对策"],
    "conclusion": ["结论", "总结"],
    "method": ["方法", "方法论"],
    "execution plan": ["执行方案", "实施方案"],
    "risk control": ["风险控制", "风险管理"],
    "oversight": ["监督机制", "监督"],
    "objective": ["目标"],
    "milestones": ["里程碑"],
    "resource plan": ["资源配置", "资源计划"],
    "target audience": ["目标用户", "受众"],
    "core value": ["核心价值", "卖点"],
    "compliance note": ["合规提示", "合规说明"],
    "issue summary": ["问题描述", "问题概述"],
    "resolution plan": ["处理方案", "解决方案"],
    "follow-up": ["后续跟进", "跟进安排"],
    "target group": ["适用人群", "适配对象"],
    "precautions": ["注意事项"],
    "when to seek care": ["就医建议", "何时就医"],
    "facts": ["事实"],
    "legal risk": ["法律风险"],
    "suggested steps": ["建议步骤", "建议流程"],
    "risk reminder": ["风险提示"],
    "allocation logic": ["资产配置", "配置逻辑"],
    "long-term principle": ["长期原则"],
    "prerequisites": ["前置条件"],
    "steps": ["操作步骤", "步骤"],
    "troubleshooting": ["故障排查", "排查"],
    "audience fit": ["适配对象", "人群适配"],
    "readability": ["易读性"],
    "accessibility": ["可访问性", "无障碍"],
    "priority": ["优先级"],
    "style guide": ["版式要求", "样式要求", "样式指南"],
    "first draft": ["初稿", "草稿"],
    "key points": ["关键要点", "要点"],
    "key takeaway": ["要点提示", "关键要点"],
    "terminology mapping": ["术语对照"],
    "disclaimer": ["免责声明"],
    "draft body": ["初稿正文"],
    "editable checklist": ["可修改项清单"],
    "action checklist": ["可执行清单"],
    "simhei": ["黑体"],
    "simsun": ["宋体"],
    "宋体": ["SimSun", "simsun", "小四", "12pt"],
    "黑体": ["SimHei", "simhei", "三号", "16pt"],
    "小四": ["12pt", "四号"],
    "三号": ["16pt"],
    "里程碑": ["Milestones", "milestones", "milestone"],
    "风险闭环": ["Risk Control", "risk control", "risk loop", "风险控制"],
    "风险控制": ["Risk Control", "risk control", "风险闭环"],
}


STATUS_RUNNING_HINTS = (
    "生成中",
    "解析中",
    "分析",
    "规划",
    "stream",
    "running",
    "model preparing",
)

STATUS_FAILURE_HINTS = (
    "生成失败",
    "失败",
    "中止",
    "aborted",
    "error",
    "failed",
)

STATUS_BUSY_HINTS = (
    "http 409",
    "正在执行 stream",
    "当前文档正在执行",
)

FORMAT_SENSITIVE_HINTS = (
    "format_required",
    "font",
    "fontsize",
    "line spacing",
    "style guide",
    "title centered",
    "simsun",
    "simhei",
    "字体",
    "字号",
    "样式",
    "格式",
    "排版",
    "行距",
    "居中",
)
