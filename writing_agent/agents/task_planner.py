from __future__ import annotations

from dataclasses import dataclass

from writing_agent.models import ReportRequest


@dataclass(frozen=True)
class Plan:
    outline_template: str


class TaskPlannerAgent:
    def plan(self, req: ReportRequest) -> Plan:
        rt = (req.report_type or "").strip().lower()
        if "实验" in rt or "experiment" in rt:
            return Plan(outline_template="experiment")
        if "研究" in rt or "research" in rt or "论文" in rt:
            return Plan(outline_template="paper")
        return Plan(outline_template="course_report")


