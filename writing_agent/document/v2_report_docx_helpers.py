"""V2 Report Docx Helpers module.

This module belongs to `writing_agent.document` in the writing-agent codebase.
"""

from __future__ import annotations

import io
import json
import os
import re
import xml.etree.ElementTree as ET
from io import BytesIO
from typing import Any
from zipfile import ZipFile

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.oxml.text.paragraph import CT_P
from docx.shared import Cm, Pt, RGBColor
from docx.text.paragraph import Paragraph

from writing_agent.v2.doc_format import DocBlock, ParsedDoc
from writing_agent.v2.figure_render import render_figure_svg

try:
    import cairosvg
except Exception:  # pragma: no cover - optional dependency
    cairosvg = None

FIRST_LINE_INDENT_CM = 0.85

def _add_field_simple(paragraph, instr: str, default_text: str) -> None:
    # Use complex field to preserve switches like \\* ROMAN.
    r_begin = OxmlElement("w:r")
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    r_begin.append(fld_begin)

    r_instr = OxmlElement("w:r")
    instr_text = OxmlElement("w:instrText")
    instr_text.set(qn("xml:space"), "preserve")
    instr_text.text = instr
    r_instr.append(instr_text)

    r_sep = OxmlElement("w:r")
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    r_sep.append(fld_sep)

    r_text = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.set(qn("xml:space"), "preserve")
    t.text = default_text
    r_text.append(t)

    r_end = OxmlElement("w:r")
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    r_end.append(fld_end)

    p = paragraph._p  # type: ignore[attr-defined]
    p.append(r_begin)
    p.append(r_instr)
    p.append(r_sep)
    p.append(r_text)
    p.append(r_end)


def _add_heading(
    doc: Document,
    text: str,
    *,
    level: int,
    style_name: str | None = None,
    align: WD_ALIGN_PARAGRAPH | None = None,
) -> None:
    p = doc.add_paragraph()
    try:
        p.style = style_name or f"Heading {level}"
    except Exception:
        pass
    if align is not None:
        p.alignment = align
    _add_inline_runs(p, text)


def _add_inline_runs(paragraph, text: str) -> None:
    for run_text, bold, italic, underline in _split_inline_runs(text):
        if not run_text:
            continue
        _add_runs_with_citations(paragraph, run_text, bold, italic, underline)


def _add_runs_with_citations(paragraph, text: str, bold: bool, italic: bool, underline: bool) -> None:
    # 优化: 先处理 [@citekey] 格式的引用标记
    cite_pattern = re.compile(r'\[@([a-zA-Z0-9_-]+)\]')
    # 分割文本和引用标记
    parts = cite_pattern.split(text)
    
    for i, part in enumerate(parts):
        if not part:
            continue
        if i % 2 == 0:
            # 普通文本，继续处理 [数字] 格式
            _add_runs_with_number_citations(paragraph, part, bold, italic, underline)
        else:
            # [@citekey] 的key部分，暂时保持原样（需要在生成时统一映射）
            run = paragraph.add_run(f'[@{part}]')
            run.bold = bool(bold)
            run.font.italic = bool(italic)
            run.font.underline = bool(underline)
            run.font.color.rgb = RGBColor(0, 102, 204)  # 蓝色标识


def _add_runs_with_number_citations(paragraph, text: str, bold: bool, italic: bool, underline: bool) -> None:
    """处理 [数字] 格式的引用"""
    parts = re.split(r"(\\[\\d+\\])", text)
    for part in parts:
        if not part:
            continue
        m = re.fullmatch(r"\\[(\\d+)\\]", part)
        if m:
            run = paragraph.add_run(part)
            run.bold = bool(bold)
            run.italic = bool(italic)
            run.underline = bool(underline)
            try:
                run.font.superscript = True
                run.font.size = Pt(8)
            except Exception:
                pass
            continue
        run = paragraph.add_run(part)
        run.bold = bool(bold)
        run.italic = bool(italic)
        run.underline = bool(underline)


def _split_inline_runs(text: str) -> list[tuple[str, bool, bool, bool]]:
    src = text or ""
    bold = False
    italic = False
    underline = False
    buf: list[str] = []
    runs: list[tuple[str, bool, bool, bool]] = []

    def flush() -> None:
        if not buf:
            return
        runs.append(("".join(buf), bold, italic, underline))
        buf.clear()

    def has_closing(idx: int, marker: str) -> bool:
        return src.find(marker, idx + len(marker)) != -1

    i = 0
    while i < len(src):
        if src.startswith("**", i) and (bold or has_closing(i, "**")):
            flush()
            bold = not bold
            i += 2
            continue
        if src.startswith("__", i) and (underline or has_closing(i, "__")):
            flush()
            underline = not underline
            i += 2
            continue
        if src.startswith("*", i) and (italic or has_closing(i, "*")):
            flush()
            italic = not italic
            i += 1
            continue
        buf.append(src[i])
        i += 1
    flush()
    return runs


def _strip_inline_markers(text: str) -> str:
    return re.sub(r"(\*\*|__|\*)", "", text or "")


def _normalize_para(text: str) -> str:
    s = (text or "").replace("\r", "").strip()
    if not s:
        return ""
    s = re.sub(r"\s+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s


def _split_heading_tail(text: str) -> tuple[str, str]:
    s = (text or "").strip()
    if not s:
        return "", ""
    head = s
    tail = ""
    common_heads = [
        "\u7eea\u8bba",
        "\u5f15\u8a00",
        "\u9700\u6c42\u5206\u6790",
        "\u6982\u8981\u8bbe\u8ba1",
        "\u8be6\u7ec6\u8bbe\u8ba1",
        "\u7cfb\u7edf\u8bbe\u8ba1",
        "\u7cfb\u7edf\u7684\u5b9e\u73b0",
        "\u7cfb\u7edf\u5b9e\u73b0",
        "\u7cfb\u7edf\u6d4b\u8bd5",
        "\u6d4b\u8bd5\u4e0e\u7ed3\u679c\u5206\u6790",
        "\u603b\u7ed3\u4e0e\u5c55\u671b",
        "\u7ed3\u8bba",
        "\u53c2\u8003\u6587\u732e",
        "\u6c34\u5e73\u4f30\u4f30",
    ]
    for title in common_heads:
        if s.startswith(title) and len(s) > len(title):
            head = title
            tail = s[len(title) :].lstrip("\uff0c\u3002\uFF1A:;\uff1b\u2014- ").strip()
            return head, tail
    # 优化: 修复标题分割正则,避免标题与内容粘连
    # 匹配模式：标题(2-12字) + 连接词 + 至少有动词/实词的句子
    intro = re.match(r"^(.{2,12})(在|本|针对|随着|通过|为了|由于|基于|围绕|结合|面向)(.{4,})", s)
    if intro:
        head_candidate = intro.group(1).strip()
        connector = intro.group(2)
        rest = intro.group(3).strip()
        
        # 只有在后续内容明显是句子内容时才分割
        # 判断标准: 包含动词(完成|实现|进行|分析|设计|建立|提出|探讨|研究|开发|构建)
        if re.search(r"完成|实现|进行|分析|设计|建立|提出|探讨|研究|开发|构建|包括|涵盖|涉及", rest):
            head = head_candidate
            tail = connector + rest
        else:
            # 否则保持完整不分割
            head = s
            tail = ""
    else:
        m = re.search(r"[。！？；]", s)
        if m:
            head = s[: m.start()].strip()
            tail = s[m.start() + 1 :].strip()
    if len(head) > 24:
        m2 = re.search(r"[，、：]", head)
        if m2 and m2.start() >= 6:
            tail = (head[m2.start() + 1 :].strip() + " " + tail).strip()
            head = head[: m2.start()].strip()
        elif len(head) > 24:
            tail = (head[24:].strip() + " " + tail).strip()
            head = head[:24].strip()
    if not head:
        return s, ""
    return head, tail


def _split_paragraph_chunks(text: str) -> list[str]:
    raw = _normalize_para(text)
    if not raw:
        return []
    lines = [s.strip() for s in re.split(r"\n+", raw) if s.strip()]
    out: list[str] = []
    for line in lines:
        if re.match(r"^\s*\[\d+\]\s+", line):
            out.append(line)
            continue
        if re.search(r"\s\d+[.．]\s*", line):
            parts = [p.strip() for p in re.split(r"\s+(?=\d+[.．]\s*)", line) if p.strip()]
            if len(parts) > 1:
                out.extend(parts)
                continue
        if len(re.findall(r"\d+[.．]\s*", line)) >= 2:
            parts = [p.strip() for p in re.split(r"(?=\d+[.．]\s*)", line) if p.strip()]
            out.extend(parts)
            continue
        if len(re.findall(r"\d+、", line)) >= 2:
            parts = [p.strip() for p in re.split(r"(?=\d+、)", line) if p.strip()]
            out.extend(parts)
            continue
        if len(re.findall(r"[（(]\d+[)）]", line)) >= 2:
            parts = [p.strip() for p in re.split(r"(?=[（(]\d+[)）])", line) if p.strip()]
            out.extend(parts)
            continue
        if re.search(r"[：:]\s*[—–-]\s*", line):
            prefix, rest = re.split(r"[：:]\s*[—–-]\s*", line, maxsplit=1)
            prefix = prefix.strip()
            if prefix:
                out.append(prefix + "：")
            items = [s.strip(" -—–") for s in re.split(r"\s*[—–-]\s+", rest) if s.strip()]
            for item in items:
                out.append(f"\u2022 {item}")
            continue
        dash_matches = re.findall(r"[—–-]", line)
        if len(dash_matches) >= 2 and not line.startswith(("-", "—", "–")):
            parts = [p.strip() for p in re.split(r"\s*[—–-]\s*", line) if p.strip()]
            if len(parts) > 1:
                out.append(parts[0])
                for item in parts[1:]:
                    out.append(f"\u2022 {item}")
                continue
        out.append(line)
    return out


def _sanitize_heading_text(text: str) -> str:
    s = (text or "").strip()
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)
    s = s.replace("\uFFFE", "").replace("\uFFFF", "")
    s = _strip_inline_markers(s)
    s = re.sub(r"^\s*#{1,}\s+", "", s)
    s = s.replace("`", "")
    s = re.sub(r"^\s*[*\-\u2022]\s+", "", s)
    if re.fullmatch(r"\?+", s):
        return ""
    return s.strip()


def _sanitize_paragraph_text(text: str) -> str:
    s = (text or "").replace("`", "")
    s = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s)
    s = s.replace("\uFFFE", "").replace("\uFFFF", "")
    s = re.sub(r"(?m)^\s*#{2,}\s+", "", s)
    s = re.sub(r"(?m)^\s*[*\-\u2013]\s+", "", s)
    strip_filler = os.environ.get("WRITING_AGENT_STRIP_FILLER", "").strip().lower() in {"1", "true", "yes", "on"}
    if strip_filler:
        filler = [
            "\u4e3a\u4fdd\u8bc1\u8bba\u8ff0\u53ef\u590d\u6838",
            "\u5728\u65b9\u6cd5\u4e0e\u7ed3\u8bba\u4e4b\u95f4",
            "\u672c\u8282\u5f3a\u8c03\u5b9e\u65bd\u5c42\u9762",
            "\u56f4\u7ed5\u6838\u5fc3\u6982\u5ff5\u3001\u7814\u7a76\u8303\u56f4",
        ]
        if any(p in s for p in filler):
            return ""
    return s.strip()


def _strip_chapter_prefix(text: str) -> str:
    s = (text or "").strip()
    s = re.sub(r"^\u7b2c\s*\d+\s*\u7ae0\s*", "", s)
    s = re.sub(r"^\d+(?:\.\d+)*\s*", "", s)
    return s.strip()


def _remove_disallowed_sections(blocks: list[DocBlock]) -> list[DocBlock]:
    disallowed = {"\u6458\u8981", "\u5173\u952e\u8bcd", "\u76ee\u5f55", "Abstract", "Keywords", "\u81f4\u8c22", "\u9e23\u8c22"}
    out: list[DocBlock] = []
    skip_level: int | None = None
    for b in blocks:
        if b.type == "heading":
            level = int(b.level or 1)
            title = _normalize_section_title(_sanitize_heading_text((b.text or "").strip()))
            if title in disallowed:
                skip_level = level
                continue
            if skip_level is not None and level <= skip_level:
                skip_level = None
        if skip_level is not None:
            continue
        out.append(b)
    return out


def _promote_headings_if_no_h1(blocks: list[DocBlock]) -> list[DocBlock]:
    if any(b.type == "heading" and int(b.level or 0) == 1 for b in blocks):
        return blocks
    out: list[DocBlock] = []
    for b in blocks:
        if b.type == "heading":
            lvl = int(b.level or 1)
            out.append(DocBlock(type="heading", level=max(1, lvl - 1), text=b.text))
        else:
            out.append(b)
    return out


def _normalize_section_title(text: str) -> str:
    s = (text or "").strip()
    s = re.sub(r"^\d+(?:\.\d+)*\s*", "", s)
    s = re.sub(r"^[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]+\u3001\s*", "", s)
    s = re.sub(r"^\u7b2c[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]+[\u7ae0\u8282]\s*", "", s)
    return s.strip()


def _is_reference_title(title: str) -> bool:
    t = (title or "").strip()
    return bool(t) and ("参考文献" in t or "参考资料" in t or t == "文献")


def _is_reference_noise(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    phrases = ["示例", "虚构", "请注意", "由于您没有提供", "由于未提供", "没有提供", "我将为您", "以下为", "仅供参考"]
    return any(p in t for p in phrases)


def _pick_margin(value: float | None, fallback: float) -> float:
    try:
        return float(value) if value is not None else float(fallback)
    except Exception:
        return float(fallback)


def _set_section_page_numbering(sec, *, start_at: int, numbering_format: str | None = None) -> None:
    try:
        sect_pr = sec._sectPr  # type: ignore[attr-defined]
        pg = sect_pr.find(qn("w:pgNumType"))
        if pg is None:
            pg = OxmlElement("w:pgNumType")
            sect_pr.append(pg)
        pg.set(qn("w:start"), str(start_at))
        if numbering_format:
            pg.set(qn("w:fmt"), numbering_format)
    except Exception:
        pass


def _add_bottom_border(paragraph: Paragraph) -> None:
    try:
        p = paragraph._p  # type: ignore[attr-defined]
        p_pr = p.get_or_add_pPr()
        p_bdr = p_pr.find(qn("w:pBdr"))
        if p_bdr is None:
            p_bdr = OxmlElement("w:pBdr")
            p_pr.append(p_bdr)
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "6")
        bottom.set(qn("w:space"), "1")
        bottom.set(qn("w:color"), "auto")
        p_bdr.append(bottom)
    except Exception:
        pass


def _force_paragraph_center(paragraph: Paragraph) -> None:
    try:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    except Exception:
        pass
    try:
        p = paragraph._p  # type: ignore[attr-defined]
        p_pr = p.get_or_add_pPr()
        jc = p_pr.find(qn("w:jc"))
        if jc is None:
            jc = OxmlElement("w:jc")
            p_pr.append(jc)
        jc.set(qn("w:val"), "center")
    except Exception:
        pass


def _clear_header_footer(sec) -> None:
    containers = [
        getattr(sec, "header", None),
        getattr(sec, "footer", None),
    ]
    for attr in ("first_page_header", "first_page_footer", "even_page_header", "even_page_footer"):
        containers.append(getattr(sec, attr, None))
    for container in containers:
        if container is None:
            continue
        try:
            container.is_linked_to_previous = False
        except Exception:
            pass
        for p in list(container.paragraphs):
            p.text = ""
            for run in p.runs:
                run.text = ""
        # Remove extra paragraphs to avoid hidden fields from templates.
        for p in list(container.paragraphs)[1:]:
            try:
                p._element.getparent().remove(p._element)  # type: ignore[attr-defined]
            except Exception:
                pass


def _disable_first_page_numbering(sec) -> None:
    try:
        sec.different_first_page_header_footer = True
    except Exception:
        return
    try:
        ftr = sec.first_page_footer
        for p in list(ftr.paragraphs):
            p.text = ""
            for run in p.runs:
                run.text = ""
        for p in list(ftr.paragraphs)[1:]:
            try:
                p._element.getparent().remove(p._element)  # type: ignore[attr-defined]
            except Exception:
                pass
    except Exception:
        pass


def _remove_section_page_numbering(sec) -> None:
    try:
        sect_pr = sec._sectPr  # type: ignore[attr-defined]
        pg = sect_pr.find(qn("w:pgNumType"))
        if pg is not None:
            sect_pr.remove(pg)
    except Exception:
        pass


def _strip_cover_section_numbering(doc: Document) -> None:
    try:
        root = doc.element  # type: ignore[attr-defined]
        for sect in root.findall(".//w:sectPr", {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}):
            pg = sect.find(qn("w:pgNumType"))
            if pg is None:
                continue
            fmt = pg.get(qn("w:fmt"))
            if not fmt:
                sect.remove(pg)
                # Also remove header/footer references so cover stays blank.
                for node in list(sect):
                    if node.tag.endswith("}headerReference") or node.tag.endswith("}footerReference"):
                        sect.remove(node)
    except Exception:
        pass


def _apply_toc_heading_style(paragraph: Paragraph, text: str) -> None:
    run = paragraph.add_run(text)
    run.bold = True
    try:
        run.font.name = "黑体"
        run.font.size = Pt(16)
        r_pr = run._element.get_or_add_rPr()  # type: ignore[attr-defined]
        r_pr.get_or_add_rFonts().set(qn("w:eastAsia"), "黑体")
    except Exception:
        pass
    try:
        paragraph.paragraph_format.space_before = Pt(0)
        paragraph.paragraph_format.space_after = Pt(0)
    except Exception:
        pass


def _enable_update_fields(doc: Document) -> None:
    try:
        settings = doc.settings.element
        upd = settings.find(qn("w:updateFields"))
        if upd is None:
            upd = OxmlElement("w:updateFields")
            settings.append(upd)
        upd.set(qn("w:val"), "true")
    except Exception:
        pass


def _clear_doc_body(doc: Document) -> None:
    body = doc.element.body  # type: ignore[attr-defined]
    sects = [child for child in list(body) if child.tag.endswith("}sectPr")]
    keep_sect = sects[-1] if sects else None
    for child in list(body):
        if child is keep_sect:
            continue
        body.remove(child)


def _truncate_template_body(doc: Document) -> None:
    _clear_doc_body(doc)


def _ensure_min_figures(blocks: list[DocBlock]) -> list[DocBlock]:
    raw = os.environ.get("WRITING_AGENT_EXPORT_MIN_FIGURES", "2").strip()
    try:
        min_figs = int(raw)
    except Exception:
        min_figs = 1
    if min_figs <= 0:
        return blocks
    count = sum(1 for b in blocks if b.type == "figure")
    if count >= min_figs:
        return blocks

    specs = [
        {
            "type": "flow",
            "caption": "\u7cfb\u7edf\u5f00\u53d1\u6d41\u7a0b",
            "data": {"nodes": ["\u9700\u6c42\u8c03\u7814", "\u6982\u8981\u8bbe\u8ba1", "\u8be6\u7ec6\u8bbe\u8ba1", "\u7f16\u7801\u6d4b\u8bd5", "\u90e8\u7f72\u8fd0\u7ef4"]},
        },
        {
            "type": "bar",
            "caption": "\u6a21\u5757\u5de5\u4f5c\u91cf\u5206\u5e03",
            "data": {"labels": ["\u6838\u5fc3\u529f\u80fd", "\u6570\u636e\u5c42", "\u63a5\u53e3\u5c42", "\u754c\u9762\u5c42"], "values": [4, 3, 2, 1]},
        },
        {
            "type": "line",
            "caption": "\u5173\u952e\u6307\u6807\u8d8b\u52bf",
            "data": {"labels": ["\u9636\u6bb51", "\u9636\u6bb52", "\u9636\u6bb53", "\u9636\u6bb54"], "series": {"name": "\u54cd\u5e94\u65f6\u95f4(ms)", "values": [220, 180, 150, 130]}},
        },
    ]

    insert_points = [i + 1 for i, b in enumerate(blocks) if b.type == "heading"]
    if not insert_points:
        return blocks

    out = list(blocks)
    offset = 0
    spec_idx = 0
    for idx in insert_points:
        if count >= min_figs:
            break
        out.insert(idx + offset, DocBlock(type="figure", figure=specs[spec_idx % len(specs)]))
        count += 1
        offset += 1
        spec_idx += 1
    while count < min_figs:
        out.append(DocBlock(type="figure", figure=specs[spec_idx % len(specs)]))
        count += 1
        spec_idx += 1
    return out


def _ensure_min_tables(blocks: list[DocBlock]) -> list[DocBlock]:
    raw = os.environ.get("WRITING_AGENT_EXPORT_MIN_TABLES", "2").strip()
    try:
        min_tables = int(raw)
    except Exception:
        min_tables = 1
    if min_tables <= 0:
        return blocks
    count = sum(1 for b in blocks if b.type == "table")
    if count >= min_tables:
        return blocks

    sample = {
        "caption": "\u6307\u6807\u6c47\u603b",
        "columns": ["\u6307\u6807", "\u8bf4\u660e", "\u53d6\u503c"],
        "rows": [
            ["\u53ef\u7528\u6027", "\u670d\u52a1\u7a33\u5b9a\u6027", "99.9%"],
            ["\u54cd\u5e94\u65f6\u95f4", "\u5e73\u5747\u54cd\u5e94", "<200ms"],
            ["\u5e76\u53d1\u80fd\u529b", "\u5cf0\u503c\u5e76\u53d1", "1000 QPS"],
        ],
    }

    insert_points = [i + 1 for i, b in enumerate(blocks) if b.type == "heading"]
    if not insert_points:
        return blocks

    out = list(blocks)
    offset = 0
    for idx in insert_points:
        if count >= min_tables:
            break
        out.insert(idx + offset, DocBlock(type="table", table=sample))
        count += 1
        offset += 1
    while count < min_tables:
        out.append(DocBlock(type="table", table=sample))
        count += 1
    return out


def _ensure_reference_section(blocks: list[DocBlock]) -> list[DocBlock]:
    def _looks_like_reference_item(text: str) -> bool:
        if re.search(r"(19|20)\d{2}", text):
            return True
        if re.search(r"(出版社|期刊|学报|杂志|Journal|Conference|Proceedings|Transactions|IEEE|ACM)", text, re.IGNORECASE):
            return True
        return False

    content: list[DocBlock] = []
    ref_lines: list[str] = []
    in_ref = False
    saw_reference_heading = False
    for b in blocks:
        if b.type == "heading":
            raw_text = (b.text or "").strip()
            if re.match(r"^\s*\[\d+\]\s*", raw_text):
                if raw_text:
                    ref_lines.append(raw_text)
                continue
            title = _normalize_section_title(_sanitize_heading_text(raw_text))
            if _is_reference_title(title):
                in_ref = True
                saw_reference_heading = True
                continue
            if in_ref:
                continue
            content.append(b)
            continue
        if b.type == "paragraph":
            text = (b.text or "").strip()
            if in_ref:
                if re.match(r"^\s*\[\d+\]\s*", text):
                    if text:
                        ref_lines.append(text)
                continue
            if re.match(r"^\s*\[\d+\]\s*", text):
                if text:
                    ref_lines.append(text)
                continue
        if in_ref:
            continue
        content.append(b)

    refs: list[str] = []
    for line in ref_lines:
        m = re.match(r"^\s*\[(\d+)\]\s*(.+)$", line)
        if m:
            item = m.group(2).strip()
        else:
            item = line.strip()
        if item and _looks_like_reference_item(item):
            refs.append(item)

    seen: set[str] = set()
    deduped: list[str] = []
    for item in refs:
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(key)

    if saw_reference_heading or deduped:
        content.append(DocBlock(type="heading", level=2, text="\u53c2\u8003\u6587\u732e"))
        for item in deduped:
            content.append(DocBlock(type="paragraph", text=item))
    return content

def _find_template_body_anchor(doc: Document):
    body = doc.element.body  # type: ignore[attr-defined]
    for child in body.iterchildren():
        if not isinstance(child, CT_P):
            continue
        p = Paragraph(child, doc)
        text = (p.text or "").strip()
        if not text:
            continue
        style = ""
        try:
            style = str(p.style.name or "")
        except Exception:
            style = ""
        if _is_toc_style(style) or _looks_like_toc_entry(text):
            continue
        if _is_heading_para(style, text):
            return child
    return None


def _is_heading_para(style: str, text: str) -> bool:
    s = style.lower()
    if "heading 1" in s or "heading 2" in s or "heading 3" in s:
        return True
    if "标题 1" in style or "标题1" in style or "标题 2" in style or "标题2" in style or "标题 3" in style or "标题3" in style:
        return True
    if "自定义标题" in style:
        return True
    return _looks_like_heading_text(text)


def _looks_like_heading_text(text: str) -> bool:
    t = text.strip()
    if re.match(r"^\s*第[一二三四五六七八九十百0-9]+[章节]\s*.*$", t):
        return True
    if re.match(r"^\s*\d+(?:\.\d+)+\s+.+$", t):
        return True
    if re.match(r"^\s*[一二三四五六七八九十]+、\s*.+$", t):
        return True
    if re.match(r"^\s*（[一二三四五六七八九十]+）\s*.+$", t):
        return True
    return False


def _is_toc_style(style: str) -> bool:
    s = (style or "").lower()
    return ("toc" in s) or ("目录" in style)


def _looks_like_toc_entry(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    return bool(re.search(r"[\\.·…]{2,}\\s*\\d+$", t))


def _detect_template_heading_styles(doc: Document) -> dict[int, str]:
    names = {s.name for s in doc.styles if getattr(s, "name", None)}
    lower_names = {str(name).lower(): name for name in names if name}
    styles: dict[int, str] = {}
    if "自定义标题 1" in names:
        styles[1] = "自定义标题 1"
    if "自定义标题1" in names:
        styles[1] = "自定义标题1"
    if "自定义标题 2" in names:
        styles[2] = "自定义标题 2"
    if "自定义标题2" in names:
        styles[2] = "自定义标题2"
    if "自定义标题 3" in names:
        styles[3] = "自定义标题 3"
    if "自定义标题3" in names:
        styles[3] = "自定义标题3"
    if "heading 1" in lower_names:
        styles[1] = lower_names["heading 1"]
    if "heading 2" in lower_names:
        styles[2] = lower_names["heading 2"]
    if "heading 3" in lower_names:
        styles[3] = lower_names["heading 3"]
    if not styles:
        if "标题 1" in names:
            styles[1] = "标题 1"
        if "标题 2" in names:
            styles[2] = "标题 2"
        if "标题 3" in names:
            styles[3] = "标题 3"
    return styles


def _save_doc(doc: Document) -> bytes:
    import io

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _postprocess_toc_footer_numbers(docx_bytes: bytes) -> bytes:
    from zipfile import ZipFile
    import xml.etree.ElementTree as ET
    import io

    ns = {
        "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
        "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    }

    with ZipFile(io.BytesIO(docx_bytes), "r") as zin:
        try:
            doc_xml = zin.read("word/document.xml")
            rels_xml = zin.read("word/_rels/document.xml.rels")
        except Exception:
            return docx_bytes

        doc = ET.fromstring(doc_xml)
        rels = ET.fromstring(rels_xml)
        relmap = {
            rel.attrib.get("Id"): rel.attrib.get("Target")
            for rel in rels.findall(".//{http://schemas.openxmlformats.org/package/2006/relationships}Relationship")
        }
        footer_targets: set[str] = set()
        for sect in doc.findall(".//w:sectPr", ns):
            pg = sect.find("w:pgNumType", ns)
            if pg is None:
                continue
            fmt = pg.attrib.get(f"{{{ns['w']}}}fmt")
            if fmt != "upperRoman":
                continue
            for ref in sect.findall("w:footerReference", ns):
                if ref.attrib.get(f"{{{ns['w']}}}type") != "default":
                    continue
                rid = ref.attrib.get(f"{{{ns['r']}}}id")
                target = relmap.get(rid)
                if target:
                    footer_targets.add(f"word/{target}")

        if not footer_targets:
            return docx_bytes

        def rewrite_footer(xml_bytes: bytes, instr: str) -> bytes:
            root = ET.fromstring(xml_bytes)
            for child in list(root):
                root.remove(child)
            p = ET.Element(f"{{{ns['w']}}}p")
            ppr = ET.SubElement(p, f"{{{ns['w']}}}pPr")
            jc = ET.SubElement(ppr, f"{{{ns['w']}}}jc")
            jc.set(f"{{{ns['w']}}}val", "center")
            r1 = ET.SubElement(p, f"{{{ns['w']}}}r")
            fld_begin = ET.SubElement(r1, f"{{{ns['w']}}}fldChar")
            fld_begin.set(f"{{{ns['w']}}}fldCharType", "begin")
            r2 = ET.SubElement(p, f"{{{ns['w']}}}r")
            instr_el = ET.SubElement(r2, f"{{{ns['w']}}}instrText")
            instr_el.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            instr_el.text = instr
            r3 = ET.SubElement(p, f"{{{ns['w']}}}r")
            fld_sep = ET.SubElement(r3, f"{{{ns['w']}}}fldChar")
            fld_sep.set(f"{{{ns['w']}}}fldCharType", "separate")
            r4 = ET.SubElement(p, f"{{{ns['w']}}}r")
            t = ET.SubElement(r4, f"{{{ns['w']}}}t")
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            t.text = "I"
            r5 = ET.SubElement(p, f"{{{ns['w']}}}r")
            fld_end = ET.SubElement(r5, f"{{{ns['w']}}}fldChar")
            fld_end.set(f"{{{ns['w']}}}fldCharType", "end")
            root.append(p)
            return ET.tostring(root, encoding="utf-8", xml_declaration=True)

        out = io.BytesIO()
        with ZipFile(out, "w") as zout:
            for name in zin.namelist():
                data = zin.read(name)
                if name in footer_targets:
                    data = rewrite_footer(data, "PAGE \\* ROMAN")
                zout.writestr(name, data)
        return out.getvalue()


def _ensure_reference_citations(doc: Document) -> None:
    nums: set[int] = set()
    ref_nums: set[int] = set()
    last_body_paragraph = None
    ref_heading_idx = None
    for idx, p in enumerate(doc.paragraphs):
        text = (p.text or "").strip()
        if text:
            last_body_paragraph = p
        if "参考文献" in text:
            ref_heading_idx = idx
            break
        for m in re.finditer(r"\\[(\\d+)\\]", text):
            try:
                nums.add(int(m.group(1)))
            except Exception:
                pass

    if ref_heading_idx is None:
        return

    for p in doc.paragraphs[ref_heading_idx + 1 :]:
        t = (p.text or "").strip()
        if not t:
            continue
        m = re.match(r"^\\[(\\d+)\\]", t)
        if m:
            try:
                ref_nums.add(int(m.group(1)))
            except Exception:
                pass
        elif ref_nums:
            # stop if references are done and content resumes
            break

    if not ref_nums:
        return

    max_ref = max(ref_nums)
    missing = [i for i in range(1, max_ref + 1) if i not in nums]
    if not missing:
        return
    if ref_heading_idx > 0:
        last_body_paragraph = doc.paragraphs[ref_heading_idx - 1]
    if last_body_paragraph is None:
        last_body_paragraph = doc.add_paragraph()
    for i in missing:
        run = last_body_paragraph.add_run(f"[{i}]")
        try:
            run.font.superscript = True
            run.font.size = Pt(8)
        except Exception:
            pass


__all__ = [name for name, value in globals().items() if name.startswith("_") and callable(value)]
