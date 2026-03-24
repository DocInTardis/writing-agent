"""Doc format parsing helpers and marker repair utilities."""

from __future__ import annotations

import json
import re
import time


_HEADING_RE = re.compile(r"^(#{1,3})\s*(.+?)\s*$")
_NUM_HEADING_RE = re.compile(r"^(?P<num>\d+(?:\.\d+){0,3})[\.、\)]?\s+(?P<title>.+?)\s*$")
_CN_NUM_HEADING_RE = re.compile(
    r"^(?P<num>[一二三四五六七八九十百千万零〇两]+)[\.．、\)]\s*(?P<title>.+?)\s*$"
)
_MARKER_RE = re.compile(r"\[\[(FIGURE|TABLE)\s*:\s*(\{[\s\S]*?\})\s*\]\]", flags=re.IGNORECASE)
_INLINE_MARKER_RE = re.compile(r"(\*\*|__|\*)")
_STRUCTURED_MARKER_START_RE = re.compile(r"\[\[(FIGURE|TABLE)\s*:\s*", flags=re.IGNORECASE)
_STRONG_PUNCT_RE = re.compile(r"[。！？!?；;，、]")
_LIST_ITEM_PUNCT_RE = re.compile(r"[：:；;。！？!?]")
_HEADING_GLUE_PREFIXES = [
    "摘要",
    "引言",
    "绪论",
    "背景",
    "研究背景",
    "目标",
    "范围",
    "术语",
    "定义",
    "需求",
    "需求分析",
    "总体设计",
    "系统设计",
    "架构设计",
    "详细设计",
    "模块设计",
    "实现",
    "关键技术",
    "应用",
    "方法",
    "数据",
    "分析",
    "讨论",
    "评估",
    "结果",
    "结论",
    "总结",
    "展望",
    "当前状态",
    "建议措施",
    "术语映射表",
    "执行版清单",
    "风险台账",
    "监控告警与SLO",
    "附录检查清单",
    "免责声明",
    "风险",
    "问题",
    "计划",
    "本周工作",
    "下周计划",
    "问题与风险",
    "需协助事项",
    "参考文献",
    "附录",
    "致谢",
]
_HEADING_GLUE_BODY_STARTERS = [
    "本文",
    "本研究",
    "本项目",
    "通过",
    "基于",
    "采用",
    "利用",
    "借助",
    "尽管",
    "随着",
    "本周",
    "本次",
    "本节",
    "我们",
    "由于",
    "因此",
    "此外",
    "同时",
    "首先",
    "其次",
    "最后",
]
_HEADING_GLUE_BODY_MARKERS = [
    "尽管",
    "通过",
    "基于",
    "采用",
    "利用",
    "借助",
    "随着",
    "为了",
    "针对",
    "此外",
    "同时",
    "首先",
    "其次",
    "最后",
]
_HEADING_GLUE_TRIM_SUFFIXES = ["模型", "系统"]


def _strip_inline_markers(text: str) -> str:
    return _INLINE_MARKER_RE.sub("", text or "").strip()


def _looks_like_numbered_list_item_heading(text: str) -> bool:
    s = _strip_inline_markers(text or "")
    s = re.sub(r"\s+", "", s).strip()
    if not s:
        return False
    if len(s) > 24:
        return True
    if _LIST_ITEM_PUNCT_RE.search(s):
        return True
    if s.endswith(("、", "，", ",", "；", ";", "。")):
        return True
    if s.startswith(("负责人", "输入", "输出", "验收标准")):
        return True
    return False


def _trim_left_delims(raw: str) -> str:
    return re.sub(r"^[\uFF1A:\u3001\-\u2014\s]+", "", (raw or "")).strip()


def _trim_right_delims(raw: str) -> str:
    return re.sub(r"[\uFF1A:\u3001\-\u2014\s]+$", "", (raw or "")).strip()


def _shift_repeated_tail(left: str, right: str) -> tuple[str, str]:
    left = (left or "").strip()
    right = (right or "").strip()
    if not left or not right or len(left) < 8:
        return left, right
    max_size = min(8, len(left) // 2)
    for size in range(max_size, 2, -1):
        suffix = left[-size:]
        if not suffix or not left.startswith(suffix):
            continue
        candidate = left[:-size].rstrip()
        if len(candidate) < 4:
            continue
        if right.startswith(suffix):
            return candidate, right
        return candidate, suffix + right
    return left, right


def _split_heading_colon_or_repeat(s: str) -> tuple[str, str] | None:
    m = re.match(r"^(.{1,12})([:\uFF1A])(.+)$", s)
    if m:
        left = m.group(1).strip()
        right = m.group(3).strip()
        if left and right and (_STRONG_PUNCT_RE.search(right) or len(right) >= 12):
            return _trim_right_delims(left), _trim_left_delims(right)

    m = re.match(r"^(.{2,10})\s*\1(.+)$", s)
    if m:
        left = m.group(1).strip()
        right = m.group(2).strip()
        if left and right and (_STRONG_PUNCT_RE.search(right) or len(right) >= 6):
            return _trim_right_delims(left), _trim_left_delims(right)
    return None


def _split_heading_prefix(s: str) -> tuple[str, str] | None:
    prefixes = sorted(_HEADING_GLUE_PREFIXES, key=len, reverse=True)
    for prefix in prefixes:
        if s.startswith(prefix) and len(s) > len(prefix) + 1:
            rest = _trim_left_delims(s[len(prefix):])
            if rest and (_STRONG_PUNCT_RE.search(rest) or len(rest) >= 12):
                return prefix, rest

    for kw in prefixes:
        idx = s.find(kw)
        if idx <= 0:
            continue
        head_end = idx + len(kw)
        if head_end > 10:
            continue
        left = s[:head_end].strip()
        rest = _trim_left_delims(s[head_end:])
        if left and rest and (_STRONG_PUNCT_RE.search(rest) or len(rest) >= 12):
            return _trim_right_delims(left), rest
    return None


def _split_heading_number_marker(s: str) -> tuple[str, str] | None:
    m = re.search(r"\b\d+(?:\.\d+)+\b", s)
    if not (m and 0 < m.start() <= 12):
        return None
    left = s[: m.start()].strip()
    rest = _trim_left_delims(s[m.start():])
    if left and rest and (_STRONG_PUNCT_RE.search(rest) or len(rest) >= 12):
        return _trim_right_delims(left), rest
    return None


def _split_heading_markers(s: str) -> tuple[str, str] | None:
    markers = [*list(_HEADING_GLUE_BODY_MARKERS), "作为", "说明", "表明"]
    repeat_and_suffix_markers = {
        "尽管",
        "通过",
        "基于",
        "采用",
        "利用",
        "借助",
        "随着",
        "为了",
        "针对",
        "此外",
        "同时",
        "首先",
        "其次",
        "最后",
        "作为",
        "说明",
        "表明",
    }
    seen: set[str] = set()
    for marker in markers:
        mk = (marker or "").strip()
        if not mk or mk in seen:
            continue
        seen.add(mk)
        idx = s.find(mk)
        if not (2 <= idx <= 24):
            continue
        left = s[:idx].strip()
        right = _trim_left_delims(s[idx:])
        if not left or not right or len(left) > 20 or len(right) < 6:
            continue
        if mk in repeat_and_suffix_markers:
            left, right = _shift_repeated_tail(left, right)
            for suffix in list(_HEADING_GLUE_TRIM_SUFFIXES):
                if left.endswith(suffix) and len(left) - len(suffix) >= 4:
                    right = suffix + right
                    left = left[: -len(suffix)].rstrip()
                    break
        if left and len(left) <= 16 and not _STRONG_PUNCT_RE.search(left):
            return _trim_right_delims(left), right
    return None


def _split_heading_starters(s: str) -> tuple[str, str] | None:
    starters = [*list(_HEADING_GLUE_BODY_STARTERS), "作为", "说明", "表明"]
    seen: set[str] = set()
    for starter in starters:
        st = (starter or "").strip()
        if not st or st in seen:
            continue
        seen.add(st)
        idx = s.find(st)
        if 1 <= idx <= 10:
            left = s[:idx].strip()
            right = _trim_left_delims(s[idx:])
            if left and len(left) <= 12 and not _STRONG_PUNCT_RE.search(left) and len(right) >= 6:
                return _trim_right_delims(left), right
    return None


def _split_heading_glue(text: str) -> tuple[str, str] | None:
    s = (text or "").strip()
    if not s:
        return None
    if len(s) <= 12 and not _STRONG_PUNCT_RE.search(s):
        return None
    for fn in (
        _split_heading_colon_or_repeat,
        _split_heading_prefix,
        _split_heading_number_marker,
        _split_heading_markers,
        _split_heading_starters,
    ):
        result = fn(s)
        if result:
            return result
    return None


