from __future__ import annotations

from dataclasses import dataclass

from writing_agent.agents.citations import CitationAgent
from writing_agent.agents.figures import FigureAgent
from writing_agent.agents.outline import OutlineAgent
from writing_agent.agents.task_planner import TaskPlannerAgent
from writing_agent.agents.writing import WritingAgent
from writing_agent.models import DraftDocument, OutlineNode, Paragraph, ReportRequest


@dataclass
class Orchestrator:
    planner: TaskPlannerAgent
    outliner: OutlineAgent
    writer: WritingAgent
    citer: CitationAgent
    figure: FigureAgent

    def generate_outline(self, req: ReportRequest) -> tuple[str, OutlineNode]:
        plan = self.planner.plan(req)
        md = self.outliner.generate_outline_markdown(req=req, template=plan.outline_template)
        tree = self.outliner.parse_outline_markdown(md)
        return md, tree

    def generate_draft(
        self, req: ReportRequest, outline: OutlineNode
    ) -> tuple[DraftDocument, dict[str, object], dict[str, list[str]], list[str]]:
        parsed = self.citer.parse_manual_sources(req)
        citations = parsed.citations
        written = self.writer.generate_draft(req=req, outline=outline, citations=citations)
        draft = written.draft

        suggestions = self.figure.suggest(req=req, outline=outline)
        if suggestions:
            idx = 1
            for s in suggestions:
                target = next(
                    (sec for sec in draft.sections if any(k in sec.title for k in ["结果", "数据", "分析", "实验"])),
                    None,
                )
                if target is None and draft.sections:
                    target = draft.sections[-1]
                if target is not None:
                    target.paragraphs.append(Paragraph(text=f"【图表占位】图 {idx}：{s.caption}"))
                    idx += 1

        return draft, citations, written.citation_usage, parsed.warnings
