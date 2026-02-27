"""Routing module.

This module belongs to `writing_agent.state_engine` in the writing-agent codebase.
"""

from __future__ import annotations

import re
from typing import Any

from .context import RouteScore, RoutingDecision


_RE_OVERWRITE = re.compile(r"(全文重写|整篇重写|全部重写|重写整篇|覆盖重写|重新写一份)")
_RE_REVISE = re.compile(r"(修改|改写|润色|优化|调整|替换|重写第|改成)")
_RE_CONTINUE = re.compile(r"(续写|继续写|接着写|补写|扩写)")
_RE_FORMAT = re.compile(r"(字体|字号|行距|段前|段后|对齐|格式|样式|页边距|页眉|页脚)")
_RE_ROLE_OVERRIDE = re.compile(r"(扮演|作为).*(专家|老师|顾问|写作)")
_RE_REFERENCE = re.compile(r"(参考这个|仿照|按.*样例)")
_RE_CITATION = re.compile(r"(参考文献|引用|citation|cite)")


def classify_role(session: Any, instruction: str) -> tuple[str, float]:
    txt = instruction or ""
    if _RE_ROLE_OVERRIDE.search(txt):
        return "R06", 0.8
    if getattr(session, "template_outline", None) or getattr(session, "template_required_h2", None):
        return "R01", 0.9
    if _RE_CITATION.search(txt):
        return "R03", 0.75
    if _RE_REFERENCE.search(txt):
        return "R02", 0.7
    if txt.strip():
        return "R04", 0.6
    return "R05", 0.4


def classify_intent(instruction: str, *, has_format_only: bool = False) -> tuple[str, float]:
    txt = instruction or ""
    if has_format_only:
        return "I06", 0.95
    if _RE_OVERWRITE.search(txt):
        return "I03", 0.9
    if _RE_CONTINUE.search(txt):
        return "I05", 0.8
    if _RE_REVISE.search(txt):
        return "I04", 0.8
    if _RE_FORMAT.search(txt):
        return "I06", 0.8
    if txt.strip():
        return "I07", 0.55
    return "I08", 0.2


def resolve_scope(*, selection: str = "", block_ids: list[str] | None = None, section: str = "") -> str:
    ids = [x for x in (block_ids or []) if str(x).strip()]
    if selection.strip():
        return "C06"
    if ids and len(ids) == 1:
        return "C04"
    if ids and len(ids) > 1:
        return "C05"
    if section.strip():
        return "C02"
    return "C01"


def route_execute_branch(role: str, intent: str, scope: str) -> RoutingDecision:
    score = RouteScore(role_weight=0.4, intent_weight=0.35, scope_weight=0.25)
    route = "E22"

    if role == "R01" and intent in {"I03", "I04", "I05"}:
        route = "E13" if intent == "I03" else "E14"
        score.final_score = 0.95
    elif role == "R03" and intent in {"I04", "I07"}:
        route = "E16"
        score.final_score = 0.9
    elif intent == "I06":
        route = "E10" if scope == "C01" else "E11"
        score.final_score = 0.92
    elif intent == "I03":
        route = "E01" if scope == "C01" else "E02"
        score.final_score = 0.88
    elif intent == "I04":
        if scope == "C01":
            route = "E03"
        elif scope in {"C02", "C03"}:
            route = "E04"
        elif scope in {"C04", "C05"}:
            route = "E05"
        else:
            route = "E06"
        score.final_score = 0.86
    elif intent == "I05":
        if scope == "C01":
            route = "E07"
        elif scope in {"C02", "C03"}:
            route = "E08"
        else:
            route = "E09"
        score.final_score = 0.84
    elif intent == "I07":
        route = "E12"
        score.final_score = 0.7
    else:
        route = "E19"
        score.final_score = 0.5

    return RoutingDecision(route=route, score=score)

