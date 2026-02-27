"""Figures module.

This module belongs to `writing_agent.agents` in the writing-agent codebase.
"""

from __future__ import annotations

from dataclasses import dataclass

from writing_agent.models import OutlineNode, ReportRequest


@dataclass(frozen=True)
class FigureSuggestion:
    caption: str
    kind: str = "placeholder"


class FigureAgent:
    def suggest(self, req: ReportRequest, outline: OutlineNode) -> list[FigureSuggestion]:
        if not req.include_figures:
            return []
        suggestions: list[FigureSuggestion] = []
        for node in outline.walk():
            t = node.title
            if any(k in t for k in ["结果", "数据", "实验", "分析"]):
                suggestions.append(FigureSuggestion(caption=f"{t}：示例图表（请替换为你的真实数据图）"))
        if not suggestions:
            suggestions.append(FigureSuggestion(caption="示例图表（请替换为你的真实数据图）"))
        return suggestions[:3]


