from __future__ import annotations

import json
import re
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


_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
_MARKER_RE = re.compile(r"\[\[(FIGURE|TABLE)\s*:\s*(\{[\s\S]*?\})\s*\]\]", flags=re.IGNORECASE)


def parse_report_text(text: str) -> ParsedDoc:
    src = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = src.split("\n")

    title = "未命名文档"
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

    for line in lines:
        m = _HEADING_RE.match(line)
        if m:
            flush_paragraph(para_buf)
            level = len(m.group(1))
            heading = (m.group(2) or "").strip()
            if level == 1 and not saw_h1 and heading:
                title = heading
                saw_h1 = True
            blocks.append(DocBlock(type="heading", level=level, text=heading))
            continue

        if not line.strip():
            flush_paragraph(para_buf)
            continue

        # Inline markers live inside paragraph text; keep them as-is.
        para_buf.append(line)

    flush_paragraph(para_buf)

    if not saw_h1:
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
        required = ["摘要", "引言", "方法", "结果", "结论", "参考文献"]

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
            current_h2 = (b.text or "").strip()
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
    return re.sub(_MARKER_RE, "", s or "")
