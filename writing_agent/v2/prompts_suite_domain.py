"""Prompt suite construction and routing helpers for prompts.py."""

from __future__ import annotations

import json
import re
from typing import Any


_WEEKLY_KEYWORDS = ["\u5468\u62a5", "weekly", "this week", "next week"]
_TECHNICAL_KEYWORDS = ["\u6280\u672f\u62a5\u544a", "technical report", "report", "implementation", "\u5de5\u7a0b"]
_ACADEMIC_KEYWORDS = ["\u8bba\u6587", "thesis", "paper", "\u6458\u8981", "\u5173\u952e\u8bcd", "academic"]
_REVISE_KEYWORDS = ["\u6539\u5199", "\u6da6\u8272", "rewrite", "revise"]
_PLAN_KEYWORDS = ["\u63d0\u7eb2", "outline", "\u7ed3\u6784", "\u76ee\u5f55"]
_VISUAL_TITLE_RE = re.compile(
    r"(\u67b6\u6784|\u6846\u67b6|\u6d41\u7a0b|\u673a\u5236|\u8def\u5f84|\u65f6\u5e8f|\u6f14\u5316|\u5173\u7cfb|architecture|framework|workflow|process|sequence|timeline)",
    flags=re.IGNORECASE,
)


def _escape_prompt_text(raw: object) -> str:
    text = str(raw or "")
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= ch <= "\u9fff" for ch in (text or ""))


def _language_of(text: str) -> str:
    s = str(text or "")
    if not s.strip():
        return "zh-CN"
    cjk = sum(1 for ch in s if "\u4e00" <= ch <= "\u9fff")
    alpha = sum(1 for ch in s if ch.isascii() and ch.isalpha())
    if cjk == 0 and alpha > 0:
        return "en"
    if cjk >= max(4, alpha // 2):
        return "zh-CN"
    return "mixed"


def _writer_visual_preference(plan_hint: str, section_title: str) -> str:
    payload: dict[str, Any] = {}
    raw_hint = str(plan_hint or "").strip()
    if raw_hint.startswith("{") and raw_hint.endswith("}"):
        try:
            parsed = json.loads(raw_hint)
        except Exception:
            parsed = {}
        if isinstance(parsed, dict):
            payload = parsed

    figure_specs = payload.get("figures") if isinstance(payload, dict) else []
    has_figure_plan = isinstance(figure_specs, list) and any(
        isinstance(item, dict) and (str(item.get("type") or "").strip() or str(item.get("caption") or "").strip())
        for item in figure_specs
    )
    title_probe = " ".join(
        [
            str(section_title or "").strip(),
            str(payload.get("section_title") or "").strip(),
        ]
    ).strip()
    visual_title = bool(_VISUAL_TITLE_RE.search(title_probe))
    try:
        visual_priority = float(payload.get("visual_priority") or 0.0)
    except Exception:
        visual_priority = 0.0
    prefer_visual = has_figure_plan or visual_priority >= 0.6 or visual_title
    if not prefer_visual:
        return ""
    score_note = f"- Section visual priority score: {visual_priority:.2f}.\n" if visual_priority > 0.0 else ""
    return (
        score_note
        + "- If a visual would materially clarify structure, workflow, phase evolution, or entity interaction, prefer one valid figure block.\n"
        + "- Prefer the figure suggestion from plan_hint when available, but omit the figure instead of fabricating low-information or fake visuals.\n"
    )


def _planner_system_cn(role_hint: str) -> str:
    return (
        "You are a strict Chinese document planner. Return JSON only. "
        "Determine document genre, section structure, target length, key points, figure slots, table slots, and evidence queries. "
        f"Current role hint: {str(role_hint or 'document')}."
    )


def _analysis_system_cn() -> str:
    return (
        "You are a requirement analysis agent. Return JSON only. "
        "Extract topic, document type, audience, style, must-have constraints, banned sections, and unresolved questions."
    )


def _writer_system_cn(doc_style: str) -> str:
    return (
        "You are a strict section writer. Return NDJSON only. "
        "Output reader-facing content blocks only; never emit meta instructions, placeholders, or writing guidance. "
        f"Document style: {str(doc_style or 'Chinese writing')}."
    )


def _revision_system_cn(scope: str) -> str:
    return (
        "You are a revision agent. Apply feedback precisely while preserving terminology and structure consistency. "
        f"Revision scope: {str(scope or 'full')}."
    )


_ACADEMIC_CN_PLANNER_FEW_SHOT = """Example:
{
  "title": "Multi-agent academic writing quality loop",
  "total_chars": 9000,
  "sections": [
    {"title": "\u6458\u8981", "target_chars": 320, "key_points": ["\u7814\u7a76\u76ee\u6807", "\u65b9\u6cd5", "\u7ed3\u679c", "\u7ed3\u8bba"], "context_from_previous": false, "figures": [], "tables": [], "evidence_queries": []},
    {"title": "\u5173\u952e\u8bcd", "target_chars": 60, "key_points": ["3-5\u4e2a\u5173\u952e\u8bcd"], "context_from_previous": false, "figures": [], "tables": [], "evidence_queries": []},
    {"title": "\u5f15\u8a00", "target_chars": 1200, "key_points": ["\u7814\u7a76\u80cc\u666f", "\u95ee\u9898\u754c\u5b9a", "\u7814\u7a76\u4ef7\u503c"], "context_from_previous": true, "figures": [], "tables": [], "evidence_queries": ["research status"]},
    {"title": "\u7814\u7a76\u8bbe\u8ba1", "target_chars": 2200, "key_points": ["\u8303\u5f0f", "\u65b9\u6cd5\u8def\u5f84", "\u6570\u636e\u6765\u6e90"], "context_from_previous": true, "figures": [{"type": "flow", "caption": "\u7814\u7a76\u6d41\u7a0b\u56fe"}], "tables": [{"caption": "\u7814\u7a76\u5bf9\u8c61\u4e0e\u53d8\u91cf", "columns": ["\u5bf9\u8c61", "\u53d8\u91cf", "\u8bf4\u660e"]}], "evidence_queries": ["methodology"]},
    {"title": "\u7ed3\u679c\u5206\u6790", "target_chars": 2500, "key_points": ["\u7ed3\u679c\u5c55\u793a", "\u5bf9\u6bd4\u5206\u6790", "\u8ba8\u8bba"], "context_from_previous": true, "figures": [{"type": "line", "caption": "\u6838\u5fc3\u6307\u6807\u53d8\u5316\u8d8b\u52bf"}], "tables": [{"caption": "\u7ed3\u679c\u5bf9\u6bd4", "columns": ["\u6307\u6807", "\u65b9\u6cd5", "\u7ed3\u679c"]}], "evidence_queries": ["results"]},
    {"title": "\u7ed3\u8bba", "target_chars": 900, "key_points": ["\u4e3b\u8981\u7ed3\u8bba", "\u5c40\u9650", "\u672a\u6765\u5de5\u4f5c"], "context_from_previous": true, "figures": [], "tables": [], "evidence_queries": []},
    {"title": "\u53c2\u8003\u6587\u732e", "target_chars": 600, "key_points": ["GB/T 7714-2015"], "context_from_previous": false, "figures": [], "tables": [], "evidence_queries": ["verifiable sources"]}
  ]
}"""

_TECH_REPORT_PLANNER_FEW_SHOT = """Example:
{
  "title": "Writing agent technical report",
  "total_chars": 5000,
  "sections": [
    {"title": "\u80cc\u666f\u4e0e\u76ee\u6807", "target_chars": 700, "key_points": ["\u76ee\u6807", "\u8fb9\u754c", "\u7ea6\u675f"], "context_from_previous": false, "figures": [], "tables": [], "evidence_queries": []},
    {"title": "\u7cfb\u7edf\u67b6\u6784", "target_chars": 1400, "key_points": ["\u6a21\u5757\u8fb9\u754c", "\u6570\u636e\u6d41", "\u5173\u952e\u63a5\u53e3"], "context_from_previous": true, "figures": [{"type": "architecture", "caption": "\u7cfb\u7edf\u67b6\u6784\u56fe"}], "tables": [], "evidence_queries": []},
    {"title": "\u5173\u952e\u5b9e\u73b0", "target_chars": 1500, "key_points": ["\u6838\u5fc3\u6d41\u7a0b", "\u5f02\u5e38\u6062\u590d", "\u8d28\u91cf\u95e8\u7981"], "context_from_previous": true, "figures": [{"type": "flow", "caption": "\u5173\u952e\u6d41\u7a0b\u56fe"}], "tables": [{"caption": "\u6a21\u5757\u804c\u8d23\u5206\u5de5", "columns": ["\u6a21\u5757", "\u804c\u8d23"]}], "evidence_queries": []},
    {"title": "\u9a8c\u8bc1\u4e0e\u7ed3\u8bba", "target_chars": 900, "key_points": ["\u9a8c\u8bc1\u65b9\u5f0f", "\u7ed3\u679c", "\u98ce\u9669"], "context_from_previous": true, "figures": [], "tables": [], "evidence_queries": []}
  ]
}"""

_WEEKLY_REPORT_PLANNER_FEW_SHOT = """Example:
{
  "title": "Project weekly report",
  "total_chars": 1800,
  "sections": [
    {"title": "\u672c\u5468\u5b8c\u6210", "target_chars": 700, "key_points": ["\u5b8c\u6210\u4e8b\u9879", "\u7ed3\u679c"], "context_from_previous": false, "figures": [], "tables": [], "evidence_queries": []},
    {"title": "\u98ce\u9669\u4e0e\u95ee\u9898", "target_chars": 500, "key_points": ["\u98ce\u9669", "\u5f71\u54cd", "\u5e94\u5bf9"], "context_from_previous": true, "figures": [], "tables": [], "evidence_queries": []},
    {"title": "\u4e0b\u5468\u8ba1\u5212", "target_chars": 500, "key_points": ["\u8ba1\u5212", "\u4f9d\u8d56", "\u91cc\u7a0b\u7891"], "context_from_previous": true, "figures": [], "tables": [], "evidence_queries": []}
  ]
}"""


def build_prompt_suites(prompt_suite_cls):
    return {
        "academic_cn": prompt_suite_cls(
            suite_id="academic_cn",
            planner_system=_planner_system_cn("academic paper"),
            planner_few_shot=_ACADEMIC_CN_PLANNER_FEW_SHOT,
            analysis_system=_analysis_system_cn(),
            writer_system=_writer_system_cn("Chinese academic paper"),
            writer_note=(
                "Produce complete paragraphs ready for delivery. "
                "Avoid conversational filler and prompt echoes. "
                "Citations must remain traceable."
            ),
            revision_system=_revision_system_cn("full"),
        ),
        "technical_report_cn": prompt_suite_cls(
            suite_id="technical_report_cn",
            planner_system=_planner_system_cn("technical report"),
            planner_few_shot=_TECH_REPORT_PLANNER_FEW_SHOT,
            analysis_system=_analysis_system_cn(),
            writer_system=_writer_system_cn("Chinese technical report"),
            writer_note=(
                "Emphasize engineering details, interface definitions, and verification outcomes. "
                "Do not emit placeholders."
            ),
            revision_system=_revision_system_cn("full"),
        ),
        "weekly_cn": prompt_suite_cls(
            suite_id="weekly_cn",
            planner_system=_planner_system_cn("weekly report"),
            planner_few_shot=_WEEKLY_REPORT_PLANNER_FEW_SHOT,
            analysis_system=_analysis_system_cn(),
            writer_system=_writer_system_cn("Chinese weekly report"),
            writer_note="Keep items concise and specific.",
            revision_system=_revision_system_cn("full"),
        ),
        "revise_local_cn": prompt_suite_cls(
            suite_id="revise_local_cn",
            planner_system=_planner_system_cn("local rewrite"),
            planner_few_shot=_TECH_REPORT_PLANNER_FEW_SHOT,
            analysis_system=_analysis_system_cn(),
            writer_system=_writer_system_cn("local rewrite"),
            writer_note="Only revise the requested span and preserve surrounding context.",
            revision_system=_revision_system_cn("local"),
        ),
        "revise_full_cn": prompt_suite_cls(
            suite_id="revise_full_cn",
            planner_system=_planner_system_cn("full rewrite"),
            planner_few_shot=_TECH_REPORT_PLANNER_FEW_SHOT,
            analysis_system=_analysis_system_cn(),
            writer_system=_writer_system_cn("full rewrite"),
            writer_note="Preserve section structure and terminology consistency.",
            revision_system=_revision_system_cn("full"),
        ),
        "generic_en": prompt_suite_cls(
            suite_id="generic_en",
            planner_system=(
                "You are a strict planning agent. Return JSON only. "
                "Schema: {title,total_chars,sections:[{title,target_chars,key_points,context_from_previous,figures,tables,evidence_queries}]}."
            ),
            planner_few_shot=_TECH_REPORT_PLANNER_FEW_SHOT,
            analysis_system=(
                "You are a requirement-analysis agent. Return JSON only. "
                "Schema: {topic,doc_type,audience,style,keywords,must_include,avoid_sections,constraints,questions,doc_structure}."
            ),
            writer_system=(
                "You are a strict section writer. Return NDJSON only with schema: "
                "{section_id,block_id,type,text,items,caption,columns,rows,kind,data}. "
                "If type=figure, you must provide kind+caption+data together; never emit caption-only figure blocks."
            ),
            writer_note="Produce complete paragraphs and avoid meta instructions.",
            revision_system="You are a revision agent. Follow user feedback precisely.",
        ),
    }


def _infer_doc_type(instruction: str, doc_type: str) -> str:
    explicit = str(doc_type or "").strip().lower()
    if explicit:
        return explicit
    raw = str(instruction or "").lower()
    if any(k in raw for k in _WEEKLY_KEYWORDS):
        return "weekly"
    if any(k in raw for k in _TECHNICAL_KEYWORDS):
        return "technical_report"
    if any(k in raw for k in _ACADEMIC_KEYWORDS):
        return "academic"
    return "academic"


def _infer_intent(instruction: str, intent: str) -> str:
    explicit = str(intent or "").strip().lower()
    if explicit:
        return explicit
    raw = str(instruction or "").lower()
    if any(k in raw for k in _REVISE_KEYWORDS):
        return "revise"
    if any(k in raw for k in _PLAN_KEYWORDS):
        return "plan"
    return "generate"


def _select_suite(context: Any) -> tuple[str, str]:
    lang = str(getattr(context, "language", "zh-CN") or "zh-CN").lower()
    intent = str(getattr(context, "intent", "generate") or "generate").lower()
    doc_type = str(getattr(context, "doc_type", "academic") or "academic").lower()
    revise_scope = str(getattr(context, "revise_scope", "none") or "none").lower()

    if not lang.startswith("zh") and lang != "mixed":
        return "generic_en", "language=en"
    if intent == "revise":
        if revise_scope == "local":
            return "revise_local_cn", "intent=revise,scope=local"
        return "revise_full_cn", "intent=revise,scope=full"
    if doc_type in {"weekly", "week", "weekly_report"}:
        return "weekly_cn", "doc_type=weekly"
    if doc_type in {"technical", "technical_report", "report"}:
        return "technical_report_cn", "doc_type=technical_report"
    return "academic_cn", "doc_type=academic"


def looks_like_weekly_instruction(instruction: str) -> bool:
    s = str(instruction or "").lower()
    if not s.strip():
        return False
    return any(k in s for k in _WEEKLY_KEYWORDS)


__all__ = [name for name in globals() if not name.startswith("__")]
