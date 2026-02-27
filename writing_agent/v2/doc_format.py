"""Doc Format module.

This module belongs to `writing_agent.v2` in the writing-agent codebase.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class DocBlock:
    type: str  # "heading"|"paragraph"|"table"|"figure"|"divider"
    level: int | None = None
    text: str | None = None
    table: dict | None = None
    figure: dict | None = None


@dataclass(frozen=True)
class ParsedDoc:
    title: str
    blocks: list[DocBlock]


_HEADING_RE = re.compile(r"^(#{1,3})\s*(.+?)\s*$")
_NUM_HEADING_RE = re.compile(r"^(?P<num>\d+(?:\.\d+){0,3})[\.、\)]?\s+(?P<title>.+?)\s*$")
_CN_NUM_HEADING_RE = re.compile(
    r"^(?P<num>[一二三四五六七八九十百千万零〇两]+)[\.．、\)]\s*(?P<title>.+?)\s*$"
)
_MARKER_RE = re.compile(r"\[\[(FIGURE|TABLE)\s*:\s*(\{[\s\S]*?\})\s*\]\]", flags=re.IGNORECASE)
_INLINE_MARKER_RE = re.compile(r"(\*\*|__|\*)")
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

def parse_report_text(text: str) -> ParsedDoc:
    src = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = _normalize_lines(src.split("\n"))

    title = _default_title()
    blocks: list[DocBlock] = []

    def flush_paragraph(buf: list[str]) -> None:
        if not buf:
            return
        para = "\n".join(buf).strip()
        if para:
            blocks.append(DocBlock(type="paragraph", text=para))
        buf.clear()

    para_buf: list[str] = []
    saw_h1 = False

    prev_blank = True
    for line in lines:
        m = _HEADING_RE.match(line)
        if m:
            flush_paragraph(para_buf)
            level = len(m.group(1))
            heading = (m.group(2) or "").strip()
            rest = ""
            if level >= 2 and heading:
                split = _split_heading_glue(heading)
                if split:
                    heading, rest = split
            if level == 1 and not saw_h1 and heading:
                title = heading
                saw_h1 = True
            blocks.append(DocBlock(type="heading", level=level, text=heading))
            if rest:
                para_buf.append(rest)
            prev_blank = False
            continue

        if not line.strip():
            flush_paragraph(para_buf)
            prev_blank = True
            continue

        stripped_line = line.strip()
        num_match = _NUM_HEADING_RE.match(stripped_line)
        cn_num_match = _CN_NUM_HEADING_RE.match(stripped_line)
        m = num_match or cn_num_match
        if m:
            num = m.group("num") or ""
            heading = (m.group("title") or "").strip()
            is_single_level_num = bool(num_match and "." not in num)
            if num_match:
                dot_count = num.count(".")
                level = min(6, 2 + dot_count)
            else:
                level = 2
            looks_like_list_item = is_single_level_num and _looks_like_numbered_list_item_heading(heading)
            split = _split_heading_glue(heading) if (heading and not looks_like_list_item) else None
            short_heading = len(heading) <= 16 and not _STRONG_PUNCT_RE.search(heading)
            prefix_match = any(heading.startswith(p) for p in _HEADING_GLUE_PREFIXES)
            can_heading = prev_blank or (not para_buf) or split or short_heading or prefix_match
            if heading and can_heading and not looks_like_list_item:
                flush_paragraph(para_buf)
                rest = ""
                if split:
                    heading, rest = split
                blocks.append(DocBlock(type="heading", level=level, text=heading))
                if rest:
                    para_buf.append(rest)
                prev_blank = False
                continue

        # Inline markers live inside paragraph text; keep them as-is.
        para_buf.append(line)
        prev_blank = False

    flush_paragraph(para_buf)

    if not saw_h1:
        derived = _derive_title_from_blocks(blocks)
        if derived:
            title = derived
        blocks.insert(0, DocBlock(type="heading", level=1, text=title))
    return ParsedDoc(title=title, blocks=_explode_markers(blocks))


def _explode_markers(blocks: list[DocBlock]) -> list[DocBlock]:
    out: list[DocBlock] = []
    for b in blocks:
        if b.type != "paragraph" or not (b.text or "").strip():
            out.append(b)
            continue

        txt = b.text or ""
        pos = 0
        for m in _MARKER_RE.finditer(txt):
            before = txt[pos : m.start()].strip()
            if before:
                out.append(DocBlock(type="paragraph", text=before))
            kind = (m.group(1) or "").lower()
            raw = (m.group(2) or "").strip()
            data = _safe_json_loads(raw)
            if kind == "table":
                out.append(DocBlock(type="table", table=data if isinstance(data, dict) else {"raw": raw}))
            else:
                out.append(DocBlock(type="figure", figure=data if isinstance(data, dict) else {"raw": raw}))
            pos = m.end()
        tail = txt[pos:].strip()
        if tail:
            out.append(DocBlock(type="paragraph", text=tail))
    return out


def _normalize_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    run: list[str] = []

    def flush() -> None:
        if not run:
            return
        if len(run) >= 4:
            out.append("".join(run))
        else:
            out.extend(run)
        run.clear()

    for raw in lines:
        line = raw.strip()
        if not line:
            flush()
            out.append("")
            continue
        single = len(line) <= 1
        looks_like_char = re.search(r"[\u4e00-\u9fa5A-Za-z0-9\.\-\u3000-\u303F]", line)
        if single and looks_like_char:
            run.append(line)
            continue
        flush()
        out.append(raw)
    flush()
    return out


def _default_title() -> str:
    stamp = time.strftime("%Y%m%d-%H%M")
    return f"\u81ea\u52a8\u751f\u6210\u6587\u6863-{stamp}"


def _strip_inline_markers(text: str) -> str:
    return _INLINE_MARKER_RE.sub("", text or "").strip()


def _derive_title_from_blocks(blocks: list[DocBlock]) -> str:
    for b in blocks:
        if b.type == "heading" and (b.level or 0) >= 1 and (b.text or "").strip():
            return _strip_inline_markers(b.text or "")
        if b.type == "paragraph" and (b.text or "").strip():
            raw = _strip_inline_markers(b.text or "")
            if raw:
                return raw[:24].rstrip()
    return ""


def _safe_json_loads(raw: str):
    try:
        return json.loads(raw)
    except Exception:
        return None


def validate_doc(
    parsed: ParsedDoc,
    *,
    required_h2: list[str] | None = None,
    min_paragraphs_per_section: int | dict[str, int] = 2,
    min_chars_per_section: int | dict[str, int] | None = None,
    min_tables_per_section: int | dict[str, int] | None = None,
    min_figures_per_section: int | dict[str, int] | None = None,
    min_total_chars: int = 1200,
) -> list[str]:
    problems: list[str] = []
    blocks = parsed.blocks

    if not any(b.type == "heading" and (b.level or 0) == 1 for b in blocks):
        problems.append("缺少标题（H1）")

    required = [h.strip() for h in (required_h2 or []) if h and h.strip()]
    if not required:
        required = []

    def sec_req_int(req: int | dict[str, int] | None, sec: str, default: int) -> int:
        if req is None:
            return default
        if isinstance(req, dict):
            v = req.get(sec)
            return int(v) if isinstance(v, int) else default
        return int(req)

    # Build per-section stats
    current_h2 = None
    counts: dict[str, int] = {}
    char_counts: dict[str, int] = {}
    table_counts: dict[str, int] = {}
    figure_counts: dict[str, int] = {}
    section_text_buf: dict[str, list[str]] = {}
    for b in blocks:
        if b.type == "heading" and (b.level or 0) == 2:
            current_h2 = _strip_inline_markers((b.text or "").strip())
            if current_h2:
                counts.setdefault(current_h2, 0)
                table_counts.setdefault(current_h2, 0)
                figure_counts.setdefault(current_h2, 0)
                section_text_buf.setdefault(current_h2, [])
            continue
        if b.type == "paragraph" and current_h2:
            if (b.text or "").strip():
                counts[current_h2] = counts.get(current_h2, 0) + 1
                section_text_buf.setdefault(current_h2, []).append(b.text or "")
        if b.type == "table" and current_h2:
            table_counts[current_h2] = table_counts.get(current_h2, 0) + 1
        if b.type == "figure" and current_h2:
            figure_counts[current_h2] = figure_counts.get(current_h2, 0) + 1

    for sec, parts in section_text_buf.items():
        joined = "\n\n".join([p.strip() for p in parts if (p or "").strip()])
        joined = _strip_markers(joined)
        char_counts[sec] = len(joined.strip())

    for h in required:
        if h not in counts:
            problems.append(f"缺少章节：{h}")
            continue
        min_paras = sec_req_int(min_paragraphs_per_section, h, 2)
        if counts.get(h, 0) < min_paras:
            problems.append(f"章节“{h}”段落不足（{counts.get(h, 0)}/{min_paras}）")

        min_chars = sec_req_int(min_chars_per_section, h, 0) if min_chars_per_section is not None else 0
        if min_chars > 0 and char_counts.get(h, 0) < min_chars:
            problems.append(f"章节“{h}”内容偏短（{char_counts.get(h, 0)}/{min_chars} 字符）")

        min_tables = sec_req_int(min_tables_per_section, h, 0) if min_tables_per_section is not None else 0
        if min_tables > 0 and table_counts.get(h, 0) < min_tables:
            problems.append(f"章节“{h}”表格不足（{table_counts.get(h, 0)}/{min_tables}）")

        min_figs = sec_req_int(min_figures_per_section, h, 0) if min_figures_per_section is not None else 0
        if min_figs > 0 and figure_counts.get(h, 0) < min_figs:
            problems.append(f"章节“{h}”图不足（{figure_counts.get(h, 0)}/{min_figs}）")

    text_len = len(_strip_markers(_strip_headings(_join_text(blocks))).strip())
    if text_len < min_total_chars:
        problems.append(f"正文过短（{text_len} chars）")
    return problems


def _join_text(blocks: list[DocBlock]) -> str:
    out: list[str] = []
    for b in blocks:
        if b.type == "heading":
            level = b.level or 1
            out.append(f"{'#' * level} {(b.text or '').strip()}")
        elif b.type == "paragraph":
            out.append((b.text or "").strip())
        elif b.type == "table":
            out.append("[[TABLE:{}]]".format(json.dumps(b.table or {}, ensure_ascii=False)))
        elif b.type == "figure":
            out.append("[[FIGURE:{}]]".format(json.dumps(b.figure or {}, ensure_ascii=False)))
    return "\n\n".join([s for s in out if s])


def _strip_headings(s: str) -> str:
    return re.sub(r"(?m)^#{1,3}\s+.*?$", "", s or "")


def _strip_markers(s: str) -> str:
    stripped = re.sub(_MARKER_RE, "", s or "")
    return re.sub(_INLINE_MARKER_RE, "", stripped)
