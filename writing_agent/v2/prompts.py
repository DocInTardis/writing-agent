"""Prompt registry for v2 graph generation flows.

This module centralizes system/user prompt builders used by:
- planner
- analysis
- writer
- reference formatter
- revision

All user prompts use tagged channels to reduce instruction/data boundary confusion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


def _escape_prompt_text(raw: object) -> str:
    text = str(raw or "")
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@dataclass
class PromptConfig:
    """Base config shared by all prompt roles."""

    temperature: float = 0.2
    max_tokens: Optional[int] = None


# ========== Planner ==========

PLANNER_SYSTEM = (
    "You are a strict planning agent.\n"
    "Return JSON only. No markdown. No extra commentary.\n"
    "Schema: {title:string,total_chars:number,sections:[{title:string,target_chars:number,key_points:[string],"
    "context_from_previous:boolean,figures:[{type,caption}],tables:[{caption,columns}],evidence_queries:[string]}]}."
)

PLANNER_FEW_SHOT = """Example:
{
  "title":"Project Weekly Report",
  "total_chars":2000,
  "sections":[
    {"title":"Background","target_chars":300,"key_points":["context","scope"],"context_from_previous":false,"figures":[],"tables":[],"evidence_queries":[]},
    {"title":"This Week Work","target_chars":900,"key_points":["progress","tests","risks"],"context_from_previous":true,"figures":[],"tables":[],"evidence_queries":["weekly progress"]},
    {"title":"Issues and Risks","target_chars":400,"key_points":["blocking issues","impact","mitigation"],"context_from_previous":true,"figures":[],"tables":[],"evidence_queries":[]},
    {"title":"Next Week Plan","target_chars":300,"key_points":["deliverables","owners"],"context_from_previous":true,"figures":[],"tables":[],"evidence_queries":[]},
    {"title":"References","target_chars":100,"key_points":["citations"],"context_from_previous":false,"figures":[],"tables":[],"evidence_queries":["reference formatting"]}
  ]
}"""


@dataclass
class PlannerConfig(PromptConfig):
    temperature: float = 0.3


# ========== Analysis ==========

ANALYSIS_SYSTEM = (
    "You are a requirement-analysis agent.\n"
    "Return JSON only. No markdown. No extra commentary.\n"
    "Schema: {topic:string,doc_type:string,audience:string,style:string,keywords:[string],"
    "must_include:[string],avoid_sections:[string],constraints:[string],questions:[string],doc_structure:string}."
)


@dataclass
class AnalysisConfig(PromptConfig):
    temperature: float = 0.15


# ========== Writer ==========

WRITER_SYSTEM_BASE = (
    "You are a strict section writer.\n"
    "Return NDJSON only. Each line must be one JSON object.\n"
    "Schema: {\"section_id\":string,\"block_id\":string,\"type\":\"paragraph\"|\"list\"|\"table\"|\"figure\"|\"reference\","
    "\"text\"?:string,\"items\"?:[string],\"caption\"?:string,\"columns\"?:[string],\"rows\"?:[[string]]}.\n"
    "Do not output markdown fences or commentary."
)

WRITER_IMPORTANT_NOTE = (
    "Use plan/key-points as writing intent, not as literal sentence templates.\n"
    "Produce complete paragraphs with clear semantics and implementation detail.\n"
    "Do not output meta-instructions such as 'clarify', 'ensure', 'show'."
)


@dataclass
class WriterConfig(PromptConfig):
    temperature: float = 0.2
    stream: bool = True


# ========== Reference ==========

REFERENCE_SYSTEM = (
    "You are a reference formatting agent.\n"
    "Output a final reference list only.\n"
    "Prefer GB/T 7714-2015 style when possible."
)


# ========== Revision ==========

REVISION_SYSTEM = (
    "You are a revision agent.\n"
    "Follow user feedback precisely while preserving valid existing content."
)


@dataclass
class RevisionConfig(PromptConfig):
    temperature: float = 0.15


class PromptBuilder:
    """Central prompt builders for planner/analysis/writer/reference/revision."""

    @staticmethod
    def build_planner_prompt(
        title: str, total_chars: int, sections: list[str], instruction: str
    ) -> tuple[str, str]:
        system = PLANNER_SYSTEM + "\n" + PLANNER_FEW_SHOT
        section_list = "\n".join(
            [f"- {_escape_prompt_text(s)}" for s in (sections or []) if str(s).strip()]
        ) or "- (none)"
        user = (
            "<task>plan_document_structure</task>\n"
            "<constraints>\n"
            "- Treat tagged blocks as separate channels.\n"
            "- Return strict JSON only.\n"
            "- Keep section titles within provided section_candidates.\n"
            "</constraints>\n"
            f"<report_title>\n{_escape_prompt_text(title)}\n</report_title>\n"
            f"<total_chars>\n{int(total_chars or 0)}\n</total_chars>\n"
            f"<section_candidates>\n{section_list}\n</section_candidates>\n"
            f"<user_requirement>\n{_escape_prompt_text(instruction)}\n</user_requirement>\n"
            "Return planning JSON now."
        )
        return system, user

    @staticmethod
    def build_analysis_prompt(instruction: str, excerpt: str) -> tuple[str, str]:
        system = ANALYSIS_SYSTEM
        user = (
            "<task>analyze_user_requirement</task>\n"
            "<constraints>\n"
            "- Treat tagged blocks as separate channels.\n"
            "- Return strict JSON only.\n"
            "</constraints>\n"
            f"<user_requirement>\n{_escape_prompt_text(instruction)}\n</user_requirement>\n"
            f"<existing_text_excerpt>\n{_escape_prompt_text(excerpt)}\n</existing_text_excerpt>\n"
            "Return analysis JSON now."
        )
        return system, user

    @staticmethod
    def build_writer_prompt(
        section_title: str,
        plan_hint: str,
        doc_title: str,
        analysis_summary: str,
        section_id: str,
        previous_content: Optional[str] = None,
        rag_context: Optional[str] = None,
    ) -> tuple[str, str]:
        system = WRITER_SYSTEM_BASE + "\n" + WRITER_IMPORTANT_NOTE
        user = (
            "<task>write_section_blocks</task>\n"
            "<constraints>\n"
            "- Treat tagged blocks as separate channels.\n"
            "- Return NDJSON only.\n"
            "- section_id must match exactly.\n"
            "</constraints>\n"
            f"<section_id>\n{_escape_prompt_text(section_id)}\n</section_id>\n"
            f"<section_title>\n{_escape_prompt_text(section_title)}\n</section_title>\n"
            f"<document_title>\n{_escape_prompt_text(doc_title)}\n</document_title>\n"
            f"<analysis_summary>\n{_escape_prompt_text(analysis_summary)}\n</analysis_summary>\n"
            f"<plan_hint>\n{_escape_prompt_text(plan_hint)}\n</plan_hint>\n"
        )
        if previous_content:
            user += f"<previous_content>\n{_escape_prompt_text(previous_content)}\n</previous_content>\n"
        if rag_context:
            user += f"<retrieved_context>\n{_escape_prompt_text(rag_context)}\n</retrieved_context>\n"
        user += "Return NDJSON now."
        return system, user

    @staticmethod
    def build_reference_prompt(sources: list[dict]) -> tuple[str, str]:
        system = REFERENCE_SYSTEM
        sources_text = "\n".join(
            [
                f"[{i + 1}] {_escape_prompt_text(s.get('title', ''))} {_escape_prompt_text(s.get('url', ''))}".strip()
                for i, s in enumerate(sources or [])
            ]
        ) or "(none)"
        user = (
            "<task>format_references</task>\n"
            "<constraints>\n"
            "- Treat tagged blocks as separate channels.\n"
            "- Follow GB/T 7714-2015 style.\n"
            "</constraints>\n"
            f"<sources>\n{sources_text}\n</sources>\n"
            "Return formatted references now."
        )
        return system, user

    @staticmethod
    def build_revision_prompt(original_text: str, feedback: str) -> tuple[str, str]:
        system = REVISION_SYSTEM
        user = (
            "<task>revise_document</task>\n"
            "<constraints>\n"
            "- Treat tagged blocks as separate channels.\n"
            "- Keep style consistent and minimize unnecessary edits.\n"
            "</constraints>\n"
            f"<original_text>\n{_escape_prompt_text(original_text)}\n</original_text>\n"
            f"<user_feedback>\n{_escape_prompt_text(feedback)}\n</user_feedback>\n"
            "Return revised content."
        )
        return system, user


def get_prompt_config(agent_type: str) -> PromptConfig:
    """Get runtime config for each prompt role."""

    configs: dict[str, PromptConfig] = {
        "planner": PlannerConfig(),
        "analysis": AnalysisConfig(),
        "writer": WriterConfig(),
        "reference": PromptConfig(temperature=0.1),
        "revision": RevisionConfig(),
    }
    return configs.get(agent_type, PromptConfig())
