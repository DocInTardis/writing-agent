"""Graph Plan Domain module.

This module belongs to `writing_agent.v2` in the writing-agent codebase.
"""

from __future__ import annotations

import re
from typing import Callable


def clean_section_title(
    title: str,
    *,
    strip_chapter_prefix_local: Callable[[str], str],
) -> str:
    s = strip_chapter_prefix_local(str(title or "")).strip()
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", s)
    s = re.sub(r"\s*#+\s*$", "", s).strip()
    if not s:
        return ""
    if len(s) <= 12 and not re.search(r"[\u3002\uFF01\uFF1F\uFF1B\uFF1A\uFF0C,;?]", s):
        return s
    noise_prefixes = [
        "包括",
        "主要",
        "围绕",
        "切忌",
        "参看",
        "说明",
        "写出",
        "写成",
        "不要",
    ]
    if any(s.startswith(p) for p in noise_prefixes) and len(s) >= 6:
        return ""
    if "格式" in s and len(s) >= 6:
        return ""
    anchors = [
        "系统概述",
        "系统功能",
        "功能需求",
        "非功能需求",
        "选题背景及意义",
        "国内研究状况",
        "国外研究状况",
        "研究现状",
        "研究目标",
        "研究内容",
        "关键技术",
        "本文的结构及主要工作",
        "系统总体设计",
        "总体设计",
        "详细设计",
        "概要设计",
        "系统设计",
        "系统实现",
        "系统架构",
        "数据库设计",
        "需求分析",
        "部署与维护",
        "技术路线",
        "技术方案",
        "工程设计",
        "技术选型",
        "实验设计",
        "结果分析",
        "测试与分析",
        "系统测试",
        "后期展望",
        "结论与展望",
        "系统总结",
        "研究背景",
        "研究意义",
        "文献综述",
        "引言",
        "绪论",
        "背景",
        "方法",
        "设计",
        "实现",
        "测试",
        "结论",
        "总结",
        "参考文献",
    ]
    for key in sorted(anchors, key=len, reverse=True):
        if key in s:
            return key
    s = re.split(r"[\u3002\uff01\uff1f\uff1b;\uff1a\uff0c,、…]", s, 1)[0].strip()
    if len(s) > 18:
        s = s[:18].strip()
    return s


def normalize_plan_map(
    *,
    plan_raw: dict,
    sections: list[str],
    base_targets: dict,
    total_chars: int,
    default_plan_map: Callable[[list[str], dict, int], dict],
    section_title: Callable[[str], str],
    classify_section_type: Callable[[str], str],
    is_reference_section: Callable[[str], bool],
    plan_section_cls,
) -> dict:
    default_plan = default_plan_map(sections, base_targets, total_chars)
    if not isinstance(plan_raw, dict):
        return default_plan
    plan_sections = plan_raw.get("sections") if isinstance(plan_raw, dict) else None
    if not isinstance(plan_sections, list):
        return default_plan

    by_title: dict[str, dict] = {}
    for item in plan_sections:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        by_title[title] = item

    plan: dict[str, object] = {}
    total = 0
    for sec in sections:
        title = section_title(sec) or sec
        entry = by_title.get(title) or {}
        t_val = entry.get("target_chars")
        try:
            target = int(t_val) if t_val is not None else default_plan[sec].target_chars
        except Exception:
            target = default_plan[sec].target_chars
        target = max(180, target)
        total += target
        key_points = [str(x).strip() for x in (entry.get("key_points") or []) if str(x).strip()]
        figures = [x for x in (entry.get("figures") or []) if isinstance(x, dict)]
        tables = [x for x in (entry.get("tables") or []) if isinstance(x, dict)]
        evidence_queries = [str(x).strip() for x in (entry.get("evidence_queries") or []) if str(x).strip()]
        min_tables = int(entry.get("min_tables") or 0) if str(entry.get("min_tables") or "").isdigit() else 0
        min_figures = int(entry.get("min_figures") or 0) if str(entry.get("min_figures") or "").isdigit() else 0
        target_row = base_targets.get(sec)
        if target_row:
            min_tables = max(min_tables, int(target_row.min_tables))
            min_figures = max(min_figures, int(target_row.min_figures))
        min_tables = max(min_tables, len(tables))
        min_figures = max(min_figures, len(figures))
        section_type = classify_section_type(title)
        if section_type == "intro":
            min_chars = max(400, int(round(target * 1.2)))
            max_chars = max(min_chars + 300, int(round(target * 1.6)))
        elif section_type == "method":
            min_chars = max(800, int(round(target * 2.0)))
            max_chars = max(min_chars + 600, int(round(target * 2.5)))
        elif section_type == "conclusion":
            min_chars = max(500, int(round(target * 1.5)))
            max_chars = max(min_chars + 400, int(round(target * 1.9)))
        else:
            min_chars = max(600, int(round(target * 1.7)))
            max_chars = max(min_chars + 500, int(round(target * 2.3)))
        if is_reference_section(title):
            min_tables = 0
            min_figures = 0
        plan[sec] = plan_section_cls(
            title=title,
            target_chars=target,
            min_chars=min_chars,
            max_chars=max_chars,
            min_tables=min_tables,
            min_figures=min_figures,
            key_points=key_points,
            figures=figures,
            tables=tables,
            evidence_queries=evidence_queries,
        )

    if total_chars > 0 and total > 0:
        scale = float(total_chars) / float(total)
        if abs(scale - 1.0) > 0.05:
            for sec in sections:
                p = plan.get(sec)
                if not p:
                    continue
                target = max(180, int(round(p.target_chars * scale)))
                section_type = classify_section_type(p.title)
                if section_type == "intro":
                    min_chars = max(400, int(round(target * 1.2)))
                    max_chars = max(min_chars + 300, int(round(target * 1.6)))
                elif section_type == "method":
                    min_chars = max(800, int(round(target * 2.0)))
                    max_chars = max(min_chars + 600, int(round(target * 2.5)))
                elif section_type == "conclusion":
                    min_chars = max(500, int(round(target * 1.5)))
                    max_chars = max(min_chars + 400, int(round(target * 1.9)))
                else:
                    min_chars = max(600, int(round(target * 1.7)))
                    max_chars = max(min_chars + 500, int(round(target * 2.3)))
                plan[sec] = plan_section_cls(
                    title=p.title,
                    target_chars=target,
                    min_chars=min_chars,
                    max_chars=max_chars,
                    min_tables=p.min_tables,
                    min_figures=p.min_figures,
                    key_points=p.key_points,
                    figures=p.figures,
                    tables=p.tables,
                    evidence_queries=p.evidence_queries,
                )

    return plan
