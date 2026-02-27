"""Init module.

This module belongs to `writing_agent.agents` in the writing-agent codebase.
"""

from writing_agent.agents.citations import CitationAgent
from writing_agent.agents.figures import FigureAgent
from writing_agent.agents.outline import OutlineAgent
from writing_agent.agents.task_planner import TaskPlannerAgent
from writing_agent.agents.writing import WritingAgent

__all__ = [
    "CitationAgent",
    "FigureAgent",
    "OutlineAgent",
    "TaskPlannerAgent",
    "WritingAgent",
]

