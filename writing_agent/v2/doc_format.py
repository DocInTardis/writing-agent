"""Doc Format module.

This module belongs to `writing_agent.v2` in the writing-agent codebase.
"""

from __future__ import annotations

from dataclasses import dataclass


from writing_agent.v2 import doc_format_parse_domain as parse_domain


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


_HEADING_RE = parse_domain._HEADING_RE
_NUM_HEADING_RE = parse_domain._NUM_HEADING_RE
_CN_NUM_HEADING_RE = parse_domain._CN_NUM_HEADING_RE
_MARKER_RE = parse_domain._MARKER_RE
_INLINE_MARKER_RE = parse_domain._INLINE_MARKER_RE
_STRUCTURED_MARKER_START_RE = parse_domain._STRUCTURED_MARKER_START_RE
_STRONG_PUNCT_RE = parse_domain._STRONG_PUNCT_RE
_LIST_ITEM_PUNCT_RE = parse_domain._LIST_ITEM_PUNCT_RE
_HEADING_GLUE_PREFIXES = parse_domain._HEADING_GLUE_PREFIXES
_HEADING_GLUE_BODY_STARTERS = parse_domain._HEADING_GLUE_BODY_STARTERS
_HEADING_GLUE_BODY_MARKERS = parse_domain._HEADING_GLUE_BODY_MARKERS
_HEADING_GLUE_TRIM_SUFFIXES = parse_domain._HEADING_GLUE_TRIM_SUFFIXES

_looks_like_numbered_list_item_heading = parse_domain._looks_like_numbered_list_item_heading
_trim_left_delims = parse_domain._trim_left_delims
_trim_right_delims = parse_domain._trim_right_delims
_shift_repeated_tail = parse_domain._shift_repeated_tail
_split_heading_colon_or_repeat = parse_domain._split_heading_colon_or_repeat
_split_heading_prefix = parse_domain._split_heading_prefix
_split_heading_number_marker = parse_domain._split_heading_number_marker
_split_heading_markers = parse_domain._split_heading_markers
_split_heading_starters = parse_domain._split_heading_starters
_split_heading_glue = parse_domain._split_heading_glue
_scan_json_object_end = parse_domain._scan_json_object_end
_repair_fragmented_structured_markers = parse_domain._repair_fragmented_structured_markers
_normalize_lines = parse_domain._normalize_lines
_default_title = parse_domain._default_title
_strip_inline_markers = parse_domain._strip_inline_markers
_derive_title_from_blocks = parse_domain._derive_title_from_blocks
_safe_json_loads = parse_domain._safe_json_loads
_join_text = parse_domain._join_text
_strip_headings = parse_domain._strip_headings
_strip_markers = parse_domain._strip_markers


def parse_report_text(text: str) -> ParsedDoc:
    src = _repair_fragmented_structured_markers((text or "").replace("\r\n", "\n").replace("\r", "\n"))
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


