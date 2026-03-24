"""Runtime helpers for section segmentation and parallel drafting."""

from __future__ import annotations

import json
import os
import queue
import time
from concurrent.futures import ThreadPoolExecutor



def _section_runtime_module():
    from writing_agent.v2 import graph_runner_runtime_section_domain as _section_domain

    return _section_domain



def _meta_firewall_scan(text: str) -> bool:
    return bool(_section_runtime_module()._meta_firewall_scan(text))



def _is_reference_section(title: str) -> bool:
    return bool(_section_runtime_module()._is_reference_section(title))



def _generate_section_stream(**kwargs):
    return _section_runtime_module()._generate_section_stream(**kwargs)



def _section_body_len(text: str) -> int:
    return int(_section_runtime_module()._section_body_len(text))


def _section_segment_enabled() -> bool:
    raw = str(os.environ.get("WRITING_AGENT_SECTION_SEGMENT_ENABLED", "1")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _section_segment_threshold_chars() -> int:
    raw = str(os.environ.get("WRITING_AGENT_SECTION_SEGMENT_THRESHOLD_CHARS", "1400")).strip()
    try:
        value = int(raw)
    except Exception:
        value = 1400
    return max(600, value)


def _section_segment_target_chars() -> int:
    raw = str(os.environ.get("WRITING_AGENT_SECTION_SEGMENT_TARGET_CHARS", "760")).strip()
    try:
        value = int(raw)
    except Exception:
        value = 760
    return max(320, value)


def _section_segment_max_segments() -> int:
    raw = str(os.environ.get("WRITING_AGENT_SECTION_SEGMENT_MAX", "3")).strip()
    try:
        value = int(raw)
    except Exception:
        value = 3
    return max(2, min(6, value))


def _split_integer_budget(total: int, parts: int) -> list[int]:
    count = max(1, int(parts or 1))
    value = max(0, int(total or 0))
    base = value // count
    rem = value % count
    return [base + (1 if idx < rem else 0) for idx in range(count)]


def _split_list_evenly(items: list[str], parts: int) -> list[list[str]]:
    values = [str(x).strip() for x in (items or []) if str(x).strip()]
    count = max(1, int(parts or 1))
    if not values:
        return [[] for _ in range(count)]
    base = len(values) // count
    rem = len(values) % count
    out: list[list[str]] = []
    cursor = 0
    for idx in range(count):
        size = base + (1 if idx < rem else 0)
        if size <= 0:
            out.append([])
            continue
        out.append(values[cursor:cursor + size])
        cursor += size
    return out


def _is_segment_candidate_title(section_title: str) -> bool:
    normalized = str(section_title or "").strip().lower()
    if not normalized:
        return False
    tokens = [
        "数据来源",
        "检索策略",
        "方法",
        "方法论",
        "研究设计",
        "结果",
        "分析",
        "讨论",
        "实验",
        "样本",
        "架构",
        "实现",
        "search strategy",
        "data source",
        "method",
        "result",
        "analysis",
        "discussion",
        "experiment",
        "design",
    ]
    return any(token in normalized for token in tokens)


