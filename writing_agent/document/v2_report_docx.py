from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from writing_agent.models import FormattingRequirements
from writing_agent.v2.doc_format import DocBlock, ParsedDoc, parse_report_text


@dataclass(frozen=True)
class ExportPrefs:
    include_cover: bool = True
    include_toc: bool = True
    toc_levels: int = 3
    include_header: bool = True
    page_numbers: bool = True
    page_margins_cm: float = 2.54


class V2ReportDocxExporter:
    """
    Builds a graduation-design style .docx:
    - Cover page (no page number)
    - TOC field (Word updates on open)
    - Main content with heading numbering
    - Footer page numbers
    """

    def build_from_text(self, text: str, formatting: FormattingRequirements, prefs: ExportPrefs) -> bytes:
        parsed = parse_report_text(text)
        return self.build_from_parsed(parsed, formatting, prefs)

    def build_from_parsed(self, parsed: ParsedDoc, formatting: FormattingRequirements, prefs: ExportPrefs) -> bytes:
        doc = Document()
        self._apply_page_setup(doc, prefs)
        self._apply_styles(doc, formatting)

        title = (parsed.title or "").strip() or "未命名文档"
        blocks = list(parsed.blocks or [])

        if prefs.include_cover:
            self._add_cover(doc, title)
            # Start page numbers from 1 after cover.
            self._new_section(doc, start_page_numbering=True)
        else:
            # If no cover, still ensure page numbering starts at 1.
            self._new_section(doc, start_page_numbering=True)

        if prefs.include_header:
            self._set_header(doc, title)
        if prefs.page_numbers:
            self._set_footer_page_numbers(doc)

        if prefs.include_toc:
            self._add_toc(doc, levels=max(1, min(4, int(prefs.toc_levels))))
            doc.add_page_break()

        # Skip the first H1 block if it duplicates title.
        if blocks and blocks[0].type == "heading" and int(blocks[0].level or 0) == 1:
            blocks = blocks[1:]

        self._emit_content(doc, blocks, formatting)
        buf = _save_doc(doc)
        return buf

    def _apply_page_setup(self, doc: Document, prefs: ExportPrefs) -> None:
        sec = doc.sections[0]
        sec.page_width = Cm(21.0)
        sec.page_height = Cm(29.7)
        m = float(prefs.page_margins_cm)
        sec.top_margin = Cm(m)
        sec.bottom_margin = Cm(m)
        sec.left_margin = Cm(m)
        sec.right_margin = Cm(m)

    def _apply_styles(self, doc: Document, formatting: FormattingRequirements) -> None:
        normal = doc.styles["Normal"]
        normal.font.name = formatting.font_name
        normal.font.size = Pt(formatting.font_size_pt)
        normal.paragraph_format.line_spacing = formatting.line_spacing
        try:
            r_pr = normal._element.get_or_add_rPr()  # type: ignore[attr-defined]
            r_fonts = r_pr.get_or_add_rFonts()
            r_fonts.set(qn("w:eastAsia"), formatting.font_name_east_asia)
        except Exception:
            pass

        # Graduation-design-friendly heading defaults (can be overridden by user template later).
        try:
            h1 = doc.styles["Heading 1"]
            h1.font.name = formatting.font_name
            h1.font.size = Pt(16)
            h1.font.bold = True
            r_pr = h1._element.get_or_add_rPr()  # type: ignore[attr-defined]
            r_pr.get_or_add_rFonts().set(qn("w:eastAsia"), "黑体")
        except Exception:
            pass
        try:
            h2 = doc.styles["Heading 2"]
            h2.font.name = formatting.font_name
            h2.font.size = Pt(14)
            h2.font.bold = True
            r_pr = h2._element.get_or_add_rPr()  # type: ignore[attr-defined]
            r_pr.get_or_add_rFonts().set(qn("w:eastAsia"), "黑体")
        except Exception:
            pass

    def _add_cover(self, doc: Document, title: str) -> None:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(title)
        run.bold = True
        run.font.size = Pt(22)
        doc.add_paragraph("")
        doc.add_paragraph("")
        doc.add_paragraph("")
        meta = doc.add_paragraph()
        meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
        meta.add_run("（毕业设计/论文/报告封面信息可在此处补充）").italic = True
        # The next section will start a new page; avoid double breaks here.

    def _add_toc(self, doc: Document, *, levels: int) -> None:
        h = doc.add_heading("目录", level=1)
        h.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p = doc.add_paragraph()
        instr = f'TOC \\\\o \"1-{levels}\" \\\\h \\\\z \\\\u'
        _add_field_simple(p, instr, "（在 Word 中右键更新目录）")

    def _new_section(self, doc: Document, *, start_page_numbering: bool) -> None:
        sec = doc.add_section(WD_SECTION.NEW_PAGE)
        try:
            sec.header.is_linked_to_previous = False
            sec.footer.is_linked_to_previous = False
        except Exception:
            pass
        if start_page_numbering:
            try:
                sect_pr = sec._sectPr  # type: ignore[attr-defined]
                pg = sect_pr.find(qn("w:pgNumType"))
                if pg is None:
                    pg = OxmlElement("w:pgNumType")
                    sect_pr.append(pg)
                pg.set(qn("w:start"), "1")
            except Exception:
                pass

    def _set_header(self, doc: Document, title: str) -> None:
        sec = doc.sections[-1]
        hdr = sec.header
        p = hdr.paragraphs[0] if hdr.paragraphs else hdr.add_paragraph()
        p.text = title
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    def _set_footer_page_numbers(self, doc: Document) -> None:
        sec = doc.sections[-1]
        ftr = sec.footer
        p = ftr.paragraphs[0] if ftr.paragraphs else ftr.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run("第 ")
        _add_field_simple(p, "PAGE", "")
        p.add_run(" 页")

    def _emit_content(self, doc: Document, blocks: list[DocBlock], formatting: FormattingRequirements) -> None:
        h2 = 0
        h3 = 0
        table_no = 0
        fig_no = 0

        for b in blocks:
            if b.type == "heading":
                lvl = int(b.level or 1)
                text = (b.text or "").strip()
                if not text:
                    continue
                if lvl <= 1:
                    # treat as major section
                    h2 += 1
                    h3 = 0
                    t = f"{h2} {text}"
                    doc.add_heading(t, level=1)
                elif lvl == 2:
                    h2 += 1
                    h3 = 0
                    t = f"{h2} {text}"
                    doc.add_heading(t, level=1)
                else:
                    h3 += 1
                    t = f"{h2}.{h3} {text}"
                    doc.add_heading(t, level=2)
                continue

            if b.type == "paragraph":
                t = _normalize_para(b.text or "")
                if not t:
                    continue
                p = doc.add_paragraph(t)
                p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                try:
                    p.paragraph_format.first_line_indent = Cm(0.74)
                    p.paragraph_format.space_after = Pt(6)
                except Exception:
                    pass
                continue

            if b.type == "table":
                table_no += 1
                t = b.table or {}
                caption = str(t.get("caption") or "").strip() or f"表{table_no}"
                cols = t.get("columns") if isinstance(t, dict) else None
                rows = t.get("rows") if isinstance(t, dict) else None
                columns = [str(c) for c in cols] if isinstance(cols, list) and cols else ["列1", "列2"]
                body = rows if isinstance(rows, list) and rows else [["[待补充]", "[待补充]"]]

                cap_p = doc.add_paragraph(f"表{table_no}  {caption}")
                cap_p.alignment = WD_ALIGN_PARAGRAPH.CENTER

                table = doc.add_table(rows=1, cols=len(columns))
                table.style = "Table Grid"
                hdr_cells = table.rows[0].cells
                for i, col in enumerate(columns):
                    hdr_cells[i].text = str(col)
                for r in body:
                    rr = r if isinstance(r, list) else [str(r)]
                    row_cells = table.add_row().cells
                    for i in range(len(columns)):
                        row_cells[i].text = str(rr[i] if i < len(rr) else "")
                continue

            if b.type == "figure":
                fig_no += 1
                f = b.figure or {}
                caption = str(f.get("caption") or "").strip() or f"图{fig_no}"
                kind = str(f.get("type") or "").strip() or "figure"
                cap_p = doc.add_paragraph(f"图{fig_no}  {caption}")
                cap_p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                ph = doc.add_paragraph(f"[图占位：{kind}，{caption}]")
                ph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                continue


def _add_field_simple(paragraph, instr: str, default_text: str) -> None:
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), instr)
    r = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = default_text
    r.append(t)
    fld.append(r)
    paragraph._p.append(fld)  # type: ignore[attr-defined]


def _normalize_para(text: str) -> str:
    s = (text or "").replace("\r", "").strip()
    if not s:
        return ""
    s = re.sub(r"\s+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s


def _save_doc(doc: Document) -> bytes:
    import io

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
